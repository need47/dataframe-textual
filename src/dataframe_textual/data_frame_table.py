"""DataFrameTable widget for displaying and interacting with Polars DataFrames."""

import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from textwrap import dedent
from typing import Any

import polars as pl
from rich.text import Text, TextType
from textual._two_way_dict import TwoWayDict
from textual.coordinate import Coordinate
from textual.events import Click
from textual.reactive import reactive
from textual.render import measure
from textual.widgets import DataTable, TabPane
from textual.widgets._data_table import (
    CellDoesNotExist,
    CellKey,
    CellType,
    Column,
    ColumnKey,
    CursorType,
    DuplicateKey,
    Row,
    RowKey,
)

from .common import (
    CURSOR_TYPES,
    NULL,
    NULL_DISPLAY,
    RID,
    SUBSCRIPT_DIGITS,
    SUPPORTED_FORMATS,
    DtypeConfig,
    format_row,
    get_next_item,
    parse_placeholders,
    round_to_nearest_hundreds,
    tentative_expr,
    validate_expr,
)
from .sql_screen import AdvancedSqlScreen, SimpleSqlScreen
from .table_screen import FrequencyScreen, MetaColumnScreen, MetaShape, RowDetailScreen, StatisticsScreen
from .yes_no_screen import (
    AddColumnScreen,
    AddLinkScreen,
    ConfirmScreen,
    EditCellScreen,
    EditColumnScreen,
    FilterScreen,
    FindReplaceScreen,
    FreezeScreen,
    RenameColumnScreen,
    SaveFileScreen,
    SearchScreen,
)

# Color for highlighting selections and matches
HIGHLIGHT_COLOR = "red"

# Buffer size for loading rows
BUFFER_SIZE = 5

# Warning threshold for loading rows
WARN_ROWS_THRESHOLD = 50_000

# Maximum width for string columns before truncation
STRING_WIDTH_CAP = 35


@dataclass
class History:
    """Class to track history of dataframe states for undo/redo functionality."""

    description: str
    df: pl.DataFrame
    df_view: pl.DataFrame | None
    filename: str
    hidden_columns: set[str]
    selected_rows: set[int]
    sorted_columns: dict[str, bool]  # col_name -> descending
    matches: dict[int, set[str]]  # RID -> set of col names
    fixed_rows: int
    fixed_columns: int
    cursor_coordinate: Coordinate
    dirty: bool = False  # Whether this history state has unsaved changes


@dataclass
class ReplaceState:
    """Class to track state during interactive replace operations."""

    term_find: str
    term_replace: str
    match_nocase: bool
    match_whole: bool
    cidx: int  # Column index to search in, could be None for all columns
    rows: list[int]  # List of row indices
    cols_per_row: list[list[int]]  # List of list of column indices per row
    current_rpos: int  # Current row position index in rows
    current_cpos: int  # Current column position index within current row's cols
    current_occurrence: int  # Current occurrence count (for display)
    total_occurrence: int  # Total number of occurrences
    replaced_occurrence: int  # Number of occurrences already replaced
    skipped_occurrence: int  # Number of occurrences skipped
    done: bool = False  # Whether the replace operation is complete


def add_rid_column(df: pl.DataFrame) -> pl.DataFrame:
    """Add internal row index as last column to the dataframe if not already present.

    Args:
        df: The Polars DataFrame to modify.

    Returns:
        The modified DataFrame with the internal row index column added.
    """
    if RID not in df.columns:
        df = df.lazy().with_row_index(RID).select(pl.exclude(RID), RID).collect()
    return df


class DataFrameTable(DataTable):
    """Custom DataTable to highlight row/column labels based on cursor position."""

    # Help text for the DataTable which will be shown in the HelpPanel
    HELP = dedent("""
        # 📊 DataFrame Viewer - Table Controls

        ## ⬆️ Navigation
        - **↑↓←→** - 🎯 Move cursor (cell/row/column)
        - **g** - ⬆️ Jump to first row
        - **G** - ⬇️ Jump to last row
        - **HOME/END** - 🎯 Jump to first/last column
        - **Ctrl+HOME/END** - 🎯 Jump to page top/top
        - **Ctrl+F** - 📜 Page down
        - **Ctrl+B** - 📜 Page up
        - **PgUp/PgDn** - 📜 Page up/down

        ## ♻️ Undo/Redo/Reset
        - **u** - ↩️ Undo last action
        - **U** - 🔄 Redo last undone action
        - **Ctrl+U** - 🔁 Reset to initial state

        ## 👁️ Display
        - **Enter** - 📋 Show row details in modal
        - **F** - 📊 Show frequency distribution
        - **s** - 📈 Show statistics for current column
        - **S** - 📊 Show statistics for entire dataframe
        - **m** - 📐 Show dataframe metadata (row/column counts)
        - **M** - 📋 Show column metadata (ID, name, type)
        - **h** - 👁️ Hide current column
        - **H** - 👀 Show all hidden rows/columns
        - **_** - 📏 Toggle column full width
        - **z** - 📌 Freeze rows and columns
        - **~** - 🏷️ Toggle row labels
        - **,** - 🔢 Toggle thousand separator for numeric display
        - **K** - 🔄 Cycle cursor (cell → row → column → cell)

        ## ↕️ Sorting
        - **[** - 🔼 Sort column ascending
        - **]** - 🔽 Sort column descending
        - *(Multi-column sort supported)*

        ## ✅ Row Selection
        - **\\\\** - ✅ Select rows with cell matches or those matching cursor value in current column
        - **|** - ✅ Select rows with expression
        - **'** - ✅ Select/deselect current row
        - **t** - 💡 Toggle row selection (invert all)
        - **T** - 🧹 Clear all selections and matches
        - **{** - ⬆️ Go to previous selected row
        - **}** - ⬇️ Go to next selected row
        - *(Supports case-insensitive & whole-word matching)*

        ## 🔎 Find & Replace
        - **/** - 🔎 Find in current column with cursor value
        - **?** - 🔎 Find in current column with expression
        - **;** - 🌐 Global find using cursor value
        - **:** - 🌐 Global find with expression
        - **n** - ⬇️ Go to next match
        - **N** - ⬆️ Go to previous match
        - **r** - 🔄 Replace in current column (interactive or all)
        - **R** - 🔄 Replace across all columns (interactive or all)
        - *(Supports case-insensitive & whole-word matching)*

        ## 👁️ View & Filter
        - **"** - 📍 Filter selected rows (removes others)
        - **v** - 👁️ View selected rows (hides others)
        - **V** - 🔧 View selected rows matching expression (hides others)

        ## 🔍 SQL Interface
        - **l** - 💬 Open simple SQL interface (select columns & where clause)
        - **L** - 🔎 Open advanced SQL interface (full SQL queries)

        ## ✏️ Editing
        - **Double-click** - ✍️ Edit cell or rename column header
        - **e** - ✍️ Edit current cell
        - **E** - 📊 Edit entire column with expression
        - **a** - ➕ Add empty column after current
        - **A** - ➕ Add column with name and optional expression
        - **@** - 🔗 Add a new link column from template
        - **x** - ❌ Delete current row
        - **X** - ❌ Delete row and those below
        - **Ctrl+X** - ❌ Delete row and those above
        - **delete** - ❌ Clear current cell (set to NULL)
        - **-** - ❌ Delete current column
        - **d** - 📋 Duplicate current column
        - **D** - 📋 Duplicate current row

        ## 🎯 Reorder
        - **Shift+↑↓** - ⬆️⬇️ Move row up/down
        - **Shift+←→** - ⬅️➡️ Move column left/right

        ## 🎨 Type Casting
        - **#** - 🔢 Cast column to integer
        - **%** - 🔢 Cast column to float
        - **!** - ✅ Cast column to boolean
        - **$** - 📝 Cast column to string

        ## 💾 Copy & Save
        - **c** - 📋 Copy cell to clipboard
        - **Ctrl+c** - 📊 Copy column to clipboard
        - **Ctrl+r** - 📝 Copy row to clipboard (tab-separated)
        - **Ctrl+s** - 💾 Save current tab to file
    """).strip()

    # fmt: off
    BINDINGS = [
        # Navigation
        ("g", "jump_top", "Jump to top"),
        ("G", "jump_bottom", "Jump to bottom"),
        ("pageup,ctrl+b", "page_up", "Page up"),
        ("pagedown,ctrl+f", "page_down", "Page down"),
        # Undo/Redo/Reset
        ("u", "undo", "Undo"),
        ("U", "redo", "Redo"),
        ("ctrl+u", "reset", "Reset to initial state"),
        # Display
        ("h", "hide_column", "Hide column"),
        ("H", "show_hidden_rows_columns", "Show hidden rows/columns"),
        ("tilde", "toggle_row_labels", "Toggle row labels"),  # `~`
        ("K", "cycle_cursor_type", "Cycle cursor mode"),  # `K`
        ("z", "freeze_row_column", "Freeze rows/columns"),
        ("comma", "show_thousand_separator", "Toggle thousand separator"),  # `,`
        ("underscore", "expand_column", "Expand column to full width"),  # `_`
        ("circumflex_accent", "toggle_rid", "Toggle internal row index"),  # `^`
        # Copy
        ("c", "copy_cell", "Copy cell to clipboard"),
        ("ctrl+c", "copy_column", "Copy column to clipboard"),
        ("ctrl+r", "copy_row", "Copy row to clipboard"),
        # Save
        ("ctrl+s", "save_to_file", "Save to file"),
        # Metadata, Detail, Frequency, and Statistics
        ("m", "metadata_shape", "Show metadata for row count and column count"),
        ("M", "metadata_column", "Show metadata for column"),
        ("enter", "view_row_detail", "View row details"),
        ("F", "show_frequency", "Show frequency"),
        ("s", "show_statistics", "Show statistics for column"),
        ("S", "show_statistics('dataframe')", "Show statistics for dataframe"),
        # Sort
        ("left_square_bracket", "sort_ascending", "Sort ascending"),  # `[`
        ("right_square_bracket", "sort_descending", "Sort descending"),  # `]`
        # View & Filter
        ("v", "view_rows", "View selected rows"),
        ("V", "view_rows_expr", "View selected rows matching expression"),
        ("quotation_mark", "filter_rows", "Filter selected rows"),  # `"`
        # Row Selection
        ("backslash", "select_row", "Select rows with cell matches or those matching cursor value in current column"),  # `\`
        ("vertical_line", "select_row_expr", "Select rows with expression"),  # `|`
        ("right_curly_bracket", "next_selected_row", "Go to next selected row"),  # `}`
        ("left_curly_bracket", "previous_selected_row", "Go to previous selected row"),  # `{`
        ("apostrophe", "toggle_row_selection", "Toggle row selection"),  # `'`
        ("t", "toggle_selections", "Toggle all row selections"),
        ("T", "clear_selections_and_matches", "Clear selections"),
        # Find & Replace
        ("slash", "find_cursor_value", "Find in column with cursor value"),  # `/`
        ("question_mark", "find_expr", "Find in column with expression"),  # `?`
        ("semicolon", "find_cursor_value('global')", "Global find with cursor value"),  # `;`
        ("colon", "find_expr('global')", "Global find with expression"),  # `:`
        ("n", "next_match", "Go to next match"),  # `n`
        ("N", "previous_match", "Go to previous match"),  # `Shift+n`
        ("r", "replace", "Replace in column"),  # `r`
        ("R", "replace_global", "Replace global"),  # `Shift+R`
        # Delete
        ("delete", "clear_cell", "Clear cell"),
        ("minus", "delete_column", "Delete column"),  # `-`
        ("x", "delete_row", "Delete row"),
        ("X", "delete_row_and_below", "Delete row and those below"),
        ("ctrl+x", "delete_row_and_up", "Delete row and those up"),
        # Duplicate
        ("d", "duplicate_column", "Duplicate column"),
        ("D", "duplicate_row", "Duplicate row"),
        # Edit
        ("e", "edit_cell", "Edit cell"),
        ("E", "edit_column", "Edit column"),
        # Add
        ("a", "add_column", "Add column"),
        ("A", "add_column_expr", "Add column with expression"),
        ("at", "add_link_column", "Add a link column"),  # `@`
        # Reorder
        ("shift+left", "move_column_left", "Move column left"),
        ("shift+right", "move_column_right", "Move column right"),
        ("shift+up", "move_row_up", "Move row up"),
        ("shift+down", "move_row_down", "Move row down"),
        # Type Casting
        ("number_sign", "cast_column_dtype('pl.Int64')", "Cast column dtype to integer"),  # `#`
        ("percent_sign", "cast_column_dtype('pl.Float64')", "Cast column dtype to float"),  # `%`
        ("exclamation_mark", "cast_column_dtype('pl.Boolean')", "Cast column dtype to bool"),  # `!`
        ("dollar_sign", "cast_column_dtype('pl.String')", "Cast column dtype to string"),  # `$`
        # Sql
        ("l", "simple_sql", "Simple SQL interface"),
        ("L", "advanced_sql", "Advanced SQL interface"),
    ]
    # fmt: on

    # Track if dataframe has unsaved changes
    dirty: reactive[bool] = reactive(False)

    def __init__(self, df: pl.DataFrame, filename: str = "", tabname: str = "", **kwargs) -> None:
        """Initialize the DataFrameTable with a dataframe and manage all state.

        Sets up the table widget with display configuration, loads the dataframe, and
        initializes all state tracking variables for row/column operations.

        Args:
            df: The Polars DataFrame to display and edit.
            filename: Optional source filename for the data (used in save operations). Defaults to "".
            tabname: Optional name for the tab displaying this dataframe. Defaults to "".
            **kwargs: Additional keyword arguments passed to the parent DataTable widget.
        """
        super().__init__(**kwargs)

        # DataFrame state
        self.dataframe = add_rid_column(df)  # Original dataframe
        self.df = self.dataframe  # Internal/working dataframe
        self.filename = filename or "untitled.csv"  # Current filename
        self.tabname = tabname or Path(filename).stem  # Tab name

        # In view mode, this is the copy of self.df
        self.df_view = None

        # Pagination & Loading
        self.BATCH_SIZE = max((self.app.size.height // 100 + 1) * 100, 100)
        self.loaded_rows = 0  # Track how many rows are currently loaded
        self.loaded_ranges: list[tuple[int, int]] = []  # List of (start, end) row indices that are loaded

        # State tracking (all 0-based indexing)
        self.hidden_columns: set[str] = set()  # Set of hidden column names
        self.selected_rows: set[int] = set()  # Track selected rows by RID
        self.sorted_columns: dict[str, bool] = {}  # col_name -> descending
        self.matches: dict[int, set[str]] = defaultdict(set)  # Track search matches: RID -> set of col_names

        # Freezing
        self.fixed_rows = 0  # Number of fixed rows
        self.fixed_columns = 0  # Number of fixed columns

        # History stack for undo
        self.histories_undo: deque[History] = deque()
        # History stack for redo
        self.histories_redo: deque[History] = deque()

        # Whether to use thousand separator for numeric display
        self.thousand_separator = False

        # Set of columns expanded to full width
        self.expanded_columns: set[str] = set()

        # Whether to show internal row index column
        self.show_rid = False

    @property
    def cursor_key(self) -> CellKey:
        """Get the current cursor position as a CellKey.

        Returns:
            CellKey: A CellKey object representing the current cursor position.
        """
        return self.coordinate_to_cell_key(self.cursor_coordinate)

    @property
    def cursor_row_key(self) -> RowKey:
        """Get the current cursor row as a RowKey.

        Returns:
            RowKey: The row key for the row containing the cursor.
        """
        return self.cursor_key.row_key

    @property
    def cursor_col_key(self) -> ColumnKey:
        """Get the current cursor column as a ColumnKey.

        Returns:
            ColumnKey: The column key for the column containing the cursor.
        """
        return self.cursor_key.column_key

    @property
    def cursor_row_idx(self) -> int:
        """Get the current cursor row index (0-based) as in dataframe.

        Returns:
            int: The 0-based row index of the cursor position.

        Raises:
            AssertionError: If the cursor row index is out of bounds.
        """
        ridx = int(self.cursor_row_key.value)
        assert 0 <= ridx < len(self.df), "Cursor row index is out of bounds"
        return ridx

    @property
    def cursor_col_idx(self) -> int:
        """Get the current cursor column index (0-based) as in dataframe.

        Returns:
            int: The 0-based column index of the cursor position.

        Raises:
            AssertionError: If the cursor column index is out of bounds.
        """
        cidx = self.df.columns.index(self.cursor_col_key.value)
        assert 0 <= cidx < len(self.df.columns), "Cursor column index is out of bounds"
        return cidx

    @property
    def cursor_col_name(self) -> str:
        """Get the current cursor column name as in dataframe.

        Returns:
            str: The name of the column containing the cursor.
        """
        return self.cursor_col_key.value

    @property
    def cursor_value(self) -> Any:
        """Get the current cursor cell value in the dataframe.

        Returns:
            Any: The value of the cell at the cursor position.
        """
        return self.df.item(self.cursor_row_idx, self.cursor_col_idx)

    @property
    def ordered_selected_rows(self) -> list[int]:
        """Get the list of selected row indices in order.

        Returns:
            list[int]: A list of 0-based row indices that are currently selected.
        """
        return [ridx for ridx, rid in enumerate(self.df[RID]) if rid in self.selected_rows]

    @property
    def ordered_matches(self) -> list[tuple[int, int]]:
        """Get the list of matched cell coordinates in order.

        Returns:
            list[tuple[int, int]]: A list of (row_idx, col_idx) tuples for matched cells.
        """
        matches = []

        # Uniq columns
        cols_to_check = set()
        for cols in self.matches.values():
            cols_to_check.update(cols)

        # Ordered columns
        cidx2col = {cidx: col for cidx, col in enumerate(self.df.columns) if col in cols_to_check}

        for ridx, rid in enumerate(self.df[RID]):
            if cols := self.matches.get(rid):
                for cidx, col in cidx2col.items():
                    if col in cols:
                        matches.append((ridx, cidx))

        return matches

    def _round_to_nearest_hundreds(self, num: int):
        """Round a number to the nearest hundreds.

        Args:
            num: The number to round.
        """
        return round_to_nearest_hundreds(num, N=self.BATCH_SIZE)

    def get_row_idx(self, row_key: RowKey) -> int:
        """Get the row index for a given table row key.

        Args:
            row_key: Row key as string.
        """
        return super().get_row_index(row_key)

    def get_row_key(self, row_idx: int) -> RowKey:
        """Get the row key for a given table row index.

        Args:
            row_idx: Row index in the table display.

        Returns:
            Corresponding row key as string.
        """
        return self._row_locations.get_key(row_idx)

    def get_col_idx(self, col_key: ColumnKey) -> int:
        """Get the column index for a given table column key.

        Args:
            col_key: Column key as string.

        Returns:
            Corresponding column index as int.
        """
        return super().get_column_index(col_key)

    def get_col_key(self, col_idx: int) -> ColumnKey:
        """Get the column key for a given table column index.

        Args:
            col_idx: Column index in the table display.

        Returns:
            Corresponding column key as string.
        """
        return self._column_locations.get_key(col_idx)

    def _should_highlight(self, cursor: Coordinate, target_cell: Coordinate, type_of_cursor: CursorType) -> bool:
        """Determine if the given cell should be highlighted because of the cursor.

        In "cell" mode, also highlights the row and column headers. This overrides the default
        behavior of DataTable which only highlights the exact cell under the cursor.

        Args:
            cursor: The current position of the cursor.
            target_cell: The cell we're checking for the need to highlight.
            type_of_cursor: The type of cursor that is currently active ("cell", "row", or "column").

        Returns:
            bool: True if the target cell should be highlighted, False otherwise.
        """
        if type_of_cursor == "cell":
            # Return true if the cursor is over the target cell
            # This includes the case where the cursor is in the same row or column
            return (
                cursor == target_cell
                or (target_cell.row == -1 and target_cell.column == cursor.column)
                or (target_cell.column == -1 and target_cell.row == cursor.row)
            )
        elif type_of_cursor == "row":
            cursor_row, _ = cursor
            cell_row, _ = target_cell
            return cursor_row == cell_row
        elif type_of_cursor == "column":
            _, cursor_column = cursor
            _, cell_column = target_cell
            return cursor_column == cell_column
        else:
            return False

    def watch_cursor_coordinate(self, old_coordinate: Coordinate, new_coordinate: Coordinate) -> None:
        """Handle cursor position changes and refresh highlighting.

        This method is called by Textual whenever the cursor moves. It refreshes cells that need
        to change their highlight state. Also emits CellSelected message when cursor type is "cell"
        for keyboard navigation only (mouse clicks already trigger it).

        Args:
            old_coordinate: The previous cursor coordinate.
            new_coordinate: The new cursor coordinate.
        """
        if old_coordinate != new_coordinate:
            # Emit CellSelected message for cell cursor type (keyboard navigation only)
            # Only emit if this is from keyboard navigation (flag is True when from keyboard)
            if self.cursor_type == "cell" and getattr(self, "_from_keyboard", False):
                self._from_keyboard = False  # Reset flag
                try:
                    self._post_selected_message()
                except CellDoesNotExist:
                    # This could happen when after calling clear(), the old coordinate is invalid
                    pass

            # For cell cursor type, refresh old and new row/column headers
            if self.cursor_type == "cell":
                old_row, old_col = old_coordinate
                new_row, new_col = new_coordinate

                # Refresh entire column (not just header) to ensure proper highlighting
                self.refresh_column(old_col)
                self.refresh_column(new_col)

                # Refresh entire row (not just header) to ensure proper highlighting
                self.refresh_row(old_row)
                self.refresh_row(new_row)
            elif self.cursor_type == "row":
                self.refresh_row(old_coordinate.row)
                self._highlight_row(new_coordinate.row)
            elif self.cursor_type == "column":
                self.refresh_column(old_coordinate.column)
                self._highlight_column(new_coordinate.column)

            # Handle scrolling if needed
            if self._require_update_dimensions:
                self.call_after_refresh(self._scroll_cursor_into_view)
            else:
                self._scroll_cursor_into_view()

    def watch_dirty(self, old_dirty: bool, new_dirty: bool) -> None:
        """Watch for changes to the dirty state and update tab title.

        When new_dirty is True, set the tab color to red.
        When new_dirty is False, remove the red color.

        Args:
            old_dirty: The old dirty state.
            new_dirty: The new dirty state.
        """
        if old_dirty == new_dirty:
            return  # No change

        # Find the corresponding ContentTab
        content_tab = self.app.query_one(f"#--content-tab-{self.id}")
        if content_tab:
            if new_dirty:
                content_tab.add_class("dirty")
            else:
                content_tab.remove_class("dirty")

    def move_cursor_to(self, ridx: int | None = None, cidx: int | None = None) -> None:
        """Move cursor based on the dataframe indices.

        Args:
            ridx: Row index (0-based) in the dataframe.
            cidx: Column index (0-based) in the dataframe.
        """
        # Ensure the target row is loaded
        start, stop = self._round_to_nearest_hundreds(ridx)
        self.load_rows_range(start, stop)

        row_key = self.cursor_row_key if ridx is None else str(ridx)
        col_key = self.cursor_col_key if cidx is None else self.df.columns[cidx]
        row_idx, col_idx = self.get_cell_coordinate(row_key, col_key)
        self.move_cursor(row=row_idx, column=col_idx)

    def on_mount(self) -> None:
        """Initialize table display when the widget is mounted.

        Called by Textual when the widget is first added to the display tree.
        Currently a placeholder as table setup is deferred until first use.
        """
        # self.setup_table()
        pass

    def on_key(self, event) -> None:
        """Handle key press events for pagination.

        Args:
            event: The key event object.
        """
        if event.key == "up":
            # Let the table handle the navigation first
            self.load_rows_up()
        elif event.key == "down":
            # Let the table handle the navigation first
            self.load_rows_down()

    def on_click(self, event: Click) -> None:
        """Handle mouse click events on the table.

        Supports double-click editing of cells and renaming of column headers.

        Args:
            event: The click event containing row and column information.
        """
        if self.cursor_type == "cell" and event.chain > 1:  # only on double-click or more
            try:
                row_idx = event.style.meta["row"]
                col_idx = event.style.meta["column"]
            except (KeyError, TypeError):
                return  # Unable to get row/column info

            # header row
            if row_idx == -1:
                self.do_rename_column(col_idx)
            else:
                self.do_edit_cell()

    # Action handlers for BINDINGS
    def action_jump_top(self) -> None:
        """Jump to the top of the table."""
        self.do_jump_top()

    def action_jump_bottom(self) -> None:
        """Jump to the bottom of the table."""
        self.do_jump_bottom()

    def action_page_up(self) -> None:
        """Move the cursor one page up."""
        self.do_page_up()

    def action_page_down(self) -> None:
        """Move the cursor one page down."""
        self.do_page_down()

    def action_view_row_detail(self) -> None:
        """View details of the current row."""
        self.do_view_row_detail()

    def action_delete_column(self) -> None:
        """Delete the current column."""
        self.do_delete_column()

    def action_hide_column(self) -> None:
        """Hide the current column."""
        self.do_hide_column()

    def action_expand_column(self) -> None:
        """Expand the current column to its full width."""
        self.do_expand_column()

    def action_toggle_rid(self) -> None:
        """Toggle the internal row index column visibility."""
        self.do_toggle_rid()

    def action_show_hidden_rows_columns(self) -> None:
        """Show all hidden rows/columns."""
        self.do_show_hidden_rows_columns()

    def action_sort_ascending(self) -> None:
        """Sort by current column in ascending order."""
        self.do_sort_by_column(descending=False)

    def action_sort_descending(self) -> None:
        """Sort by current column in descending order."""
        self.do_sort_by_column(descending=True)

    def action_save_to_file(self) -> None:
        """Save the current dataframe to a file."""
        self.do_save_to_file()

    def action_show_frequency(self) -> None:
        """Show frequency distribution for the current column."""
        self.do_show_frequency()

    def action_show_statistics(self, scope: str = "column") -> None:
        """Show statistics for the current column or entire dataframe.

        Args:
            scope: Either "column" for current column stats or "dataframe" for all columns.
        """
        self.do_show_statistics(scope)

    def action_metadata_shape(self) -> None:
        """Show metadata about the dataframe (row and column counts)."""
        self.do_metadata_shape()

    def action_metadata_column(self) -> None:
        """Show metadata for the current column."""
        self.do_metadata_column()

    def action_view_rows(self) -> None:
        """View rows by current cell value."""
        self.do_view_rows()

    def action_view_rows_expr(self) -> None:
        """Open the advanced filter screen."""
        self.do_view_rows_expr()

    def action_edit_cell(self) -> None:
        """Edit the current cell."""
        self.do_edit_cell()

    def action_edit_column(self) -> None:
        """Edit the entire current column with an expression."""
        self.do_edit_column()

    def action_add_column(self) -> None:
        """Add an empty column after the current column."""
        self.do_add_column()

    def action_add_column_expr(self) -> None:
        """Add a new column with optional expression after the current column."""
        self.do_add_column_expr()

    def action_add_link_column(self) -> None:
        """Open AddLinkScreen to create a new link column from a Polars expression."""
        self.do_add_link_column()

    def action_rename_column(self) -> None:
        """Rename the current column."""
        self.do_rename_column()

    def action_clear_cell(self) -> None:
        """Clear the current cell (set to None)."""
        self.do_clear_cell()

    def action_select_row(self) -> None:
        """Select rows with cursor value in the current column."""
        self.do_select_row()

    def action_select_row_expr(self) -> None:
        """Select rows by expression."""
        self.do_select_row_expr()

    def action_find_cursor_value(self, scope="column") -> None:
        """Find by cursor value.

        Args:
            scope: "column" to find in current column, "global" to find across all columns.
        """
        self.do_find_cursor_value(scope=scope)

    def action_find_expr(self, scope="column") -> None:
        """Find by expression.

        Args:
            scope: "column" to find in current column, "global" to find across all columns.
        """
        self.do_find_expr(scope=scope)

    def action_replace(self) -> None:
        """Replace values in current column."""
        self.do_replace()

    def action_replace_global(self) -> None:
        """Replace values across all columns."""
        self.do_replace_global()

    def action_toggle_row_selection(self) -> None:
        """Toggle selection for the current row."""
        self.do_toggle_row_selection()

    def action_toggle_selections(self) -> None:
        """Toggle all row selections."""
        self.do_toggle_selections()

    def action_filter_rows(self) -> None:
        """Filter to show only selected rows."""
        self.do_filter_rows()

    def action_delete_row(self) -> None:
        """Delete the current row."""
        self.do_delete_row()

    def action_delete_row_and_below(self) -> None:
        """Delete the current row and those below."""
        self.do_delete_row(more="below")

    def action_delete_row_and_up(self) -> None:
        """Delete the current row and those above."""
        self.do_delete_row(more="above")

    def action_duplicate_column(self) -> None:
        """Duplicate the current column."""
        self.do_duplicate_column()

    def action_duplicate_row(self) -> None:
        """Duplicate the current row."""
        self.do_duplicate_row()

    def action_undo(self) -> None:
        """Undo the last action."""
        self.do_undo()

    def action_redo(self) -> None:
        """Redo the last undone action."""
        self.do_redo()

    def action_reset(self) -> None:
        """Reset to the initial state."""
        self.do_reset()

    def action_move_column_left(self) -> None:
        """Move the current column to the left."""
        self.do_move_column("left")

    def action_move_column_right(self) -> None:
        """Move the current column to the right."""
        self.do_move_column("right")

    def action_move_row_up(self) -> None:
        """Move the current row up."""
        self.do_move_row("up")

    def action_move_row_down(self) -> None:
        """Move the current row down."""
        self.do_move_row("down")

    def action_clear_selections_and_matches(self) -> None:
        """Clear all row selections and matches."""
        self.do_clear_selections_and_matches()

    def action_cycle_cursor_type(self) -> None:
        """Cycle through cursor types."""
        self.do_cycle_cursor_type()

    def action_freeze_row_column(self) -> None:
        """Open the freeze screen."""
        self.do_freeze_row_column()

    def action_toggle_row_labels(self) -> None:
        """Toggle row labels visibility."""
        self.show_row_labels = not self.show_row_labels
        # status = "shown" if self.show_row_labels else "hidden"
        # self.notify(f"Row labels {status}", title="Labels")

    def action_cast_column_dtype(self, dtype: str | pl.DataType) -> None:
        """Cast the current column to a different data type."""
        self.do_cast_column_dtype(dtype)

    def action_copy_cell(self) -> None:
        """Copy the current cell to clipboard."""
        ridx = self.cursor_row_idx
        cidx = self.cursor_col_idx

        try:
            cell_str = str(self.df.item(ridx, cidx))
            self.do_copy_to_clipboard(cell_str, f"Copied: [$success]{cell_str[:50]}[/]")
        except IndexError:
            self.notify(
                f"Error copying cell ([$error]{ridx}[/], [$accent]{cidx}[/])",
                title="Clipboard",
                severity="error",
                timeout=10,
            )

    def action_copy_column(self) -> None:
        """Copy the current column to clipboard (one value per line)."""
        col_name = self.cursor_col_name

        try:
            # Get all values in the column and join with newlines
            col_values = [str(val) for val in self.df[col_name].to_list()]
            col_str = "\n".join(col_values)

            self.do_copy_to_clipboard(
                col_str,
                f"Copied [$accent]{len(col_values)}[/] values from column [$success]{col_name}[/]",
            )
        except (FileNotFoundError, IndexError):
            self.notify(f"Error copying column [$error]{col_name}[/]", title="Clipboard", severity="error", timeout=10)

    def action_copy_row(self) -> None:
        """Copy the current row to clipboard (values separated by tabs)."""
        ridx = self.cursor_row_idx

        try:
            # Get all values in the row and join with tabs
            row_values = [str(val) for val in self.df.row(ridx)]
            row_str = "\t".join(row_values)

            self.do_copy_to_clipboard(
                row_str,
                f"Copied row [$accent]{ridx + 1}[/] with [$success]{len(row_values)}[/] values",
            )
        except (FileNotFoundError, IndexError):
            self.notify(f"Error copying row [$error]{ridx}[/]", title="Clipboard", severity="error", timeout=10)

    def action_show_thousand_separator(self) -> None:
        """Toggle thousand separator for numeric display."""
        self.thousand_separator = not self.thousand_separator
        self.setup_table()
        # status = "enabled" if self.thousand_separator else "disabled"
        # self.notify(f"Thousand separator {status}", title="Display")

    def action_next_match(self) -> None:
        """Go to the next matched cell."""
        self.do_next_match()

    def action_previous_match(self) -> None:
        """Go to the previous matched cell."""
        self.do_previous_match()

    def action_next_selected_row(self) -> None:
        """Go to the next selected row."""
        self.do_next_selected_row()

    def action_previous_selected_row(self) -> None:
        """Go to the previous selected row."""
        self.do_previous_selected_row()

    def action_simple_sql(self) -> None:
        """Open the SQL interface screen."""
        self.do_simple_sql()

    def action_advanced_sql(self) -> None:
        """Open the advanced SQL interface screen."""
        self.do_advanced_sql()

    def on_mouse_scroll_up(self, event) -> None:
        """Load more rows when scrolling up with mouse."""
        self.load_rows_up()

    def on_mouse_scroll_down(self, event) -> None:
        """Load more rows when scrolling down with mouse."""
        self.load_rows_down()

    # Setup & Loading
    def reset_df(self, new_df: pl.DataFrame, dirty: bool = True) -> None:
        """Reset the dataframe to a new one and refresh the table.

        Args:
            new_df: The new Polars DataFrame to set.
            dirty: Whether to mark the table as dirty (unsaved changes). Defaults to True.
        """
        # Set new dataframe and reset table
        self.df = new_df
        self.loaded_rows = 0
        self.hidden_columns = set()
        self.selected_rows = set()
        self.sorted_columns = {}
        self.fixed_rows = 0
        self.fixed_columns = 0
        self.matches = defaultdict(set)
        # self.histories.clear()
        # self.histories2.clear()
        self.dirty = dirty  # Mark as dirty since data changed

    def setup_table(self) -> None:
        """Setup the table for display.

        Row keys are 0-based indices, which map directly to dataframe row indices.
        Column keys are header names from the dataframe.
        """
        self.loaded_rows = 0
        self.loaded_ranges.clear()
        self.show_row_labels = True

        # Save current cursor position before clearing
        row_idx, col_idx = self.cursor_coordinate

        self.setup_columns()
        self.load_rows_range(0, self.BATCH_SIZE)  # Load initial rows

        # Restore cursor position
        if row_idx < len(self.rows) and col_idx < len(self.columns):
            self.move_cursor(row=row_idx, column=col_idx)

    def determine_column_widths(self) -> dict[str, int]:
        """Determine optimal width for each column based on data type and content.

        For String columns:
        - Minimum width: length of column label
        - Ideal width: maximum width of all cells in the column
        - If space constrained: find appropriate width smaller than maximum

        For non-String columns:
        - Return None to let Textual auto-determine width

        Returns:
            dict[str, int]: Mapping of column name to width (None for auto-sizing columns).
        """
        col_widths, col_label_widths = {}, {}

        # Get available width for the table (with some padding for borders/scrollbar)
        available_width = self.scrollable_content_region.width

        # Calculate how much width we need for string columns first
        string_cols = [col for col, dtype in zip(self.df.columns, self.df.dtypes) if dtype == pl.String]

        # No string columns, let TextualDataTable auto-size all columns
        if not string_cols:
            return col_widths

        # Sample a reasonable number of rows to calculate widths (don't scan entire dataframe)
        sample_size = min(self.BATCH_SIZE, len(self.df))
        sample_lf = self.df.lazy().slice(0, sample_size)

        # Determine widths for each column
        for col, dtype in zip(self.df.columns, self.df.dtypes):
            if col in self.hidden_columns:
                continue

            # Get column label width
            # Add padding for sort indicators if any
            label_width = measure(self.app.console, col, 1) + 2
            col_label_widths[col] = label_width

            # Let Textual auto-size for non-string columns and already expanded columns
            if dtype != pl.String or col in self.expanded_columns:
                available_width -= label_width
                continue

            try:
                # Get sample values from the column
                sample_values = sample_lf.select(col).collect().get_column(col).drop_nulls().to_list()
                if any(val.startswith(("https://", "http://")) for val in sample_values):
                    continue  # Skip link columns so they can auto-size and be clickable

                # Find maximum width in sample
                max_cell_width = max(
                    (measure(self.app.console, val, 1) for val in sample_values),
                    default=label_width,
                )

                # Set column width to max of label and sampled data (capped at reasonable max)
                max_width = max(label_width, max_cell_width)
            except Exception as e:
                # If any error, let Textual auto-size
                max_width = label_width
                self.log(f"Error determining width for column '{col}': {e}")

            col_widths[col] = max_width
            available_width -= max_width

        # If there's no more available width, auto-size remaining columns
        if available_width < 0:
            for col in col_widths:
                if col_widths[col] > STRING_WIDTH_CAP and col_label_widths[col] < STRING_WIDTH_CAP:
                    col_widths[col] = STRING_WIDTH_CAP  # Cap string columns

        return col_widths

    def setup_columns(self) -> None:
        """Clear table and setup columns.

        Column keys are header names from the dataframe.
        Column labels contain column names from the dataframe, with sort indicators if applicable.
        """
        self.clear(columns=True)

        # Get optimal column widths
        column_widths = self.determine_column_widths()

        # Add columns with justified headers
        for col, dtype in zip(self.df.columns, self.df.dtypes):
            if col in self.hidden_columns or (col == RID and not self.show_rid):
                continue  # Skip hidden columns and internal RID
            for idx, c in enumerate(self.sorted_columns, 1):
                if c == col:
                    # Add sort indicator to column header
                    descending = self.sorted_columns[col]
                    sort_indicator = (
                        f" ▼{SUBSCRIPT_DIGITS.get(idx, '')}" if descending else f" ▲{SUBSCRIPT_DIGITS.get(idx, '')}"
                    )
                    cell_value = col + sort_indicator
                    break
            else:  # No break occurred, so column is not sorted
                cell_value = col

            # Get the width for this column (None means auto-size)
            width = column_widths.get(col)

            self.add_column(Text(cell_value, justify=DtypeConfig(dtype).justify), key=col, width=width)

    def _calculate_load_range(self, start: int, stop: int) -> list[tuple[int, int]]:
        """Calculate the actual ranges to load, accounting for already-loaded ranges.

        Handles complex cases where a loaded range is fully contained within the requested
        range (creating head and tail segments to load). All overlapping/adjacent loaded
        ranges are merged first to minimize gaps.

        Args:
            start: Requested start index (0-based).
            stop: Requested stop index (0-based, exclusive).

        Returns:
            List of (actual_start, actual_stop) tuples to load. Empty list if the entire
            requested range is already loaded.

        Example:
            If loaded ranges are [(150, 250)] and requesting (100, 300):
            - Returns [(100, 150), (250, 300)] to load head and tail
            If loaded ranges are [(0, 100), (100, 200)] and requesting (50, 150):
            - After merging, loaded_ranges becomes [(0, 200)]
            - Returns [] (already fully loaded)
        """
        if not self.loaded_ranges:
            return [(start, stop)]

        # Sort loaded ranges by start index
        sorted_ranges = sorted(self.loaded_ranges)

        # Merge overlapping/adjacent ranges
        merged = []
        for range_start, range_stop in sorted_ranges:
            # Fully covered, no need to load anything
            if range_start <= start and range_stop >= stop:
                return []
            # Overlapping or adjacent: merge
            elif merged and range_start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], range_stop))
            else:
                merged.append((range_start, range_stop))

        self.loaded_ranges = merged

        # Calculate ranges to load by finding gaps in the merged ranges
        ranges_to_load = []
        current_pos = start

        for range_start, range_stop in merged:
            # If there's a gap before this loaded range, add it to load list
            if current_pos < range_start and current_pos < stop:
                gap_end = min(range_start, stop)
                ranges_to_load.append((current_pos, gap_end))
                current_pos = range_stop
            elif current_pos >= range_stop:
                # Already moved past this loaded range
                continue
            else:
                # Current position is inside this loaded range, skip past it
                current_pos = max(current_pos, range_stop)

        # If there's remaining range after all loaded ranges, add it
        if current_pos < stop:
            ranges_to_load.append((current_pos, stop))

        return ranges_to_load

    def _merge_loaded_ranges(self) -> None:
        """Merge adjacent and overlapping ranges in self.loaded_ranges.

        Ranges like (0, 100) and (100, 200) are merged into (0, 200).
        """
        if len(self.loaded_ranges) <= 1:
            return

        # Sort by start index
        sorted_ranges = sorted(self.loaded_ranges)

        # Merge overlapping/adjacent ranges
        merged = [sorted_ranges[0]]
        for range_start, range_stop in sorted_ranges[1:]:
            # Overlapping or adjacent: merge
            if range_start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], range_stop))
            else:
                merged.append((range_start, range_stop))

        self.loaded_ranges = merged

    def _find_insert_position_for_row(self, ridx: int) -> int:
        """Find the correct table position to insert a row with the given dataframe index.

        In the table display, rows are ordered by their dataframe index, regardless of
        the internal row keys. This method finds where a row should be inserted based on
        its dataframe index and the indices of already-loaded rows.

        Args:
            ridx: The 0-based dataframe row index.

        Returns:
            The 0-based table position where the row should be inserted.
        """
        # Count how many already-loaded rows have lower dataframe indices
        # Iterate through loaded rows instead of iterating 0..ridx for efficiency
        insert_pos = 0
        for row_key in self._row_locations:
            loaded_ridx = int(row_key.value)
            if loaded_ridx < ridx:
                insert_pos += 1

        return insert_pos

    def load_rows_segment(self, segment_start: int, segment_stop: int) -> int:
        """Load a single contiguous segment of rows into the table.

        This is the core loading logic that inserts rows at correct positions,
        respecting visibility and selection states. Used by load_rows_range()
        to handle each segment independently.

        Args:
            segment_start: Start loading rows from this index (0-based).
            segment_stop: Stop loading rows when this index is reached (0-based, exclusive).
        """
        # Record this range before loading
        self.loaded_ranges.append((segment_start, segment_stop))

        # Load the dataframe slice
        df_slice = self.df.slice(segment_start, segment_stop - segment_start)

        # Load each row at the correct position
        for (ridx, row), rid in zip(enumerate(df_slice.rows(), segment_start), df_slice[RID]):
            is_selected = rid in self.selected_rows
            match_cols = self.matches.get(rid, set())

            vals, dtypes, styles = [], [], []
            for val, col, dtype in zip(row, self.df.columns, self.df.dtypes, strict=True):
                if col in self.hidden_columns or (col == RID and not self.show_rid):
                    continue  # Skip hidden columns and internal RID

                vals.append(val)
                dtypes.append(dtype)

                # Highlight entire row with selection or cells with matches
                styles.append(HIGHLIGHT_COLOR if is_selected or col in match_cols else None)

            formatted_row = format_row(vals, dtypes, styles=styles, thousand_separator=self.thousand_separator)

            # Find correct insertion position and insert
            insert_pos = self._find_insert_position_for_row(ridx)
            self.insert_row(*formatted_row, key=str(ridx), label=str(ridx + 1), position=insert_pos)

        # Number of rows loaded in this segment
        segment_count = len(df_slice)

        # Update loaded rows count
        self.loaded_rows += segment_count

        return segment_count

    def load_rows_range(self, start: int, stop: int) -> int:
        """Load a batch of rows into the table.

        Row keys are 0-based indices as strings, which map directly to dataframe row indices.
        Row labels are 1-based indices as strings.

        Intelligently handles range loading:
        1. Calculates which ranges actually need loading (avoiding reloading)
        2. Handles complex cases where loaded ranges create "holes" (head and tail segments)
        3. Inserts rows at correct positions in the table
        4. Merges adjacent/overlapping ranges to optimize future loading

        Args:
            start: Start loading rows from this index (0-based).
            stop: Stop loading rows when this index is reached (0-based, exclusive).
        """
        start = max(0, start)  # Clamp to non-negative
        stop = min(stop, len(self.df))  # Clamp to dataframe length

        try:
            # Calculate actual ranges to load, accounting for already-loaded ranges
            ranges_to_load = self._calculate_load_range(start, stop)

            # If nothing needs loading, return early
            if not ranges_to_load:
                return 0  # Already loaded

            # Track the number of loaded rows in this range
            range_count = 0

            # Load each segment
            for segment_start, segment_stop in ranges_to_load:
                range_count += self.load_rows_segment(segment_start, segment_stop)

            # Merge adjacent/overlapping ranges to optimize storage
            self._merge_loaded_ranges()

            self.log(f"Loaded {range_count} rows for range {start}-{stop}/{len(self.df)}")
            return range_count

        except Exception as e:
            self.notify("Error loading rows", title="Load", severity="error", timeout=10)
            self.log(f"Error loading rows: {str(e)}")
            return 0

    def load_rows_up(self) -> None:
        """Check if we need to load more rows and load them."""
        # If we've loaded everything, no need to check
        if self.loaded_rows >= len(self.df):
            return

        top_row_index = int(self.scroll_y) + BUFFER_SIZE
        top_row_key = self.get_row_key(top_row_index)

        if top_row_key:
            top_ridx = int(top_row_key.value)
        else:
            top_ridx = 0  # No top row key at index, default to 0

        # Load upward
        start, stop = self._round_to_nearest_hundreds(top_ridx - BUFFER_SIZE * 2)
        range_count = self.load_rows_range(start, stop)

        # Adjust scroll to maintain position if rows were loaded above
        if range_count > 0:
            self.move_cursor(row=top_row_index + range_count)
            self.log(f"Loaded up: {range_count} rows in range {start}-{stop}/{len(self.df)}")

    def load_rows_down(self) -> None:
        """Check if we need to load more rows and load them."""
        # If we've loaded everything, no need to check
        if self.loaded_rows >= len(self.df):
            return

        visible_row_count = self.scrollable_content_region.height - (self.header_height if self.show_header else 0)
        bottom_row_index = self.scroll_y + visible_row_count - BUFFER_SIZE

        bottom_row_key = self.get_row_key(bottom_row_index)
        if bottom_row_key:
            bottom_ridx = int(bottom_row_key.value)
        else:
            bottom_ridx = 0  # No bottom row key at index, default to 0

        # Load downward
        start, stop = self._round_to_nearest_hundreds(bottom_ridx + BUFFER_SIZE * 2)
        range_count = self.load_rows_range(start, stop)

        if range_count > 0:
            self.log(f"Loaded down: {range_count} rows in range {start}-{stop}/{len(self.df)}")

    def insert_row(
        self,
        *cells: CellType,
        height: int | None = 1,
        key: str | None = None,
        label: TextType | None = None,
        position: int | None = None,
    ) -> RowKey:
        """Insert a row at a specific position in the DataTable.

        When inserting, all rows at and after the insertion position are shifted down,
        and their entries in self._row_locations are updated accordingly.

        Args:
            *cells: Positional arguments should contain cell data.
            height: The height of a row (in lines). Use `None` to auto-detect the optimal
                height.
            key: A key which uniquely identifies this row. If None, it will be generated
                for you and returned.
            label: The label for the row. Will be displayed to the left if supplied.
            position: The 0-based row index where the new row should be inserted.
                If None, inserts at the end (same as add_row). If out of bounds,
                inserts at the nearest valid position.

        Returns:
            Unique identifier for this row. Can be used to retrieve this row regardless
                of its current location in the DataTable (it could have moved after
                being added due to sorting or insertion/deletion of other rows).

        Raises:
            DuplicateKey: If a row with the given key already exists.
            ValueError: If more cells are provided than there are columns.
        """
        # Default to appending if position not specified or >= row_count
        row_count = self.row_count
        if position is None or position >= row_count:
            return self.add_row(*cells, height=height, key=key, label=label)

        # Clamp position to valid range [0, row_count)
        position = max(0, position)

        row_key = RowKey(key)
        if row_key in self._row_locations:
            raise DuplicateKey(f"The row key {row_key!r} already exists.")

        if len(cells) > len(self.ordered_columns):
            raise ValueError("More values provided than there are columns.")

        # TC: Rebuild self._row_locations to shift rows at and after position down by 1
        # Create a mapping of old index -> new index
        old_to_new = {}
        for old_idx in range(row_count):
            if old_idx < position:
                old_to_new[old_idx] = old_idx  # No change
            else:
                old_to_new[old_idx] = old_idx + 1  # Shift down by 1

        # Update _row_locations with the new indices
        new_row_locations = TwoWayDict({})
        for row_key_item in self._row_locations:
            old_idx = self.get_row_idx(row_key_item)
            new_idx = old_to_new.get(old_idx, old_idx)
            new_row_locations[row_key_item] = new_idx

        # Update the internal mapping
        self._row_locations = new_row_locations
        # TC

        row_index = position
        # Map the key of this row to its current index
        self._row_locations[row_key] = row_index
        self._data[row_key] = {column.key: cell for column, cell in zip_longest(self.ordered_columns, cells)}

        label = Text.from_markup(label, end="") if isinstance(label, str) else label

        # Rows with auto-height get a height of 0 because 1) we need an integer height
        # to do some intermediate computations and 2) because 0 doesn't impact the data
        # table while we don't figure out how tall this row is.
        self.rows[row_key] = Row(
            row_key,
            height or 0,
            label,
            height is None,
        )
        self._new_rows.add(row_key)
        self._require_update_dimensions = True
        self.cursor_coordinate = self.cursor_coordinate

        # If a position has opened for the cursor to appear, where it previously
        # could not (e.g. when there's no data in the table), then a highlighted
        # event is posted, since there's now a highlighted cell when there wasn't
        # before.
        cell_now_available = self.row_count == 1 and len(self.columns) > 0
        visible_cursor = self.show_cursor and self.cursor_type != "none"
        if cell_now_available and visible_cursor:
            self._highlight_cursor()

        self._update_count += 1
        self.check_idle()
        return row_key

    # Navigation
    def do_jump_top(self) -> None:
        """Jump to the top of the table."""
        self.move_cursor(row=0)

    def do_jump_bottom(self) -> None:
        """Jump to the bottom of the table."""
        stop = len(self.df)
        start = max(0, stop - self.BATCH_SIZE)

        if start % self.BATCH_SIZE != 0:
            start = (start // self.BATCH_SIZE + 1) * self.BATCH_SIZE

        if stop - start < self.BATCH_SIZE:
            start -= self.BATCH_SIZE

        self.load_rows_range(start, stop)
        self.move_cursor(row=self.row_count - 1)

    def do_page_up(self) -> None:
        """Move the cursor one page up."""
        self._set_hover_cursor(False)
        if self.show_cursor and self.cursor_type in ("cell", "row"):
            height = self.scrollable_content_region.height - (self.header_height if self.show_header else 0)

            col_idx = self.cursor_column
            ridx = self.cursor_row_idx
            next_ridx = max(0, ridx - height - BUFFER_SIZE)
            start, stop = self._round_to_nearest_hundreds(next_ridx)
            self.load_rows_range(start, stop)

            self.move_cursor(row=self.get_row_idx(str(next_ridx)), column=col_idx)
        else:
            super().action_page_up()

    def do_page_down(self) -> None:
        """Move the cursor one page down."""
        super().action_page_down()
        self.load_rows_down()

    # History & Undo
    def create_history(self, description: str) -> None:
        """Create the initial history state."""
        return History(
            description=description,
            df=self.df,
            df_view=self.df_view,
            filename=self.filename,
            hidden_columns=self.hidden_columns.copy(),
            selected_rows=self.selected_rows.copy(),
            sorted_columns=self.sorted_columns.copy(),
            matches={k: v.copy() for k, v in self.matches.items()},
            fixed_rows=self.fixed_rows,
            fixed_columns=self.fixed_columns,
            cursor_coordinate=self.cursor_coordinate,
            dirty=self.dirty,
        )

    def apply_history(self, history: History) -> None:
        """Apply the current history state to the table."""
        if history is None:
            return

        # Restore state
        self.df = history.df
        self.df_view = history.df_view
        self.filename = history.filename
        self.hidden_columns = history.hidden_columns.copy()
        self.selected_rows = history.selected_rows.copy()
        self.sorted_columns = history.sorted_columns.copy()
        self.matches = {k: v.copy() for k, v in history.matches.items()} if history.matches else defaultdict(set)
        self.fixed_rows = history.fixed_rows
        self.fixed_columns = history.fixed_columns
        self.cursor_coordinate = history.cursor_coordinate
        self.dirty = history.dirty

        # Recreate table for display
        self.setup_table()

    def add_history(self, description: str, dirty: bool = False, clear_redo: bool = True) -> None:
        """Add the current state to the history stack.

        Args:
            description: Description of the action for this history entry.
            dirty: Whether this operation modifies the data (True) or just display state (False).
        """
        self.histories_undo.append(self.create_history(description))

        # Clear redo stack when a new action is performed
        if clear_redo:
            self.histories_redo.clear()

        # Mark table as dirty if this operation modifies data
        if dirty:
            self.dirty = True

    def do_undo(self) -> None:
        """Undo the last action."""
        if not self.histories_undo:
            self.notify("No actions to undo", title="Undo", severity="warning")
            return

        # Pop the last history state for undo and save to redo stack
        history = self.histories_undo.pop()
        self.histories_redo.append(self.create_history(history.description))

        # Restore state
        self.apply_history(history)

        self.notify(f"Reverted: {history.description}", title="Undo")

    def do_redo(self) -> None:
        """Redo the last undone action."""
        if not self.histories_redo:
            self.notify("No actions to redo", title="Redo", severity="warning")
            return

        # Pop the last undone state from redo stack
        history = self.histories_redo.pop()
        description = history.description

        # Save current state for undo
        self.add_history(description, clear_redo=False)

        # Restore state
        self.apply_history(history)

        self.notify(f"Reapplied: {description}", title="Redo")

    def do_reset(self) -> None:
        """Reset the table to the initial state."""
        self.reset_df(self.dataframe, dirty=False)
        self.setup_table()
        self.notify("Restored initial state", title="Reset")

    # Display
    def do_cycle_cursor_type(self) -> None:
        """Cycle through cursor types: cell -> row -> column -> cell."""
        next_type = get_next_item(CURSOR_TYPES, self.cursor_type)
        self.cursor_type = next_type

        # self.notify(f"Changed cursor type to [$success]{next_type}[/]", title="Cursor")

    def do_view_row_detail(self) -> None:
        """Open a modal screen to view the selected row's details."""
        ridx = self.cursor_row_idx

        # Push the modal screen
        self.app.push_screen(RowDetailScreen(ridx, self))

    def do_show_frequency(self) -> None:
        """Show frequency distribution for the current column."""
        cidx = self.cursor_col_idx

        # Push the frequency modal screen
        self.app.push_screen(FrequencyScreen(cidx, self))

    def do_show_statistics(self, scope: str = "column") -> None:
        """Show statistics for the current column or entire dataframe.

        Args:
            scope: Either "column" for current column stats or "dataframe" for all columns.
        """
        if scope == "dataframe":
            # Show statistics for entire dataframe
            self.app.push_screen(StatisticsScreen(self, col_idx=None))
        else:
            # Show statistics for current column
            cidx = self.cursor_col_idx
            self.app.push_screen(StatisticsScreen(self, col_idx=cidx))

    def do_metadata_shape(self) -> None:
        """Show metadata about the dataframe (row and column counts)."""
        self.app.push_screen(MetaShape(self))

    def do_metadata_column(self) -> None:
        """Show metadata for all columns in the dataframe."""
        self.app.push_screen(MetaColumnScreen(self))

    def do_freeze_row_column(self) -> None:
        """Open the freeze screen to set fixed rows and columns."""
        self.app.push_screen(FreezeScreen(), callback=self.freeze_row_column)

    def freeze_row_column(self, result: tuple[int, int] | None) -> None:
        """Handle result from PinScreen.

        Args:
            result: Tuple of (fixed_rows, fixed_columns) or None if cancelled.
        """
        if result is None:
            return

        fixed_rows, fixed_columns = result

        # Add to history
        self.add_history(f"Pinned [$success]{fixed_rows}[/] rows and [$accent]{fixed_columns}[/] columns")

        # Apply the pin settings to the table
        if fixed_rows >= 0:
            self.fixed_rows = fixed_rows
        if fixed_columns >= 0:
            self.fixed_columns = fixed_columns

        # self.notify(f"Pinned [$success]{fixed_rows}[/] rows and [$accent]{fixed_columns}[/] columns", title="Pin")

    def do_hide_column(self) -> None:
        """Hide the currently selected column from the table display."""
        col_key = self.cursor_col_key
        col_name = col_key.value
        col_idx = self.cursor_column

        # Add to history
        self.add_history(f"Hid column [$success]{col_name}[/]")

        # Remove the column from the table display (but keep in dataframe)
        self.remove_column(col_key)

        # Track hidden columns
        self.hidden_columns.add(col_name)

        # Move cursor left if we hid the last column
        if col_idx >= len(self.columns):
            self.move_cursor(column=len(self.columns) - 1)

        # self.notify(f"Hid column [$success]{col_name}[/]. Press [$accent]H[/] to show hidden columns", title="Hide")

    def do_expand_column(self) -> None:
        """Expand the current column to show the widest cell in the loaded data."""
        col_idx = self.cursor_col_idx
        col_key = self.cursor_col_key
        col_name = col_key.value
        dtype = self.df.dtypes[col_idx]

        # Only expand string columns
        if dtype != pl.String:
            return

        # The column to expand/shrink
        col: Column = self.columns[col_key]

        # Calculate the maximum width across all loaded rows
        label_width = len(col_name) + 2  # Start with column name width + padding

        try:
            need_expand = False
            max_width = label_width

            # Scan through all loaded rows that are visible to find max width
            for row_idx in range(self.loaded_rows):
                cell_value = str(self.df.item(row_idx, col_idx))
                cell_width = measure(self.app.console, cell_value, 1)

                if cell_width > max_width:
                    need_expand = True
                max_width = max(max_width, cell_width)

            if not need_expand:
                return

            if col_name in self.expanded_columns:
                col.width = max(label_width, STRING_WIDTH_CAP)
                self.expanded_columns.remove(col_name)
            else:
                self.expanded_columns.add(col_name)

                # Update the column width
                col.width = max_width

        except Exception as e:
            self.notify(
                f"Error expanding column [$error]{col_name}[/]", title="Expand Column", severity="error", timeout=10
            )
            self.log(f"Error expanding column `{col_name}`: {str(e)}")

        # Force a refresh
        self._update_count += 1
        self._require_update_dimensions = True
        self.refresh(layout=True)

        # self.notify(f"Expanded column [$success]{col_name}[/] to width [$accent]{max_width}[/]", title="Expand")

    def do_toggle_rid(self) -> None:
        """Toggle display of the internal RID column."""
        self.show_rid = not self.show_rid

        # Recreate table for display
        self.setup_table()

    def do_show_hidden_rows_columns(self) -> None:
        """Show all hidden rows/columns by recreating the table."""
        if not self.hidden_columns and self.df_view is None:
            self.notify("No hidden rows or columns to show", title="Show", severity="warning")
            return

        # Add to history
        self.add_history("Showed hidden rows/columns")

        # If in a filtered view, restore the full dataframe
        if self.df_view is not None:
            self.df = self.df_view
            self.df_view = None

        # Clear hidden rows/columns tracking
        self.hidden_columns.clear()

        # Recreate table for display
        self.setup_table()

        self.notify("Showed hidden row(s) and/or hidden column(s)", title="Show")

    # Sort
    def do_sort_by_column(self, descending: bool = False) -> None:
        """Sort by the currently selected column.

        Supports multi-column sorting:
        - First press on a column: sort by that column only
        - Subsequent presses on other columns: add to sort order

        Args:
            descending: If True, sort in descending order. If False, ascending order.
        """
        col_name = self.cursor_col_name
        col_idx = self.cursor_column

        # Check if this column is already in the sort keys
        old_desc = self.sorted_columns.get(col_name)

        # Add to history
        self.add_history(f"Sorted on column [$success]{col_name}[/]", dirty=True)

        # New column - add to sort
        if old_desc is None:
            self.sorted_columns[col_name] = descending

        # Old column, same direction - remove from sort
        elif old_desc == descending:
            del self.sorted_columns[col_name]

        # Old column, different direction - add to sort at end
        else:
            del self.sorted_columns[col_name]
            self.sorted_columns[col_name] = descending

        lf = self.df.lazy()
        sort_by = {}

        # Apply multi-column sort
        if sort_cols := list(self.sorted_columns.keys()):
            descending_flags = list(self.sorted_columns.values())
            sort_by = {"by": sort_cols, "descending": descending_flags, "nulls_last": True}
        else:
            # No sort - restore original order by adding a temporary index column
            sort_by = {"by": RID}

        # Perform the sort
        df_sorted = lf.sort(**sort_by).collect()

        # Also update df_view if applicable
        if self.df_view is not None:
            self.df_view = self.df_view.lazy().sort(**sort_by).collect()

        # Update the dataframe
        self.df = df_sorted

        # Recreate table for display
        self.setup_table()

        # Restore cursor position on the sorted column
        self.move_cursor(column=col_idx, row=0)

    # Edit
    def do_edit_cell(self, ridx: int = None, cidx: int = None) -> None:
        """Open modal to edit the selected cell."""
        ridx = self.cursor_row_idx if ridx is None else ridx
        cidx = self.cursor_col_idx if cidx is None else cidx

        # Push the edit modal screen
        self.app.push_screen(
            EditCellScreen(ridx, cidx, self.df),
            callback=self.edit_cell,
        )

    def edit_cell(self, result) -> None:
        """Handle result from EditCellScreen."""
        if result is None:
            return

        ridx, cidx, new_value = result
        if new_value is None:
            self.app.push_screen(
                EditCellScreen(ridx, cidx, self.df),
                callback=self.edit_cell,
            )
            return

        col_name = self.df.columns[cidx]

        # Add to history
        self.add_history(f"Edited cell [$success]({ridx + 1}, {col_name})[/]", dirty=True)

        # Update the cell in the dataframe
        try:
            self.df = self.df.with_columns(
                pl.when(pl.arange(0, len(self.df)) == ridx)
                .then(pl.lit(new_value))
                .otherwise(pl.col(col_name))
                .alias(col_name)
            )

            # Also update the view if applicable
            if self.df_view is not None:
                # Get the RID value for this row in df_view
                ridx_view = self.df.item(ridx, self.df.columns.index(RID))
                self.df_view = self.df_view.with_columns(
                    pl.when(pl.col(RID) == ridx_view)
                    .then(pl.lit(new_value))
                    .otherwise(pl.col(col_name))
                    .alias(col_name)
                )

            # Update the display
            cell_value = self.df.item(ridx, cidx)
            if cell_value is None:
                cell_value = NULL_DISPLAY
            dtype = self.df.dtypes[cidx]
            dc = DtypeConfig(dtype)
            formatted_value = Text(str(cell_value), style=dc.style, justify=dc.justify)

            # string as keys
            row_key = str(ridx)
            col_key = col_name
            self.update_cell(row_key, col_key, formatted_value, update_width=True)

            # self.notify(f"Cell updated to [$success]{cell_value}[/]", title="Edit Cell")
        except Exception as e:
            self.notify(
                f"Error updating cell ([$error]{ridx}[/], [$accent]{col_name}[/])",
                title="Edit Cell",
                severity="error",
                timeout=10,
            )
            self.log(f"Error updating cell ({ridx}, {col_name}): {str(e)}")

    def do_edit_column(self) -> None:
        """Open modal to edit the entire column with an expression."""
        cidx = self.cursor_col_idx

        # Push the edit column modal screen
        self.app.push_screen(
            EditColumnScreen(cidx, self.df),
            callback=self.edit_column,
        )

    def edit_column(self, result) -> None:
        """Edit a column."""
        if result is None:
            return
        term, cidx = result

        col_name = self.df.columns[cidx]

        # Null case
        if term is None or term == NULL:
            expr = pl.lit(None)

        # Check if term is a valid expression
        elif tentative_expr(term):
            try:
                expr = validate_expr(term, self.df.columns, cidx)
            except Exception as e:
                self.notify(
                    f"Error validating expression [$error]{term}[/]", title="Edit Column", severity="error", timeout=10
                )
                self.log(f"Error validating expression `{term}`: {str(e)}")
                return

        # Otherwise, treat term as a literal value
        else:
            dtype = self.df.dtypes[cidx]
            try:
                value = DtypeConfig(dtype).convert(term)
                expr = pl.lit(value)
            except Exception:
                self.notify(
                    f"Error converting [$error]{term}[/] to [$accent]{dtype}[/]. Cast to string.",
                    title="Edit",
                    severity="error",
                )
                expr = pl.lit(str(term))

        # Add to history
        self.add_history(f"Edited column [$success]{col_name}[/] with expression", dirty=True)

        try:
            # Apply the expression to the column
            self.df = self.df.lazy().with_columns(expr.alias(col_name)).collect()

            # Also update the view if applicable
            # Update the value of col_name in df_view using the value of col_name from df based on RID mapping between them
            if self.df_view is not None:
                # Get updated column from df for rows that exist in df_view
                col_updated = f"^_{col_name}_^"
                col_exists = "^_exists_^"
                lf_updated = self.df.lazy().select(
                    RID, pl.col(col_name).alias(col_updated), pl.lit(True).alias(col_exists)
                )
                # Join and use when/then/otherwise to handle all updates including NULLs
                self.df_view = (
                    self.df_view.lazy()
                    .join(lf_updated, on=RID, how="left")
                    .with_columns(
                        pl.when(pl.col(col_exists))
                        .then(pl.col(col_updated))
                        .otherwise(pl.col(col_name))
                        .alias(col_name)
                    )
                    .drop(col_updated, col_exists)
                    .collect()
                )
        except Exception as e:
            self.notify(
                f"Error applying expression: [$error]{term}[/] to column [$accent]{col_name}[/]",
                title="Edit Column",
                severity="error",
                timeout=10,
            )
            self.log(f"Error applying expression `{term}` to column `{col_name}`: {str(e)}")
            return

        # Recreate table for display
        self.setup_table()

        # self.notify(f"Column [$accent]{col_name}[/] updated with [$success]{expr}[/]", title="Edit Column")

    def do_rename_column(self, col_idx: int | None) -> None:
        """Open modal to rename the selected column."""
        col_idx = self.cursor_column if col_idx is None else col_idx
        col_name = self.get_col_key(col_idx).value

        # Push the rename column modal screen
        self.app.push_screen(
            RenameColumnScreen(col_idx, col_name, self.df.columns),
            callback=self.rename_column,
        )

    def rename_column(self, result) -> None:
        """Handle result from RenameColumnScreen."""
        if result is None:
            return

        col_idx, col_name, new_name = result
        if new_name is None:
            self.app.push_screen(
                RenameColumnScreen(col_idx, col_name, self.df.columns),
                callback=self.rename_column,
            )
            return

        # Add to history
        self.add_history(f"Renamed column [$success]{col_name}[/] to [$accent]{new_name}[/]", dirty=True)

        # Rename the column in the dataframe
        self.df = self.df.rename({col_name: new_name})

        # Also update the view if applicable
        if self.df_view is not None:
            self.df_view = self.df_view.rename({col_name: new_name})

        # Update sorted_columns if this column was sorted and maintain order
        if col_name in self.sorted_columns:
            sorted_columns = {}
            for col, order in self.sorted_columns.items():
                if col == col_name:
                    sorted_columns[new_name] = order
                else:
                    sorted_columns[col] = order
            self.sorted_columns = sorted_columns

        # Update matches if this column had cell matches
        for cols in self.matches.values():
            if col_name in cols:
                cols.remove(col_name)
                cols.add(new_name)

        # Recreate table for display
        self.setup_table()

        # Move cursor to the renamed column
        self.move_cursor(column=col_idx)

        # self.notify(f"Renamed column [$success]{col_name}[/] to [$success]{new_name}[/]", title="Column")

    def do_clear_cell(self) -> None:
        """Clear the current cell by setting its value to None."""
        row_key, col_key = self.cursor_key
        ridx = self.cursor_row_idx
        cidx = self.cursor_col_idx
        col_name = self.cursor_col_name

        # Add to history
        self.add_history(f"Cleared cell [$success]({ridx + 1}, {col_name})[/]", dirty=True)

        # Update the cell to None in the dataframe
        try:
            self.df = self.df.with_columns(
                pl.when(pl.arange(0, len(self.df)) == ridx)
                .then(pl.lit(None))
                .otherwise(pl.col(col_name))
                .alias(col_name)
            )

            # Also update the view if applicable
            if self.df_view is not None:
                ridx_view = self.df.item(ridx, self.df.columns.index(RID))
                self.df_view = self.df_view.with_columns(
                    pl.when(pl.col(RID) == ridx_view).then(pl.lit(None)).otherwise(pl.col(col_name)).alias(col_name)
                )

            # Update the display
            dtype = self.df.dtypes[cidx]
            dc = DtypeConfig(dtype)
            formatted_value = Text(NULL_DISPLAY, style=dc.style, justify=dc.justify)

            self.update_cell(row_key, col_key, formatted_value)

            # self.notify(f"Cell cleared to [$success]{NULL_DISPLAY}[/]", title="Clear Cell")
        except Exception as e:
            self.notify(
                f"Error clearing cell ([$error]{ridx}[/], [$accent]{col_name}[/])",
                title="Clear Cell",
                severity="error",
                timeout=10,
            )
            self.log(f"Error clearing cell ({ridx}, {col_name}): {str(e)}")
            raise e

    def do_add_column(self, col_name: str = None) -> None:
        """Add acolumn after the current column."""
        cidx = self.cursor_col_idx

        if not col_name:
            # Generate a unique column name
            base_name = "new_col"
            new_col_name = base_name
            counter = 1
            while new_col_name in self.df.columns:
                new_col_name = f"{base_name}_{counter}"
                counter += 1
        else:
            new_col_name = col_name

        # Add to history
        self.add_history(f"Added column [$success]{new_col_name}[/] after column [$accent]{cidx + 1}[/]", dirty=True)

        try:
            # Create an empty column (all None values)
            new_col_name = pl.lit(None).alias(new_col_name)

            # Get columns up to current, the new column, then remaining columns
            cols = self.df.columns
            cols_before = cols[: cidx + 1]
            cols_after = cols[cidx + 1 :]

            # Build the new dataframe with columns reordered
            select_cols = cols_before + [new_col_name] + cols_after
            self.df = self.df.lazy().with_columns(new_col_name).select(select_cols).collect()

            # Also update the view if applicable
            if self.df_view is not None:
                self.df_view = self.df_view.lazy().with_columns(new_col_name).select(select_cols).collect()

            # Recreate table for display
            self.setup_table()

            # Move cursor to the new column
            self.move_cursor(column=cidx + 1)

            # self.notify(f"Added column [$success]{new_name}[/]", title="Add Column")
        except Exception as e:
            self.notify(
                f"Error adding column [$error]{new_col_name}[/]", title="Add Column", severity="error", timeout=10
            )
            self.log(f"Error adding column `{new_col_name}`: {str(e)}")
            raise e

    def do_add_column_expr(self) -> None:
        """Open screen to add a new column with optional expression."""
        cidx = self.cursor_col_idx
        self.app.push_screen(
            AddColumnScreen(cidx, self.df),
            self.add_column_expr,
        )

    def add_column_expr(self, result: tuple[int, str, str, pl.Expr] | None) -> None:
        """Add a new column with an expression."""
        if result is None:
            return

        cidx, new_col_name, expr = result

        # Add to history
        self.add_history(f"Added column [$success]{new_col_name}[/] with expression [$accent]{expr}[/].", dirty=True)

        try:
            # Create the column
            new_col = expr.alias(new_col_name)

            # Get columns up to current, the new column, then remaining columns
            cols = self.df.columns
            cols_before = cols[: cidx + 1]
            cols_after = cols[cidx + 1 :]

            # Build the new dataframe with columns reordered
            select_cols = cols_before + [new_col_name] + cols_after
            self.df = self.df.lazy().with_columns(new_col).select(select_cols).collect()

            # Also update the view if applicable
            if self.df_view is not None:
                # Get updated column from df for rows that exist in df_view
                lf_updated = self.df.lazy().select(RID, pl.col(new_col_name))
                # Join and use coalesce to prefer updated value or keep original
                self.df_view = self.df_view.lazy().join(lf_updated, on=RID, how="left").select(select_cols).collect()

            # Recreate table for display
            self.setup_table()

            # Move cursor to the new column
            self.move_cursor(column=cidx + 1)

            # self.notify(f"Added column [$success]{col_name}[/]", title="Add Column")
        except Exception as e:
            self.notify(
                f"Error adding column [$error]{new_col_name}[/]", title="Add Column", severity="error", timeout=10
            )
            self.log(f"Error adding column `{new_col_name}`: {str(e)}")

    def do_add_link_column(self) -> None:
        self.app.push_screen(
            AddLinkScreen(self.cursor_col_idx, self.df),
            callback=self.add_link_column,
        )

    def add_link_column(self, result: tuple[str, str] | None) -> None:
        """Handle result from AddLinkScreen.

        Creates a new link column in the dataframe based on a user-provided template.
        Supports multiple placeholder types:
        - `$_` - Current column (based on cursor position)
        - `$1`, `$2`, etc. - Column by index (1-based)
        - `$name` - Column by name (e.g., `$id`, `$product_name`)

        The template is evaluated for each row using Polars expressions with vectorized
        string concatenation. The new column is inserted after the current column.

        Args:
            result: Tuple of (cidx, new_col_name, link_template) or None if cancelled.
        """
        if result is None:
            return
        cidx, new_col_name, link_template = result

        self.add_history(
            f"Added link column [$success]{new_col_name}[/] with template [$accent]{link_template}[/].", dirty=True
        )

        try:
            # Hack to support PubChem link
            link_template = link_template.replace("PC", "pubchem.ncbi.nlm.nih.gov")

            # Ensure link starts with http:// or https://
            if not link_template.startswith(("https://", "http://")):
                link_template = "https://" + link_template

            # Parse template placeholders into Polars expressions
            parts = parse_placeholders(link_template, self.df.columns, cidx)

            # Build the concatenation expression
            exprs = [part if isinstance(part, pl.Expr) else pl.lit(part) for part in parts]
            new_col = pl.concat_str(exprs).alias(new_col_name)

            # Get columns up to current, the new column, then remaining columns
            cols = self.df.columns
            cols_before = cols[: cidx + 1]
            cols_after = cols[cidx + 1 :]

            # Build the new dataframe with columns reordered
            select_cols = cols_before + [new_col_name] + cols_after
            self.df = self.df.lazy().with_columns(new_col).select(select_cols).collect()

            # Also update the view if applicable
            if self.df_view is not None:
                # Get updated column from df for rows that exist in df_view
                lf_updated = self.df.lazy().select(RID, pl.col(new_col_name))
                # Join and use coalesce to prefer updated value or keep original
                self.df_view = self.df_view.lazy().join(lf_updated, on=RID, how="left").select(select_cols).collect()

            # Recreate table for display
            self.setup_table()

            # Move cursor to the new column
            self.move_cursor(column=cidx + 1)

            self.notify(f"Added link column [$success]{new_col_name}[/]. Use Ctrl/Cmd click to open.", title="Add Link")

        except Exception as e:
            self.notify(
                f"Error adding link column [$error]{new_col_name}[/]", title="Add Link", severity="error", timeout=10
            )
            self.log(f"Error adding link column: {str(e)}")

    def do_delete_column(self, more: str = None) -> None:
        """Remove the currently selected column from the table."""
        # Get the column to remove
        col_idx = self.cursor_column
        try:
            col_name = self.cursor_col_name
        except CellDoesNotExist:
            self.notify("No column to delete at the current cursor position", title="Delete Column", severity="warning")
            return

        col_key = self.cursor_col_key

        col_names_to_remove = []
        col_keys_to_remove = []

        # Remove all columns before the current column
        if more == "before":
            for i in range(col_idx + 1):
                col_key = self.get_col_key(i)
                col_names_to_remove.append(col_key.value)
                col_keys_to_remove.append(col_key)

            message = f"Removed column [$success]{col_name}[/] and all columns before"

        # Remove all columns after the current column
        elif more == "after":
            for i in range(col_idx, len(self.columns)):
                col_key = self.get_col_key(i)
                col_names_to_remove.append(col_key.value)
                col_keys_to_remove.append(col_key)

            message = f"Removed column [$success]{col_name}[/] and all columns after"

        # Remove only the current column
        else:
            col_names_to_remove.append(col_name)
            col_keys_to_remove.append(col_key)
            message = f"Removed column [$success]{col_name}[/]"

        # Add to history
        self.add_history(message, dirty=True)

        # Remove the columns from the table display using the column names as keys
        for ck in col_keys_to_remove:
            self.remove_column(ck)

        # Move cursor left if we deleted the last column(s)
        last_col_idx = len(self.columns) - 1
        if col_idx > last_col_idx:
            self.move_cursor(column=last_col_idx)

        # Remove from sorted columns if present
        for col_name in col_names_to_remove:
            if col_name in self.sorted_columns:
                del self.sorted_columns[col_name]

        # Remove from hidden columns if present
        for col_name in col_names_to_remove:
            self.hidden_columns.discard(col_name)

        # Remove from matches
        for rid in list(self.matches.keys()):
            self.matches[rid].difference_update(col_names_to_remove)
            # Remove empty entries
            if not self.matches[rid]:
                del self.matches[rid]

        # Remove from dataframe
        self.df = self.df.drop(col_names_to_remove)

        # Also update the view if applicable
        if self.df_view is not None:
            self.df_view = self.df_view.drop(col_names_to_remove)

        self.notify(message, title="Delete Column")

    def do_duplicate_column(self) -> None:
        """Duplicate the currently selected column, inserting it right after the current column."""
        cidx = self.cursor_col_idx
        col_name = self.cursor_col_name

        col_idx = self.cursor_column
        new_col_name = f"{col_name}_copy"

        # Ensure new column name is unique
        counter = 1
        while new_col_name in self.df.columns:
            new_col_name = f"{new_col_name}{counter}"
            counter += 1

        # Add to history
        self.add_history(f"Duplicated column [$success]{col_name}[/]", dirty=True)

        # Create new column and reorder columns to insert after current column
        cols_before = self.df.columns[: cidx + 1]
        cols_after = self.df.columns[cidx + 1 :]
        cols_new = cols_before + [new_col_name] + cols_after

        # Add the new column and reorder columns for insertion after current column
        self.df = self.df.lazy().with_columns(pl.col(col_name).alias(new_col_name)).select(cols_new).collect()

        # Also update the view if applicable
        if self.df_view is not None:
            self.df_view = (
                self.df_view.lazy().with_columns(pl.col(col_name).alias(new_col_name)).select(cols_new).collect()
            )

        # Recreate table for display
        self.setup_table()

        # Move cursor to the new duplicated column
        self.move_cursor(column=col_idx + 1)

        # self.notify(f"Duplicated column [$success]{col_name}[/] as [$accent]{new_col_name}[/]", title="Duplicate")

    def do_delete_row(self, more: str = None) -> None:
        """Delete rows from the table and dataframe.

        Supports deleting multiple selected rows. If no rows are selected, deletes the row at the cursor.
        """
        old_count = len(self.df)
        rids_to_delete = set()

        # Delete all selected rows
        if selected_count := len(self.selected_rows):
            history_desc = f"Deleted {selected_count} selected row(s)"
            rids_to_delete.update(self.selected_rows)

        # Delete current row and those above
        elif more == "above":
            ridx = self.cursor_row_idx
            history_desc = f"Deleted current row [$success]{ridx + 1}[/] and those above"
            for rid in self.df[RID][: ridx + 1]:
                rids_to_delete.add(rid)

        # Delete current row and those below
        elif more == "below":
            ridx = self.cursor_row_idx
            history_desc = f"Deleted current row [$success]{ridx + 1}[/] and those below"
            for rid in self.df[RID][ridx:]:
                rids_to_delete.add(rid)

        # Delete the row at the cursor
        else:
            ridx = self.cursor_row_idx
            history_desc = f"Deleted row [$success]{ridx + 1}[/]"
            rids_to_delete.add(self.df[RID][ridx])

        # Add to history
        self.add_history(history_desc, dirty=True)

        # Apply the filter to remove rows
        try:
            df_filtered = self.df.lazy().filter(~pl.col(RID).is_in(rids_to_delete)).collect()
        except Exception as e:
            self.notify(f"Error deleting row(s): {e}", title="Delete", severity="error", timeout=10)
            self.histories_undo.pop()  # Remove last history entry
            return

        # RIDs of remaining rows
        ok_rids = set(df_filtered[RID])

        # Update selected rows tracking
        if self.selected_rows:
            self.selected_rows.intersection_update(ok_rids)

        # Update the dataframe
        self.df = df_filtered

        # Update matches since row indices have changed
        if self.matches:
            self.matches = {rid: cols for rid, cols in self.matches.items() if rid in ok_rids}

        # Also update the view if applicable
        if self.df_view is not None:
            self.df_view = self.df_view.lazy().filter(~pl.col(RID).is_in(rids_to_delete)).collect()

        # Recreate table for display
        self.setup_table()

        deleted_count = old_count - len(self.df)
        if deleted_count > 0:
            self.notify(f"Deleted [$success]{deleted_count}[/] row(s)", title="Delete")

    def do_duplicate_row(self) -> None:
        """Duplicate the currently selected row, inserting it right after the current row."""
        ridx = self.cursor_row_idx
        rid = self.df[RID][ridx]

        lf = self.df.lazy()

        # Get the row to duplicate
        row_to_duplicate = lf.slice(ridx, 1).with_columns(pl.col(RID) + 1)

        # Add to history
        self.add_history(f"Duplicated row [$success]{ridx + 1}[/]", dirty=True)

        # Concatenate: rows before + duplicated row + rows after
        lf_before = lf.slice(0, ridx + 1)
        lf_after = lf.slice(ridx + 1).with_columns(pl.col(RID) + 1)

        # Combine the parts
        self.df = pl.concat([lf_before, row_to_duplicate, lf_after]).collect()

        # Also update the view if applicable
        if self.df_view is not None:
            lf_view = self.df_view.lazy()
            lf_view_before = lf_view.slice(0, rid + 1)
            lf_view_after = lf_view.slice(rid + 1).with_columns(pl.col(RID) + 1)
            self.df_view = pl.concat([lf_view_before, row_to_duplicate, lf_view_after]).collect()

        # Recreate table for display
        self.setup_table()

        # Move cursor to the new duplicated row
        self.move_cursor(row=ridx + 1)

        # self.notify(f"Duplicated row [$success]{ridx + 1}[/]", title="Row")

    def do_move_column(self, direction: str) -> None:
        """Move the current column left or right.

        Args:
            direction: "left" to move left, "right" to move right.
        """
        row_idx, col_idx = self.cursor_coordinate
        col_key = self.cursor_col_key
        col_name = col_key.value
        cidx = self.cursor_col_idx

        # Validate move is possible
        if direction == "left":
            if col_idx <= 0:
                self.notify("Cannot move column left", title="Move", severity="warning")
                return
            swap_idx = col_idx - 1
        elif direction == "right":
            if col_idx >= len(self.columns) - 1:
                self.notify("Cannot move column right", title="Move", severity="warning")
                return
            swap_idx = col_idx + 1

        # Get column to swap
        _, swap_key = self.coordinate_to_cell_key(Coordinate(row_idx, swap_idx))
        swap_name = swap_key.value
        swap_cidx = self.df.columns.index(swap_name)

        # Add to history
        self.add_history(
            f"Moved column [$success]{col_name}[/] [$accent]{direction}[/] (swapped with [$success]{swap_name}[/])",
            dirty=True,
        )

        # Swap columns in the table's internal column locations
        self.check_idle()

        (
            self._column_locations[col_key],
            self._column_locations[swap_key],
        ) = (
            self._column_locations.get(swap_key),
            self._column_locations.get(col_key),
        )

        self._update_count += 1
        self.refresh()

        # Restore cursor position on the moved column
        self.move_cursor(row=row_idx, column=swap_idx)

        # Update the dataframe column order
        cols = list(self.df.columns)
        cols[cidx], cols[swap_cidx] = cols[swap_cidx], cols[cidx]
        self.df = self.df.select(cols)

        # Also update the view if applicable
        if self.df_view is not None:
            self.df_view = self.df_view.select(cols)

        # self.notify(f"Moved column [$success]{col_name}[/] {direction}", title="Move")

    def do_move_row(self, direction: str) -> None:
        """Move the current row up or down.

        Args:
            direction: "up" to move up, "down" to move down.
        """
        curr_row_idx, col_idx = self.cursor_coordinate

        # Validate move is possible
        if direction == "up":
            if curr_row_idx <= 0:
                self.notify("Cannot move row up", title="Move", severity="warning")
                return
            swap_row_idx = curr_row_idx - 1
        elif direction == "down":
            if curr_row_idx >= len(self.rows) - 1:
                self.notify("Cannot move row down", title="Move", severity="warning")
                return
            swap_row_idx = curr_row_idx + 1
        else:
            # Invalid direction
            return

        # Add to history
        self.add_history(
            f"Moved row [$success]{curr_row_idx}[/] [$accent]{direction}[/] (swapped with row [$success]{swap_row_idx}[/])",
            dirty=True,
        )

        # Swap rows in the table's internal row locations
        curr_key = self.coordinate_to_cell_key((curr_row_idx, 0)).row_key
        swap_key = self.coordinate_to_cell_key((swap_row_idx, 0)).row_key

        self.check_idle()

        (
            self._row_locations[curr_key],
            self._row_locations[swap_key],
        ) = (
            self.get_row_idx(swap_key),
            self.get_row_idx(curr_key),
        )

        self._update_count += 1
        self.refresh()

        # Restore cursor position on the moved row
        self.move_cursor(row=swap_row_idx, column=col_idx)

        # Locate the rows to swap
        curr_ridx = curr_row_idx
        swap_ridx = swap_row_idx
        first, second = sorted([curr_ridx, swap_ridx])

        # Swap the rows in the dataframe
        self.df = pl.concat(
            [
                self.df.slice(0, first).lazy(),
                self.df.slice(second, 1).lazy(),
                self.df.slice(first + 1, second - first - 1).lazy(),
                self.df.slice(first, 1).lazy(),
                self.df.slice(second + 1).lazy(),
            ]
        ).collect()

        # Also update the view if applicable
        if self.df_view is not None:
            # Find RID values
            curr_rid = self.df[RID][curr_row_idx]
            swap_rid = self.df[RID][swap_row_idx]

            # Locate the rows by RID in the view
            curr_ridx = self.df_view[RID].index_of(curr_rid)
            swap_ridx = self.df_view[RID].index_of(swap_rid)
            first, second = sorted([curr_ridx, swap_ridx])

            # Swap the rows in the view
            self.df_view = pl.concat(
                [
                    self.df_view.slice(0, first).lazy(),
                    self.df_view.slice(second, 1).lazy(),
                    self.df_view.slice(first + 1, second - first - 1).lazy(),
                    self.df_view.slice(first, 1).lazy(),
                    self.df_view.slice(second + 1).lazy(),
                ]
            ).collect()

        # self.notify(f"Moved row [$success]{row_key.value}[/] {direction}", title="Move Row")

    # Type casting
    def do_cast_column_dtype(self, dtype: str) -> None:
        """Cast the current column to a different data type.

        Args:
            dtype: Target data type (string representation, e.g., "pl.String", "pl.Int64")
        """
        cidx = self.cursor_col_idx
        col_name = self.cursor_col_name
        current_dtype = self.df.dtypes[cidx]

        try:
            target_dtype = eval(dtype)
        except Exception:
            self.notify(f"Invalid target data type: [$error]{dtype}[/]", title="Cast", severity="error", timeout=10)
            return

        if current_dtype == target_dtype:
            self.notify(
                f"Column [$warning]{col_name}[/] is already of type [$accent]{target_dtype}[/]",
                title="Cast",
                severity="warning",
            )
            return  # No change needed

        # Add to history
        self.add_history(
            f"Cast column [$success]{col_name}[/] from [$accent]{current_dtype}[/] to [$success]{target_dtype}[/]",
            dirty=True,
        )

        try:
            # Cast the column using Polars
            self.df = self.df.with_columns(pl.col(col_name).cast(target_dtype))

            # Also update the view if applicable
            if self.df_view is not None:
                self.df_view = self.df_view.with_columns(pl.col(col_name).cast(target_dtype))

            # Recreate table for display
            self.setup_table()

            self.notify(f"Cast column [$success]{col_name}[/] to [$accent]{target_dtype}[/]", title="Cast")
        except Exception as e:
            self.notify(
                f"Error casting column [$error]{col_name}[/] to [$accent]{target_dtype}[/]",
                title="Cast",
                severity="error",
                timeout=10,
            )
            self.log(f"Error casting column `{col_name}`: {str(e)}")

    # Row selection
    def do_select_row(self) -> None:
        """Select rows.

        If there are existing cell matches, use those to select rows.
        Otherwise, use the current cell value as the search term and select rows matching that value.
        """
        cidx = self.cursor_col_idx

        # Use existing cell matches if present
        if self.matches:
            term = pl.col(RID).is_in(self.matches)
        else:
            col_name = self.cursor_col_name

            # Get the value of the currently selected cell
            term = NULL if self.cursor_value is None else str(self.cursor_value)
            if self.cursor_value is None:
                term = pl.col(col_name).is_null()
            else:
                term = pl.col(col_name) == self.cursor_value

        self.select_row((term, cidx, False, True))

    def do_select_row_expr(self) -> None:
        """Select rows by expression."""
        cidx = self.cursor_col_idx

        # Use current cell value as default search term
        term = NULL if self.cursor_value is None else str(self.cursor_value)

        # Push the search modal screen
        self.app.push_screen(
            SearchScreen("Select", term, self.df, cidx),
            callback=self.select_row,
        )

    def select_row(self, result) -> None:
        """Select rows by value or expression."""
        if result is None:
            return

        term, cidx, match_nocase, match_whole = result
        col_name = "all columns" if cidx is None else self.df.columns[cidx]

        # Already a Polars expression
        if isinstance(term, pl.Expr):
            expr = term

        # bool list or Series
        elif isinstance(term, (list, pl.Series)):
            expr = term

        # Null case
        elif term == NULL:
            expr = pl.col(col_name).is_null()

        # Expression in string form
        elif tentative_expr(term):
            try:
                expr = validate_expr(term, self.df.columns, cidx)
            except Exception as e:
                self.notify(
                    f"Error validating expression [$error]{term}[/]", title="Search", severity="error", timeout=10
                )
                self.log(f"Error validating expression `{term}`: {str(e)}")
                return

        # Perform type-aware search based on column dtype
        else:
            dtype = self.df.dtypes[cidx]
            if dtype == pl.String:
                if match_whole:
                    term = f"^{term}$"
                if match_nocase:
                    term = f"(?i){term}"
                expr = pl.col(col_name).str.contains(term)
            else:
                try:
                    value = DtypeConfig(dtype).convert(term)
                    expr = pl.col(col_name) == value
                except Exception:
                    if match_whole:
                        term = f"^{term}$"
                    if match_nocase:
                        term = f"(?i){term}"
                    expr = pl.col(col_name).cast(pl.String).str.contains(term)
                    self.notify(
                        f"Error converting [$error]{term}[/] to [$accent]{dtype}[/]. Cast to string.",
                        title="Search",
                        severity="warning",
                    )

        # Lazyframe for filtering
        lf = self.df.lazy()

        # Apply filter to get matched row indices
        try:
            ok_rids = set(lf.filter(expr).collect()[RID])
        except Exception as e:
            self.notify(
                f"Error applying search filter `[$error]{term}[/]`", title="Search", severity="error", timeout=10
            )
            self.log(f"Error applying search filter `{term}`: {str(e)}")
            return

        match_count = len(ok_rids)
        if match_count == 0:
            self.notify(
                f"No matches found for `[$warning]{term}[/]`. Try [$accent](?i)abc[/] for case-insensitive search.",
                title="Search",
                severity="warning",
            )
            return

        message = f"Found [$success]{match_count}[/] matching row(s)"

        # Add to history
        self.add_history(message)

        # Update selected rows to include new selections
        self.selected_rows.update(ok_rids)

        # Show notification immediately, then start highlighting
        self.notify(message, title="Select Row")

        # Recreate table for display
        self.setup_table()

    def do_toggle_selections(self) -> None:
        """Toggle selected rows highlighting on/off."""
        # Add to history
        self.add_history("Toggled row selection")

        # Invert all selected rows
        self.selected_rows = {rid for rid in self.df[RID] if rid not in self.selected_rows}

        # Check if we're highlighting or un-highlighting
        if selected_count := len(self.selected_rows):
            self.notify(f"Toggled selection for [$success]{selected_count}[/] rows", title="Toggle")

        # Recreate table for display
        self.setup_table()

    def do_toggle_row_selection(self) -> None:
        """Select/deselect current row."""
        # Add to history
        self.add_history("Toggled row selection")

        # Get current row RID
        ridx = self.cursor_row_idx
        rid = self.df[RID][ridx]

        if rid in self.selected_rows:
            self.selected_rows.discard(rid)
        else:
            self.selected_rows.add(rid)

        row_key = self.cursor_row_key
        is_selected = rid in self.selected_rows
        match_cols = self.matches.get(rid, set())

        for col_idx, col in enumerate(self.ordered_columns):
            col_key = col.key
            col_name = col_key.value
            cell_text: Text = self.get_cell(row_key, col_key)

            if is_selected or (col_name in match_cols):
                cell_text.style = HIGHLIGHT_COLOR
            else:
                # Reset to default style based on dtype
                dtype = self.df.dtypes[col_idx]
                dc = DtypeConfig(dtype)
                cell_text.style = dc.style

            self.update_cell(row_key, col_key, cell_text)

    def do_clear_selections_and_matches(self) -> None:
        """Clear all selected rows and matches without removing them from the dataframe."""
        # Check if any selected rows or matches
        if not self.selected_rows and not self.matches:
            self.notify("No selections to clear", title="Clear", severity="warning")
            return

        row_count = len(self.selected_rows | set(self.matches.keys()))

        # Add to history
        self.add_history("Cleared all selected rows")

        # Clear all selections
        self.selected_rows = set()
        self.matches = defaultdict(set)

        # Recreate table for display
        self.setup_table()

        self.notify(f"Cleared selections for [$success]{row_count}[/] rows", title="Clear")

    # Find & Replace
    def find_matches(
        self, term: str, cidx: int | None = None, match_nocase: bool = False, match_whole: bool = False
    ) -> dict[int, set[str]]:
        """Find matches for a term in the dataframe.

        Args:
            term: The search term (can be NULL, expression, or plain text)
            cidx: Column index for column-specific search. If None, searches all columns.
            match_nocase: Whether to perform case-insensitive matching (for string terms)
            match_whole: Whether to match the whole cell content (for string terms)

        Returns:
            Dictionary mapping row indices to sets of column indices containing matches.
            For column-specific search, each matched row has a set with single cidx.
            For global search, each matched row has a set of all matching cidxs in that row.

        Raises:
            Exception: If expression validation or filtering fails.
        """
        matches: dict[int, set[str]] = defaultdict(set)

        # Lazyframe for filtering
        lf = self.df.lazy()

        # Determine which columns to search: single column or all columns
        if cidx is not None:
            columns_to_search = [(cidx, self.df.columns[cidx])]
        else:
            columns_to_search = list(enumerate(self.df.columns))

        # Search each column consistently
        for col_idx, col_name in columns_to_search:
            # Build expression based on term type
            if term == NULL:
                expr = pl.col(col_name).is_null()
            elif tentative_expr(term):
                try:
                    expr = validate_expr(term, self.df.columns, col_idx)
                except Exception as e:
                    self.notify(
                        f"Error validating expression [$error]{term}[/]", title="Find", severity="error", timeout=10
                    )
                    self.log(f"Error validating expression `{term}`: {str(e)}")
                    return matches
            else:
                if match_whole:
                    term = f"^{term}$"
                if match_nocase:
                    term = f"(?i){term}"
                expr = pl.col(col_name).cast(pl.String).str.contains(term)

            # Get matched row indices
            try:
                matched_ridxs = lf.filter(expr).collect()[RID]
            except Exception as e:
                self.notify(f"Error applying filter: [$error]{expr}[/]", title="Find", severity="error", timeout=10)
                self.log(f"Error applying filter: {str(e)}")
                return matches

            for ridx in matched_ridxs:
                matches[ridx].add(col_name)

        return matches

    def do_find_cursor_value(self, scope="column") -> None:
        """Find by cursor value.

        Args:
            scope: "column" to find in current column, "global" to find across all columns.
        """
        # Get the value of the currently selected cell
        term = NULL if self.cursor_value is None else str(self.cursor_value)

        if scope == "column":
            cidx = self.cursor_col_idx
            self.find((term, cidx, False, True))
        else:
            self.find_global((term, None, False, True))

    def do_find_expr(self, scope="column") -> None:
        """Open screen to find by expression.

        Args:
            scope: "column" to find in current column, "global" to find across all columns.
        """
        # Use current cell value as default search term
        term = NULL if self.cursor_value is None else str(self.cursor_value)
        cidx = self.cursor_col_idx if scope == "column" else None

        # Push the search modal screen
        self.app.push_screen(
            SearchScreen("Find", term, self.df, cidx),
            callback=self.find if scope == "column" else self.find_global,
        )

    def find(self, result) -> None:
        """Find a term in current column."""
        if result is None:
            return
        term, cidx, match_nocase, match_whole = result

        col_name = self.df.columns[cidx]

        try:
            matches = self.find_matches(term, cidx, match_nocase, match_whole)
        except Exception as e:
            self.notify(f"Error finding matches for `[$error]{term}[/]`", title="Find", severity="error", timeout=10)
            self.log(f"Error finding matches for `{term}`: {str(e)}")
            return

        if not matches:
            self.notify(
                f"No matches found for `[$warning]{term}[/]` in current column. Try [$accent](?i)abc[/] for case-insensitive search.",
                title="Find",
                severity="warning",
            )
            return

        # Add to history
        self.add_history(f"Found `[$success]{term}[/]` in column [$accent]{col_name}[/]")

        # Add to matches and count total
        match_count = sum(len(cols) for cols in matches.values())
        for rid, cols in matches.items():
            self.matches[rid].update(cols)

        self.notify(f"Found [$success]{match_count}[/] matches for `[$accent]{term}[/]`", title="Find")

        # Recreate table for display
        self.setup_table()

    def find_global(self, result) -> None:
        """Global find a term across all columns."""
        if result is None:
            return
        term, cidx, match_nocase, match_whole = result

        try:
            matches = self.find_matches(term, cidx=None, match_nocase=match_nocase, match_whole=match_whole)
        except Exception as e:
            self.notify(f"Error finding matches for `[$error]{term}[/]`", title="Find", severity="error", timeout=10)
            self.log(f"Error finding matches for `{term}`: {str(e)}")
            return

        if not matches:
            self.notify(
                f"No matches found for `[$warning]{term}[/]` in any column. Try [$accent](?i)abc[/] for case-insensitive search.",
                title="Global Find",
                severity="warning",
            )
            return

        # Add to history
        self.add_history(f"Found `[$success]{term}[/]` across all columns")

        # Add to matches and count total
        match_count = sum(len(cols) for cols in matches.values())
        for rid, cols in matches.items():
            self.matches[rid].update(cols)

        self.notify(
            f"Found [$success]{match_count}[/] matches for `[$accent]{term}[/]` across all columns",
            title="Global Find",
        )

        # Recreate table for display
        self.setup_table()

    def do_next_match(self) -> None:
        """Move cursor to the next match."""
        if not self.matches:
            self.notify("No matches to navigate", title="Next Match", severity="warning")
            return

        # Get sorted list of matched coordinates
        ordered_matches = self.ordered_matches

        # Current cursor position
        current_pos = (self.cursor_row_idx, self.cursor_col_idx)

        # Find the next match after current position
        for ridx, cidx in ordered_matches:
            if (ridx, cidx) > current_pos:
                self.move_cursor_to(ridx, cidx)
                return

        # If no next match, wrap around to the first match
        first_ridx, first_cidx = ordered_matches[0]
        self.move_cursor_to(first_ridx, first_cidx)

    def do_previous_match(self) -> None:
        """Move cursor to the previous match."""
        if not self.matches:
            self.notify("No matches to navigate", title="Previous Match", severity="warning")
            return

        # Get sorted list of matched coordinates
        ordered_matches = self.ordered_matches

        # Current cursor position
        current_pos = (self.cursor_row_idx, self.cursor_col_idx)

        # Find the previous match before current position
        for ridx, cidx in reversed(ordered_matches):
            if (ridx, cidx) < current_pos:
                row_key = str(ridx)
                col_key = self.df.columns[cidx]
                row_idx, col_idx = self.get_cell_coordinate(row_key, col_key)
                self.move_cursor(row=row_idx, column=col_idx)
                return

        # If no previous match, wrap around to the last match
        last_ridx, last_cidx = ordered_matches[-1]
        row_key = str(last_ridx)
        col_key = self.df.columns[last_cidx]
        row_idx, col_idx = self.get_cell_coordinate(row_key, col_key)
        self.move_cursor(row=row_idx, column=col_idx)

    def do_next_selected_row(self) -> None:
        """Move cursor to the next selected row."""
        if not self.selected_rows:
            self.notify("No selected rows to navigate", title="Next Selected Row", severity="warning")
            return

        # Get list of selected row indices in order
        selected_row_indices = self.ordered_selected_rows

        # Current cursor row
        current_ridx = self.cursor_row_idx

        # Find the next selected row after current position
        for ridx in selected_row_indices:
            if ridx > current_ridx:
                self.move_cursor_to(ridx, self.cursor_col_idx)
                return

        # If no next selected row, wrap around to the first selected row
        first_ridx = selected_row_indices[0]
        self.move_cursor_to(first_ridx, self.cursor_col_idx)

    def do_previous_selected_row(self) -> None:
        """Move cursor to the previous selected row."""
        if not self.selected_rows:
            self.notify("No selected rows to navigate", title="Previous Selected Row", severity="warning")
            return

        # Get list of selected row indices in order
        selected_row_indices = self.ordered_selected_rows

        # Current cursor row
        current_ridx = self.cursor_row_idx

        # Find the previous selected row before current position
        for ridx in reversed(selected_row_indices):
            if ridx < current_ridx:
                self.move_cursor_to(ridx, self.cursor_col_idx)
                return

        # If no previous selected row, wrap around to the last selected row
        last_ridx = selected_row_indices[-1]
        self.move_cursor_to(last_ridx, self.cursor_col_idx)

    def do_replace(self) -> None:
        """Open replace screen for current column."""
        # Push the replace modal screen
        self.app.push_screen(
            FindReplaceScreen(self, title="Find and Replace in Current Column"),
            callback=self.replace,
        )

    def replace(self, result) -> None:
        """Handle replace in current column."""
        self.handle_replace(result, self.cursor_col_idx)

    def do_replace_global(self) -> None:
        """Open replace screen for all columns."""
        # Push the replace modal screen
        self.app.push_screen(
            FindReplaceScreen(self, title="Global Find and Replace"),
            callback=self.replace_global,
        )

    def replace_global(self, result) -> None:
        """Handle replace across all columns."""
        self.handle_replace(result, None)

    def handle_replace(self, result, cidx) -> None:
        """Handle replace result from ReplaceScreen.

        Args:
            result: Result tuple from ReplaceScreen
            cidx: Column index to perform replacement. If None, replace across all columns.
        """
        if result is None:
            return
        term_find, term_replace, match_nocase, match_whole, replace_all = result

        if cidx is None:
            col_name = "all columns"
        else:
            col_name = self.df.columns[cidx]

        # Find all matches
        matches = self.find_matches(term_find, cidx, match_nocase, match_whole)

        if not matches:
            self.notify(f"No matches found for [$warning]{term_find}[/]", title="Replace", severity="warning")
            return

        # Add to history
        self.add_history(
            f"Replaced [$success]{term_find}[/] with [$accent]{term_replace}[/] in column [$success]{col_name}[/]"
        )

        # Update matches
        self.matches = matches

        # Recreate table for display
        self.setup_table()

        # Store state for interactive replacement using dataclass
        rid2ridx = {rid: ridx for ridx, rid in enumerate(self.df[RID]) if rid in self.matches}

        # Unique columns to replace
        cols_to_replace = set()
        for cols in self.matches.values():
            cols_to_replace.update(cols)

        # Sorted column indices to replace
        cidx2col = {cidx: col for cidx, col in enumerate(self.df.columns) if col in cols_to_replace}

        self.replace_state = ReplaceState(
            term_find=term_find,
            term_replace=term_replace,
            match_nocase=match_nocase,
            match_whole=match_whole,
            cidx=cidx,
            rows=list(rid2ridx.values()),
            cols_per_row=[[cidx for cidx, col in cidx2col.items() if col in self.matches[rid]] for rid in rid2ridx],
            current_rpos=0,
            current_cpos=0,
            current_occurrence=0,
            total_occurrence=sum(len(cols) for cols in self.matches.values()),
            replaced_occurrence=0,
            skipped_occurrence=0,
            done=False,
        )

        try:
            if replace_all:
                # Replace all occurrences
                self.replace_all(term_find, term_replace)
            else:
                # Replace with confirmation for each occurrence
                self.replace_interactive(term_find, term_replace)

        except Exception as e:
            self.notify(
                f"Error replacing [$error]{term_find}[/] with [$accent]{term_replace}[/]",
                title="Replace",
                severity="error",
                timeout=10,
            )
            self.log(f"Error replacing `{term_find}` with `{term_replace}`: {str(e)}")

    def replace_all(self, term_find: str, term_replace: str) -> None:
        """Replace all occurrences."""
        state = self.replace_state
        self.app.push_screen(
            ConfirmScreen(
                "Replace All",
                label=f"Replace `[$success]{term_find}[/]` with `[$success]{term_replace}[/]` for all [$accent]{state.total_occurrence}[/] occurrences?",
            ),
            callback=self.handle_replace_all_confirmation,
        )

    def handle_replace_all_confirmation(self, result) -> None:
        """Handle user's confirmation for replace all."""
        if result is None:
            return

        state = self.replace_state
        rows = state.rows
        cols_per_row = state.cols_per_row

        # Batch replacements by column for efficiency
        # Group row indices by column to minimize dataframe operations
        cidxs_to_replace: dict[int, set[int]] = defaultdict(set)

        # Single column replacement
        if state.cidx is not None:
            cidxs_to_replace[state.cidx].update(rows)
        # Multiple columns replacement
        else:
            for ridx, cidxs in zip(rows, cols_per_row):
                for cidx in cidxs:
                    cidxs_to_replace[cidx].add(ridx)

        # Apply replacements column by column (single operation per column)
        for cidx, ridxs in cidxs_to_replace.items():
            col_name = self.df.columns[cidx]
            dtype = self.df.dtypes[cidx]

            # Create a mask for rows to replace
            mask = pl.arange(0, len(self.df)).is_in(ridxs)

            # Only applicable to string columns for substring matches
            if dtype == pl.String and not state.match_whole:
                term_find = f"(?i){state.term_find}" if state.match_nocase else state.term_find
                self.df = self.df.with_columns(
                    pl.when(mask)
                    .then(pl.col(col_name).str.replace_all(term_find, state.term_replace))
                    .otherwise(pl.col(col_name))
                    .alias(col_name)
                )
            else:
                # Try to convert replacement value to column dtype
                try:
                    value = DtypeConfig(dtype).convert(state.term_replace)
                except Exception:
                    value = state.term_replace

                self.df = self.df.with_columns(
                    pl.when(mask).then(pl.lit(value)).otherwise(pl.col(col_name)).alias(col_name)
                )

            # Also update the view if applicable
            if self.df_view is not None:
                col_updated = f"^_{col_name}_^"
                lf_updated = self.df.lazy().filter(mask).select(pl.col(col_name).alias(col_updated), pl.col(RID))
                self.df_view = (
                    self.df_view.lazy()
                    .join(lf_updated, on=RID, how="left")
                    .with_columns(pl.coalesce(pl.col(col_updated), pl.col(col_name)).alias(col_name))
                    .drop(col_updated)
                    .collect()
                )

            state.replaced_occurrence += len(ridxs)

        # Recreate table for display
        self.setup_table()

        # Mark as dirty if any replacements were made
        if state.replaced_occurrence > 0:
            self.dirty = True

        col_name = "all columns" if state.cidx is None else self.df.columns[state.cidx]
        self.notify(
            f"Replaced [$success]{state.replaced_occurrence}[/] of [$success]{state.total_occurrence}[/] in [$accent]{col_name}[/]",
            title="Replace",
        )

    def replace_interactive(self, term_find: str, term_replace: str) -> None:
        """Replace with user confirmation for each occurrence."""
        try:
            # Start with first match
            self.show_next_replace_confirmation()
        except Exception as e:
            self.notify(
                f"Error replacing [$error]{term_find}[/] with [$accent]{term_replace}[/]",
                title="Replace",
                severity="error",
                timeout=10,
            )
            self.log(f"Error in interactive replace: {str(e)}")

    def show_next_replace_confirmation(self) -> None:
        """Show confirmation for next replacement."""
        state = self.replace_state
        if state.done:
            # All done - show final notification
            col_name = "all columns" if state.cidx is None else self.df.columns[state.cidx]
            msg = f"Replaced [$success]{state.replaced_occurrence}[/] of [$success]{state.total_occurrence}[/] in [$accent]{col_name}[/]"
            if state.skipped_occurrence > 0:
                msg += f", [$warning]{state.skipped_occurrence}[/] skipped"
            self.notify(msg, title="Replace")

            if state.replaced_occurrence > 0:
                self.dirty = True

            return

        # Move cursor to next match
        ridx = state.rows[state.current_rpos]
        cidx = state.cols_per_row[state.current_rpos][state.current_cpos]
        self.move_cursor_to(ridx, cidx)

        state.current_occurrence += 1

        # Show confirmation
        label = f"Replace `[$warning]{state.term_find}[/]` with `[$success]{state.term_replace}[/]` ({state.current_occurrence} of {state.total_occurrence})?"

        self.app.push_screen(
            ConfirmScreen("Replace", label=label, maybe="Skip"),
            callback=self.handle_replace_confirmation,
        )

    def handle_replace_confirmation(self, result) -> None:
        """Handle user's confirmation response."""
        state = self.replace_state
        if state.done:
            return

        ridx = state.rows[state.current_rpos]
        cidx = state.cols_per_row[state.current_rpos][state.current_cpos]
        col_name = self.df.columns[cidx]
        dtype = self.df.dtypes[cidx]
        rid = self.df[RID][ridx]

        # Replace
        if result is True:
            # Only applicable to string columns for substring matches
            if dtype == pl.String and not state.match_whole:
                term_find = f"(?i){state.term_find}" if state.match_nocase else state.term_find
                self.df = self.df.with_columns(
                    pl.when(pl.arange(0, len(self.df)) == ridx)
                    .then(pl.col(col_name).str.replace_all(term_find, state.term_replace))
                    .otherwise(pl.col(col_name))
                    .alias(col_name)
                )

                # Also update the view if applicable
                if self.df_view is not None:
                    self.df_view = self.df_view.with_columns(
                        pl.when(pl.col(RID) == rid)
                        .then(pl.col(col_name).str.replace_all(term_find, state.term_replace))
                        .otherwise(pl.col(col_name))
                        .alias(col_name)
                    )
            else:
                # try to convert replacement value to column dtype
                try:
                    value = DtypeConfig(dtype).convert(state.term_replace)
                except Exception:
                    value = state.term_replace

                self.df = self.df.with_columns(
                    pl.when(pl.arange(0, len(self.df)) == ridx)
                    .then(pl.lit(value))
                    .otherwise(pl.col(col_name))
                    .alias(col_name)
                )

                # Also update the view if applicable
                if self.df_view is not None:
                    self.df_view = self.df_view.with_columns(
                        pl.when(pl.col(RID) == rid).then(pl.lit(value)).otherwise(pl.col(col_name)).alias(col_name)
                    )

            state.replaced_occurrence += 1

        # Skip
        elif result is False:
            state.skipped_occurrence += 1

        # Cancel
        else:
            state.done = True

        if not state.done:
            # Get the new value of the current cell after replacement
            new_cell_value = self.df.item(ridx, cidx)
            row_key = str(ridx)
            col_key = col_name
            self.update_cell(
                row_key, col_key, Text(str(new_cell_value), style=HIGHLIGHT_COLOR, justify=DtypeConfig(dtype).justify)
            )

            # Move to next
            if state.current_cpos + 1 < len(state.cols_per_row[state.current_rpos]):
                state.current_cpos += 1
            else:
                state.current_cpos = 0
                state.current_rpos += 1

            if state.current_rpos >= len(state.rows):
                state.done = True

        # Show next confirmation
        self.show_next_replace_confirmation()

    # View & Filter
    def do_view_rows(self) -> None:
        """View rows.

        If there are selected rows, view those.
        Otherwise, view based on the cursor value.
        """

        cidx = self.cursor_col_idx
        col_name = self.cursor_col_name

        # If there are selected rows, use those
        if self.selected_rows:
            term = pl.col(RID).is_in(self.selected_rows)
        # Otherwise, use the current cell value
        else:
            ridx = self.cursor_row_idx
            value = self.df.item(ridx, cidx)
            term = pl.col(col_name).is_null() if value is None else pl.col(col_name) == value

        self.view_rows((term, cidx, False, True))

    def do_view_rows_expr(self) -> None:
        """Open the filter screen to enter an expression."""
        ridx = self.cursor_row_idx
        cidx = self.cursor_col_idx
        cursor_value = self.df.item(ridx, cidx)
        term = NULL if cursor_value is None else str(cursor_value)

        self.app.push_screen(
            FilterScreen(self.df, cidx, term),
            callback=self.view_rows,
        )

    def view_rows(self, result) -> None:
        """View selected rows and hide others. Do not modify the dataframe."""
        if result is None:
            return
        term, cidx, match_nocase, match_whole = result

        col_name = self.df.columns[cidx]

        # Support for polars expression
        if isinstance(term, pl.Expr):
            expr = term

        # Support for list of booleans (selected rows)
        elif isinstance(term, (list, pl.Series)):
            expr = term

        # Null case
        elif term == NULL:
            expr = pl.col(col_name).is_null()

        # Support for polars expression in string form
        elif tentative_expr(term):
            try:
                expr = validate_expr(term, self.df.columns, cidx)
            except Exception as e:
                self.notify(
                    f"Error validating expression [$error]{term}[/]", title="Filter", severity="error", timeout=10
                )
                self.log(f"Error validating expression `{term}`: {str(e)}")
                return

        # Type-aware search based on column dtype
        else:
            dtype = self.df.dtypes[cidx]
            if dtype == pl.String:
                if match_whole:
                    term = f"^{term}$"
                if match_nocase:
                    term = f"(?i){term}"
                expr = pl.col(col_name).str.contains(term)
            else:
                try:
                    value = DtypeConfig(dtype).convert(term)
                    expr = pl.col(col_name) == value
                except Exception:
                    if match_whole:
                        term = f"^{term}$"
                    if match_nocase:
                        term = f"(?i){term}"
                    expr = pl.col(col_name).cast(pl.String).str.contains(term)
                    self.notify(
                        f"Unknown column type [$warning]{dtype}[/]. Cast to string.", title="Filter", severity="warning"
                    )

        # Lazyframe with row indices
        lf = self.df.lazy()

        expr_str = "boolean list or series" if isinstance(expr, (list, pl.Series)) else str(expr)

        # Apply the filter expression
        try:
            df_filtered = lf.filter(expr).collect()
        except Exception as e:
            self.histories_undo.pop()  # Remove last history entry
            self.notify(f"Error applying filter [$error]{expr_str}[/]", title="Filter", severity="error", timeout=10)
            self.log(f"Error applying filter `{expr_str}`: {str(e)}")
            return

        matched_count = len(df_filtered)
        if not matched_count:
            self.notify(f"No rows match the expression: [$success]{expr}[/]", title="Filter", severity="warning")
            return

        # Add to history
        self.add_history(f"Filtered by expression [$success]{expr_str}[/]")

        ok_rids = set(df_filtered[RID])

        # Create a view of self.df as a copy
        if self.df_view is None:
            self.df_view = self.df

        # Update dataframe
        self.df = df_filtered

        # Update selected rows
        if self.selected_rows:
            self.selected_rows.intersection_update(ok_rids)

        # Update matches
        if self.matches:
            self.matches = {rid: cols for rid, cols in self.matches.items() if rid in ok_rids}

        # Recreate table for display
        self.setup_table()

        self.notify(f"Filtered to [$success]{matched_count}[/] matching row(s)", title="Filter")

    def do_filter_rows(self) -> None:
        """Filter rows.

        If there are selected rows, use those.
        Otherwise, filter based on the cursor value.
        """
        if self.selected_rows:
            message = "Filtered to selected rows (other rows removed)"
            filter_expr = pl.col(RID).is_in(self.selected_rows)
        else:  # Search cursor value in current column
            message = "Filtered to rows matching cursor value (other rows removed)"
            cidx = self.cursor_col_idx
            col_name = self.df.columns[cidx]
            value = self.cursor_value

            if value is None:
                filter_expr = pl.col(col_name).is_null()
            else:
                filter_expr = pl.col(col_name) == value

        # Add to history
        self.add_history(message, dirty=True)

        # Apply filter to dataframe with row indices
        df_filtered = self.df.lazy().filter(filter_expr).collect()
        ok_rids = set(df_filtered[RID])

        # Update selected rows
        if self.selected_rows:
            selected_rows = {rid for rid in self.selected_rows if rid in ok_rids}
        else:
            selected_rows = set()

        # Update matches
        if self.matches:
            matches = {rid: cols for rid, cols in self.matches.items() if rid in ok_rids}
        else:
            matches = defaultdict(set)

        # Update dataframe
        self.reset_df(df_filtered)

        # Clear view for filter mode
        self.df_view = None

        # Restore selected rows and matches
        self.selected_rows = selected_rows
        self.matches = matches

        # Recreate table for display
        self.setup_table()

        self.notify(f"{message}. Now showing [$success]{len(self.df)}[/] rows.", title="Filter")

    # Copy & Save
    def do_copy_to_clipboard(self, content: str, message: str) -> None:
        """Copy content to clipboard using pbcopy (macOS) or xclip (Linux).

        Args:
            content: The text content to copy to clipboard.
            message: The notification message to display on success.
        """
        import subprocess

        try:
            subprocess.run(
                [
                    "pbcopy" if sys.platform == "darwin" else "xclip",
                    "-selection",
                    "clipboard",
                ],
                input=content,
                text=True,
            )
            self.notify(message, title="Clipboard")
        except FileNotFoundError:
            self.notify("Error copying to clipboard", title="Clipboard", severity="error", timeout=10)

    def do_save_to_file(self, all_tabs: bool | None = None, task_after_save: str | None = None) -> None:
        """Open screen to save file."""
        self._task_after_save = task_after_save
        tab_count = len(self.app.tabs)
        save_all = tab_count > 1 and all_tabs is not False

        filepath = Path(self.filename)
        if save_all:
            ext = filepath.suffix.lower()
            if ext in (".xlsx", ".xls"):
                filename = self.filename
            else:
                filename = "all-tabs.xlsx"
        else:
            filename = str(filepath.with_stem(self.tabname))

        self.app.push_screen(
            SaveFileScreen(filename, save_all=save_all, tab_count=tab_count),
            callback=self.save_to_file,
        )

    def save_to_file(self, result) -> None:
        """Handle result from SaveFileScreen."""
        if result is None:
            return
        filename, save_all, overwrite_prompt = result
        self._save_all = save_all

        # Check if file exists
        if overwrite_prompt and Path(filename).exists():
            self._pending_filename = filename
            self.app.push_screen(
                ConfirmScreen("File already exists. Overwrite?"),
                callback=self.confirm_overwrite,
            )
        else:
            self.save_file(filename)

    def confirm_overwrite(self, should_overwrite: bool) -> None:
        """Handle result from ConfirmScreen."""
        if should_overwrite:
            self.save_file(self._pending_filename)
        else:
            # Go back to SaveFileScreen to allow user to enter a different name
            self.app.push_screen(
                SaveFileScreen(self._pending_filename, save_all=self._save_all),
                callback=self.save_to_file,
            )

    def save_file(self, filename: str) -> None:
        """Actually save the dataframe to a file."""
        filepath = Path(filename)
        ext = filepath.suffix.lower()
        if ext == ".gz":
            ext = Path(filename).with_suffix("").suffix.lower()

        fmt = ext.removeprefix(".")
        if fmt not in SUPPORTED_FORMATS:
            self.notify(
                f"Unsupported file format [$success]{fmt}[/]. Use [$accent]CSV[/] as fallback. Supported formats: {', '.join(SUPPORTED_FORMATS)}",
                title="Save to File",
                severity="warning",
            )
            fmt = "csv"

        df = (self.df if self.df_view is None else self.df_view).select(pl.exclude(RID))
        try:
            if fmt == "csv":
                df.write_csv(filename)
            elif fmt in ("tsv", "tab"):
                df.write_csv(filename, separator="\t")
            elif fmt in ("xlsx", "xls"):
                self.save_excel(filename)
            elif fmt == "json":
                df.write_json(filename)
            elif fmt == "ndjson":
                df.write_ndjson(filename)
            elif fmt == "parquet":
                df.write_parquet(filename)
            else:  # Fallback to CSV
                df.write_csv(filename)

            # Update current filename
            self.filename = filename

            # Reset dirty flag after save
            if self._save_all:
                tabs: dict[TabPane, DataFrameTable] = self.app.tabs
                for table in tabs.values():
                    table.dirty = False
            else:
                self.dirty = False

            if hasattr(self, "_task_after_save"):
                if self._task_after_save == "close_tab":
                    self.app.do_close_tab()
                elif self._task_after_save == "quit_app":
                    self.app.exit()

            # From ConfirmScreen callback, so notify accordingly
            if self._save_all:
                self.notify(f"Saved all tabs to [$success]{filename}[/]", title="Save to File")
            else:
                self.notify(f"Saved current tab to [$success]{filename}[/]", title="Save to File")

        except Exception as e:
            self.notify(f"Error saving [$error]{filename}[/]", title="Save to File", severity="error", timeout=10)
            self.log(f"Error saving file `{filename}`: {str(e)}")

    def save_excel(self, filename: str) -> None:
        """Save to an Excel file."""
        import xlsxwriter

        if not self._save_all or len(self.app.tabs) == 1:
            # Single tab - save directly
            df = (self.df if self.df_view is None else self.df_view).select(pl.exclude(RID))
            df.write_excel(filename, worksheet=self.tabname)
        else:
            # Multiple tabs - use xlsxwriter to create multiple sheets
            with xlsxwriter.Workbook(filename) as wb:
                tabs: dict[TabPane, DataFrameTable] = self.app.tabs
                for table in tabs.values():
                    worksheet = wb.add_worksheet(table.tabname)
                    df = (table.df if table.df_view is None else table.df_view).select(pl.exclude(RID))
                    df.write_excel(workbook=wb, worksheet=worksheet)

    # SQL Interface
    def do_simple_sql(self) -> None:
        """Open the SQL interface screen."""
        self.app.push_screen(
            SimpleSqlScreen(self),
            callback=self.simple_sql,
        )

    def simple_sql(self, result) -> None:
        """Handle SQL result result from SimpleSqlScreen."""
        if result is None:
            return
        columns, where, view = result

        sql = f"SELECT {columns} FROM self"
        if where:
            sql += f" WHERE {where}"

        self.run_sql(sql, view)

    def do_advanced_sql(self) -> None:
        """Open the advanced SQL interface screen."""
        self.app.push_screen(
            AdvancedSqlScreen(self),
            callback=self.advanced_sql,
        )

    def advanced_sql(self, result) -> None:
        """Handle SQL result result from AdvancedSqlScreen."""
        if result is None:
            return
        sql, view = result

        self.run_sql(sql, view)

    def run_sql(self, sql: str, view: bool = True) -> None:
        """Execute a SQL query directly.

        Args:
            sql: The SQL query string to execute.
        """

        sql = sql.replace("$#", f"(`{RID}` + 1)")
        if RID not in sql and "*" not in sql:
            # Ensure RID is selected
            import re

            RE_FROM_SELF = re.compile(r"\bFROM\s+self\b", re.IGNORECASE)
            sql = RE_FROM_SELF.sub(f", `{RID}` FROM self", sql)

        # Execute the SQL query
        try:
            df_filtered = self.df.lazy().sql(sql).collect()

            if not len(df_filtered):
                self.notify(
                    f"SQL query returned no results for [$warning]{sql}[/]", title="SQL Query", severity="warning"
                )
                return

        except Exception as e:
            self.notify(f"Error executing SQL query [$error]{sql}[/]", title="SQL Query", severity="error", timeout=10)
            self.log(f"Error executing SQL query `{sql}`: {str(e)}")
            return

        # Add to history
        self.add_history(f"SQL Query:\n[$success]{sql}[/]", dirty=not view)

        # Create a view of self.df as a copy
        if view and self.df_view is None:
            self.df_view = self.df

        # Clear view for filter mode
        if not view:
            self.df_view = None

        # Update dataframe
        self.df = df_filtered
        ok_rids = set(df_filtered[RID])

        # Update selected rows
        if self.selected_rows:
            self.selected_rows.intersection_update(ok_rids)

        # Update matches
        if self.matches:
            self.matches = {rid: cols for rid, cols in self.matches.items() if rid in ok_rids}

        # Recreate table for display
        self.setup_table()

        self.notify(
            f"SQL query executed successfully. Now showing [$accent]{len(self.df)}[/] rows and [$accent]{len(self.df.columns)}[/] columns.",
            title="SQL Query",
        )
