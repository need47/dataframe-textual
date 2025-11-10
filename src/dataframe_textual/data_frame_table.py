"""DataFrameTable widget for displaying and interacting with Polars DataFrames."""

import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

import polars as pl
from rich.text import Text
from textual.coordinate import Coordinate
from textual.events import Click
from textual.widgets import DataTable, TabPane
from textual.widgets._data_table import (
    CellDoesNotExist,
    CellKey,
    ColumnKey,
    CursorType,
    RowKey,
)

from .common import (
    CURSOR_TYPES,
    NULL,
    NULL_DISPLAY,
    RIDX,
    SUBSCRIPT_DIGITS,
    DtypeConfig,
    format_row,
    get_next_item,
    rindex,
    tentative_expr,
    validate_expr,
)
from .table_screen import FrequencyScreen, RowDetailScreen, StatisticsScreen
from .yes_no_screen import (
    AddColumnScreen,
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


@dataclass
class History:
    """Class to track history of dataframe states for undo/redo functionality."""

    description: str
    df: pl.DataFrame
    filename: str
    loaded_rows: int
    sorted_columns: dict[str, bool]
    hidden_columns: set[str]
    selected_rows: list[bool]
    visible_rows: list[bool]
    fixed_rows: int
    fixed_columns: int
    cursor_coordinate: Coordinate
    matches: dict[int, set[int]]


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


class DataFrameTable(DataTable):
    """Custom DataTable to highlight row/column labels based on cursor position."""

    # Help text for the DataTable which will be shown in the HelpPanel
    HELP = dedent("""
        # 📊 DataFrame Viewer - Table Controls

        ## ⬆️ Navigation
        - **↑↓←→** - 🎯 Move cursor (cell/row/column)
        - **g** - ⬆️ Jump to first row
        - **G** - ⬇️ Jump to last row
        - **PgUp/PgDn** - 📜 Page up/down

        ## 👁️ View & Display
        - **Enter** - 📋 Show row details in modal
        - **F** - 📊 Show frequency distribution
        - **s** - 📈 Show statistics for current column
        - **S** - 📊 Show statistics for entire dataframe
        - **K** - 🔄 Cycle cursor (cell → row → column → cell)
        - **~** - 🏷️ Toggle row labels

        ## ↕️ Sorting
        - **[** - 🔼 Sort column ascending
        - **]** - 🔽 Sort column descending
        - *(Multi-column sort supported)*

        ## 🔍 Search & Filter
        - **|** - 🔎 Search in current column with expression
        - **\\\\** - 🔎 Search in current column using cursor value
        - **/** - 🔎 Find in current column with cursor value
        - **?** - 🔎 Find in current column with expression
        - **f** - 🌐 Global find using cursor value
        - **Ctrl+f** - 🌐 Global find with expression
        - **n** - ⬇️ Go to next match
        - **N** - ⬆️ Go to previous match
        - **v** - 👁️ View/filter rows by cell or selected rows
        - **V** - 🔧 View/filter rows by expression
        - *(All search/find support case-insensitive & whole-word matching)*

        ## ✏️ Replace
        - **r** - 🔄 Replace in current column (interactive or all)
        - **R** - 🔄 Replace across all columns (interactive or all)
        - *(Supports case-insensitive & whole-word matching)*

        ## ✅ Selection & Filtering
        - **'** - ✓️ Select/deselect current row
        - **t** - 💡 Toggle row selection (invert all)
        - **{** - ⬆️ Go to previous selected row
        - **}** - ⬇️ Go to next selected row
        - **"** - 📍 Filter to show only selected rows
        - **T** - 🧹 Clear all selections

        ## ✏️ Edit & Modify
        - **Double-click** - ✍️ Edit cell or rename column header
        - **e** - ✍️ Edit current cell
        - **E** - 📊 Edit entire column with expression
        - **a** - ➕ Add empty column after current
        - **A** - ➕ Add column with name and optional expression
        - **x** - 🗑️ Delete current row
        - **X** - ✨ Clear current cell (set to None)
        - **D** - 📋 Duplicate current row
        - **-** - ❌ Delete current column
        - **d** - 📋 Duplicate current column
        - **h** - 👁️ Hide current column
        - **H** - 👀 Show all hidden columns

        ## 🎯 Reorder
        - **Shift+↑↓** - ⬆️⬇️ Move row up/down
        - **Shift+←→** - ⬅️➡️ Move column left/right

        ## 🎨 Type Conversion
        - **#** - 🔢 Cast column to integer
        - **%** - 🔢 Cast column to float
        - **!** - ✅ Cast column to boolean
        - **$** - 📝 Cast column to string

        ## 🔗 URL Handling
        - **@** - 🔗 Make URLs in current column clickable with Ctrl/Cmd

        ## 💾 Data Management
        - **z** - 📌 Freeze rows and columns
        - **,** - 🔢 Toggle thousand separator for numeric display
        - **c** - 📋 Copy cell to clipboard
        - **Ctrl+c** - 📊 Copy column to clipboard
        - **Ctrl+r** - 📝 Copy row to clipboard (tab-separated)
        - **Ctrl+s** - 💾 Save current tab to file
        - **u** - ↩️ Undo last action
        - **U** - 🔄 Reset to original data
    """).strip()

    # fmt: off
    BINDINGS = [
        ("g", "jump_top", "Jump to top"),
        ("G", "jump_bottom", "Jump to bottom"),
        ("h", "hide_column", "Hide column"),
        ("H", "show_column", "Show columns"),
        ("c", "copy_cell", "Copy cell to clipboard"),
        ("ctrl+c", "copy_column", "Copy column to clipboard"),
        ("ctrl+r", "copy_row", "Copy row to clipboard"),
        ("ctrl+s", "save_to_file", "Save to file"),
        ("enter", "view_row_detail", "View row details"),
        # Frequency & Statistics
        ("F", "show_frequency", "Show frequency"),
        ("s", "show_statistics", "Show statistics for column"),
        ("S", "show_statistics('dataframe')", "Show statistics for dataframe"),
        # Sorting
        ("left_square_bracket", "sort_ascending", "Sort ascending"),  # `[`
        ("right_square_bracket", "sort_descending", "Sort descending"),  # `]`
        # View
        ("v", "view_rows", "View rows"),
        ("V", "view_rows_expr", "View rows by expression"),
        # Search
        ("backslash", "search_cursor_value", "Search column with cursor value"),  # `\`
        ("vertical_line", "search_expr", "Search column with expression"),  # `|`
        ("right_curly_bracket", "next_selected_row", "Go to next selected row"),  # `}`
        ("left_curly_bracket", "previous_selected_row", "Go to previous selected row"),  # `{`
        # Find
        ("slash", "find_cursor_value", "Find in column with cursor value"),  # `/`
        ("question_mark", "find_expr", "Find in column with expression"),  # `?`
        ("f", "find_cursor_value('global')", "Global find with cursor value"),  # `f`
        ("ctrl+f", "find_expr('global')", "Global find with expression"),  # `Ctrl+F`
        ("n", "next_match", "Go to next match"),  # `n`
        ("N", "previous_match", "Go to previous match"),  # `Shift+n`
        # Replace
        ("r", "replace", "Replace in column"),  # `r`
        ("R", "replace_global", "Replace global"),  # `Shift+R`
        # Selection
        ("apostrophe", "make_selections", "Toggle row selection"),  # `'`
        ("t", "toggle_selections", "Toggle all row selections"),
        ("T", "clear_selections", "Clear selections"),
        ("quotation_mark", "filter_selected_rows", "Filter selected"),  # `"`
        # Edit
        ("minus", "delete_column", "Delete column"),  # `-`
        ("x", "delete_row", "Delete row"),
        ("X", "clear_cell", "Clear cell"),
        ("d", "duplicate_column", "Duplicate column"),
        ("D", "duplicate_row", "Duplicate row"),
        ("e", "edit_cell", "Edit cell"),
        ("E", "edit_column", "Edit column"),
        ("a", "add_column", "Add column"),
        ("A", "add_column_expr", "Add column with expression"),
        # Reorder
        ("shift+left", "move_column_left", "Move column left"),
        ("shift+right", "move_column_right", "Move column right"),
        ("shift+up", "move_row_up", "Move row up"),
        ("shift+down", "move_row_down", "Move row down"),
        # Type Conversion
        ("number_sign", "cast_column_dtype('int')", "Cast column dtype to int"),  # `#`
        ("percent_sign", "cast_column_dtype('float')", "Cast column dtype to float"),  # `%`
        ("exclamation_mark", "cast_column_dtype('bool')", "Cast column dtype to bool"),  # `!`
        ("dollar_sign", "cast_column_dtype('string')", "Cast column dtype to string"),  # `$`
        ("at", "make_cell_clickable", "Make cell clickable"),  # `@`
        # Misc
        ("tilde", "toggle_row_labels", "Toggle row labels"),  # `~`
        ("K", "cycle_cursor_type", "Cycle cursor mode"),  # `K`
        ("z", "freeze_row_column", "Freeze rows/columns"),
        ("comma", "show_thousand_separator", "Toggle thousand separator"),  # `,`
        # Undo/Redo
        ("u", "undo", "Undo"),
        ("U", "reset", "Reset to original"),
    ]
    # fmt: on

    def __init__(self, df: pl.DataFrame | pl.LazyFrame, filename: str = "", name: str = "", **kwargs) -> None:
        """Initialize the DataFrameTable with a dataframe and manage all state.

        Sets up the table widget with display configuration, loads the dataframe, and
        initializes all state tracking variables for row/column operations.

        Args:
            df: The Polars DataFrame or LazyFrame to display and edit.
            filename: Optional source filename for the data (used in save operations). Defaults to "".
            name: Optional display name for the table tab. Defaults to "" (uses filename stem).
            **kwargs: Additional keyword arguments passed to the parent DataTable widget.

        Returns:
            None
        """
        super().__init__(name=(name or Path(filename).stem), **kwargs)

        # DataFrame state
        self.lazyframe = df.lazy()  # Original dataframe
        self.df = self.lazyframe.collect()  # Internal/working dataframe
        self.filename = filename  # Current filename

        # Pagination & Loading
        self.INITIAL_BATCH_SIZE = (self.app.size.height // 100 + 1) * 100
        self.BATCH_SIZE = self.INITIAL_BATCH_SIZE // 2
        self.loaded_rows = 0  # Track how many rows are currently loaded

        # State tracking (all 0-based indexing)
        self.sorted_columns: dict[str, bool] = {}  # col_name -> descending
        self.hidden_columns: set[str] = set()  # Set of hidden column names
        self.selected_rows: list[bool] = [False] * len(self.df)  # Track selected rows
        self.visible_rows: list[bool] = [True] * len(self.df)  # Track visible rows (for filtering)
        self.matches: dict[int, set[int]] = defaultdict(set)  # Track search matches: row_idx -> set of col_idx

        # Freezing
        self.fixed_rows = 0  # Number of fixed rows
        self.fixed_columns = 0  # Number of fixed columns

        # History stack for undo/redo
        self.histories: deque[History] = deque()

        # Pending filename for save operations
        self._pending_filename = ""

        # Whether to use thousand separator for numeric display
        self.thousand_separator = False

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
        """Get the current cursor cell value.

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
        return [ridx for ridx, selected in enumerate(self.selected_rows) if selected]

    @property
    def ordered_matches(self) -> list[tuple[int, int]]:
        """Get the list of matched cell coordinates in order.

        Returns:
            list[tuple[int, int]]: A list of (row_idx, col_idx) tuples for matched cells.
        """
        matches = []
        for ridx in sorted(self.matches.keys()):
            for cidx in sorted(self.matches[ridx]):
                matches.append((ridx, cidx))
        return matches

    def on_mount(self) -> None:
        """Initialize table display when the widget is mounted.

        Called by Textual when the widget is first added to the display tree.
        Currently a placeholder as table setup is deferred until first use.

        Returns:
            None
        """
        # self._setup_table()
        pass

    def _should_highlight(self, cursor: Coordinate, target_cell: Coordinate, type_of_cursor: CursorType) -> bool:
        """Determine if the given cell should be highlighted because of the cursor.

        In "cell" mode, also highlights the row and column headers. In "row" and "column"
        modes, highlights the entire row or column respectively.

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

        Returns:
            None
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

    def on_key(self, event) -> None:
        """Handle key press events for pagination.

        Currently handles "pagedown" and "down" keys to trigger lazy loading of additional rows
        when scrolling near the end of the loaded data.

        Args:
            event: The key event object.

        Returns:
            None
        """
        if event.key in ("pagedown", "down"):
            # Let the table handle the navigation first
            self._check_and_load_more()

    def on_click(self, event: Click) -> None:
        """Handle mouse click events on the table.

        Supports double-click editing of cells and renaming of column headers.

        Args:
            event: The click event containing row and column information.

        Returns:
            None
        """
        if self.cursor_type == "cell" and event.chain > 1:  # only on double-click or more
            try:
                row_idx = event.style.meta["row"]
                # col_idx = event.style.meta["column"]
            except (KeyError, TypeError):
                return  # Unable to get row/column info

            # header row
            if row_idx == -1:
                self._rename_column()
            else:
                self._edit_cell()

    # Action handlers for BINDINGS
    def action_jump_top(self) -> None:
        """Jump to the top of the table."""
        self.move_cursor(row=0)

    def action_jump_bottom(self) -> None:
        """Jump to the bottom of the table."""
        self._load_rows()
        self.move_cursor(row=self.row_count - 1)

    def action_view_row_detail(self) -> None:
        """View details of the current row."""
        self._view_row_detail()

    def action_delete_column(self) -> None:
        """Delete the current column."""
        self._delete_column()

    def action_hide_column(self) -> None:
        """Hide the current column."""
        self._hide_column()

    def action_show_column(self) -> None:
        """Show all hidden columns."""
        self._show_column()

    def action_sort_ascending(self) -> None:
        """Sort by current column in ascending order."""
        self._sort_by_column(descending=False)

    def action_sort_descending(self) -> None:
        """Sort by current column in descending order."""
        self._sort_by_column(descending=True)

    def action_save_to_file(self) -> None:
        """Save the current dataframe to a file."""
        self._save_to_file()

    def action_show_frequency(self) -> None:
        """Show frequency distribution for the current column."""
        self._show_frequency()

    def action_show_statistics(self, scope: str = "column") -> None:
        """Show statistics for the current column or entire dataframe.

        Args:
            scope: Either "column" for current column stats or "dataframe" for all columns.
        """
        self._show_statistics(scope)

    def action_view_rows(self) -> None:
        """View rows by current cell value."""
        self._view_rows()

    def action_view_rows_expr(self) -> None:
        """Open the advanced filter screen."""
        self._view_rows_expr()

    def action_edit_cell(self) -> None:
        """Edit the current cell."""
        self._edit_cell()

    def action_edit_column(self) -> None:
        """Edit the entire current column with an expression."""
        self._edit_column()

    def action_add_column(self) -> None:
        """Add an empty column after the current column."""
        self._add_column()

    def action_add_column_expr(self) -> None:
        """Add a new column with optional expression after the current column."""
        self._add_column_expr()

    def action_rename_column(self) -> None:
        """Rename the current column."""
        self._rename_column()

    def action_clear_cell(self) -> None:
        """Clear the current cell (set to None)."""
        self._clear_cell()

    def action_search_cursor_value(self) -> None:
        """Search cursor value in the current column."""
        self._search_cursor_value()

    def action_search_expr(self) -> None:
        """Search by expression in the current column."""
        self._search_expr()

    def action_find_cursor_value(self, scope="column") -> None:
        """Find by cursor value.

        Args:
            scope: "column" to find in current column, "global" to find across all columns.
        """
        self._find_cursor_value(scope=scope)

    def action_find_expr(self, scope="column") -> None:
        """Find by expression.

        Args:
            scope: "column" to find in current column, "global" to find across all columns.
        """
        self._find_expr(scope=scope)

    def action_replace(self) -> None:
        """Replace values in current column."""
        self._replace()

    def action_replace_global(self) -> None:
        """Replace values across all columns."""
        self._replace_global()

    def action_make_selections(self) -> None:
        """Toggle selection for the current row."""
        self._make_selections()

    def action_toggle_selections(self) -> None:
        """Toggle all row selections."""
        self._toggle_selections()

    def action_filter_selected_rows(self) -> None:
        """Filter to show only selected rows."""
        self._filter_selected_rows()

    def action_delete_row(self) -> None:
        """Delete the current row."""
        self._delete_row()

    def action_duplicate_column(self) -> None:
        """Duplicate the current column."""
        self._duplicate_column()

    def action_duplicate_row(self) -> None:
        """Duplicate the current row."""
        self._duplicate_row()

    def action_undo(self) -> None:
        """Undo the last action."""
        self._undo()

    def action_reset(self) -> None:
        """Reset to the original data."""
        self._setup_table(reset=True)
        self.notify("Restored original display", title="Reset")

    def action_move_column_left(self) -> None:
        """Move the current column to the left."""
        self._move_column("left")

    def action_move_column_right(self) -> None:
        """Move the current column to the right."""
        self._move_column("right")

    def action_move_row_up(self) -> None:
        """Move the current row up."""
        self._move_row("up")

    def action_move_row_down(self) -> None:
        """Move the current row down."""
        self._move_row("down")

    def action_clear_selections(self) -> None:
        """Clear all row selections."""
        self._clear_selections()

    def action_cycle_cursor_type(self) -> None:
        """Cycle through cursor types."""
        self._cycle_cursor_type()

    def action_freeze_row_column(self) -> None:
        """Open the freeze screen."""
        self._freeze_row_column()

    def action_toggle_row_labels(self) -> None:
        """Toggle row labels visibility."""
        self.show_row_labels = not self.show_row_labels
        # status = "shown" if self.show_row_labels else "hidden"
        # self.notify(f"Row labels {status}", title="Labels")

    def action_cast_column_dtype(self, dtype: str | pl.DataType) -> None:
        """Cast the current column to a different data type."""
        self._cast_column_dtype(dtype)

    def action_copy_cell(self) -> None:
        """Copy the current cell to clipboard."""
        ridx = self.cursor_row_idx
        cidx = self.cursor_col_idx

        try:
            cell_str = str(self.df.item(ridx, cidx))
            self._copy_to_clipboard(cell_str, f"Copied: [$success]{cell_str[:50]}[/]")
        except IndexError:
            self.notify("Error copying cell", title="Clipboard", severity="error")

    def action_copy_column(self) -> None:
        """Copy the current column to clipboard (one value per line)."""
        col_name = self.cursor_col_name

        try:
            # Get all values in the column and join with newlines
            col_values = [str(val) for val in self.df[col_name].to_list()]
            col_str = "\n".join(col_values)

            self._copy_to_clipboard(
                col_str,
                f"Copied [$accent]{len(col_values)}[/] values from column [$success]{col_name}[/]",
            )
        except (FileNotFoundError, IndexError):
            self.notify("Error copying column", title="Clipboard", severity="error")

    def action_copy_row(self) -> None:
        """Copy the current row to clipboard (values separated by tabs)."""
        ridx = self.cursor_row_idx

        try:
            # Get all values in the row and join with tabs
            row_values = [str(val) for val in self.df.row(ridx)]
            row_str = "\t".join(row_values)

            self._copy_to_clipboard(
                row_str,
                f"Copied row [$accent]{ridx + 1}[/] with [$success]{len(row_values)}[/] values",
            )
        except (FileNotFoundError, IndexError):
            self.notify("Error copying row", title="Clipboard", severity="error")

    def action_make_cell_clickable(self) -> None:
        """Make cells with URLs in current column clickable."""
        self._make_cell_clickable()

    def action_show_thousand_separator(self) -> None:
        """Toggle thousand separator for numeric display."""
        self.thousand_separator = not self.thousand_separator
        self._setup_table()
        # status = "enabled" if self.thousand_separator else "disabled"
        # self.notify(f"Thousand separator {status}", title="Display")

    def action_next_match(self) -> None:
        """Go to the next matched cell."""
        self._next_match()

    def action_previous_match(self) -> None:
        """Go to the previous matched cell."""
        self._previous_match()

    def action_next_selected_row(self) -> None:
        """Go to the next selected row."""
        self._next_selected_row()

    def action_previous_selected_row(self) -> None:
        """Go to the previous selected row."""
        self._previous_selected_row()

    def _make_cell_clickable(self) -> None:
        """Make cells with URLs in the current column clickable.

        Scans all loaded rows in the current column for cells containing URLs
        (starting with 'http://' or 'https://') and applies Textual link styling
        to make them clickable. Does not modify the dataframe.

        Returns:
            None
        """
        cidx = self.cursor_col_idx
        col_key = self.cursor_col_key
        dtype = self.df.dtypes[cidx]

        # Only process string columns
        if dtype != pl.String:
            return

        # Count how many URLs were made clickable
        url_count = 0

        # Iterate through all loaded rows and make URLs clickable
        for row in self.ordered_rows:
            cell_text: Text = self.get_cell(row.key, col_key)
            if cell_text.plain.startswith(("http://", "https://")):
                cell_text.style = f"#00afff link {cell_text.plain}"  # sky blue
                self.update_cell(row.key, col_key, cell_text)
                url_count += 1

        if url_count:
            self.notify(
                f"Made [$accent]{url_count}[/] cell(s) clickable in column [$success]{col_key.value}[/]",
                title="Make Clickable",
            )

    def on_mouse_scroll_down(self, event) -> None:
        """Load more rows when scrolling down with mouse."""
        self._check_and_load_more()

    # Setup & Loading
    def _setup_table(self, reset: bool = False) -> None:
        """Setup the table for display.

        Row keys are 0-based indices, which map directly to dataframe row indices.
        Column keys are header names from the dataframe.
        """
        # Reset to original dataframe
        if reset:
            self.df = self.lazyframe.collect()
            self.loaded_rows = 0
            self.sorted_columns = {}
            self.hidden_columns = set()
            self.selected_rows = [False] * len(self.df)
            self.visible_rows = [True] * len(self.df)
            self.fixed_rows = 0
            self.fixed_columns = 0
            self.matches = defaultdict(set)

        # Lazy load up to INITIAL_BATCH_SIZE visible rows
        stop, visible_count = len(self.df), 0
        for row_idx, visible in enumerate(self.visible_rows):
            if not visible:
                continue
            visible_count += 1
            if visible_count >= self.INITIAL_BATCH_SIZE:
                stop = row_idx + 1
                break

        # Save current cursor position before clearing
        row_idx, col_idx = self.cursor_coordinate

        self._setup_columns()
        self._load_rows(stop)
        self._do_highlight()

        # Restore cursor position
        if row_idx < len(self.rows) and col_idx < len(self.columns):
            self.move_cursor(row=row_idx, column=col_idx)

    def _setup_columns(self) -> None:
        """Clear table and setup columns.

        Column keys are header names from the dataframe.
        Column labels contain column names from the dataframe, with sort indicators if applicable.
        """
        self.loaded_rows = 0
        self.clear(columns=True)
        self.show_row_labels = True

        # Add columns with justified headers
        for col, dtype in zip(self.df.columns, self.df.dtypes):
            if col in self.hidden_columns:
                continue  # Skip hidden columns
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

            self.add_column(Text(cell_value, justify=DtypeConfig(dtype).justify), key=col)

    def _load_rows(self, stop: int | None = None) -> None:
        """Load a batch of rows into the table.

        Row keys are 0-based indices as strings, which map directly to dataframe row indices.
        Row labels are 1-based indices as strings.

        Args:
            stop: Stop loading rows when this index is reached. If None, load until the end of the dataframe.
        """
        if stop is None or stop > len(self.df):
            stop = len(self.df)

        if stop <= self.loaded_rows:
            return

        start = self.loaded_rows
        df_slice = self.df.slice(start, stop - start)

        for row_idx, row in enumerate(df_slice.rows(), start):
            if not self.visible_rows[row_idx]:
                continue  # Skip hidden rows
            vals, dtypes = [], []
            for val, col, dtype in zip(row, self.df.columns, self.df.dtypes):
                if col in self.hidden_columns:
                    continue  # Skip hidden columns
                vals.append(val)
                dtypes.append(dtype)
            formatted_row = format_row(vals, dtypes, thousand_separator=self.thousand_separator)
            # Always add labels so they can be shown/hidden via CSS
            self.add_row(*formatted_row, key=str(row_idx), label=str(row_idx + 1))

        # Update loaded rows count
        self.loaded_rows = stop

        # self.notify(f"Loaded [$accent]{stop}/{len(self.df)}[/] rows from [$success]{self.name}[/]", title="Load")

    def _check_and_load_more(self) -> None:
        """Check if we need to load more rows and load them."""
        # If we've loaded everything, no need to check
        if self.loaded_rows >= len(self.df):
            return

        visible_row_count = self.size.height - self.header_height
        bottom_visible_row = self.scroll_y + visible_row_count

        # If visible area is close to the end of loaded rows, load more
        if bottom_visible_row >= self.loaded_rows - 10:
            self._load_rows(self.loaded_rows + self.BATCH_SIZE)

    def _do_highlight(self, clear: bool = False) -> None:
        """Update all rows, highlighting selected ones and restoring others to default.

        Args:
            clear: If True, clear all highlights.
        """
        if clear:
            self.selected_rows = [False] * len(self.df)
            self.matches = defaultdict(set)

        # Ensure all selected rows or matches are loaded
        stop = rindex(self.selected_rows, True) + 1
        stop = max(stop, max(self.matches.keys(), default=0) + 1)

        self._load_rows(stop)
        self._highlight_table()

    def _highlight_table(self) -> None:
        """Highlight selected rows/cells in red."""
        # Update all rows based on selected state
        for row in self.ordered_rows:
            row_idx = int(row.key.value)  # 0-based index
            is_selected = self.selected_rows[row_idx]
            match_cols = self.matches.get(row_idx, set())

            # Update all cells in this row
            for col_idx, col in enumerate(self.ordered_columns):
                cell_text: Text = self.get_cell(row.key, col.key)

                # Get style config based on dtype
                dtype = self.df.dtypes[col_idx]
                dc = DtypeConfig(dtype)
                cell_text.style = "red" if is_selected or col_idx in match_cols else dc.style

                # Update the cell in the table
                self.update_cell(row.key, col.key, cell_text)

    # History & Undo
    def _add_history(self, description: str) -> None:
        """Add the current state to the history stack.

        Args:
            description: Description of the action for this history entry.
        """
        history = History(
            description=description,
            df=self.df,
            filename=self.filename,
            loaded_rows=self.loaded_rows,
            sorted_columns=self.sorted_columns.copy(),
            hidden_columns=self.hidden_columns.copy(),
            selected_rows=self.selected_rows.copy(),
            visible_rows=self.visible_rows.copy(),
            fixed_rows=self.fixed_rows,
            fixed_columns=self.fixed_columns,
            cursor_coordinate=self.cursor_coordinate,
            matches={k: v.copy() for k, v in self.matches.items()},
        )
        self.histories.append(history)

    def _undo(self) -> None:
        """Undo the last action."""
        if not self.histories:
            self.notify("No actions to undo", title="Undo", severity="warning")
            return

        history = self.histories.pop()

        # Restore state
        self.df = history.df
        self.filename = history.filename
        self.loaded_rows = history.loaded_rows
        self.sorted_columns = history.sorted_columns.copy()
        self.hidden_columns = history.hidden_columns.copy()
        self.selected_rows = history.selected_rows.copy()
        self.visible_rows = history.visible_rows.copy()
        self.fixed_rows = history.fixed_rows
        self.fixed_columns = history.fixed_columns
        self.cursor_coordinate = history.cursor_coordinate
        self.matches = {k: v.copy() for k, v in history.matches.items()}

        # Recreate the table for display
        self._setup_table()

        # self.notify(f"Reverted: {history.description}", title="Undo")

    # View
    def _view_row_detail(self) -> None:
        """Open a modal screen to view the selected row's details."""
        ridx = self.cursor_row_idx

        # Push the modal screen
        self.app.push_screen(RowDetailScreen(ridx, self))

    def _show_frequency(self) -> None:
        """Show frequency distribution for the current column."""
        cidx = self.cursor_col_idx

        # Push the frequency modal screen
        self.app.push_screen(FrequencyScreen(cidx, self))

    def _show_statistics(self, scope: str = "column") -> None:
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

    def _freeze_row_column(self) -> None:
        """Open the freeze screen to set fixed rows and columns."""
        self.app.push_screen(FreezeScreen(), callback=self._do_freeze)

    def _do_freeze(self, result: tuple[int, int] | None) -> None:
        """Handle result from PinScreen.

        Args:
            result: Tuple of (fixed_rows, fixed_columns) or None if cancelled.
        """
        if result is None:
            return

        fixed_rows, fixed_columns = result

        # Add to history
        self._add_history(f"Pinned [$accent]{fixed_rows}[/] rows and [$success]{fixed_columns}[/] columns")

        # Apply the pin settings to the table
        if fixed_rows > 0:
            self.fixed_rows = fixed_rows
        if fixed_columns > 0:
            self.fixed_columns = fixed_columns

        self.notify(
            f"Pinned [$accent]{fixed_rows}[/] rows and [$success]{fixed_columns}[/] columns",
            title="Pin",
        )

    # Delete & Move
    def _delete_column(self) -> None:
        """Remove the currently selected column from the table."""
        # Get the column to remove
        col_idx = self.cursor_column
        col_name = self.cursor_col_name
        col_key = self.cursor_col_key

        # Add to history
        self._add_history(f"Removed column [$success]{col_name}[/]")

        # Remove the column from the table display using the column name as key
        self.remove_column(col_key)

        # Move cursor left if we deleted the last column
        if col_idx >= len(self.columns):
            self.move_cursor(column=len(self.columns) - 1)

        # Remove from sorted columns if present
        if col_name in self.sorted_columns:
            del self.sorted_columns[col_name]

        # Remove from matches
        for row_idx in list(self.matches.keys()):
            self.matches[row_idx].discard(col_idx)
            # Remove empty entries
            if not self.matches[row_idx]:
                del self.matches[row_idx]

        # Remove from dataframe
        self.df = self.df.drop(col_name)

        self.notify(f"Removed column [$success]{col_name}[/]", title="Delete")

    def _hide_column(self) -> None:
        """Hide the currently selected column from the table display."""
        col_key = self.cursor_col_key
        col_name = col_key.value
        col_idx = self.cursor_column

        # Add to history
        self._add_history(f"Hid column [$success]{col_name}[/]")

        # Remove the column from the table display (but keep in dataframe)
        self.remove_column(col_key)

        # Track hidden columns
        self.hidden_columns.add(col_name)

        # Move cursor left if we hid the last column
        if col_idx >= len(self.columns):
            self.move_cursor(column=len(self.columns) - 1)

        # self.notify(f"Hid column [$accent]{col_name}[/]. Press [$success]H[/] to show hidden columns", title="Hide")

    def _show_column(self) -> None:
        """Show all hidden columns by recreating the table with all dataframe columns."""
        # Get currently visible columns
        visible_cols = set(col.key for col in self.ordered_columns)

        # Find hidden columns (in dataframe but not in table)
        hidden_cols = [col for col in self.df.columns if col not in visible_cols]

        if not hidden_cols:
            self.notify("No hidden columns to show", title="Column", severity="warning")
            return

        # Add to history
        self._add_history(f"Showed {len(hidden_cols)} hidden column(s)")

        # Clear hidden columns tracking
        self.hidden_columns.clear()

        # Recreate table with all columns
        self._setup_table()

        self.notify(f"Showed [$accent]{len(hidden_cols)}[/] hidden column(s)", title="Column")

    def _duplicate_column(self) -> None:
        """Duplicate the currently selected column, inserting it right after the current column."""
        cidx = self.cursor_col_idx
        col_name = self.cursor_col_name

        col_idx = self.cursor_column
        new_col_name = f"{col_name}_copy"

        # Add to history
        self._add_history(f"Duplicated column [$success]{col_name}[/]")

        # Create new column and reorder columns to insert after current column
        cols_before = self.df.columns[: cidx + 1]
        cols_after = self.df.columns[cidx + 1 :]

        # Add the new column and reorder columns for insertion after current column
        self.df = self.df.with_columns(pl.col(col_name).alias(new_col_name)).select(
            list(cols_before) + [new_col_name] + list(cols_after)
        )

        # Recreate the table for display
        self._setup_table()

        # Move cursor to the new duplicated column
        self.move_cursor(column=col_idx + 1)

        self.notify(
            f"Duplicated column [$accent]{col_name}[/] as [$success]{new_col_name}[/]",
            title="Duplicate",
        )

    def _delete_row(self) -> None:
        """Delete rows from the table and dataframe.

        Supports deleting multiple selected rows. If no rows are selected, deletes the row at the cursor.
        """
        old_count = len(self.df)
        predicates = [True] * len(self.df)

        # Delete all selected rows
        if selected_count := self.selected_rows.count(True):
            history_desc = f"Deleted {selected_count} selected row(s)"

            for ridx, selected in enumerate(self.selected_rows):
                if selected:
                    predicates[ridx] = False

        # Delete the row at the cursor
        else:
            ridx = self.cursor_row_idx
            history_desc = f"Deleted row [$success]{ridx + 1}[/]"
            predicates[ridx] = False

        # Add to history
        self._add_history(history_desc)

        # Apply the filter to remove rows
        try:
            df = self.df.with_row_index(RIDX).filter(predicates)
        except Exception as e:
            self.notify(f"Error deleting row(s): {e}", title="Delete", severity="error")
            self.histories.pop()  # Remove last history entry
            return

        self.df = df.drop(RIDX)

        # Update selected and visible rows tracking
        old_row_indices = set(df[RIDX].to_list())
        self.selected_rows = [selected for i, selected in enumerate(self.selected_rows) if i in old_row_indices]
        self.visible_rows = [visible for i, visible in enumerate(self.visible_rows) if i in old_row_indices]

        # Clear all matches since row indices have changed
        self.matches = defaultdict(set)

        # Recreate the table display
        self._setup_table()

        deleted_count = old_count - len(self.df)
        if deleted_count > 1:
            self.notify(f"Deleted {deleted_count} row(s)", title="Delete")

    def _duplicate_row(self) -> None:
        """Duplicate the currently selected row, inserting it right after the current row."""
        ridx = self.cursor_row_idx

        # Get the row to duplicate
        row_to_duplicate = self.df.slice(ridx, 1)

        # Add to history
        self._add_history(f"Duplicated row [$success]{ridx + 1}[/]")

        # Concatenate: rows before + duplicated row + rows after
        df_before = self.df.slice(0, ridx + 1)
        df_after = self.df.slice(ridx + 1)

        # Combine the parts
        self.df = pl.concat([df_before, row_to_duplicate, df_after])

        # Update selected and visible rows tracking to account for new row
        new_selected_rows = self.selected_rows[: ridx + 1] + [self.selected_rows[ridx]] + self.selected_rows[ridx + 1 :]
        new_visible_rows = self.visible_rows[: ridx + 1] + [self.visible_rows[ridx]] + self.visible_rows[ridx + 1 :]
        self.selected_rows = new_selected_rows
        self.visible_rows = new_visible_rows

        # Clear all matches since row indices have changed
        self.matches = defaultdict(set)

        # Recreate the table display
        self._setup_table()

        # Move cursor to the new duplicated row
        self.move_cursor(row=ridx + 1)

        # self.notify(f"Duplicated row [$success]{ridx + 1}[/]", title="Row")

    def _move_column(self, direction: str) -> None:
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
        self._add_history(f"Moved column [$success]{col_name}[/] {direction} (swapped with [$success]{swap_name}[/])")

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

        # self.notify(f"Moved column [$success]{col_name}[/] {direction}", title="Move")

    def _move_row(self, direction: str) -> None:
        """Move the current row up or down.

        Args:
            direction: "up" to move up, "down" to move down.
        """
        row_idx, col_idx = self.cursor_coordinate

        # Validate move is possible
        if direction == "up":
            if row_idx <= 0:
                self.notify("Cannot move row up", title="Move", severity="warning")
                return
            swap_idx = row_idx - 1
        elif direction == "down":
            if row_idx >= len(self.rows) - 1:
                self.notify("Cannot move row down", title="Move", severity="warning")
                return
            swap_idx = row_idx + 1
        else:
            self.notify(f"Invalid direction: {direction}", title="Move", severity="error")
            return

        row_key = self.coordinate_to_cell_key((row_idx, 0)).row_key
        swap_key = self.coordinate_to_cell_key((swap_idx, 0)).row_key

        # Add to history
        self._add_history(
            f"Moved row [$success]{row_key.value}[/] {direction} (swapped with row [$success]{swap_key.value}[/])"
        )

        # Swap rows in the table's internal row locations
        self.check_idle()

        (
            self._row_locations[row_key],
            self._row_locations[swap_key],
        ) = (
            self._row_locations.get(swap_key),
            self._row_locations.get(row_key),
        )

        self._update_count += 1
        self.refresh()

        # Restore cursor position on the moved row
        self.move_cursor(row=swap_idx, column=col_idx)

        # Swap rows in the dataframe
        ridx = int(row_key.value)  # 0-based
        swap_ridx = int(swap_key.value)  # 0-based
        first, second = sorted([ridx, swap_ridx])

        self.df = pl.concat(
            [
                self.df.slice(0, first),
                self.df.slice(second, 1),
                self.df.slice(first + 1, second - first - 1),
                self.df.slice(first, 1),
                self.df.slice(second + 1),
            ]
        )

        # self.notify(f"Moved row [$success]{row_key.value}[/] {direction}", title="Move")

    # Sort
    def _sort_by_column(self, descending: bool = False) -> None:
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
        self._add_history(f"Sorted on column [$success]{col_name}[/]")
        if old_desc is None:
            # Add new column to sort
            self.sorted_columns[col_name] = descending
        elif old_desc == descending:
            # Same direction - remove from sort
            del self.sorted_columns[col_name]
        else:
            # Move to end of sort order
            del self.sorted_columns[col_name]
            self.sorted_columns[col_name] = descending

        # Apply multi-column sort
        if sort_cols := list(self.sorted_columns.keys()):
            descending_flags = list(self.sorted_columns.values())
            df_sorted = self.df.with_row_index(RIDX).sort(sort_cols, descending=descending_flags, nulls_last=True)
        else:
            # No sort columns - restore original order
            df_sorted = self.df.with_row_index(RIDX)

        # Updated selected_rows and visible_rows to match new order
        old_row_indices = df_sorted[RIDX].to_list()
        self.selected_rows = [self.selected_rows[i] for i in old_row_indices]
        self.visible_rows = [self.visible_rows[i] for i in old_row_indices]

        # Update the dataframe
        self.df = df_sorted.drop(RIDX)

        # Recreate the table for display
        self._setup_table()

        # Restore cursor position on the sorted column
        self.move_cursor(column=col_idx, row=0)

    # Edit
    def _edit_cell(self, ridx: int = None, cidx: int = None) -> None:
        """Open modal to edit the selected cell."""
        ridx = self.cursor_row_idx if ridx is None else ridx
        cidx = self.cursor_col_idx if cidx is None else cidx
        col_name = self.df.columns[cidx]

        # Save current state to history
        self._add_history(f"Edited cell [$success]({ridx + 1}, {col_name})[/]")

        # Push the edit modal screen
        self.app.push_screen(
            EditCellScreen(ridx, cidx, self.df),
            callback=self._do_edit_cell,
        )

    def _do_edit_cell(self, result) -> None:
        """Handle result from EditCellScreen."""
        if result is None:
            return

        ridx, cidx, new_value = result
        if new_value is None:
            self.app.push_screen(
                EditCellScreen(ridx, cidx, self.df),
                callback=self._do_edit_cell,
            )
            return

        col_name = self.df.columns[cidx]

        # Update the cell in the dataframe
        try:
            self.df = self.df.with_columns(
                pl.when(pl.arange(0, len(self.df)) == ridx)
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

            self.notify(f"Cell updated to [$success]{cell_value}[/]", title="Edit")
        except Exception as e:
            self.notify(f"Failed to update cell: {str(e)}", title="Edit", severity="error")

    def _edit_column(self) -> None:
        """Open modal to edit the entire column with an expression."""
        cidx = self.cursor_col_idx

        # Push the edit column modal screen
        self.app.push_screen(
            EditColumnScreen(cidx, self.df),
            callback=self._do_edit_column,
        )

    def _do_edit_column(self, result) -> None:
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
                expr = validate_expr(term, self.df, cidx)
            except Exception as e:
                self.notify(f"Error validating expression [$error]{term}[/]: {str(e)}", title="Edit", severity="error")
                return

        # Otherwise, treat term as a literal value
        else:
            dtype = self.df.dtypes[cidx]
            try:
                value = DtypeConfig(dtype).convert(term)
                expr = pl.lit(value)
            except Exception:
                self.notify(
                    f"Unable to convert [$accent]{term}[/] to [$error]{dtype}[/]. Cast to string.",
                    title="Edit",
                    severity="error",
                )
                expr = pl.lit(str(term))

        # Add to history
        self._add_history(f"Edited column [$accent]{col_name}[/] with expression")

        try:
            # Apply the expression to the column
            self.df = self.df.with_columns(expr.alias(col_name))
        except Exception as e:
            self.notify(f"Failed to apply expression: [$error]{str(e)}[/]", title="Edit", severity="error")
            return

        # Recreate the table for display
        self._setup_table()

        self.notify(
            f"Column [$accent]{col_name}[/] updated with [$success]{expr}[/]",
            title="Edit",
        )

    def _rename_column(self) -> None:
        """Open modal to rename the selected column."""
        col_name = self.cursor_col_name
        col_idx = self.cursor_column

        # Push the rename column modal screen
        self.app.push_screen(
            RenameColumnScreen(col_idx, col_name, self.df.columns),
            callback=self._do_rename_column,
        )

    def _do_rename_column(self, result) -> None:
        """Handle result from RenameColumnScreen."""
        if result is None:
            return

        col_idx, col_name, new_name = result
        if new_name is None:
            self.app.push_screen(
                RenameColumnScreen(col_idx, col_name, self.df.columns),
                callback=self._do_rename_column,
            )
            return

        # Add to history
        self._add_history(f"Renamed column [$accent]{col_name}[/] to [$success]{new_name}[/]")

        # Rename the column in the dataframe
        self.df = self.df.rename({col_name: new_name})

        # Update sorted_columns if this column was sorted
        if col_name in self.sorted_columns:
            self.sorted_columns[new_name] = self.sorted_columns.pop(col_name)

        # Update hidden_columns if this column was hidden
        if col_name in self.hidden_columns:
            self.hidden_columns.remove(col_name)
            self.hidden_columns.add(new_name)

        # Recreate the table for display
        self._setup_table()

        # Move cursor to the renamed column
        self.move_cursor(column=col_idx)

        self.notify(
            f"Renamed column [$success]{col_name}[/] to [$success]{new_name}[/]",
            title="Column",
        )

    def _clear_cell(self) -> None:
        """Clear the current cell by setting its value to None."""
        row_key, col_key = self.cursor_key
        ridx = self.cursor_row_idx
        cidx = self.cursor_col_idx
        col_name = self.cursor_col_name

        # Add to history
        self._add_history(f"Cleared cell [$success]({ridx + 1}, {col_name})[/]")

        # Update the cell to None in the dataframe
        try:
            self.df = self.df.with_columns(
                pl.when(pl.arange(0, len(self.df)) == ridx)
                .then(pl.lit(None))
                .otherwise(pl.col(col_name))
                .alias(col_name)
            )

            # Update the display
            dtype = self.df.dtypes[cidx]
            dc = DtypeConfig(dtype)
            formatted_value = Text(NULL_DISPLAY, style=dc.style, justify=dc.justify)

            self.update_cell(row_key, col_key, formatted_value)

            self.notify(f"Cell cleared to [$success]{NULL_DISPLAY}[/]", title="Clear")
        except Exception as e:
            self.notify(f"Failed to clear cell: {str(e)}", title="Clear", severity="error")
            raise e

    def _add_column(self, col_name: str = None, col_value: pl.Expr = None) -> None:
        """Add acolumn after the current column."""
        cidx = self.cursor_col_idx

        if not col_name:
            # Generate a unique column name
            base_name = "new_col"
            new_name = base_name
            counter = 1
            while new_name in self.df.columns:
                new_name = f"{base_name}_{counter}"
                counter += 1
        else:
            new_name = col_name

        # Add to history
        self._add_history(f"Added column [$success]{new_name}[/] after column {cidx + 1}")

        try:
            # Create an empty column (all None values)
            if isinstance(col_value, pl.Expr):
                new_col = col_value.alias(new_name)
            else:
                new_col = pl.lit(col_value).alias(new_name)

            # Get columns up to current, the new column, then remaining columns
            cols = self.df.columns
            cols_before = cols[: cidx + 1]
            cols_after = cols[cidx + 1 :]

            # Build the new dataframe with columns reordered
            select_cols = cols_before + [new_name] + cols_after
            self.df = self.df.with_columns(new_col).select(select_cols)

            # Recreate the table display
            self._setup_table()

            # Move cursor to the new column
            self.move_cursor(column=cidx + 1)

            self.notify(f"Added column [$success]{new_name}[/]", title="Add Column")
        except Exception as e:
            self.notify(f"Failed to add column: {str(e)}", title="Add Column", severity="error")
            raise e

    def _add_column_expr(self) -> None:
        """Open screen to add a new column with optional expression."""
        cidx = self.cursor_col_idx
        self.app.push_screen(
            AddColumnScreen(cidx, self.df),
            self._do_add_column_expr,
        )

    def _do_add_column_expr(self, result: tuple[int, str, str, pl.Expr] | None) -> None:
        """Add a new column with an expression."""
        if result is None:
            return

        cidx, col_name, expr = result

        # Add to history
        self._add_history(f"Added column [$success]{col_name}[/] with expression {expr}.")

        try:
            # Create the column
            new_col = expr.alias(col_name)

            # Get columns up to current, the new column, then remaining columns
            cols = self.df.columns
            cols_before = cols[: cidx + 1]
            cols_after = cols[cidx + 1 :]

            # Build the new dataframe with columns reordered
            select_cols = cols_before + [col_name] + cols_after
            self.df = self.df.with_row_index(RIDX).with_columns(new_col).select(select_cols)

            # Recreate the table display
            self._setup_table()

            # Move cursor to the new column
            self.move_cursor(column=cidx + 1)

            # self.notify(f"Added column [$success]{col_name}[/]", title="Add Column")
        except Exception as e:
            self.notify(f"Failed to add column: [$error]{str(e)}[/]", title="Add Column", severity="error")
            raise e

    def _string_to_polars_dtype(self, dtype_str: str) -> pl.DataType:
        """Convert string type name to Polars DataType.

        Args:
            dtype_str: String representation of the type ("string", "int", "float", "bool")

        Returns:
            Corresponding Polars DataType

        Raises:
            ValueError: If the type string is not recognized
        """
        dtype_map = {
            "string": pl.String,
            "int": pl.Int64,
            "float": pl.Float64,
            "bool": pl.Boolean,
        }

        dtype_lower = dtype_str.lower().strip()
        return dtype_map.get(dtype_lower)

    def _cast_column_dtype(self, dtype: str | pl.DataType = pl.String) -> None:
        """Cast the current column to a different data type.

        Args:
            dtype: Target data type (string like "int", "float", "bool", "string" or Polars DataType)
        """
        cidx = self.cursor_col_idx
        col_name = self.cursor_col_name
        current_dtype = self.df.dtypes[cidx]

        # Convert string dtype to Polars DataType if needed
        if isinstance(dtype, str):
            target_dtype = self._string_to_polars_dtype(dtype)
            if target_dtype is None:
                self.notify(
                    f"Use string for unknown data type: {dtype}. Supported types: {', '.join(self._string_to_polars_dtype.keys())}",
                    title="Cast",
                    severity="warning",
                )
                target_dtype = pl.String
        else:
            target_dtype = dtype

        # Add to history
        self._add_history(
            f"Cast column [$accent]{col_name}[/] from [$success]{current_dtype}[/] to [$success]{target_dtype}[/]"
        )

        try:
            # Cast the column using Polars
            self.df = self.df.with_columns(pl.col(col_name).cast(target_dtype))

            # Recreate the table display
            self._setup_table()

            self.notify(
                f"Cast column [$accent]{col_name}[/] to [$success]{target_dtype}[/]",
                title="Cast",
            )
        except Exception as e:
            self.notify(f"Failed to cast column: {str(e)}", title="Cast", severity="error")
            raise e

    def _search_cursor_value(self) -> None:
        """Search with cursor value in current column."""
        cidx = self.cursor_col_idx

        # Get the value of the currently selected cell
        term = NULL if self.cursor_value is None else str(self.cursor_value)

        self._do_search((term, cidx, False, False))

    def _search_expr(self) -> None:
        """Search by expression."""
        cidx = self.cursor_col_idx

        # Use current cell value as default search term
        term = NULL if self.cursor_value is None else str(self.cursor_value)

        # Push the search modal screen
        self.app.push_screen(
            SearchScreen("Search", term, self.df, cidx),
            callback=self._do_search,
        )

    def _do_search(self, result) -> None:
        """Search for a term."""
        if result is None:
            return
        term, cidx, match_nocase, match_whole = result
        col_name = self.df.columns[cidx]

        if term == NULL:
            expr = pl.col(col_name).is_null()

        # Support for polars expressions
        elif tentative_expr(term):
            try:
                expr = validate_expr(term, self.df, cidx)
            except Exception as e:
                self.notify(
                    f"Failed to validate Polars expression [$error]{term}[/]: {str(e)}",
                    title="Search",
                    severity="error",
                )
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
                        f"Unable to convert [$accent]{term}[/] to [$error]{dtype}[/]. Cast to string.",
                        title="Search",
                        severity="warning",
                    )

        # Lazyframe for filtering
        lf = self.df.lazy().with_row_index(RIDX)
        if False in self.visible_rows:
            lf = lf.filter(self.visible_rows)

        # Apply filter to get matched row indices
        try:
            matches = set(lf.filter(expr).select(RIDX).collect().to_series().to_list())
        except Exception as e:
            self.notify(
                f"Error applying search filter: [$error]{str(e)}[/]",
                title="Search",
                severity="error",
            )
            return

        match_count = len(matches)
        if match_count == 0:
            self.notify(
                f"No matches found for [$warning]{term}[/]. Try [$accent](?i)abc[/] for case-insensitive search.",
                title="Search",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(f"Searched [$accent]{term}[/] in column [$success]{col_name}[/]")

        # Update selected rows to include new matches
        for m in matches:
            self.selected_rows[m] = True

        # Highlight matches
        self._do_highlight()

        self.notify(f"Found [$accent]{match_count}[/] matches for [$success]{term}[/]", title="Search")

    def _find_matches(
        self, term: str, cidx: int | None = None, match_nocase: bool = False, match_whole: bool = False
    ) -> dict[int, set[int]]:
        """Find matches for a term in the dataframe.

        Args:
            term: The search term (can be NULL, expression, or plain text)
            cidx: Column index for column-specific search. If None, searches all columns.

        Returns:
            Dictionary mapping row indices to sets of column indices containing matches.
            For column-specific search, each matched row has a set with single cidx.
            For global search, each matched row has a set of all matching cidxs in that row.

        Raises:
            Exception: If expression validation or filtering fails.
        """
        matches: dict[int, set[int]] = defaultdict(set)

        # Lazyframe for filtering
        lf = self.df.lazy().with_row_index(RIDX)
        if False in self.visible_rows:
            lf = lf.filter(self.visible_rows)

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
                    expr = validate_expr(term, self.df, col_idx)
                except Exception as e:
                    raise Exception(f"Error validating Polars expression: {str(e)}")
            else:
                if match_whole:
                    term = f"^{term}$"
                if match_nocase:
                    term = f"(?i){term}"
                expr = pl.col(col_name).cast(pl.String).str.contains(term)

            # Get matched row indices
            try:
                matched_ridxs = lf.filter(expr).select(RIDX).collect().to_series().to_list()
            except Exception as e:
                raise Exception(f"Error applying filter: {str(e)}")

            for ridx in matched_ridxs:
                matches[ridx].add(col_idx)

        return matches

    def _find_cursor_value(self, scope="column") -> None:
        """Find by cursor value.

        Args:
            scope: "column" to find in current column, "global" to find across all columns.
        """
        # Get the value of the currently selected cell
        term = NULL if self.cursor_value is None else str(self.cursor_value)

        if scope == "column":
            cidx = self.cursor_col_idx
            self._do_find((term, cidx, False, False))
        else:
            self._do_find_global((term, None, False, False))

    def _find_expr(self, scope="column") -> None:
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
            callback=self._do_find if scope == "column" else self._do_find_global,
        )

    def _do_find(self, result) -> None:
        """Find a term in current column."""
        if result is None:
            return
        term, cidx, match_nocase, match_whole = result

        col_name = self.df.columns[cidx]

        try:
            matches = self._find_matches(term, cidx, match_nocase, match_whole)
        except Exception as e:
            self.notify(
                f"Error finding matches: [$error]{str(e)}[/]",
                title="Find",
                severity="error",
            )
            return

        if not matches:
            self.notify(
                f"No matches found for [$warning]{term}[/] in current column. Try [$accent](?i)abc[/] for case-insensitive search.",
                title="Find",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(f"Found [$accent]{term}[/] in column [$success]{col_name}[/]")

        # Add to matches and count total
        match_count = sum(len(col_idxs) for col_idxs in matches.values())
        for ridx, col_idxs in matches.items():
            self.matches[ridx].update(col_idxs)

        # Highlight matches
        self._do_highlight()

        self.notify(f"Found [$accent]{match_count}[/] matches for [$success]{term}[/]", title="Find")

    def _do_find_global(self, result) -> None:
        """Global find a term across all columns."""
        if result is None:
            return
        term, cidx, match_nocase, match_whole = result

        try:
            matches = self._find_matches(term, cidx=None, match_nocase=match_nocase, match_whole=match_whole)
        except Exception as e:
            self.notify(
                f"Error finding matches: [$error]{str(e)}[/]",
                title="Find",
                severity="error",
            )
            return

        if not matches:
            self.notify(
                f"No matches found for [$warning]{term}[/] in any column. Try [$accent](?i)abc[/] for case-insensitive search.",
                title="Global Find",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(f"Found [$success]{term}[/] across all columns")

        # Add to matches and count total
        match_count = sum(len(col_idxs) for col_idxs in matches.values())
        for ridx, col_idxs in matches.items():
            self.matches[ridx].update(col_idxs)

        # Highlight matches
        self._do_highlight()

        self.notify(
            f"Found [$accent]{match_count}[/] matches for [$success]{term}[/] across all columns",
            title="Global Find",
        )

    def _move_cursor(self, ridx: int, cidx: int) -> None:
        """Move cursor based on the dataframe indices.

        Args:
            ridx: Row index (0-based) in the dataframe.
            cidx: Column index (0-based) in the dataframe.
        """
        row_key = str(ridx)
        col_key = self.df.columns[cidx]
        row_idx, col_idx = self.get_cell_coordinate(row_key, col_key)
        self.move_cursor(row=row_idx, column=col_idx)

    def _next_match(self) -> None:
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
                self._move_cursor(ridx, cidx)
                return

        # If no next match, wrap around to the first match
        first_ridx, first_cidx = ordered_matches[0]
        self._move_cursor(first_ridx, first_cidx)

    def _previous_match(self) -> None:
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

    def _next_selected_row(self) -> None:
        """Move cursor to the next selected row."""
        if not any(self.selected_rows):
            self.notify("No selected rows to navigate", title="Next Selected Row", severity="warning")
            return

        # Get list of selected row indices in order
        selected_row_indices = self.ordered_selected_rows

        # Current cursor row
        current_ridx = self.cursor_row_idx

        # Find the next selected row after current position
        for ridx in selected_row_indices:
            if ridx > current_ridx:
                self._move_cursor(ridx, self.cursor_col_idx)
                return

        # If no next selected row, wrap around to the first selected row
        first_ridx = selected_row_indices[0]
        self._move_cursor(first_ridx, self.cursor_col_idx)

    def _previous_selected_row(self) -> None:
        """Move cursor to the previous selected row."""
        if not any(self.selected_rows):
            self.notify("No selected rows to navigate", title="Previous Selected Row", severity="warning")
            return

        # Get list of selected row indices in order
        selected_row_indices = self.ordered_selected_rows

        # Current cursor row
        current_ridx = self.cursor_row_idx

        # Find the previous selected row before current position
        for ridx in reversed(selected_row_indices):
            if ridx < current_ridx:
                self._move_cursor(ridx, self.cursor_col_idx)
                return

        # If no previous selected row, wrap around to the last selected row
        last_ridx = selected_row_indices[-1]
        self._move_cursor(last_ridx, self.cursor_col_idx)

    def _replace(self) -> None:
        """Open replace screen for current column."""
        # Push the replace modal screen
        self.app.push_screen(
            FindReplaceScreen(self),
            callback=self._do_replace,
        )

    def _do_replace(self, result) -> None:
        """Handle replace in current column."""
        self._handle_replace(result, self.cursor_col_idx)

    def _replace_global(self) -> None:
        """Open replace screen for all columns."""
        # Push the replace modal screen
        self.app.push_screen(
            FindReplaceScreen(self),
            callback=self._do_replace_global,
        )

    def _do_replace_global(self, result) -> None:
        """Handle replace across all columns."""
        self._handle_replace(result, None)

    def _handle_replace(self, result, cidx) -> None:
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
        matches = self._find_matches(term_find, cidx, match_nocase, match_whole)

        if not matches:
            self.notify(
                f"No matches found for [$warning]{term_find}[/]",
                title="Replace",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(
            f"Replacing [$accent]{term_find}[/] with [$success]{term_replace}[/] in column [$accent]{col_name}[/]"
        )

        # Update matches
        self.matches = {ridx: set(col_idxs) for ridx, col_idxs in matches.items()}

        # Highlight matches
        self._do_highlight()

        # Store state for interactive replacement using dataclass
        self._replace_state = ReplaceState(
            term_find=term_find,
            term_replace=term_replace,
            match_nocase=match_nocase,
            match_whole=match_whole,
            cidx=cidx,
            rows=sorted(list(self.matches.keys())),
            cols_per_row=[sorted(list(self.matches[ridx])) for ridx in sorted(self.matches.keys())],
            current_rpos=0,
            current_cpos=0,
            current_occurrence=0,
            total_occurrence=len(self.matches),
            replaced_occurrence=0,
            skipped_occurrence=0,
            done=False,
        )

        try:
            if replace_all:
                # Replace all occurrences
                self._do_replace_all(term_find, term_replace)
            else:
                # Replace with confirmation for each occurrence
                self._do_replace_interactive(term_find, term_replace)

        except Exception as e:
            self.notify(
                f"Error replacing [$accent]{term_find}[/] with [$error]{term_replace}[/]: {str(e)}",
                title="Replace",
                severity="error",
            )

    def _do_replace_all(self, term_find: str, term_replace: str) -> None:
        """Replace all occurrences."""
        state = self._replace_state
        self.app.push_screen(
            ConfirmScreen(
                "Replace All",
                label=f"Replace [$accent]{term_find}[/] with [$success]{term_replace}[/] for all [$accent]{state.total_occurrence}[/] occurrences?",
            ),
            callback=self._handle_replace_all_confirmation,
        )

    def _handle_replace_all_confirmation(self, result) -> None:
        """Handle user's confirmation for replace all."""
        if result is None:
            return

        state = self._replace_state
        rows = state.rows
        cols_per_row = state.cols_per_row

        # Replace in each matched row/column
        for ridx, col_idxs in zip(rows, cols_per_row):
            for cidx in col_idxs:
                col_name = self.df.columns[cidx]
                dtype = self.df.dtypes[cidx]

                # Only applicable to string columns for substring matches
                if dtype == pl.String and not state.match_whole:
                    term_find = f"(?i){state.term_find}" if state.match_nocase else state.term_find
                    self.df = self.df.with_columns(
                        pl.when(pl.arange(0, len(self.df)) == ridx)
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

                state.replaced_occurrence += 1

        # Recreate the table display
        self._setup_table()

        col_name = "all columns" if state.cidx is None else self.df.columns[state.cidx]
        self.notify(
            f"Replaced [$accent]{state.replaced_occurrence}[/] of [$accent]{state.total_occurrence}[/] in [$success]{col_name}[/]",
            title="Replace",
        )

    def _do_replace_interactive(self, term_find: str, term_replace: str) -> None:
        """Replace with user confirmation for each occurrence."""
        try:
            # Start with first match
            self._show_next_replace_confirmation()
        except Exception as e:
            self.notify(
                f"Error replacing [$accent]{term_find}[/] with [$error]{term_replace}[/]: {str(e)}",
                title="Replace",
                severity="error",
            )

    def _show_next_replace_confirmation(self) -> None:
        """Show confirmation for next replacement."""
        state = self._replace_state
        if state.done:
            # All done - show final notification
            col_name = "all columns" if state.cidx is None else self.df.columns[state.cidx]
            msg = f"Replaced [$accent]{state.replaced_occurrence}[/] of [$accent]{state.total_occurrence}[/] in [$success]{col_name}[/]"
            if state.skipped_occurrence > 0:
                msg += f", [$warning]{state.skipped_occurrence}[/] skipped"
            self.notify(msg, title="Replace")
            return

        # Move cursor to next match
        ridx = state.rows[state.current_rpos]
        cidx = state.cols_per_row[state.current_rpos][state.current_cpos]
        self.move_cursor(row=ridx, column=cidx)

        state.current_occurrence += 1

        # Show confirmation
        label = f"Replace [$warning]{state.term_find}[/] with [$success]{state.term_replace}[/] (Occurrence {state.current_occurrence} of {state.total_occurrence})?"

        self.app.push_screen(
            ConfirmScreen("Replace", label=label, maybe="Skip"),
            callback=self._handle_replace_confirmation,
        )

    def _handle_replace_confirmation(self, result) -> None:
        """Handle user's confirmation response."""
        state = self._replace_state
        if state.done:
            return

        ridx = state.rows[state.current_rpos]
        cidx = state.cols_per_row[state.current_rpos][state.current_cpos]
        col_name = self.df.columns[cidx]
        dtype = self.df.dtypes[cidx]

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

            state.replaced_occurrence += 1

        # Skip
        elif result is False:
            state.skipped_occurrence += 1

        # Cancel
        else:
            state.done = True
            self._setup_table()
            return

        # Move to next
        if state.current_cpos + 1 < len(state.cols_per_row[state.current_rpos]):
            state.current_cpos += 1
        else:
            state.current_cpos = 0
            state.current_rpos += 1

        if state.current_rpos >= len(state.rows):
            state.done = True

        # Recreate the table display
        self._setup_table()

        # Show next confirmation
        self._show_next_replace_confirmation()

    def _toggle_selections(self) -> None:
        """Toggle selected rows highlighting on/off."""
        # Save current state to history
        self._add_history("Toggled row selection")

        if False in self.visible_rows:
            # Some rows are hidden - invert only selected visible rows and clear selections for hidden rows
            for i in range(len(self.selected_rows)):
                if self.visible_rows[i]:
                    self.selected_rows[i] = not self.selected_rows[i]
                else:
                    self.selected_rows[i] = False
        else:
            # Invert all selected rows
            self.selected_rows = [not selected for selected in self.selected_rows]

        # Check if we're highlighting or un-highlighting
        if new_selected_count := self.selected_rows.count(True):
            self.notify(
                f"Toggled selection for [$accent]{new_selected_count}[/] rows",
                title="Toggle",
            )

        # Refresh the highlighting (also restores default styles for unselected rows)
        self._do_highlight()

    def _make_selections(self) -> None:
        """Make selections based on current matches or toggle current row selection."""
        # Save current state to history
        self._add_history("Toggled row selection")

        if self.matches:
            # There are matched cells - select rows with matches
            for ridx in self.matches.keys():
                self.selected_rows[ridx] = True
        else:
            # No matched cells - select/deselect the current row
            ridx = self.cursor_row_idx
            self.selected_rows[ridx] = not self.selected_rows[ridx]

        # Check if we're highlighting or un-highlighting
        if new_selected_count := self.selected_rows.count(True):
            self.notify(f"Selected [$accent]{new_selected_count}[/] rows", title="Toggle")

        # Refresh the highlighting (also restores default styles for unselected rows)
        self._do_highlight()

    def _clear_selections(self) -> None:
        """Clear all selected rows without removing them from the dataframe."""
        # Check if any selected rows or matches
        if not any(self.selected_rows) and not self.matches:
            self.notify("No selections to clear", title="Clear", severity="warning")
            return

        row_count = sum(
            1 if (selected or idx in self.matches) else 0 for idx, selected in enumerate(self.selected_rows)
        )

        # Save current state to history
        self._add_history("Cleared all selected rows")

        # Clear all selections and refresh highlighting
        self._do_highlight(clear=True)

        self.notify(f"Cleared selections for [$accent]{row_count}[/] rows", title="Clear")

    def _filter_selected_rows(self) -> None:
        """Keep only the selected rows and remove unselected ones."""
        selected_count = self.selected_rows.count(True)
        if selected_count == 0:
            self.notify("No rows selected to filter", title="Filter", severity="warning")
            return

        # Save current state to history
        self._add_history("Filtered to selected rows")

        # Update dataframe to only include selected rows
        self.df = self.df.filter(self.selected_rows)
        self.selected_rows = [True] * len(self.df)

        # Recreate the table for display
        self._setup_table()

        self.notify(
            f"Removed unselected rows. Now showing [$accent]{selected_count}[/] rows",
            title="Filter",
        )

    def _view_rows(self) -> None:
        """View rows.

        If there are selected rows, view those rows.
        Otherwise, view based on the value of the currently selected cell.
        """

        cidx = self.cursor_col_idx

        # If there are selected rows or matches, use those
        if any(self.selected_rows) or self.matches:
            term = [
                True if (selected or idx in self.matches) else False for idx, selected in enumerate(self.selected_rows)
            ]
        # Otherwise, use the current cell value
        else:
            ridx = self.cursor_row_idx
            term = str(self.df.item(ridx, cidx))

        self._do_view_rows((term, cidx, False, False))

    def _view_rows_expr(self) -> None:
        """Open the filter screen to enter an expression."""
        ridx = self.cursor_row_idx
        cidx = self.cursor_col_idx
        cursor_value = str(self.df.item(ridx, cidx))

        self.app.push_screen(
            FilterScreen(self.df, cidx, cursor_value),
            callback=self._do_view_rows,
        )

    def _do_view_rows(self, result) -> None:
        """Show only those matching rows and hide others. Do not modify the dataframe."""
        if result is None:
            return
        term, cidx, match_nocase, match_whole = result

        col_name = self.df.columns[cidx]

        if term == NULL:
            expr = pl.col(col_name).is_null()
        elif isinstance(term, (list, pl.Series)):
            # Support for list of booleans (selected rows)
            expr = term
        elif tentative_expr(term):
            # Support for polars expressions
            try:
                expr = validate_expr(term, self.df, cidx)
            except Exception as e:
                self.notify(
                    f"Error validating Polars expression [$error]{term}[/]: {str(e)}", title="Filter", severity="error"
                )
                return
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
                        f"Unknown column type [$warning]{dtype}[/]. Cast to string.",
                        title="Filter",
                        severity="warning",
                    )

        # Lazyframe with row indices
        lf = self.df.lazy().with_row_index(RIDX)

        # Apply existing visibility filter first
        if False in self.visible_rows:
            lf = lf.filter(self.visible_rows)

        # Apply the filter expression
        try:
            df_filtered = lf.filter(expr).collect()
        except Exception as e:
            self.notify(f"Failed to apply filter [$error]{expr}[/]: {str(e)}", title="Filter", severity="error")
            self.histories.pop()  # Remove last history entry
            return

        matched_count = len(df_filtered)
        if not matched_count:
            self.notify(
                f"No rows match the expression: [$success]{expr}[/]",
                title="Filter",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(f"Filtered by expression [$success]{expr}[/]")

        # Mark unfiltered rows as invisible
        filtered_row_indices = set(df_filtered[RIDX].to_list())
        if filtered_row_indices:
            for ridx in range(len(self.visible_rows)):
                if ridx not in filtered_row_indices:
                    self.visible_rows[ridx] = False

        # Recreate the table for display
        self._setup_table()

        self.notify(
            f"Filtered to [$accent]{matched_count}[/] matching rows",
            title="Filter",
        )

    def _cycle_cursor_type(self) -> None:
        """Cycle through cursor types: cell -> row -> column -> cell."""
        next_type = get_next_item(CURSOR_TYPES, self.cursor_type)
        self.cursor_type = next_type

        # self.notify(f"Changed cursor type to [$success]{next_type}[/]", title="Cursor")

    def _copy_to_clipboard(self, content: str, message: str) -> None:
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
            self.notify("Error copying to clipboard", title="Clipboard", severity="error")

    def _save_to_file(self) -> None:
        """Open screen to save file."""
        self.app.push_screen(SaveFileScreen(self.filename), callback=self._do_save_file)

    def _do_save_file(self, filename: str | None, all_tabs: bool = False) -> None:
        """Handle result from SaveFileScreen."""
        if filename is None:
            return
        filepath = Path(filename)
        ext = filepath.suffix.lower()

        # Whether to save all tabs (for Excel files)
        self._all_tabs = all_tabs

        # Check if file exists
        if filepath.exists():
            self._pending_filename = filename
            self.app.push_screen(
                ConfirmScreen("File already exists. Overwrite?"),
                callback=self._on_overwrite_screen,
            )
        elif ext in (".xlsx", ".xls"):
            self._do_save_excel(filename)
        else:
            self._do_save(filename)

    def _on_overwrite_screen(self, should_overwrite: bool) -> None:
        """Handle result from ConfirmScreen."""
        if should_overwrite:
            self._do_save(self._pending_filename)
        else:
            # Go back to SaveFileScreen to allow user to enter a different name
            self.app.push_screen(
                SaveFileScreen(self._pending_filename),
                callback=self._do_save_file,
            )

    def _do_save(self, filename: str) -> None:
        """Actually save the dataframe to a file."""
        filepath = Path(filename)
        ext = filepath.suffix.lower()

        try:
            if ext in (".xlsx", ".xls"):
                self._do_save_excel(filename)
            elif ext in (".tsv", ".tab"):
                self.df.write_csv(filename, separator="\t")
            elif ext == ".json":
                self.df.write_json(filename)
            elif ext == ".parquet":
                self.df.write_parquet(filename)
            else:
                self.df.write_csv(filename)

            self.lazyframe = self.df.lazy()  # Update original dataframe
            self.filename = filename  # Update current filename
            if not self._all_tabs:
                extra = "current tab with " if len(self.app.tabs) > 1 else ""
                self.notify(
                    f"Saved {extra}[$accent]{len(self.df)}[/] rows to [$success]{filename}[/]",
                    title="Save",
                )
        except Exception as e:
            self.notify(f"Failed to save: {str(e)}", title="Save", severity="error")
            raise e

    def _do_save_excel(self, filename: str) -> None:
        """Save to an Excel file."""
        import xlsxwriter

        if not self._all_tabs or len(self.app.tabs) == 1:
            # Single tab - save directly
            self.df.write_excel(filename)
        else:
            # Multiple tabs - use xlsxwriter to create multiple sheets
            with xlsxwriter.Workbook(filename) as wb:
                tabs: dict[TabPane, DataFrameTable] = self.app.tabs
                for tab, table in tabs.items():
                    worksheet = wb.add_worksheet(tab.name)
                    table.df.write_excel(workbook=wb, worksheet=worksheet)

        # From ConfirmScreen callback, so notify accordingly
        if self._all_tabs is True:
            self.notify(
                f"Saved all tabs to [$success]{filename}[/]",
                title="Save",
            )
        else:
            self.notify(
                f"Saved current tab with [$accent]{len(self.df)}[/] rows to [$success]{filename}[/]",
                title="Save",
            )
