"""DataFrameTable widget for displaying and interacting with Polars DataFrames."""

import io
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import partial
from itertools import zip_longest
from pathlib import Path
from textwrap import dedent
from threading import Event
from typing import Any, Callable

import polars as pl
from rich.text import Text, TextType
from textual import work
from textual._two_way_dict import TwoWayDict
from textual.coordinate import Coordinate
from textual.events import Click, Key
from textual.reactive import reactive
from textual.render import measure
from textual.widgets import DataTable
from textual.widgets.data_table import (
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
    COLUMN_WIDTH_CAP,
    CURSOR_TYPES,
    HIGHLIGHT_COLOR,
    NULL,
    NULL_DISPLAY,
    RID,
    RID_OLD,
    SUBSCRIPT_DIGITS,
    THOUSAND_SEPARATOR,
    DtypeConfig,
    add_rid_column,
    format_row,
    get_next_item,
    parse_placeholders,
    round_to_nearest_hundreds,
    tentative_expr,
    validate_expr,
    with_leader_key,
)
from .loading_screen import BusyScreen, LoadingScreen
from .table_screen import (
    BarScreen,
    CellDetailScreen,
    FrequencyScreen,
    HistogramScreen,
    MetaColumnScreen,
    RowDetailScreen,
    StatisticsScreen,
)
from .text_screen import TextScreen
from .yes_no_screen import (
    AddColumnScreen,
    AddLinkScreen,
    AdvancedSqlScreen,
    ConfirmScreen,
    CustomBinScreen,
    EditCellScreen,
    EditColumnScreen,
    ExplodeColumnScreen,
    FilterBooleanScreen,
    FilterListScreen,
    FilterNumericScreen,
    FilterStringScreen,
    FilterTemporalScreen,
    FindReplaceScreen,
    FreezeScreen,
    GoToRowScreen,
    RenameColumnScreen,
    SearchScreen,
    SimpleSqlScreen,
)

# Buffer size for loading rows
BUFFER_SIZE = 5

# Threshold for number of rows loaded before showing a warning to the user
WARN_ROWS_THRESHOLD = 1_000_000


@dataclass
class History:
    """Class to track history of dataframe states for undo/redo functionality."""

    description: str
    df: pl.DataFrame
    df_view: pl.DataFrame | None
    filename: str
    hidden_columns: set[str]
    selected_rows: set[int]
    selected_columns: set[str]
    sorted_columns: dict[str, bool]  # col_name -> descending
    matches: dict[int, set[str]]  # RID -> set of col names
    fixed_rows: int
    fixed_columns: int
    cursor_coordinate: Coordinate
    expanded_columns: set[str]
    thousand_separator_columns: set[str]
    float_precision_columns: dict[str, int]
    show_rid: bool
    show_column_index: bool
    dirty: bool = False  # Whether this history state has unsaved changes


@dataclass
class ReplaceState:
    """Class to track state during interactive replace operations."""

    term_find: str
    term_replace: str
    match_nocase: bool
    match_whole: bool
    match_literal: bool
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


def handle_term(
    term: str, col_name: str, match_nocase: bool, match_whole: bool, match_literal: bool, cast_to_str: bool = False
) -> pl.Expr:
    """Handle search term based on matching options.

    Args:
        term: The original search term input by the user.
        col_name: The name of the column to search in.
        match_nocase: Whether to ignore case when matching.
        match_whole: Whether to match whole cell values only.
        match_literal: Whether to treat the term as a literal string (not a regex).
        cast_to_str: Whether to cast the term to a string if possible (for non-regex search).

    Returns:
        A Polars expression that can be used for filtering based on the search term and options.
    """
    str_to_search = pl.col(col_name).cast(pl.String) if cast_to_str else pl.col(col_name)

    if match_literal:
        if match_whole:
            if match_nocase:
                expr = str_to_search.str.to_lowercase() == term.lower()
            else:
                expr = str_to_search == term
        else:
            if match_nocase:
                expr = str_to_search.str.to_lowercase().str.contains(term.lower(), literal=True)
            else:
                expr = str_to_search.str.contains(term, literal=True)
    else:
        if match_whole:
            term = f"^{term}$"
        if match_nocase:
            term = f"(?i){term}"
        expr = str_to_search.str.contains(term, literal=match_literal)

    return expr


class DataFrameTable(DataTable):
    """Custom DataTable to highlight row/column labels based on cursor position."""

    # Help text for the DataTable which will be shown in the HelpPanel
    HELP = dedent("""
        # 📊 DataFrame Viewer - Table Controls

        ## ⬆️ Navigation
        - **gg** - ⬆️ Go to first row
        - **G** - ⬇️ Go to last row
        - **Ctrl+G** - 🎯 Go to row
        - **↑↓←→** - 🎯 Move cursor (cell/row/column)
        - **hjkl** - 🎯 Move cursor left/down/up/right (Vim-style)
        - **gh** - ⬅️ Scroll to leftmost column
        - **gj** - ⬇️ Scroll to last row
        - **gk** - ⬆️ Scroll to first row
        - **gl** - ➡️ Scroll to rightmost column
        - **HOME/END** - 🎯 Go to first/last column
        - **Ctrl+HOME/END** - 🎯 Go to page top/bottom
        - **PgUp/PgDn** - 📜 Page up/down
        - **Ctrl+F** - 📜 Page down
        - **Ctrl+B** - 📜 Page up

        ## ♻️ Undo/Redo/Reset
        - **u/U** - ↩️ Undo last action
        - **R** - 🔄 Redo last undone action
        - **gu** - 🔁 Reset to initial state

        ## 👁️ Display
        - **Enter** - 📋 Show row details in modal
        - **Tab** - 🔍 Show current cell details in modal; use `Tab` again there to drill deeper
        - **F** - 📊 Show frequency distribution for current or selected columns
        - **m** - 📊 Show histogram for current column
        - **M** - 📊 Show histogram for current column with custom bins
        - **I** - 📈 Show statistics for current column
        - **gI** - 📊 Show statistics for entire dataframe
        - **zC** - 🎯 Cycle cursor type (cell → row → column)
        - **=** - 📊 Show bar chart using first selected column as label and cursor column as value
        - **C** - 📋 Show column metadata (ID, name, type)
        - **-** (minus) - 👁️ Hide selected columns or current column
        - **g-** (minus) - 👁️ Hide current column and those before
        - **z-** (minus) - 👁️ Hide current column and those after
        - **gv** - 👀 Show all hidden columns
        - **_** (underscore) - 📏 Toggle column full width for current column
        - **g_** (underscore) - 📏 Toggle column full width for all string/list columns
        - **+** - 📌 Freeze rows and/or columns
        - **z~** - 🏷️ Toggle column index prefix
        - **g^** - 📌 Mark current row as header
        - **gT** - 🎨 Open theme selection
        - **z^** - 🆔 Toggle internal row index (RID)
        - **,** - 🔢 Toggle thousand separator for current column
        - **g,** - 🔢 Toggle thousand separator for all numeric columns
        - **<** - 🔢 Decrease float precision for current column
        - **>** - 🔢 Increase float precision for current column

        ## ✏️ Editing
        - **Double-click** - ✍️ Edit cell or rename column header
        - **e** - ✍️ Edit current cell
        - **E** - 📊 Edit entire column with expression
        - **a** - ➕ Add empty column after current
        - **A** - ➕ Add column with name and optional expression
        - **i** - ➕ Add an index column after current
        - **za** - ➕ Add a link column after current
        - **^** - ✏️ Rename current column
        - **d** - ✖️ Delete current row
        - **gd** - ✖️ Delete row and those above
        - **zd** - ✖️ Delete row and those below
        - **Delete** - ✖️ Clear current cell (set to NULL)
        - **Shift+Delete** - ✖️ Clear current column (set matching cells to NULL)
        - **\\*** - ✖️ Delete selected columns or current column
        - **g\\*** - ✖️ Delete column and those before current column
        - **z\\*** - ✖️ Delete column and those after current column
        - **D** - 📋 Duplicate current row
        - **zD** - 📋 Duplicate current column
        - **gU** - 🧹 Remove duplicate rows (keep first occurrence)
        - **zT** - 🔃 Transpose table (swap rows/columns)
        - **(** - 🧩 Expand current list column into indexed columns
        - **o** - 💥 Explode current list column into rows
        - **O** - 💥 Explode current string column by delimiter into rows
        - **:** - ✂️ Split current string column into a new column by delimiter
        - **Ctrl+U** - 🔠 Convert current or selected string column(s) to uppercase
        - **Ctrl+L** - 🔡 Convert current or selected string column(s) to lowercase

        ## ✅ Row/Column Selection
        - **\\\\** - ✅ Select rows with cell matches or those matching cursor value in current column
        - **|** - ✅ Select rows with expression
        - **s** - ✅ Select/deselect current row
        - **'** (apostrophe) - ✅ Select/deselect current column
        - **t** - 💡 Toggle row selection (invert all)
        - **T** - 🧹 Clear all row/column selections and cell matches
        - **{** - ⬆️ Go to previous selected row
        - **}** - ⬇️ Go to next selected row
        - *(Supports case-insensitive & whole-word matching)*

        ## 🔎 Find & Replace
        - **/** - 🔎 Find in current column with cursor value
        - **g/** - 🌐 Find in all columns with cursor value
        - **?** - 🔎 Find in current column with expression
        - **g?** - 🌐 Find in all columns with expression
        - **n** - ⬇️ Go to next match
        - **N** - ⬆️ Go to previous match
        - **r** - 🔄 Replace in current column (interactive or all)
        - **gr** - 🔄 Replace across all columns (interactive or all)
        - *(Supports case-insensitive & whole-word matching)*

        ## ⏬ Filter & Collect
        - **v** - ⏬ Filter rows with cursor value in current column
        - **V** - ⏬ Filter rows with expression
        - **.** - ⏬ Filter rows with non-null values in current column
        - **f** - ⏬ Filter rows by column value
        - **"** (double quote) - 📤 Collect rows to a new tab

        ## 🔀 Sorting
        - **[** - 🔼 Sort column ascending
        - **]** - 🔽 Sort column descending
        - *(Multi-column sort supported)*

        ## 🔃 Reorder
        - **Shift+↑↓** - ⬆️⬇️ Move row up/down
        - **Shift+←→** - ⬅️➡️ Move column left/right
        - **J/K** - ⬇️⬆️ Move row down/up (Vim-style)
        - **H/L** - ⬅️➡️ Move column left/right (Vim-style)

        ## 🎨 Type Casting
        - **#** - 🔢 Cast column to integer
        - **%** - 🔢 Cast column to float
        - **$** - ✅ Cast column to boolean
        - **~** - 📝 Cast column to string
        - **@** - 📅 Cast column to date

        ## 📋 Copy
        - **c** - 📋 Copy cell to clipboard
        - **Ctrl+c** - 📊 Copy column to clipboard
        - **Ctrl+r** - 📝 Copy row to clipboard (tab-separated)

        ## ⌨️ SQL Interface
        - **Q** - 🔎 Open advanced SQL interface (full SQL queries)
        - **zQ** - 💬 Open simple SQL interface (select columns & where clause)
    """).strip()

    # fmt: off
    BINDINGS = [
        # Navigation
        ("h", "cursor_left", "Move cursor left"),
        ("j", "cursor_down", "Move cursor down"),
        ("k", "cursor_up", "Move cursor up"),
        ("l", "cursor_right", "Move cursor right"),
        ("g", "go_top", "Go to first row"),
        ("G", "go_bottom", "Go to last row"),
        ("ctrl+g", "go_to_row", "Go to row"),
        ("ctrl+b", "page_up", "Page up"),
        ("ctrl+f", "page_down", "Page down"),
        # Undo/Redo/Reset
        ("u,U", "undo", "Undo"),
        ("R", "redo", "Redo"),
        ("ctrl+u", "upper_case_column", "Convert string column(s) to uppercase"),  # `Ctrl+U`
        ("ctrl+l", "lower_case_column", "Convert string column(s) to lowercase"),  # `Ctrl+L`
        # Display
        ("underscore", "expand_column", "Toggle column full width"),  # `_`
        ("minus", "hide_column", "Hide selected columns or current column"),  # `-`
        ("+", "toggle_freeze_row_column", "Freeze rows/columns"), # `+`
        ("comma", "toggle_thousand_separator", "Toggle thousand separator for column"),  # `,`
        ("left_parenthesis", "expand_list_column", "Expand current list column into indexed columns"),  # `(`
        ("less_than_sign", "adjust_float_precision(-1)", "Decrease float precision for column"),  # `<`
        ("greater_than_sign", "adjust_float_precision(1)", "Increase float precision for column"),  # `>`
        ("circumflex_accent", "rename_column", "Rename current column"),  # `^`
        # Copy
        ("c", "copy_cell", "Copy cell to clipboard"),
        ("ctrl+c", "copy_column", "Copy column to clipboard"),
        ("ctrl+r", "copy_row", "Copy row to clipboard"),
        # Column Metadata, Row Detail, Frequency, and Statistics
        ("C", "metadata_column", "Show metadata for all columns"),
        ("enter", "view_row_detail", "View row details"),
        ("tab", "view_cell_detail", "View cell details"),
        ("F", "show_frequency", "Show frequency for current column"),
        ("m", "show_histogram", "Show histogram for current column"),
        ("M", "show_histogram(0)", "Show histogram for current column with custom bins"),
        ("I", "show_statistics", "Show statistics"),
        ("equals_sign", "show_bar", "Show bar chart using first selected column as label and cursor column as value"),  # `=`
        # Sort
        ("left_square_bracket", "sort_ascending", "Sort ascending"),  # `[`
        ("right_square_bracket", "sort_descending", "Sort descending"),  # `]`
        # Filter & Collect
        ("v", "filter_rows", "Filter rows"),
        ("V", "filter_rows_expr", "Filter rows with specified value or expression"),  # `V`
        ("full_stop", "filter_rows_non_null", "Filter rows with non-null values in current column"),
        ("f", "filter_rows_value", "Filter rows by value"),  # `f`
        ("quotation_mark", "collect_rows_columns", "Collect rows/columns to a new tab"),  # `"`
        # Row/Column Selection
        ("backslash", "select_rows", "Select rows with cell matches or those matching cursor value in current column"),  # `\`
        ("vertical_line", "select_rows_expr", "Select rows with expression"),  # `|`
        ("right_curly_bracket", "next_selected_row", "Go to next selected row"),  # `}`
        ("left_curly_bracket", "previous_selected_row", "Go to previous selected row"),  # `{`
        ("s", "toggle_selection_current_row", "Toggle row selection"),  # `s`
        ("apostrophe", "toggle_selection_current_column", "Toggle column selection"),  # `'`
        ("t", "toggle_selections", "Toggle row selections"),
        ("T", "clear_selections_and_matches", "Clear row/column selections and cell matches"),
        # Find & Replace
        ("slash", "find_cursor_value", "Find with cursor value"),  # `/`
        ("question_mark", "find_expr", "Find with expression"),  # `?`
        ("n", "next_match", "Go to next match"),
        ("N", "previous_match", "Go to previous match"),
        ("r", "replace", "Replace with value"),
        # Delete
        ("delete", "clear_cell", "Clear cell"),
        ("shift+delete", "clear_column", "Clear cells in current column that match cursor value"),  # `Shift+Delete`
        ("asterisk", "delete_column", "Delete selected columns or current column"),  # `*`
        ("d", "delete_row", "Delete row"),
        # Duplicate
        ("D", "duplicate_row_column", "Duplicate row or column"),
        # Edit
        ("e", "edit_cell", "Edit cell"),
        ("E", "edit_column", "Edit column"),
        # Explode
        ("o", "explode_column", "Explode column"),
        ("O", "explode_column_delim", "Explode column by delimiter"),
        # Add Column
        ("a", "add_column", "Add column"),
        ("A", "add_column_expr", "Add column with expression"),
        ("i", "add_index_column", "Add an index column"),  # `i`
        # Split Column
        ("colon", "split_column", "Split column"),
        # Reorder
        ("shift+left,H", "move_column_left", "Move column left"),
        ("shift+right,L", "move_column_right", "Move column right"),
        ("shift+up,K", "move_row_up", "Move row up"),
        ("shift+down,J", "move_row_down", "Move row down"),
        # Type Casting
        ("number_sign", "cast_column_dtype('pl.Int64')", "Cast column dtype to integer"),  # `#`
        ("percent_sign", "cast_column_dtype('pl.Float64')", "Cast column dtype to float"),  # `%`
        ("dollar_sign", "cast_column_dtype('pl.Boolean')", "Cast column dtype to bool"),  # `$`
        ("tilde", "cast_column_dtype('pl.String')", "Cast column dtype to string"),  # `~`
        ("at", "cast_column_dtype('pl.Date')", "Cast column dtype to date"),  # `@`
        # Sql
        ("Q", "sql_query", "Open SQL interface"),  # `Q`
    ]
    # fmt: on

    # Track if dataframe has unsaved changes
    dirty: reactive[bool] = reactive(False)

    def __init__(self, frame: pl.DataFrame | pl.LazyFrame, filename: str = "", tabname: str = "", **kwargs) -> None:
        """Initialize the DataFrameTable with a dataframe and manage all state.

        Sets up the table widget with display configuration, loads the dataframe, and
        initializes all state tracking variables for row/column operations.

        Args:
            frame: The Polars DataFrame or LazyFrame to display and edit.
            filename: Optional source filename for the data (used in save operations). Defaults to "".
            tabname: Optional name for the tab displaying this dataframe. Defaults to "".
            **kwargs: Additional keyword arguments passed to the parent DataTable widget.
        """
        super().__init__(**kwargs)

        # DataFrame state
        if isinstance(frame, pl.LazyFrame):
            self.lf = frame  # Original LazyFrame for reference
            self.df = None  # Internal/working dataframe that gets loaded in batches
            self.df_done = False  # Whether the entire dataframe has been loaded
        else:
            self.lf = frame.lazy()  # Convert DataFrame to LazyFrame
            self.df = frame  # Internal/working dataframe
            self.df_done = True  # Whether the entire dataframe has been loaded

        self.dataframe = None  # Original dataframe
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
        self.selected_columns: set[str] = set()  # Track selected columns by name
        self.sorted_columns: dict[str, bool] = {}  # col_name -> descending
        self.matches: dict[int, set[str]] = defaultdict(set)  # Track search matches: RID -> set of col_names

        # Freezing
        self.fixed_rows = 0  # Number of fixed rows
        self.fixed_columns = 0  # Number of fixed columns

        # History stack for undo
        self.histories_undo: deque[History] = deque()
        # History stack for redo
        self.histories_redo: deque[History] = deque()

        # Set of columns expanded to full width
        self.expanded_columns: set[str] = set()

        # Set of columns with thousand separator enabled for numeric display
        self.thousand_separator_columns: set[str] = set()

        # Per-column float precision: col_name -> number of decimal places
        self.float_precision_columns: dict[str, int] = {}

        # Whether to show internal row index column
        self.show_rid = False

        # Whether to show 1-based index prefix in column labels (e.g., "1_colname")
        self.show_column_index = False

    def init_table(self) -> None:
        """Initial load of the dataframe and setup of the table display.

        - If a DataFrame is provided, set up the table immediately.
        - If a LazyFrame is provided, set up the table with the first batch of rows
          while the remaining rows continue to load in the background.
        """
        # If we already have a loaded DataFrame, use it directly
        if self.df is not None:
            self.dataframe = add_rid_column(self.df)
            self.df = self.dataframe
            self.df_done = True
            self.setup_table()
            return

        # Otherwise, we have a LazyFrame that needs to be loaded in batches
        batch_gen = self.lf.collect_batches()

        try:
            self.dataframe = add_rid_column(next(batch_gen))
            self.df = self.dataframe
            # self.log(f"loaded {len(self.df)} rows in initial batch")
        except pl.exceptions.ComputeError as e:
            self.log(f"Error loading initial batch: {e}")
            return self.app.exit(return_code=1, result=str(e))
        except StopIteration:
            self.log("The provided LazyFrame has no data to load")
            return self.app.exit(return_code=1, result="The provided LazyFrame has no data to load")

        # Populate the table with the initial batch of data
        self.setup_table()

        # Continue loading the rest of the dataframe in the background
        self.load_remaining_batches(batch_gen)

    @work(thread=True)
    def load_remaining_batches(self, batch_gen) -> None:
        """Background load the rest of the dataframe in batches."""
        batches, offset = [], len(self.df)
        total_loaded = len(self.df)
        warned, fully_loaded = False, True

        try:
            for batch in batch_gen:
                batches.append(add_rid_column(batch, offset=offset))
                offset += len(batch)
                total_loaded += len(batch)

                # Ask once when the loader reaches the warning threshold.
                if not warned and total_loaded >= WARN_ROWS_THRESHOLD:
                    warned = True
                    decision_ready = Event()
                    decision = {"continue": True}

                    def on_decision(result: bool | None) -> None:
                        """Record the user's continue/cancel decision and signal the loader thread."""
                        decision["continue"] = bool(result)
                        decision_ready.set()

                    def prompt_continue_loading() -> None:
                        """Push the confirmation dialog on the main thread."""
                        self.app.push_screen(
                            ConfirmScreen(
                                "Continue Loading?",
                                label=(
                                    f"Loaded [$accent]{total_loaded:{THOUSAND_SEPARATOR}}[/] rows so far. "
                                    "Continue loading the remaining rows?"
                                ),
                            ),
                            callback=on_decision,
                        )

                    self.app.call_from_thread(prompt_continue_loading)
                    decision_ready.wait()

                    if not decision["continue"]:
                        fully_loaded = False
                        break
        except pl.exceptions.ComputeError as e:
            self.log(f"Error loading remaining batch: {e}")
            return self.app.exit(return_code=1, result=str(e))

        if batches:
            self.dataframe = pl.concat([self.df] + batches, rechunk=True)
            self.df = self.dataframe

            if self.loaded_rows < self.BATCH_SIZE:
                self.load_rows_range(self.loaded_rows, self.BATCH_SIZE)

        # fully loaded the dataframe
        self.df_done = True

        self.notify(
            "Data fully loaded" if fully_loaded else "Data loading stopped by user",
            title="Load DataFrame",
            severity="information" if fully_loaded else "warning",
        )

    def with_full_df(func: Callable) -> Callable:
        """Decorator to ensure the dataframe is fully loaded before executing a method.

        If the dataframe is not loaded, show a loading indicator and schedule the
        method to be called once loading is complete.
        """

        def wrapper(self, *args, **kwargs):
            """Invoke the wrapped action only when the dataframe is fully loaded."""
            if self.df_done:
                return func(self, *args, **kwargs)

            callback = partial(func, self, *args, **kwargs)
            self.app.push_screen(LoadingScreen(self, callback=callback))

        return wrapper

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
    def cursor_col_name(self) -> str | None:
        """Get the current cursor column name as in dataframe.

        Returns:
            str: The name of the column containing the cursor.
        """
        return self.cursor_col_key.value

    @property
    def cursor_col_dtype(self) -> pl.DataType:
        """Get the current cursor column dtype.

        Returns:
            pl.DataType: The Polars data type of the column containing the cursor.
        """
        return self.df.schema[self.cursor_col_name]

    @property
    def cursor_ridx(self) -> int:
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
    def cursor_cidx(self) -> int:
        """Get the current cursor column index (0-based) as in dataframe.

        Returns:
            int: The 0-based column index of the cursor position.

        Raises:
            AssertionError: If the cursor column index is out of bounds.
        """
        try:
            cidx = self.df.get_column_index(self.cursor_col_name)
        except pl.exceptions.ColumnNotFoundError:
            raise AssertionError("Cursor column index is out of bounds")
        return cidx

    @property
    def cursor_value(self) -> Any:
        """Get the current cursor cell value in the dataframe.

        Returns:
            Any: The value of the cell at the cursor position.
        """
        return self.df.item(self.cursor_ridx, self.cursor_cidx)

    @property
    def visible_columns(self) -> dict[str, pl.DataType]:
        """Get the list of visible columns ordered by their appearance in the dataframe.

        Returns:
            dict[str, pl.DataType]: A dictionary of visible column names and their data types.
        """
        return {
            col: dtype
            for col, dtype in zip(self.df.columns, self.df.dtypes, strict=True)
            if col not in self.hidden_columns and (col != RID or self.show_rid)
        }

    @property
    def leader_key(self) -> bool:
        """The current leader-mode key (``'g'``, ``'z'``, or ``''`` when inactive)."""
        return self.app.leader_key

    @leader_key.setter
    def leader_key(self, value: bool) -> None:
        """Set the leader-mode key on the app."""
        self.app.leader_key = value

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

    def _round_to_nearest_hundreds(self, num: int) -> tuple[int, int]:
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

    def get_row_key(self, row_idx: int) -> RowKey | None:
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

    def get_col_key(self, col_idx: int) -> ColumnKey | None:
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

    def stop_timer(self) -> None:
        """Stop the timeout timer in the app."""
        if self.app.timeout_timer:
            self.app.timeout_timer.stop()
            self.app.timeout_timer = None

    def on_key(self, event: Key) -> None:
        """Handle key press events for leader-key sequences and row loading.

        Handles two-key leader sequences and scroll-triggered row loading:

        Leader ``g`` sequences:
          - ``gv``: Show all hidden columns.
          - ``gT``: Open theme selection.
          - ``gU``: Remove duplicate rows.
          - ``g^``: Mark current row as header.
          - ``gh``: Scroll to leftmost column.
          - ``gj``: Scroll to last row (bottom).
          - ``gk``: Scroll to first row (top).
          - ``gl``: Scroll to rightmost column.

        Leader ``z`` sequences:
          - ``zC``: Cycle cursor type.
          - ``zT``: Transpose table.
          - ``z^``: Toggle internal row index (RID) column.
          - ``z~``: Toggle 1-based column index prefixes in visible headers.

        Row loading triggers:
          - ``↑``: Load rows above current visible range.
          - ``↓``: Load rows below current visible range.

        All other key actions are handled via BINDINGS and their ``action_*`` methods.

        Args:
            event: The key event object.
        """
        # Handle leader key sequences for `g`
        if self.leader_key == "g":
            if event.key == "v":  # `gv`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.do_show_hidden_columns()
                return
            elif event.key == "T":  # `gT`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.app.select_theme()
                return
            elif event.key == "U":  # `gU`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.do_uniq_rows()
                return
            # Set current row as header
            elif event.key == "circumflex_accent":  # `g^`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.do_set_cursor_row_as_header()
                return
            # Go to leftmost column
            elif event.key == "h":  # `gh`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.action_scroll_home()
                self.leader_key = ""
                self.notify("Scrolled to [$success]home[/]", title="Scroll")
                return
            # Go to last row
            elif event.key == "j":  # `gj`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.action_scroll_bottom()
                self.leader_key = ""
                self.notify("Scrolled to [$success]bottom[/]", title="Scroll")
                return
            # Go to top row
            elif event.key == "k":  # `gk`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.action_scroll_top()
                self.leader_key = ""
                self.notify("Scrolled to [$success]top[/]", title="Scroll")
                return
            # Go to last column
            elif event.key == "l":  # `gl`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.action_scroll_end()
                self.leader_key = ""
                self.notify("Scrolled to [$success]end[/]", title="Scroll")
                return

        # Handle leader key sequences for `z`
        elif self.leader_key == "z":
            # Toggle internal row index column (RID)
            if event.key == "circumflex_accent":  # `z^`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.do_toggle_rid()
                return
            elif event.key == "tilde":  # `z~`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.do_toggle_column_index()
                return
            elif event.key == "T":  # `zT`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.do_transpose()
                return
            elif event.key == "C":  # `zC`:
                event.stop()
                event.prevent_default()
                self.stop_timer()
                self.do_cycle_cursor_type()
                return

        if event.key == "up":
            self.load_rows_up()
        elif event.key == "down":
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

    def on_mouse_scroll_up(self, event) -> None:
        """Load more rows when scrolling up with mouse."""
        self.load_rows_up()

    def on_mouse_scroll_down(self, event) -> None:
        """Load more rows when scrolling down with mouse."""
        self.load_rows_down()

    @with_leader_key
    def action_go_top(self) -> None:
        """Go to the top of the table."""
        self.do_go_top()

    @with_full_df
    def action_go_bottom(self) -> None:
        """Go to the bottom of the table."""
        self.do_go_bottom()

    def action_go_to_row(self) -> None:
        """Go to a specific row number."""
        self.do_go_to_row()

    def action_page_up(self) -> None:
        """Move the cursor one page up."""
        self.do_page_up()
        super().action_page_up()

    def action_page_down(self) -> None:
        """Move the cursor one page down."""
        self.do_page_down()
        super().action_page_down()

    def action_view_row_detail(self) -> None:
        """View details of the current row."""
        self.do_view_row_detail()

    def action_view_cell_detail(self) -> None:
        """View details of the current cell."""
        self.do_view_cell_detail()

    @with_full_df
    @with_leader_key
    def action_delete_column(self) -> None:
        """Delete selected columns or the current column."""
        if self.leader_key == "g":
            self.do_delete_column(more="before")
        elif self.leader_key == "z":
            self.do_delete_column(more="after")
        else:
            self.do_delete_column()

    @with_leader_key
    def action_hide_column(self) -> None:
        """Hide selected columns or the current column."""
        if self.leader_key == "g":
            self.do_hide_column(more="before")
        elif self.leader_key == "z":
            self.do_hide_column(more="after")
        else:
            self.do_hide_column()

    def action_show_hidden_columns(self) -> None:
        """Show all hidden columns."""
        self.do_show_hidden_columns()

    @with_leader_key
    def action_expand_column(self) -> None:
        """Expand the current column to its full width."""
        self.do_expand_column()

    @with_full_df
    def action_sort_ascending(self) -> None:
        """Sort by current column in ascending order."""
        self.do_sort_by_column(descending=False)

    @with_full_df
    def action_sort_descending(self) -> None:
        """Sort by current column in descending order."""
        self.do_sort_by_column(descending=True)

    @with_full_df
    def action_show_frequency(self) -> None:
        """Show frequency distribution for the current column."""
        self.do_show_frequency()

    @with_full_df
    def action_show_histogram(self, default: int = 1) -> None:
        """Show histogram for the current column."""
        self.do_show_histogram(default=default)

    @with_full_df
    def action_show_bar(self) -> None:
        """Show bar chart using first selected column as label and cursor column as value."""
        self.do_show_bar()

    @with_full_df
    @with_leader_key
    def action_show_statistics(self) -> None:
        """Show statistics for the current column or entire dataframe."""
        self.do_show_statistics()

    def action_metadata_column(self) -> None:
        """Show metadata for the current column."""
        self.do_metadata_column()

    @with_full_df
    @with_leader_key
    def action_filter_rows(self, result: dict | None = None) -> None:
        """Filter rows by value or expression"""
        self.do_filter_rows(result)

    @with_full_df
    def action_filter_rows_expr(self) -> None:
        """Filter rows by value or expression."""
        self.do_filter_rows_expr()

    @with_full_df
    def action_filter_rows_non_null(self) -> None:
        """Filter rows with non-null values in the current column."""
        self.do_filter_rows_non_null()

    @with_full_df
    def action_filter_rows_value(self) -> None:
        """Filter rows by value for the current column."""
        self.do_filter_rows_value()

    @with_full_df
    def action_collect_rows_columns(self, cidx: int | None = None, term: Any = None) -> None:
        """Collect rows to a new tab based on the current selection or value."""
        self.do_collect_rows_columns(cidx=cidx, term=term)

    def action_edit_cell(self) -> None:
        """Edit the current cell."""
        self.do_edit_cell()

    def action_edit_column(self) -> None:
        """Edit the entire current column with an expression."""
        self.do_edit_column()

    @with_full_df
    @with_leader_key
    def action_add_column(self) -> None:
        """Add an empty column after the current column."""
        if self.leader_key == "z":
            self.do_add_link_column()
        else:
            self.do_add_column()

    def action_add_column_expr(self) -> None:
        """Add a new column with optional expression after the current column."""
        self.do_add_column_expr()

    @with_full_df
    def action_add_index_column(self) -> None:
        """Add an index column after the current column."""
        self.do_add_index_column()

    @with_full_df
    def action_split_column(self) -> None:
        """Split the current string column into a new column by delimiter."""
        self.do_split_column()

    @with_full_df
    def action_expand_list_column(self) -> None:
        """Expand the current list column into indexed columns."""
        self.do_expand_list_column()

    def action_rename_column(self, col_idx: int | None = None) -> None:
        """Rename the current column."""
        self.do_rename_column(col_idx=col_idx)

    @with_full_df
    def action_clear_cell(self) -> None:
        """Clear the current cell (set to None)."""
        self.do_clear_cell()

    @with_full_df
    def action_clear_column(self) -> None:
        """Clear cells in the current column that match the cursor value."""
        self.do_clear_column()

    def action_select_rows(self) -> None:
        """Select rows with cursor value in the current column."""
        self.do_select_rows()

    def action_select_rows_expr(self) -> None:
        """Select rows by expression."""
        self.do_select_rows_expr()

    @with_leader_key
    def action_find_cursor_value(self) -> None:
        """Find by cursor value in current column or globally across all columns."""
        self.do_find_cursor_value()

    @with_leader_key
    def action_find_expr(self) -> None:
        """Find by expression in current column or globally across all columns."""
        self.do_find_expr()

    @with_leader_key
    def action_replace(self) -> None:
        """Replace values in current column or globally across all columns."""
        scope = "global" if self.leader_key == "g" else "column"
        self.do_replace(scope=scope)

    def action_toggle_selection_current_row(self) -> None:
        """Toggle selection for the current row."""
        self.do_toggle_selection_current_row()

    def action_toggle_selection_current_column(self) -> None:
        """Toggle selection for the current column."""
        self.do_toggle_selection_current_column()

    @with_full_df
    def action_toggle_selections(self) -> None:
        """Toggle all row selections."""
        self.do_toggle_selections()

    @with_full_df
    @with_leader_key
    def action_delete_row(self) -> None:
        """Delete the current row."""
        if self.leader_key == "g":
            self.do_delete_row(more="above")
        elif self.leader_key == "z":
            self.do_delete_row(more="below")
        else:
            self.do_delete_row()

    @with_full_df
    def action_explode_column(self) -> None:
        """Explode the current list column into multiple rows."""
        self.do_explode_column()

    def action_explode_column_delim(self) -> None:
        """Explode the current column by a delimiter into multiple rows."""
        self.do_explode_column_delim()

    @with_full_df
    @with_leader_key
    def action_duplicate_row_column(self) -> None:
        """Duplicate the current row or column."""
        self.do_duplicate_row_column()

    @with_full_df
    @with_leader_key
    def action_undo(self) -> None:
        """Undo the last action."""
        if self.leader_key == "g":
            self.do_reset()
        else:
            self.do_undo()

    @with_full_df
    def action_redo(self) -> None:
        """Redo the last undone action."""
        self.do_redo()

    @with_full_df
    def action_move_column_left(self, col_idx: int | None = None) -> None:
        """Move the current column to the left."""
        self.do_move_column("left", col_idx=col_idx)

    @with_full_df
    def action_move_column_right(self, col_idx: int | None = None) -> None:
        """Move the current column to the right."""
        self.do_move_column("right", col_idx=col_idx)

    @with_full_df
    def action_move_row_up(self) -> None:
        """Move the current row up."""
        self.do_move_row("up")

    @with_full_df
    def action_move_row_down(self) -> None:
        """Move the current row down."""
        self.do_move_row("down")

    def action_clear_selections_and_matches(self) -> None:
        """Clear all row/column selections and cell matches."""
        self.do_clear_selections_and_matches()

    def action_toggle_freeze_row_column(self) -> None:
        """Toggle the freeze."""
        self.do_toggle_freeze_row_column()

    @with_full_df
    def action_cast_column_dtype(self, dtype: str | pl.DataType) -> None:
        """Cast the current column to a different data type."""
        self.do_cast_column_dtype(dtype)

    @with_full_df
    def action_upper_case_column(self) -> None:
        """Convert the current or selected string column(s) to uppercase."""
        self.do_case_column("upper")

    @with_full_df
    def action_lower_case_column(self) -> None:
        """Convert the current or selected string column(s) to lowercase."""
        self.do_case_column("lower")

    def action_copy_cell(self) -> None:
        """Copy the current cell to clipboard."""
        ridx = self.cursor_ridx
        cidx = self.cursor_cidx

        try:
            cell_str = str(self.df.item(ridx, cidx))
            self.do_copy_to_clipboard(cell_str, f"Copied: [$success]{cell_str[:50]}[/]")
        except IndexError:
            self.notify(
                f"Failed to copy cell ([$error]{ridx}[/], [$accent]{cidx}[/]) to clipboard",
                title="Copy Cell",
                severity="error",
            )

    @with_full_df
    def action_copy_column(self) -> None:
        """Copy the current column to clipboard (one value per line)."""
        col_name = self.cursor_col_name

        try:
            # Get all values in the column and join with newlines
            col_values = [str(val) for val in self.df[col_name].to_list()]
            col_str = "\n".join(col_values)

            self.do_copy_to_clipboard(
                col_str,
                f"Copied [$success]{len(col_values)}[/] values from column [$accent]{col_name}[/]",
            )
        except (FileNotFoundError, IndexError):
            self.notify(
                f"Failed to copy column [$error]{col_name}[/] to clipboard", title="Copy Column", severity="error"
            )

    def action_copy_row(self) -> None:
        """Copy the current row to clipboard (values separated by tabs)."""
        ridx = self.cursor_ridx

        try:
            # Get all values in the row and join with tabs
            row_values = [str(val) for val in self.df.row(ridx)]
            row_str = "\t".join(row_values)

            self.do_copy_to_clipboard(
                row_str,
                f"Copied row [$success]{ridx + 1}[/] with [$accent]{len(row_values)}[/] values",
            )
        except (FileNotFoundError, IndexError):
            self.notify(f"Failed to copy row [$error]{ridx}[/] to clipboard", title="Copy Row", severity="error")

    @with_leader_key
    def action_toggle_thousand_separator(self) -> None:
        """Toggle thousand separator for the current cursor column."""
        if self.leader_key == "g":
            if self.thousand_separator_columns:
                self.thousand_separator_columns.clear()
                status = "off"
            else:
                self.thousand_separator_columns = {
                    c for c, dtype in self.visible_columns.items() if DtypeConfig(dtype).gtype in ("integer", "float")
                }

                if not self.thousand_separator_columns:
                    self.notify(
                        "No numeric columns to toggle thousand separator on",
                        title="Toggle Thousand Separator",
                        severity="warning",
                    )
                    return

                status = "on"
        else:
            col_name = self.cursor_col_name
            if col_name in self.thousand_separator_columns:
                self.thousand_separator_columns.discard(col_name)
                status = "off"
            else:
                dtype = self.df[col_name].dtype
                dc = DtypeConfig(dtype)
                if dc.gtype in ("integer", "float"):
                    self.thousand_separator_columns.add(col_name)
                    status = "on"
                else:
                    self.notify(
                        f"Column [$warning]{col_name}[/] is not a numeric column and cannot be formatted as such",
                        title="Toggle Thousand Separator",
                        severity="warning",
                    )
                    return

        self.setup_table()
        message = f"Thousand separator is [$success]{status}[/] for " + (
            "[$accesent]all numeric columns[/]" if self.leader_key == "g" else f"column [$accent]{col_name}[/]"
        )

        self.notify(message, title="Toggle Thousand Separator")

    def action_adjust_float_precision(self, delta: int) -> None:
        """Adjust float precision for the current cursor column."""
        col_name = self.cursor_col_name
        dtype = self.cursor_col_dtype
        dc = DtypeConfig(dtype)
        if dc.gtype != "float":
            self.notify(
                f"Column [$warning]{col_name}[/] is not a float column",
                title="Set Float Precision",
                severity="warning",
            )
            return

        current = self.float_precision_columns.get(col_name, 0)
        new_precision = max(0, current + delta)

        if new_precision == 0:
            self.float_precision_columns.pop(col_name, None)
        else:
            self.float_precision_columns[col_name] = new_precision

        if new_precision != current:
            self.setup_table()

        message = (
            f"Float precision turned [$success]off[/] for column [$accent]{col_name}[/]"
            if new_precision == 0
            else f"Float precision for column [$success]{col_name}[/] set to [$accent]{new_precision}[/] decimal place(s)"
        )
        self.notify(message, title="Set Float Precision")

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

    @with_leader_key
    def action_sql_query(self) -> None:
        """Open the SQL interface screen."""
        if self.leader_key == "z":
            self.do_simple_sql()
        else:
            self.do_advanced_sql()

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

        # # Use the app's set_status_context method to set the current context for status messages
        # self.app._set_status_context(self)

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

        # Check if there are any string or list columns to determine if we need to calculate widths
        has_string_or_list_col = any(dtype == pl.String or dtype == pl.List for dtype in self.df.dtypes)

        # No string columns, let Textual auto-size all columns
        if not has_string_or_list_col:
            return col_widths

        # Get available width for the table (with some padding for borders/scrollbar)
        init_available_width = self.scrollable_content_region.width or self.app.size.width
        available_width = init_available_width

        # Sample a reasonable number of rows to calculate widths (don't scan entire dataframe)
        sample_size = min(self.BATCH_SIZE, len(self.df))
        sample_lf = self.df.lazy().head(sample_size)

        # Determine widths for each visible column
        for col_idx, (col, dtype) in enumerate(self.visible_columns.items(), 1):
            # Get column label width
            label_text = self._build_column_label(col, col_idx)
            label_width = measure(self.app.console, label_text, 1) + 2
            col_label_widths[col] = label_width

            # Let Textual auto-size for non-string and non-list columns and already expanded columns
            if (dtype != pl.String and dtype != pl.List) or col in self.expanded_columns:
                available_width -= label_width
                continue

            try:
                # Get sample values from the column
                sample_values = sample_lf.select(col).collect().get_column(col).drop_nulls().to_list()
                if dtype == pl.String and any(val.startswith(("https://", "http://")) for val in sample_values):
                    continue  # Skip link columns so they can auto-size and be clickable

                # Find maximum width in sample
                # For list columns, measure the string representation of the first three items to avoid extremely long widths
                max_cell_width = max(
                    (
                        measure(self.app.console, str(val[:3]) if isinstance(val, list) else str(val), 1)
                        for val in sample_values
                    ),
                    default=label_width,
                )

                # Set column width to max of label and sampled data (capped at reasonable max)
                max_width = max(label_width, max_cell_width)
            except Exception as e:
                # If any error, let Textual auto-size
                max_width = label_width
                self.log(f"Error determining width for column `{col}`: {e}")

            col_widths[col] = max_width
            available_width -= max_width

        # If there's no more available width, auto-size remaining columns
        if available_width < 0:
            # Recalculate available width after capping wide columns
            available_width = init_available_width
            for col in col_widths:
                if col_widths[col] > COLUMN_WIDTH_CAP and col_label_widths[col] < COLUMN_WIDTH_CAP:
                    col_widths[col] = COLUMN_WIDTH_CAP  # Cap width to prevent extremely wide columns
                available_width -= col_widths[col]

        # If there's still available width, distribute it proportionally to columns that are above the cap
        if available_width > BUFFER_SIZE:
            flexible_cols = [col for col in col_widths if col_widths[col] >= COLUMN_WIDTH_CAP]
            # Only distribute if there's more than one flexible column to avoid giving all extra space to a single column
            if len(flexible_cols) > 1:
                extra_width_per_col = (available_width - BUFFER_SIZE) // len(flexible_cols)
                for col in flexible_cols:
                    new_width = col_widths[col] + extra_width_per_col
                    col_widths[col] = max(new_width, COLUMN_WIDTH_CAP)

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
        for col_idx, (col, dtype) in enumerate(self.visible_columns.items(), 1):
            cell_value = self._build_column_label(col, col_idx)

            # Get the width for this column (None means auto-size)
            width = column_widths.get(col)

            self.add_column(Text(cell_value, justify=DtypeConfig(dtype).justify), key=col, width=width)

    def _build_column_label(self, col_name: str, visible_col_idx: int | None = None) -> str:
        """Build display label for a column header.

        Args:
            col_name: Source dataframe column name.
            visible_col_idx: 1-based index of the column among visible columns.

        Returns:
            Column label text with optional index prefix and sort indicator.
        """
        label = col_name
        if self.show_column_index:
            label = f"{visible_col_idx or self.cursor_column + 1}_{label}"

        for idx, c in enumerate(self.sorted_columns, 1):
            if c == col_name:
                # Add sort indicator to column header
                descending = self.sorted_columns[col_name]
                sort_indicator = (
                    f" ▼{SUBSCRIPT_DIGITS.get(idx, '')}" if descending else f" ▲{SUBSCRIPT_DIGITS.get(idx, '')}"
                )
                label = col_name + sort_indicator
                break

        return label

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

        # Cache visible columns
        visible_columns = self.visible_columns

        # Load the dataframe slice
        df_slice = self.df.slice(segment_start, segment_stop - segment_start)
        thousand_separator = [col in self.thousand_separator_columns for col in visible_columns]
        float_precision = [self.float_precision_columns.get(col, 0) for col in visible_columns]

        # Load each row at the correct position
        for (ridx, row), rid in zip(enumerate(df_slice.iter_rows(), segment_start), df_slice[RID]):
            is_selected = rid in self.selected_rows
            match_cols = self.matches.get(rid, set())

            vals, dtypes, styles = [], [], []
            for val, col, dtype in zip(row, self.df.columns, self.df.dtypes, strict=True):
                if col not in visible_columns:
                    continue

                vals.append(val)
                dtypes.append(dtype)

                # Highlight entire row with selection or cells with matches
                styles.append(
                    HIGHLIGHT_COLOR if is_selected or col in match_cols or col in self.selected_columns else None
                )

            formatted_row = format_row(
                vals,
                dtypes,
                style=styles,
                thousand_separator=thousand_separator,
                float_precision=float_precision,
            )

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
            self.notify(f"Failed to load rows: {e}", title="Load Rows", severity="error")
            self.log(f"Error loading rows: {e}")
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
    def do_go_top(self) -> None:
        """Go to the top of the table."""
        self.move_cursor(row=0)

        self.notify("Moved to top of table", title="Go to Top")

    def do_go_bottom(self) -> None:
        """Go to the bottom of the table."""
        stop = len(self.df)
        start = max(0, stop - self.BATCH_SIZE)

        if start % self.BATCH_SIZE != 0:
            start = (start // self.BATCH_SIZE + 1) * self.BATCH_SIZE

        if stop - start < self.BATCH_SIZE:
            start -= self.BATCH_SIZE

        self.load_rows_range(start, stop)
        self.move_cursor(row=self.row_count - 1)

        self.notify("Moved to bottom of table", title="Go to Bottom")

    def do_go_to_row(self) -> None:
        """Open a modal screen to Go to a specific row."""
        self.app.push_screen(GoToRowScreen(self), callback=self.go_to_row)

    @with_full_df
    def go_to_row(self, result: int | None) -> None:
        """Go to a specific row.

        Args:
            result: The 1-based row index to jump to.
        """
        if result is None:
            return  # User cancelled the prompt

        ridx = result - 1  # Convert to 0-based index in the dataframe
        self.move_cursor_to(ridx, 0)

        self.notify(f"Moved to row {result}", title="Go to Row")

    def do_page_up(self) -> None:
        """Move the cursor one page up."""
        self._set_hover_cursor(False)
        if self.show_cursor and self.cursor_type in ("cell", "row"):
            height = self.scrollable_content_region.height - (self.header_height if self.show_header else 0)

            col_idx = self.cursor_column
            ridx = self.cursor_ridx
            next_ridx = max(0, ridx - height - BUFFER_SIZE)
            start, stop = self._round_to_nearest_hundreds(next_ridx)
            self.load_rows_range(start, stop)

            self.move_cursor(row=self.get_row_idx(str(next_ridx)), column=col_idx)

    def do_page_down(self) -> None:
        """Move the cursor one page down."""
        self.load_rows_down()

    # History & Undo
    def create_history(self, description: str) -> "History":
        """Create the initial history state."""
        return History(
            description=description,
            df=self.df,
            df_view=self.df_view,
            filename=self.filename,
            hidden_columns=self.hidden_columns.copy(),
            selected_rows=self.selected_rows.copy(),
            selected_columns=self.selected_columns.copy(),
            sorted_columns=self.sorted_columns.copy(),
            matches={k: v.copy() for k, v in self.matches.items()},
            fixed_rows=self.fixed_rows,
            fixed_columns=self.fixed_columns,
            cursor_coordinate=self.cursor_coordinate,
            expanded_columns=self.expanded_columns.copy(),
            thousand_separator_columns=self.thousand_separator_columns.copy(),
            float_precision_columns=self.float_precision_columns.copy(),
            show_rid=self.show_rid,
            show_column_index=self.show_column_index,
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
        self.selected_columns = history.selected_columns.copy()
        self.sorted_columns = history.sorted_columns.copy()
        self.matches = {k: v.copy() for k, v in history.matches.items()} if history.matches else defaultdict(set)
        self.fixed_rows = history.fixed_rows
        self.fixed_columns = history.fixed_columns
        self.cursor_coordinate = history.cursor_coordinate
        self.expanded_columns = history.expanded_columns.copy()
        self.thousand_separator_columns = history.thousand_separator_columns.copy()
        self.float_precision_columns = history.float_precision_columns.copy()
        self.show_rid = history.show_rid
        self.show_column_index = history.show_column_index
        self.dirty = history.dirty

        # Recreate table for display
        self.setup_table()

    def add_history(self, description: str, dirty: bool = False, clear_redo: bool = True) -> None:
        """Add the current state to the history stack.

        Args:
            description: Description of the action for this history entry.
            dirty: Whether this operation modifies the data (True) or just display state (False).
            clear_redo: Whether to clear the redo stack. Defaults to True.
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

        self.notify(history.description, title="Undo")

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

        self.notify(description, title="Redo")

    def apply_frame(self, frame: pl.DataFrame | pl.LazyFrame | pl.Series, dirty: bool = True) -> None:
        """Replace the current dataframe from given data and refresh the table.

        Args:
            frame: Data to apply to the table.
            dirty: Whether to mark the table as modified.

        Raises:
            TypeError: If frame is not convertible to a Polars DataFrame.
        """
        if isinstance(frame, pl.Series):
            frame = frame.to_frame()
        elif isinstance(frame, pl.LazyFrame):
            frame = frame.collect()

        if not isinstance(frame, pl.DataFrame):
            raise TypeError(f"Expected a Polars DataFrame, LazyFrame, or Series, got {type(frame).__name__}")

        frame = add_rid_column(frame)

        self.df = frame
        self.df_view = None
        self.loaded_rows = 0
        self.loaded_ranges.clear()
        self.hidden_columns.clear()
        self.selected_rows.clear()
        self.selected_columns.clear()
        self.sorted_columns.clear()
        self.matches.clear()
        self.fixed_rows = 0
        self.fixed_columns = 0
        self.histories_undo.clear()
        self.histories_redo.clear()
        self.expanded_columns.clear()
        self.thousand_separator_columns = set()
        self.float_precision_columns = {}
        self.df_done = True
        self.dirty = dirty
        self.show_rid = False
        self.show_column_index = False
        self.setup_table()

    def do_reset(self) -> None:
        """Reset the table to the initial state."""
        self.apply_frame(self.dataframe, dirty=False)
        self.notify("Restored to initial state", title="Reset")

    # Display
    @with_leader_key
    def do_cycle_cursor_type(self) -> None:
        """Cycle through cursor types: cell -> row -> column -> cell."""
        next_type = get_next_item(CURSOR_TYPES, self.cursor_type)
        self.cursor_type = next_type

        self.notify(f"Cursor type is now [$success]{next_type}[/]", title="Cycle Cursor Type")

    def do_view_row_detail(self) -> None:
        """Open a modal screen to view the selected row's details."""
        ridx = self.cursor_ridx

        # Push the modal screen
        self.app.push_screen(RowDetailScreen(self, ridx))

    def do_view_cell_detail(self) -> None:
        """Open a modal screen to view the selected cell's details."""
        cidx = self.cursor_cidx
        col_name = self.df.columns[cidx]
        dtype = self.df.dtypes[cidx]
        cell_value = self.cursor_value

        if dtype == pl.String and cell_value:
            # String contains the delimiter '|' (indicating a potential list of values)
            if "|" in cell_value:
                self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))
            # Show long string in a text screen for better readability
            elif len(cell_value) > COLUMN_WIDTH_CAP:
                self.app.push_screen(TextScreen(cell_value))

        # Show cell detail screen if the value is a non-empty list
        elif dtype == pl.List and not cell_value.is_empty():
            if len(cell_value) == 1 and isinstance(cell_value[0], str) and len(cell_value[0]) > COLUMN_WIDTH_CAP:
                self.app.push_screen(TextScreen(cell_value[0]))
            else:
                self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))

        # or a non-empty dict (struct)
        elif dtype == pl.Struct and cell_value:
            self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))

    def do_show_frequency(self, cidx: int | list[int] | None = None) -> None:
        """Show frequency distribution for one or more columns.

        Args:
            cidx: Optional target column index or indices. If None and multiple columns are selected,
                the frequency table is computed over the selected visible columns.
        """
        if self.selected_columns:
            self.app.push_screen(FrequencyScreen(self, [self.df.columns.index(col) for col in self.selected_columns]))
            return

        if cidx is None:
            selected_visible = [col for col in self.df.columns if col in self.selected_columns]
            if len(selected_visible) > 1:
                cidx = [self.df.columns.index(col) for col in selected_visible]
            else:
                cidx = self.cursor_cidx

        # Push the frequency modal screen
        self.app.push_screen(FrequencyScreen(self, cidx))

    def do_show_histogram(self, default: int = 1) -> None:
        """Show histogram for a given columnn."""
        dtype = self.cursor_col_dtype
        dc = DtypeConfig(dtype)

        if dc.gtype not in ("integer", "float"):
            self.notify(
                f"Cannot show histogram for non-numeric column [$warning]{self.cursor_col_name}[/] of type [$accent]{dtype}[/]",
                title="Show Histogram",
                severity="warning",
            )
            return

        if default:
            self.show_histogram((None, None))
        else:
            min_value = self.df[self.cursor_col_name].min()
            max_value = self.df[self.cursor_col_name].max()
            self.app.push_screen(CustomBinScreen(min_value, max_value), callback=self.show_histogram)

    def show_histogram(self, result) -> None:
        """Show histogram with the given parameters.

        Args:
            result: Tuple of (column index, bin count) from the histogram settings screen.
        """
        if result is None:
            return

        bin_count, bins = result
        self.app.push_screen(HistogramScreen(self, bins=bins, bin_count=bin_count))

    @with_full_df
    def do_show_bar(self) -> None:
        """Show bar chart using first selected column as label and cursor column as value."""
        if not self.selected_columns:
            self.notify(
                "Select a column first to use as the label",
                title="Show Bar Chart",
                severity="warning",
            )
            return

        col_label_name = next(col for col in self.df.columns if col in self.selected_columns)
        col_value_name = self.cursor_col_name

        cidx = self.df.columns.index(col_value_name)
        dtype = self.df.dtypes[cidx]
        dc = DtypeConfig(dtype)

        if dc.gtype not in ("integer", "float"):
            self.notify(
                f"Cannot show bar chart for non-numeric column [$warning]{col_value_name}[/] of type [$accent]{dtype}[/]",
                title="Show Bar Chart",
                severity="warning",
            )
            return

        cidx_label = self.df.columns.index(col_label_name)
        self.app.push_screen(BarScreen(self, cidx, cidx_label))

    def do_show_statistics(self, cidx: int | None = None) -> None:
        """Show statistics for the current column or entire dataframe."""
        # Show statistics for entire dataframe
        if self.leader_key == "g":
            self.app.push_screen(StatisticsScreen(self, cidx=None))
        # Show statistics for current column
        else:
            self.app.push_screen(StatisticsScreen(self, cidx=self.cursor_cidx if cidx is None else cidx))

    def do_metadata_column(self) -> None:
        """Show metadata for all columns in the dataframe."""
        self.app.push_screen(MetaColumnScreen(self))

    def do_toggle_freeze_row_column(self) -> None:
        """Toggle the freeze."""
        if self.fixed_rows or self.fixed_columns:
            self.fixed_rows = self.fixed_columns = 0
            self.notify("Unfreezed all rows and columns", title="Freeze Row/Column")
        else:
            self.app.push_screen(FreezeScreen(), callback=self.toggle_freeze_row_column)

    def toggle_freeze_row_column(self, result: tuple[int, int] | None) -> None:
        """Handle result from PinScreen.

        Args:
            result: Tuple of (fixed_rows, fixed_columns) or None if cancelled.
        """
        if result is None:
            return
        fixed_rows, fixed_columns = result

        if fixed_rows > 0 and fixed_columns > 0:
            descr = f"Freezed [$success]{fixed_rows}[/] rows and [$accent]{fixed_columns}[/] columns"
        elif fixed_rows > 0:
            descr = f"Freezed [$success]{fixed_rows}[/] rows"
        elif fixed_columns > 0:
            descr = f"Freezed [$success]{fixed_columns}[/] columns"
        else:
            return

        # Add to history
        self.add_history(descr)

        # Apply the pin settings to the table
        if fixed_rows >= 0:
            self.fixed_rows = fixed_rows
        if fixed_columns >= 0:
            self.fixed_columns = fixed_columns

        self.notify(descr, title="Freeze Row/Column")

    def do_hide_column(self, more: str | None = None) -> None:
        """Hide columns from the table display.

        Args:
            more: If "before", hide current column and all before it.
                  If "after", hide current column and all after it.
                  If None, hide selected columns or current column.
        """
        col_idx = self.cursor_column
        col_name = self.cursor_col_name

        if more == "before":
            target_columns = [self.get_col_key(i).value for i in range(col_idx + 1)]
            descr = f"Hide column [$success]{col_name}[/] and all columns before"
        elif more == "after":
            target_columns = [self.get_col_key(i).value for i in range(col_idx, len(self.columns))]
            descr = f"Hide column [$success]{col_name}[/] and all columns after"
        else:
            target_columns = [col for col in self.visible_columns if col in self.selected_columns]
            if not target_columns:
                target_columns = [self.cursor_col_name]
            descr = (
                f"Hide column [$success]{target_columns[0]}[/]"
                if len(target_columns) == 1
                else f"Hide [$accent]{len(target_columns)}[/] selected columns"
            )

        # Add to history before mutating the display state.
        self.add_history(descr)

        for col_name in target_columns:
            col_key = ColumnKey(col_name)
            if col_key not in self.columns:
                continue
            self.remove_column(col_key)
            self.hidden_columns.add(col_name)
            self.selected_columns.discard(col_name)

        # Recompute labels for remaining visible columns when prefixes are shown.
        if self.show_column_index:
            for idx, col in enumerate(self.ordered_columns, start=1):
                col.label = self._build_column_label(col.key.value, idx)
                self.refresh_column(idx - 1)

        # Move cursor left if we hid the last visible column.
        if self.columns and self.cursor_column >= len(self.columns):
            self.move_cursor(column=len(self.columns) - 1)

        self.notify(f"{descr}. Press [$success]g[/][$accent]v[/] to show hidden columns", title="Hide Column")

    def _expand_single_column(self, col_name: str) -> str | None:
        """Expand or unexpand a single column. Returns a status message fragment, or None on failure."""
        cidx = self.df.columns.index(col_name)
        col_key = self.get_col_key(cidx)
        col: Column = self.columns[col_key]

        label_width = len(self._build_column_label(col_name)) + 2

        # If already expanded, shrink back
        if col_name in self.expanded_columns:
            col.width = max(label_width, COLUMN_WIDTH_CAP)
            self.expanded_columns.remove(col_name)
            return f"[$success]{col_name}[/] shrunk to [$accent]{col.width}[/]"

        # Otherwise, expand to widest cell
        try:
            new_width = label_width
            need_expand = False

            for row_start, row_end in self.loaded_ranges:
                for ridx in range(row_start, row_end):
                    cell_value = str(self.df.item(ridx, cidx))
                    cell_width = measure(self.app.console, cell_value, 1)
                    if cell_width > new_width:
                        need_expand = True
                        new_width = cell_width

            if not need_expand:
                return None

            self.expanded_columns.add(col_name)
            col.width = new_width
            return f"[$success]{col_name}[/] expanded to [$accent]{new_width}[/]"

        except Exception as e:
            self.log(f"Error expanding column `{col_name}`: {e}")
            return None

    def do_expand_column(self) -> None:
        """Expand/unexpand string/list columns.

        In leader mode: expand or unexpand all string/list columns.
        Otherwise: expand or unexpand the current column only.
        """
        if self.leader_key == "g":
            # Collect all string/list column names
            target_cols = [
                col for col, dtype in self.visible_columns.items() if DtypeConfig(dtype).gtype in ("string", "list")
            ]

            if not target_cols:
                # self.notify("No string/list columns to expand", title="Expand Columns")
                return

            results = []
            for col_name in target_cols:
                result = self._expand_single_column(col_name)
                if result:
                    results.append(result)

            if not results:
                return

            self._update_count += 1
            self._require_update_dimensions = True
            self.refresh(layout=True)

            self.notify(
                f"Toggled {len(results)} column(s)",
                title="Expand Columns",
            )
        else:
            dtype = self.cursor_col_dtype
            if dtype != pl.String and dtype != pl.List:
                return

            col_name = self.cursor_col_key.value
            result = self._expand_single_column(col_name)
            if not result:
                return

            self._update_count += 1
            self._require_update_dimensions = True
            self.refresh(layout=True)

            self.notify(f"Column {result}", title="Expand Column")

    @with_leader_key
    def do_toggle_rid(self) -> None:
        """Toggle display of the internal RID column."""
        self.add_history("Toggle RID column display")
        self.show_rid = not self.show_rid

        # Recreate table for display
        self.setup_table()

        self.notify(
            f"{'Showing' if self.show_rid else 'Hiding'} internal RID column. Press [$success]z[/][$accent]^[/] to toggle.",
            title="Toggle RID",
        )

    @with_leader_key
    def do_toggle_column_index(self) -> None:
        """Toggle display of column index prefixes in headers."""
        self.add_history("Toggle column index display")

        self.show_column_index = not self.show_column_index
        self.setup_table()
        status = "on" if self.show_column_index else "off"
        self.notify(f"Column index prefix is [$success]{status}[/]", title="Toggle Column Index")

    @with_full_df
    @with_leader_key
    def do_set_cursor_row_as_header(self) -> None:
        """Set cursor row as the new header row."""
        ridx = self.cursor_ridx

        # Get the new header values
        new_header = list(self.df.row(ridx))
        new_header[-1] = RID  # Ensure last column remains RID

        # Handle duplicate column names by appending suffixes
        seen = {}
        for i, col in enumerate(new_header):
            if col in seen:
                seen[col] += 1
                new_header[i] = f"{col}_{seen[col]}"
            else:
                seen[col] = 0

        # Create a mapping of old column names to new column names
        col_rename_map = {old_col: str(new_col) for old_col, new_col in zip(self.df.columns, new_header)}

        # Add to history
        self.add_history(f"Set row [$success]{ridx + 1}[/] as header", dirty=False)

        # Rename columns in the dataframe
        self.df = self.df.slice(ridx + 1).rename(col_rename_map)

        # Write to string buffer
        buffer = io.StringIO()
        self.df.write_csv(buffer)

        # Re-read with schema inference to get correct dtypes
        try:
            buffer.seek(0)
            self.df = pl.read_csv(buffer)
        except Exception as e:
            self.log(f"Error setting row {ridx} as header: {e}")
            # Try again without inferring schema (all columns as string) to at least update the header
            try:
                buffer.seek(0)
                self.df = pl.read_csv(buffer, infer_schema=False)
            except Exception as e2:
                self.notify(
                    f"Failed to set row as header even without inferring schema: {e2}",
                    title="Set Row as Header",
                    severity="error",
                )
                self.log(f"Error setting row {ridx} as header without inferring schema: {e2}")
                return

        # Recreate table for display
        self.setup_table()

        # Move cursor to first column
        self.move_cursor(row=ridx, column=0)

        self.notify(f"Set row [$success]{ridx + 1}[/] as header", title="Set Row as Header")

    def do_show_hidden_columns(self) -> None:
        """Show all hidden columns by recreating the table."""
        if not self.hidden_columns:
            self.notify("No hidden columns to show", title="Show Hidden Column(s)", severity="warning")
            return

        # Add to history
        self.add_history("Show hidden column(s)")

        # Clear hidden columns tracking
        self.hidden_columns.clear()

        # Recreate table for display
        self.setup_table()

        self.notify("Displayed hidden column(s)", title="Show Hidden Column(s)")

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
        self.add_history(f"Sort on column [$success]{col_name}[/]", dirty=True)

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

        if not sort_cols:
            self.notify("Restored original order", title="Sort")
        elif col_name not in sort_cols:
            self.notify(f"Removed column [$success]{col_name}[/] from sort", title="Sort")
        else:
            self.notify(
                f"Sorted by column [$success]{col_name}[/] in {'descending' if descending else 'ascending'} order. Press again to remove from sort.",
                title="Sort",
            )

    # Edit
    def do_edit_cell(self, ridx: int | None = None, cidx: int | None = None) -> None:
        """Open modal to edit the selected cell."""
        ridx = self.cursor_ridx if ridx is None else ridx
        cidx = self.cursor_cidx if cidx is None else cidx

        # Push the edit modal screen
        self.app.push_screen(
            EditCellScreen(ridx, cidx, self.df),
            callback=self.edit_cell,
        )

    @with_full_df
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
        self.add_history(f"Edit cell [$success]({ridx + 1}, {col_name})[/]", dirty=True)

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

            self.notify(f"Updated cell to [$success]{cell_value}[/]", title="Edit Cell")
        except Exception as e:
            self.notify(
                f"Failed to update cell ([$error]{ridx}[/], [$accent]{col_name}[/])",
                title="Edit Cell",
                severity="error",
            )
            self.log(f"Error updating cell ({ridx}, {col_name}): {e}")

    def do_edit_column(self) -> None:
        """Open modal to edit the entire column with an expression."""
        cidx = self.cursor_cidx

        # Push the edit column modal screen
        self.app.push_screen(
            EditColumnScreen(cidx, self.df),
            callback=self.edit_column,
        )

    @with_full_df
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
                expr = validate_expr(term, self.df.columns, cidx, self.df)
            except Exception as e:
                self.notify(f"Failed to validate expression [$error]{term}[/]", title="Edit Column", severity="error")
                self.log(f"Error validating expression `{term}`: {e}")
                return

        # Otherwise, treat term as a literal value
        else:
            dtype = self.df.dtypes[cidx]
            try:
                value = DtypeConfig(dtype).convert(term)
                expr = pl.lit(value)
            except Exception:
                self.notify(
                    f"Failed to convert [$error]{term}[/] to [$accent]{dtype}[/]. Casting to string.",
                    title="Edit Column",
                    severity="error",
                )
                expr = pl.lit(str(term))

        # Add to history
        self.add_history(f"Edit column [$success]{col_name}[/] with expression", dirty=True)

        try:
            # Apply the expression to the column
            self.df = self.df.lazy().with_columns(expr.alias(col_name)).collect()

            # Also update the view if applicable
            # Update the value of col_name in df_view using the value of col_name from df based on RID mapping between them
            if self.df_view is not None:
                # Get updated column from df
                lf_updated = self.df.lazy().select(RID, pl.col(col_name))
                # Update df_view by joining on RID
                self.df_view = self.df_view.lazy().update(lf_updated, on=RID, include_nulls=True).collect()
        except Exception as e:
            self.notify(
                f"Failed to apply expression [$error]{term}[/] to column [$accent]{col_name}[/]",
                title="Edit Column",
                severity="error",
            )
            self.log(f"Error applying expression `{term}` to column `{col_name}`: {e}")
            return

        # Recreate table for display
        self.setup_table()

        self.notify(f"Updated column [$success]{col_name}[/] with [$accent]{expr}[/]", title="Edit Column")

    def do_rename_column(self, col_idx: int | None = None) -> None:
        """Open modal to rename the selected column."""
        col_idx = self.cursor_column if col_idx is None else col_idx
        col_name = self.get_col_key(col_idx).value

        # Push the rename column modal screen
        self.app.push_screen(
            RenameColumnScreen(col_idx, col_name, self.df.columns),
            callback=self.rename_column,
        )

    @with_full_df
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
        self.add_history(f"Rename column [$success]{col_name}[/] to [$accent]{new_name}[/]", dirty=True)

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

        # Defer table rebuild until after modal is fully closed
        self.call_later(self.setup_table)

        # Move cursor to the renamed column
        self.move_cursor(column=col_idx)

        self.notify(f"Renamed column [$success]{col_name}[/] to [$accent]{new_name}[/]", title="Rename Column")

    def do_clear_cell(self) -> None:
        """Clear the current cell by setting its value to None."""
        row_key, col_key = self.cursor_key
        ridx = self.cursor_ridx
        col_name = self.cursor_col_name
        dtype = self.cursor_col_dtype

        # Add to history
        self.add_history(f"Clear cell [$success]({ridx + 1}, {col_name})[/]", dirty=True)

        # Update the cell to None in the dataframe
        try:
            self.df = (
                self.df.lazy()
                .with_columns(
                    pl.when(pl.arange(0, len(self.df)) == ridx)
                    .then(pl.lit(None))
                    .otherwise(pl.col(col_name))
                    .alias(col_name)
                )
                .collect()
            )

            # Also update the view if applicable
            if self.df_view is not None:
                ridx_view = self.df.item(ridx, self.df.columns.index(RID))
                self.df_view = (
                    self.df_view.lazy()
                    .with_columns(
                        pl.when(pl.col(RID) == ridx_view).then(pl.lit(None)).otherwise(pl.col(col_name)).alias(col_name)
                    )
                    .collect()
                )

            # Update the display
            dc = DtypeConfig(dtype)
            formatted_value = Text(NULL_DISPLAY, style=dc.style, justify=dc.justify)

            self.update_cell(row_key, col_key, formatted_value)

            self.notify(f"Cell cleared to [$success]{NULL_DISPLAY}[/]", title="Clear Cell")
        except Exception as e:
            self.notify(
                f"Failed to clear cell ([$error]{ridx}[/], [$accent]{col_name}[/])",
                title="Clear Cell",
                severity="error",
            )
            self.log(f"Error clearing cell ({ridx}, {col_name}): {e}")

    def do_clear_column(self) -> None:
        """Clear cells in the current column that match the cursor value by setting them to None."""
        col_idx = self.cursor_column
        col_name = self.cursor_col_name
        value = self.cursor_value

        # Add to history
        self.add_history(f"Clear column [$success]{col_name}[/]", dirty=True)

        try:
            # Update the entire column to None in the dataframe
            self.df = (
                self.df.lazy()
                .with_columns(
                    pl.when(pl.col(col_name) == value).then(pl.lit(None)).otherwise(pl.col(col_name)).alias(col_name)
                )
                .collect()
            )

            # Also update the view if applicable
            if self.df_view is not None:
                lf_updated = self.df.lazy().select(RID, pl.col(col_name))
                self.df_view = self.df_view.lazy().update(lf_updated, on=RID, include_nulls=True).collect()

            # Recreate table for display
            self.setup_table()

            # Move cursor to the cleared column
            self.move_cursor(column=col_idx)

            self.notify(
                f"Cleared cells matching [$success]{value}[/] in column [$accent]{col_name}[/]", title="Clear Column"
            )
        except Exception as e:
            self.notify(f"Failed to clear column [$error]{col_name}[/]", title="Clear Column", severity="error")
            self.log(f"Error clearing column `{col_name}`: {e}")

    def _get_column_name(self, colname) -> str:
        """Get a unique column name based on the provided name."""
        if colname not in self.df.columns:
            return colname

        base_name = colname
        counter = 1
        new_col_name = f"{base_name}_{counter}"
        while new_col_name in self.df.columns:
            counter += 1
            new_col_name = f"{base_name}_{counter}"
        return new_col_name

    def do_add_column(self, col_name: str | None = None) -> None:
        """Add acolumn after the current column."""
        cidx = self.cursor_cidx

        # Generate a unique column name
        if not col_name:
            new_col_name = self._get_column_name("new_col")
        else:
            new_col_name = col_name

        # Add to history
        self.add_history(f"Add column [$success]{new_col_name}[/] after column [$accent]{cidx + 1}[/]", dirty=True)

        try:
            # Create an empty column (all None values)
            new_col = pl.lit(None).alias(new_col_name)

            # Get columns up to current, the new column, then remaining columns
            cols = self.df.columns
            cols_before = cols[: cidx + 1]
            cols_after = cols[cidx + 1 :]

            # Build the new dataframe with columns reordered
            select_cols = cols_before + [new_col] + cols_after
            self.df = self.df.lazy().with_columns(new_col).select(select_cols).collect()

            # Also update the view if applicable
            if self.df_view is not None:
                self.df_view = self.df_view.lazy().with_columns(new_col).select(select_cols).collect()

            # Recreate table for display
            self.setup_table()

            # Move cursor to the new column
            self.move_cursor(column=cidx + 1)

            self.notify(f"Added column [$success]{new_col_name}[/]", title="Add Column")
        except Exception as e:
            self.notify(f"Failed to add column [$error]{new_col_name}[/]", title="Add Column", severity="error")
            self.log(f"Error adding column `{new_col_name}`: {e}")

    def do_add_column_expr(self) -> None:
        """Open screen to add a new column with optional expression."""
        cidx = self.cursor_cidx
        self.app.push_screen(
            AddColumnScreen(cidx, self.df),
            self.add_column_expr,
        )

    @with_full_df
    def add_column_expr(self, result: tuple[int, str, pl.Expr] | None) -> None:
        """Add a new column with an expression."""
        if result is None:
            return

        cidx, new_col_name, expr = result

        # Add to history
        self.add_history(f"Add column [$success]{new_col_name}[/] with expression [$accent]{expr}[/].", dirty=True)

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

            self.notify(f"Added column [$success]{new_col_name}[/]", title="Add Column")
        except Exception as e:
            self.notify(f"Failed to add column [$error]{new_col_name}[/]", title="Add Column", severity="error")
            self.log(f"Error adding column `{new_col_name}`: {e}")

    def do_add_index_column(self, start: int = 1, step: int = 1) -> None:
        """Add an index column after the current column.

        Args:
            start: Starting value for the sequence. Defaults to 1.
            step: Step between values in the sequence. Defaults to 1.
        """
        cidx = self.cursor_cidx
        new_col_name = self._get_column_name("index")

        # Add to history
        self.add_history(
            f"Add index column [$success]{new_col_name}[/] after column [$accent]{cidx + 1}[/]", dirty=True
        )

        try:
            if step == 0:
                step = 1

            # Create a sequential column using the requested start and step.
            index_values = pl.Series(new_col_name, range(start, start + (step * len(self.df)), step))

            # Get columns up to current, the new column, then remaining columns.
            cols = self.df.columns
            cols_before = cols[: cidx + 1]
            cols_after = cols[cidx + 1 :]

            # Build the new dataframe with columns reordered.
            select_cols = cols_before + [new_col_name] + cols_after
            self.df = self.df.lazy().with_columns(index_values).select(select_cols).collect()

            # Also update the view if applicable.
            if self.df_view is not None:
                view_index_values = pl.Series(new_col_name, range(start, start + (step * len(self.df_view)), step))
                self.df_view = self.df_view.lazy().with_columns(view_index_values).select(select_cols).collect()

            # Recreate table for display.
            self.setup_table()

            # Move cursor to the new column.
            self.move_cursor(column=cidx + 1)

            self.notify(
                f"Added index column [$success]{new_col_name}[/] starting at [$accent]{start}[/] with step [$accent]{step}[/]",
                title="Add Index Column",
            )
        except Exception as e:
            self.notify(
                f"Failed to add index column [$error]{new_col_name}[/]", title="Add Index Column", severity="error"
            )
            self.log(f"Error adding index column `{new_col_name}`: {e}")

    def do_split_column(self) -> None:
        """Open a confirmation screen to split the current string column into a new column."""
        col_name = self.cursor_col_name
        dtype = self.cursor_col_dtype

        if dtype != pl.String:
            self.notify(
                f"Column [$warning]{col_name}[/] is not a string column",
                title="Split Column",
                severity="warning",
            )
            return

        self.app.push_screen(
            ConfirmScreen(
                "Split Column",
                label=f"Enter the delimiter to split [$success]{col_name}[/] into a new column",
                input="|",
            ),
            callback=self.split_column,
        )

    @with_full_df
    def split_column(self, result: str | None) -> None:
        """Split the current string column into a new list column.

        Args:
            result: Delimiter entered by the user.
        """
        if result is None:
            return

        delimiter = result
        if delimiter == "":
            self.notify("Delimiter cannot be empty", title="Split Column", severity="warning")
            return

        cidx = self.cursor_cidx
        col_name = self.cursor_col_name
        new_col_name = self._get_column_name(f"{col_name}_split")

        self.add_history(
            f"Split column [$success]{col_name}[/] into [$success]{new_col_name}[/] using delimiter [$accent]{delimiter}[/]",
            dirty=True,
        )

        try:
            new_col = pl.col(col_name).str.split(delimiter).alias(new_col_name)

            cols = self.df.columns
            cols_before = cols[: cidx + 1]
            cols_after = cols[cidx + 1 :]
            select_cols = cols_before + [new_col_name] + cols_after

            self.df = self.df.lazy().with_columns(new_col).select(select_cols).collect()

            if self.df_view is not None:
                self.df_view = self.df_view.lazy().with_columns(new_col).select(select_cols).collect()

            self.setup_table()
            self.move_cursor(column=self.cursor_column + 1)

            self.notify(
                f"Split column [$success]{col_name}[/] into [$success]{new_col_name}[/] using delimiter [$accent]{delimiter}[/]",
                title="Split Column",
            )
        except Exception as e:
            if self.histories_undo:
                self.histories_undo.pop()
            self.notify(
                f"Failed to split column [$error]{col_name}[/] with delimiter [$accent]{delimiter}[/]",
                title="Split Column",
                severity="error",
            )
            self.log(f"Error splitting column `{col_name}` with delimiter `{delimiter}`: {e}")

    @with_full_df
    def do_expand_list_column(self) -> None:
        """Expand the current list column into multiple indexed columns.

        Example: ``items`` -> ``items_1``, ``items_2``, ... based on the
        maximum list length found in the column.
        """
        cidx = self.cursor_cidx
        col_name = self.cursor_col_name
        dtype = self.cursor_col_dtype

        if dtype != pl.List:
            self.notify(
                f"Column [$warning]{col_name}[/] is not a list column",
                title="Expand List Column",
                severity="warning",
            )
            return

        max_len = self.df[col_name].list.len().max()
        if not max_len:
            self.notify(
                f"Column [$warning]{col_name}[/] has no list items to expand",
                title="Expand List Column",
                severity="warning",
            )
            return

        max_len = int(max_len)
        used_names = set(self.df.columns)
        new_col_names: list[str] = []

        for idx in range(1, max_len + 1):
            base_name = f"{col_name}_{idx}"
            new_name = base_name
            suffix = 1
            while new_name in used_names:
                new_name = f"{base_name}_{suffix}"
                suffix += 1
            used_names.add(new_name)
            new_col_names.append(new_name)

        self.add_history(
            f"Expand list column [$success]{col_name}[/] into [$accent]{len(new_col_names)}[/] columns",
            dirty=True,
        )

        try:
            new_exprs = [pl.col(col_name).list.get(i).alias(new_col_names[i]) for i in range(max_len)]

            cols = self.df.columns
            select_cols = cols[:cidx] + new_col_names + cols[cidx + 1 :]

            self.df = self.df.lazy().with_columns(new_exprs).select(select_cols).collect()

            if self.df_view is not None:
                self.df_view = self.df_view.lazy().with_columns(new_exprs).select(select_cols).collect()

            self.setup_table()
            self.move_cursor(column=cidx)

            self.notify(
                f"Expanded [$success]{col_name}[/] into [$accent]{len(new_col_names)}[/] indexed columns",
                title="Expand List Column",
            )
        except Exception as e:
            if self.histories_undo:
                self.histories_undo.pop()
            self.notify(
                f"Failed to expand list column [$error]{col_name}[/]",
                title="Expand List Column",
                severity="error",
            )
            self.log(f"Error expanding list column `{col_name}`: {e}")

    def do_add_link_column(self) -> None:
        """Open AddLinkScreen to collect a link template and add a new link column."""
        self.app.push_screen(
            AddLinkScreen(self.cursor_cidx, self.df),
            callback=self.add_link_column,
        )

    def add_link_column(self, result: tuple[str, str, str] | None) -> None:
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
            f"Add link column [$success]{new_col_name}[/] with template [$accent]{link_template}[/].", dirty=True
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
            self.notify(f"Failed to add link column [$error]{new_col_name}[/]", title="Add Link", severity="error")
            self.log(f"Error adding link column: {e}")

    def do_delete_column(self, more: str | None = None, col_idx: int | None = None) -> None:
        """Remove selected columns when present, otherwise the current column."""
        # Get the column to remove
        if col_idx is None:
            col_idx = self.cursor_column

        col_key = self.get_col_key(col_idx)
        col_name = col_key.value

        col_names_to_delete = []
        col_keys_to_delete = []

        # Remove all columns before the current column
        if more == "before":
            for i in range(col_idx + 1):
                col_key = self.get_col_key(i)
                col_names_to_delete.append(col_key.value)
                col_keys_to_delete.append(col_key)

            message = f"Deleted column [$success]{col_name}[/] and all columns before"

        # Remove all columns after the current column
        elif more == "after":
            for i in range(col_idx, len(self.columns)):
                col_key = self.get_col_key(i)
                col_names_to_delete.append(col_key.value)
                col_keys_to_delete.append(col_key)

            message = f"Deleted column [$success]{col_name}[/] and all columns after"

        # Remove selected visible columns, or fall back to the current column.
        else:
            selected_visible_columns = [col for col in self.visible_columns if col in self.selected_columns]
            if selected_visible_columns:
                col_names_to_delete.extend(selected_visible_columns)
                col_keys_to_delete.extend(ColumnKey(col) for col in selected_visible_columns)
                message = (
                    f"Deleted column [$success]{selected_visible_columns[0]}[/]"
                    if len(selected_visible_columns) == 1
                    else f"Deleted [$accent]{len(selected_visible_columns)}[/] selected columns"
                )
            else:
                col_names_to_delete.append(col_name)
                col_keys_to_delete.append(col_key)
                message = f"Deleted column [$success]{col_name}[/]"

        # Add to history
        self.add_history(message, dirty=True)

        # Remove from sorted columns if present
        for col_name in col_names_to_delete:
            if col_name in self.sorted_columns:
                del self.sorted_columns[col_name]

        # Remove from hidden columns if present
        for col_name in col_names_to_delete:
            self.hidden_columns.discard(col_name)
            self.selected_columns.discard(col_name)

        # Remove from matches
        for rid in list(self.matches.keys()):
            self.matches[rid].difference_update(col_names_to_delete)
            # Remove empty entries
            if not self.matches[rid]:
                del self.matches[rid]

        # Remove from dataframe
        self.df = self.df.lazy().drop(col_names_to_delete).collect()

        # Also update the view if applicable
        if self.df_view is not None:
            self.df_view = self.df_view.lazy().drop(col_names_to_delete).collect()

        # Recreate table for display
        self.setup_table()

        # Move cursor left if we deleted the last column(s)
        last_col_idx = len(self.columns) - 1
        if self.columns and col_idx > last_col_idx:
            self.move_cursor(column=last_col_idx)

        self.notify(message, title="Delete Column")

    def do_explode_column(self) -> None:
        """Explode the current list column into multiple rows."""
        col_name = self.cursor_col_name
        dtype = self.cursor_col_dtype

        # Only explode list or string columns (string columns will be split by delimiter)
        if dtype not in (pl.List, pl.String):
            return

        self.task_done = False
        self.app.push_screen(BusyScreen(self, task=partial(self.explode_column, col_name)))

    def do_explode_column_delim(self) -> None:
        """Open screen to explode a string column based on delimiter."""
        col_name = self.cursor_col_name
        dtype = self.cursor_col_dtype

        # Only explode string columns
        if not isinstance(dtype, pl.String):
            return

        self.app.push_screen(
            ExplodeColumnScreen(self.df, col_name),
            callback=self.explode_column_delim,
        )

    @with_full_df
    def explode_column_delim(self, result) -> None:
        """Handle result from ExplodeColumnScreen and launch the delimiter-based explode task."""
        if result is None:
            return
        col_name, delimiter = result

        self.task_done = False
        self.app.push_screen(BusyScreen(self, task=partial(self.explode_column, col_name, delimiter)))

    @work(thread=True)
    def explode_column(self, col_name: str, delimiter: str | None = "|") -> None:
        """Explode a column based on a delimiter (if provided) or as a list column."""
        self.add_history(f"Explode column [$success]{col_name}[/]", dirty=True)

        dtype = self.df.schema[col_name]

        try:
            if self.df_view is not None:
                old_rids = set(self.df[RID])

                # If it's already a list column, just explode it
                if dtype == pl.List:
                    lf_view = add_rid_column(self.df_view.lazy().rename({RID: RID_OLD}).explode(col_name))
                # If a delimiter is provided, split the string column by the delimiter
                elif dtype == pl.String and delimiter:
                    lf_view = add_rid_column(
                        self.df_view.lazy()
                        .rename({RID: RID_OLD})
                        .with_columns(pl.col(col_name).str.split(delimiter))
                        .explode(col_name)
                    )
                else:
                    return

                self.df = lf_view.filter(pl.col(RID_OLD).is_in(old_rids)).drop(RID_OLD).collect()
                self.df_view = lf_view.drop(RID_OLD).collect()
            else:
                if dtype == pl.List:
                    self.df = add_rid_column(self.df.lazy().drop(RID).explode(col_name)).collect()
                elif dtype == pl.String and delimiter:
                    self.df = add_rid_column(
                        self.df.lazy().drop(RID).with_columns(pl.col(col_name).str.split(delimiter)).explode(col_name)
                    ).collect()
                else:
                    return

            self.selected_rows.clear()
            self.matches = defaultdict(set)

            self.task_done = True
            self.setup_table()

            self.notify(f"Exploded column [$success]{col_name}[/]", title="Explode Column")
        except Exception as e:
            if self.histories_undo:
                self.histories_undo.pop()
            self.notify(
                f"Failed to explode column [$error]{col_name}[/] with delimiter [$accent]{delimiter}[/]",
                title="Explode Column with Delimiter",
                severity="error",
            )
            self.log(f"Error exploding column `{col_name}` with delimiter `{delimiter}`: {e}")

    def do_delete_row(self, more: str | None = None) -> None:
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
            ridx = self.cursor_ridx
            history_desc = f"Deleted current row [$success]{ridx + 1}[/] and those above"
            for rid in self.df[RID][: ridx + 1]:
                rids_to_delete.add(rid)

        # Delete current row and those below
        elif more == "below":
            ridx = self.cursor_ridx
            history_desc = f"Deleted current row [$success]{ridx + 1}[/] and those below"
            for rid in self.df[RID][ridx:]:
                rids_to_delete.add(rid)

        # Delete the row at the cursor
        else:
            ridx = self.cursor_ridx
            history_desc = f"Deleted row [$success]{ridx + 1}[/]"
            rids_to_delete.add(self.df[RID][ridx])

        # Add to history
        self.add_history(history_desc, dirty=True)

        # Apply the filter to remove rows
        try:
            df_filtered = self.df.lazy().filter(~pl.col(RID).is_in(rids_to_delete)).collect()
        except Exception as e:
            self.notify(f"Failed to delete row(s): {e}", title="Delete Row(s)", severity="error")
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
            self.notify(f"Deleted [$success]{deleted_count}[/] row(s)", title="Delete Row(s)")

    def do_duplicate_row_column(self) -> None:
        """Duplicate the currently selected row or column."""
        if self.leader_key == "z":
            self.do_duplicate_column()
        else:
            self.do_duplicate_row()

    def do_duplicate_row(self) -> None:
        """Duplicate the currently selected row, inserting it right after the current row."""
        ridx = self.cursor_ridx
        rid = self.df[RID][ridx]

        lf = self.df.lazy()

        # Get the row to duplicate
        row_to_duplicate = lf.slice(ridx, 1).with_columns(pl.col(RID) + 1)

        # Add to history
        self.add_history(f"Duplicate row [$success]{ridx + 1}[/]", dirty=True)

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

        self.notify(f"Duplicated row [$success]{ridx + 1}[/]", title="Duplicate Row")

    def do_duplicate_column(self) -> None:
        """Duplicate the currently selected column, inserting it right after the current column."""
        cidx = self.cursor_cidx
        col_name = self.cursor_col_name

        col_idx = self.cursor_column
        new_col_name = f"{col_name}_copy"

        # Ensure new column name is unique
        counter = 1
        while new_col_name in self.df.columns:
            new_col_name = f"{new_col_name}{counter}"
            counter += 1

        # Add to history
        self.add_history(f"Duplicate column [$success]{col_name}[/]", dirty=True)

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

        self.notify(
            f"Duplicated column [$success]{col_name}[/] as [$accent]{new_col_name}[/]", title="Duplicate Column"
        )

    @with_full_df
    def do_uniq_rows(self) -> None:
        """Remove duplicate rows from the current dataframe, keeping the first occurrence."""
        subset = list(self.visible_columns.keys())
        unique_df = self.df.unique(subset=subset, keep="first", maintain_order=True)
        removed_count = len(self.df) - len(unique_df)

        if removed_count <= 0:
            return

        self.add_history(f"Remove [$success]{removed_count}[/] duplicate row(s)", dirty=True)

        ok_rids = set(unique_df[RID])
        self.df = unique_df

        if self.selected_rows:
            self.selected_rows.intersection_update(ok_rids)

        if self.matches:
            self.matches = {rid: cols for rid, cols in self.matches.items() if rid in ok_rids}

        if self.df_view is not None:
            self.df_view = self.df_view.lazy().filter(pl.col(RID).is_in(ok_rids)).collect()

        self.setup_table()

        self.notify(
            f"Removed [$success]{removed_count}[/] duplicate row(s), now [$accent]{len(self.df)}[/] row(s) remaining",
            title="Unique Rows",
        )

    def do_move_column(self, direction: str, col_idx: int | None = None) -> None:
        """Move the current column left or right.

        Args:
            direction: "left" to move left, "right" to move right.
        """
        row_idx = self.cursor_row
        if col_idx is None:
            col_idx = self.cursor_column

        col_key = self.get_col_key(col_idx)
        col_name = col_key.value
        cidx = self.df.columns.index(col_name)

        # Validate move is possible
        if direction == "left":
            if col_idx <= 0:
                self.notify("Cannot move column left", title="Move Column", severity="warning")
                return
            swap_idx = col_idx - 1
        elif direction == "right":
            if col_idx >= len(self.columns) - 1:
                self.notify("Cannot move column right", title="Move Column", severity="warning")
                return
            swap_idx = col_idx + 1

        # Get column to swap
        _, swap_key = self.coordinate_to_cell_key(Coordinate(row_idx, swap_idx))
        swap_name = swap_key.value
        swap_cidx = self.df.columns.index(swap_name)

        # Add to history
        self.add_history(
            f"Move column [$success]{col_name}[/] [$accent]{direction}[/] (swapped with [$success]{swap_name}[/])",
            dirty=True,
        )

        # Update the dataframe column order
        cols = list(self.df.columns)
        cols[cidx], cols[swap_cidx] = cols[swap_cidx], cols[cidx]
        self.df = self.df.lazy().select(cols).collect()

        # Also update the view if applicable
        if self.df_view is not None:
            self.df_view = self.df_view.lazy().select(cols).collect()

        # Recreate table for display
        self.setup_table()

        # Restore cursor position on the moved column
        self.move_cursor(row=row_idx, column=swap_idx)

        self.notify(f"Moved column [$success]{col_name}[/] {direction}", title="Move Column")

    def do_move_row(self, direction: str) -> None:
        """Move the current row up or down.

        Args:
            direction: "up" to move up, "down" to move down.
        """
        curr_row_idx, col_idx = self.cursor_coordinate

        # Validate move is possible
        if direction == "up":
            if curr_row_idx <= 0:
                self.notify("Cannot move row up", title="Move Row", severity="warning")
                return
            swap_row_idx = curr_row_idx - 1
        elif direction == "down":
            if curr_row_idx >= len(self.rows) - 1:
                self.notify("Cannot move row down", title="Move Row", severity="warning")
                return
            swap_row_idx = curr_row_idx + 1
        else:
            # Invalid direction
            return

        # Add to history
        self.add_history(
            f"Move row [$success]{curr_row_idx}[/] [$accent]{direction}[/] (swapped with row [$success]{swap_row_idx}[/])",
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

        self.notify(f"Moved row [$success]{curr_key.value}[/] {direction}", title="Move Row")

    def do_transpose(self) -> None:
        """Transpose the dataframe, swapping rows and columns."""
        if not self.visible_columns:
            self.notify("No data columns available to transpose", title="Transpose", severity="warning")
            return

        try:
            self.add_history("Transpose table", dirty=True)

            # Use apply_frame so reset/rebuild behavior stays consistent with other table-wide mutations.
            transposed = (
                self.df.lazy()
                .select(list(self.visible_columns.keys()))
                .collect()
                .transpose(include_header=True, header_name="column")
            )
            self.apply_frame(transposed, dirty=True)
            self.notify("Transposed table", title="Transpose")
        except Exception as e:
            if self.histories_undo:
                self.histories_undo.pop()
            self.notify(f"Failed to transpose table: {e}", title="Transpose", severity="error")
            self.log(f"Error transposing table: {e}")

    # Type casting
    def do_cast_column_dtype(self, dtype: str) -> None:
        """Cast the current column to a different data type.

        Args:
            dtype: Target data type (string representation, e.g., "pl.String", "pl.Int64")
        """
        col_name = self.cursor_col_name
        current_dtype = self.cursor_col_dtype

        try:
            target_dtype = eval(dtype)
        except Exception:
            self.notify(f"Invalid target data type: [$error]{dtype}[/]", title="Cast Column", severity="error")
            return

        if current_dtype == target_dtype:
            self.notify(
                f"Column [$warning]{col_name}[/] is already of type [$accent]{target_dtype}[/]",
                title="Cast Column",
                severity="warning",
            )
            return  # No change needed

        # Add to history
        self.add_history(
            f"Cast column [$success]{col_name}[/] from [$accent]{current_dtype}[/] to [$accent]{target_dtype}[/]",
            dirty=True,
        )

        try:
            # Cast the column using Polars
            if target_dtype == pl.Date:
                if current_dtype == pl.String:
                    self.df = self.df.with_columns(pl.col(col_name).str.to_date())
                elif current_dtype == pl.Datetime:
                    self.df = self.df.with_columns(pl.col(col_name).dt.date())
                else:
                    self.df = self.df.with_columns(pl.col(col_name).cast(target_dtype))
            else:
                self.df = self.df.with_columns(pl.col(col_name).cast(target_dtype))

            # Also update the view if applicable
            if self.df_view is not None:
                self.df_view = self.df_view.with_columns(pl.col(col_name).cast(target_dtype))

            # Recreate table for display
            self.setup_table()

            self.notify(f"Cast column [$success]{col_name}[/] to [$accent]{target_dtype}[/]", title="Cast")
        except Exception as e:
            self.notify(
                f"Failed to cast column [$error]{col_name}[/] to [$accent]{target_dtype}[/]",
                title="Cast Column",
                severity="error",
            )
            self.log(f"Error casting column `{col_name}`: {e}")

    def do_case_column(self, case: str) -> None:
        """Convert string column(s) to uppercase or lowercase.

        Applies the transformation to all selected string columns when a column
        selection is active; otherwise applies to the current cursor column.

        Args:
            case: ``"upper"`` to convert to uppercase, ``"lower"`` to convert to lowercase.
        """
        label = "uppercase" if case == "upper" else "lowercase"

        # Resolve target columns: selected string columns or current column.
        target_cols = [
            col for col, dtype in self.visible_columns.items() if col in self.selected_columns and dtype == pl.String
        ]
        if not target_cols:
            col_name = self.cursor_col_name
            if self.cursor_col_dtype != pl.String:
                self.notify(
                    f"Column [$warning]{col_name}[/] is not a string column",
                    title=f"Convert to {label.capitalize()}",
                    severity="warning",
                )
                return
            target_cols = [col_name]

        if len(target_cols) == 1:
            descr = f"Convert column [$success]{target_cols[0]}[/] to {label}"
        else:
            descr = f"Convert [$accent]{len(target_cols)}[/] columns to {label}"

        self.add_history(descr, dirty=True)

        transforms = [
            (pl.col(c).str.to_uppercase() if case == "upper" else pl.col(c).str.to_lowercase()).alias(c)
            for c in target_cols
        ]
        self.df = self.df.with_columns(transforms)

        if self.df_view is not None:
            self.df_view = self.df_view.with_columns(transforms)

        self.setup_table()
        self.notify(descr, title=f"Convert to {label.capitalize()}")

    # Find & Replace
    @with_full_df
    def find_matches(
        self,
        term: str,
        cidx: int | None = None,
        match_nocase: bool = False,
        match_whole: bool = False,
        match_literal: bool = False,
        match_reverse: bool = False,
    ) -> dict[int, set[str]]:
        """Find matches for a term in the dataframe.

        Args:
            term: The search term (can be NULL, expression, or plain text)
            cidx: Column index for column-specific search. If None, searches all columns.
            match_nocase: Whether to perform case-insensitive matching (for string terms)
            match_whole: Whether to match the whole cell content (for string terms)
            match_literal: Whether to treat the search term as a literal string (disables regex)
            match_reverse: Whether to reverse the match (i.e., find non-matching rows)

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
        if cidx is None:
            columns_to_search = list(enumerate(self.df.columns))
        else:
            columns_to_search = [(cidx, self.df.columns[cidx])]

        # Handle each column consistently
        for col_idx, col_name in columns_to_search:
            # Build expression based on term type
            if term == NULL:
                expr = pl.col(col_name).is_null()
            elif term == "":
                if self.df.dtypes[col_idx] == pl.String:
                    expr = pl.col(col_name) == ""
                else:
                    expr = pl.col(col_name).is_null()
            elif tentative_expr(term):
                try:
                    expr = validate_expr(term, self.df.columns, col_idx, self.df)
                except Exception as e:
                    self.notify(f"Failed to validate expression [$error]{term}[/]", title="Find", severity="error")
                    self.log(f"Error validating expression `{term}`: {e}")
                    return matches
            else:
                expr = handle_term(term, col_name, match_nocase, match_whole, match_literal, cast_to_str=True)

            # Reverse the expression if requested
            if match_reverse:
                expr = ~expr

            # Get matched row indices
            try:
                matched_ridxs = lf.filter(expr).collect()[RID]
            except Exception as e:
                self.notify(f"Failed to apply filter [$error]{expr}[/]", title="Find", severity="error")
                self.log(f"Error applying filter: {e}")
                return matches

            for ridx in matched_ridxs:
                matches[ridx].add(col_name)

        return matches

    def do_find_cursor_value(self) -> None:
        """Find by cursor value.

        Scope is determined by leader mode: current column by default, or global when in leader mode.
        """
        # Get the value of the currently selected cell
        term = NULL if self.cursor_value is None else str(self.cursor_value)
        cidx = self.cursor_cidx

        self.find(
            {
                "term": term,
                "cidx": cidx,
                "match_nocase": False,
                "match_whole": True,
                "match_literal": True,
                "match_reverse": False,
            },
            scope="global" if self.leader_key == "g" else "column",
        )

    def do_find_expr(self) -> None:
        """Open screen to find by expression.

        Scope is determined by leader mode: current column by default, or global when in leader mode.
        """
        # Use current cell value as default search term
        term = NULL if self.cursor_value is None else str(self.cursor_value)
        cidx = self.cursor_cidx
        scope = "global" if self.leader_key == "g" else "column"

        # Push the search modal screen
        self.app.push_screen(
            SearchScreen("Find" if scope == "column" else "Global Find", self.df, cidx, term),
            callback=partial(self.find, scope=scope),
        )

    @with_full_df
    def find(self, result: dict, scope="column") -> None:
        """Find a term in current column or globally across all columns.

        Args:
            result: A dictionary with keys "term", "cidx", "match_nocase", "match_whole", "match_literal", "match_reverse".
            scope: "column" to find in current column, "global" to find across all columns. Defaults to "column".
        """
        if result is None:
            return
        term = result.get("term")
        cidx = result.get("cidx", self.cursor_cidx)
        match_nocase = result.get("match_nocase")
        match_whole = result.get("match_whole")
        match_literal = result.get("match_literal")
        match_reverse = result.get("match_reverse")

        col_name = self.df.columns[cidx] if scope == "column" else "all columns"
        title = "Find" if scope == "column" else "Global Find"
        cidx = cidx if scope == "column" else None

        try:
            matches = self.find_matches(
                term=term,
                cidx=cidx,
                match_nocase=match_nocase,
                match_whole=match_whole,
                match_literal=match_literal,
                match_reverse=match_reverse,
            )
        except Exception as e:
            self.notify(f"Failed to find matches for [$error]{term}[/]", title=title, severity="error")
            self.log(f"Error finding matches for `{term}`: {e}")
            return

        if not matches:
            self.notify(
                f"No matches found for [$warning]{term}[/] in [$accent]{col_name}[/]. Try other search options.",
                title=title,
                severity="warning",
            )
            return

        # Add to history
        self.add_history(f"Find [$success]{term}[/] in [$accent]{col_name}[/]")

        # Update matches and count total
        match_count = sum(len(cols) for cols in matches.values())
        self.matches = matches

        message = f"Found [$success]{match_count}[/] matches for `[$accent]{term}[/]`"
        message += f" in [$accent]{col_name}[/]" if scope == "column" else " across all columns"
        self.notify(message, title=title)

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
        current_pos = (self.cursor_ridx, self.cursor_cidx)

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
        current_pos = (self.cursor_ridx, self.cursor_cidx)

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
        current_ridx = self.cursor_ridx

        # Find the next selected row after current position
        for ridx in selected_row_indices:
            if ridx > current_ridx:
                self.move_cursor_to(ridx, self.cursor_cidx)
                return

        # If no next selected row, wrap around to the first selected row
        first_ridx = selected_row_indices[0]
        self.move_cursor_to(first_ridx, self.cursor_cidx)

    def do_previous_selected_row(self) -> None:
        """Move cursor to the previous selected row."""
        if not self.selected_rows:
            self.notify("No selected rows to navigate", title="Previous Selected Row", severity="warning")
            return

        # Get list of selected row indices in order
        selected_row_indices = self.ordered_selected_rows

        # Current cursor row
        current_ridx = self.cursor_ridx

        # Find the previous selected row before current position
        for ridx in reversed(selected_row_indices):
            if ridx < current_ridx:
                self.move_cursor_to(ridx, self.cursor_cidx)
                return

        # If no previous selected row, wrap around to the last selected row
        last_ridx = selected_row_indices[-1]
        self.move_cursor_to(last_ridx, self.cursor_cidx)

    def do_replace(self, scope="column") -> None:
        """Open replace screen for current column or globally across all columns."""
        # Push the replace modal screen
        title = "Find and Replace" if scope == "column" else "Global Find and Replace"
        self.app.push_screen(
            FindReplaceScreen(title, self),
            callback=partial(self.replace, scope=scope),
        )

    def replace(self, result, scope="column") -> None:
        """Handle replace in current column or globally across all columns."""
        self.handle_replace(result, self.cursor_cidx if scope == "column" else None)

    def handle_replace(self, result: dict, cidx) -> None:
        """Handle replace result.

        Args:
            result: A dictionary containing the replace parameters.
            cidx: Column index to perform replacement. If None, replace across all columns.
        """
        if result is None:
            return
        replace_all = result.get("replace_all")
        term_find = result.get("term_find")
        term_replace = result.get("term_replace")
        match_nocase = result.get("match_nocase")
        match_whole = result.get("match_whole")
        match_literal = result.get("match_literal")

        if cidx is None:
            col_name = "all columns"
        else:
            col_name = self.df.columns[cidx]

        # Find all matches
        matches = self.find_matches(
            term=term_find,
            cidx=cidx,
            match_nocase=match_nocase,
            match_whole=match_whole,
            match_literal=match_literal,
            match_reverse=False,
        )

        if not matches:
            self.notify(f"No matches found for [$warning]{term_find}[/]", title="Replace", severity="warning")
            return

        # Add to history
        self.add_history(
            f"Replace [$success]{term_find}[/] with [$success]{term_replace}[/] in column [$accent]{col_name}[/]"
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
            match_literal=match_literal,
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
                f"Failed to replace [$error]{term_find}[/] with [$accent]{term_replace}[/]",
                title="Replace",
                severity="error",
            )
            self.log(f"Error replacing `{term_find}` with `{term_replace}`: {e}")

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
                new_value = (
                    pl.lit(None)
                    if state.term_replace == NULL
                    else pl.col(col_name).str.replace_all(term_find, state.term_replace, literal=state.match_literal)
                )
                self.df = self.df.with_columns(
                    pl.when(mask).then(new_value).otherwise(pl.col(col_name)).alias(col_name)
                )
            else:
                if state.term_replace == NULL:
                    value = None
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
                lf_updated = self.df.lazy().filter(mask).select(pl.col(RID), pl.col(col_name))
                self.df_view = self.df_view.lazy().update(lf_updated, on=RID, include_nulls=True).collect()

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
                f"Failed to replace [$error]{term_find}[/] with [$accent]{term_replace}[/]",
                title="Replace",
                severity="error",
            )
            self.log(f"Error in interactive replace: {e}")

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
        label = f"Replace `[$success]{state.term_find}[/]` with `[$accent]{state.term_replace}[/]` ({state.current_occurrence} of {state.total_occurrence})?"

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
                new_value = (
                    pl.lit(None)
                    if state.term_replace == NULL
                    else pl.col(col_name).str.replace_all(term_find, state.term_replace, literal=state.match_literal)
                )
                self.df = self.df.with_columns(
                    pl.when(pl.arange(0, len(self.df)) == ridx)
                    .then(new_value)
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
                if state.term_replace == NULL:
                    value = None
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
            if new_cell_value is None:
                new_cell_value = NULL_DISPLAY
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

    # Filter & Collect
    def do_filter_rows(self, result: dict | None = None) -> None:
        """Filter rows.

        If there are selected rows, view those, Otherwise, view based on the cursor value.
        """
        if result is not None:
            self.filter_rows(result)
        else:
            cidx = self.cursor_cidx
            col_name = self.cursor_col_name
            dtype = self.cursor_col_dtype

            # If there are selected rows, use those
            if self.selected_rows:
                term = pl.col(RID).is_in(self.selected_rows)
            # Otherwise, use the current cell value
            else:
                value = self.cursor_value
                term = (
                    pl.col(col_name).is_null()
                    if value is None
                    else pl.col(col_name) == value.to_list()
                    if isinstance(dtype, pl.List)
                    else pl.col(col_name) == value
                )

            self.filter_rows(
                {
                    "term": term,
                    "cidx": cidx,
                    "match_nocase": False,
                    "match_whole": True,
                    "match_literal": True,
                    "match_reverse": False,
                }
            )

    def do_filter_rows_non_null(self) -> None:
        """Filter non-null rows."""
        cidx = self.cursor_cidx
        col_name = self.cursor_col_name
        dtype = self.cursor_col_dtype
        term = pl.col(col_name).list.len() > 0 if isinstance(dtype, pl.List) else pl.col(col_name).is_not_null()

        self.filter_rows(
            {
                "term": term,
                "cidx": cidx,
                "match_nocase": False,
                "match_whole": True,
                "match_literal": True,
                "match_reverse": False,
            }
        )

    def do_filter_rows_expr(self) -> None:
        """Open the filter screen to enter an expression."""
        cidx = self.cursor_cidx
        dtype = self.cursor_col_dtype
        value = self.cursor_value
        term = NULL if value is None else (str(value.to_list()) if isinstance(dtype, pl.List) else str(value))

        self.app.push_screen(
            SearchScreen("Filter Rows", self.df, cidx, term),
            callback=self.filter_rows,
        )

    @with_full_df
    def filter_rows(self, result) -> None:
        """Filter selected rows and hide others. Do not modify the dataframe.

        Args:
            result: A dictionary with keys "term", "cidx", "match_nocase", "match_whole", "match_literal", "match_reverse"
        """
        if result is None:
            return
        term = result.get("term", NULL)
        cidx = result.get("cidx", self.cursor_cidx)
        match_nocase = result.get("match_nocase", False)
        match_whole = result.get("match_whole", False)
        match_literal = result.get("match_literal", False)
        match_reverse = result.get("match_reverse", False)

        col_name = self.df.columns[cidx]
        dtype = self.df.dtypes[cidx]

        # Support for polars expression
        if isinstance(term, pl.Expr):
            expr = term

        # Support for list of booleans (selected rows)
        elif isinstance(term, (list, pl.Series)):
            expr = term

        # Null case
        elif term == NULL:
            expr = pl.col(col_name).is_null()

        # Empty string case
        elif term == "":
            if dtype == pl.String:
                expr = pl.col(col_name) == ""
            else:
                expr = pl.col(col_name).is_null()

        # Support for polars expression in string form
        elif tentative_expr(term):
            try:
                expr = validate_expr(term, self.df.columns, cidx, self.df)
            except Exception as e:
                self.notify(f"Failed to validate expression [$error]{term}[/]", title="View Rows", severity="error")
                self.log(f"Error validating expression `{term}`: {e}")
                return

        # Type-aware search based on column dtype
        else:
            if dtype == pl.String:
                expr = handle_term(term, col_name, match_nocase, match_whole, match_literal)
            elif dtype == pl.List and isinstance(term, str):
                # list
                if term.startswith("[") and term.endswith("]"):
                    try:
                        list_value = eval(term)

                        if isinstance(list_value, list):
                            expr = pl.col(col_name) == list_value
                        else:
                            expr = pl.col(col_name) == term
                            self.notify(
                                f"Invalid list format for column [$warning]{col_name}[/]. Cast to string.",
                                title="View Rows",
                            )
                    except Exception as e:
                        expr = pl.col(col_name) == term
                        self.notify(
                            f"Failed to evaluate values for column [$warning]{col_name}[/]. Casting to string.",
                            title="View Rows",
                        )
                        self.log(f"Error evaling term `{term}` for list column `{col_name}`: {e}")
                # element
                else:
                    expr = pl.col(col_name).list.contains(term)
            else:
                try:
                    value = DtypeConfig(dtype).convert(term)
                    expr = pl.col(col_name) == value
                except Exception:
                    expr = handle_term(term, col_name, match_nocase, match_whole, match_literal, cast_to_str=True)
                    self.notify(
                        f"Unknown column type [$warning]{dtype}[/]. Cast to string.",
                        title="View Rows",
                        severity="warning",
                    )

        # Lazyframe with row indices
        lf = self.df.lazy()

        # Reverse the expression if requested
        if match_reverse:
            expr = ~expr
        expr_str = "boolean list or series" if isinstance(expr, (list, pl.Series)) else str(expr)

        # Add to history
        self.add_history(f"View rows by expression [$success]{expr_str}[/]")

        # Apply the filter expression
        try:
            df_filtered = lf.filter(expr).collect()
        except Exception as e:
            self.histories_undo.pop()  # Remove last history entry
            self.notify(f"Failed to apply filter [$error]{expr_str}[/]", title="View Rows", severity="error")
            self.log(f"Error applying filter `{expr_str}`: {e}")
            return

        matched_count = len(df_filtered)
        if not matched_count:
            self.histories_undo.pop()  # Remove last history entry
            self.notify(
                f"No rows match the expression: [$warning]{expr_str}[/]",
                title="View Rows",
                severity="warning",
                markup=True,
            )
            return

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

        self.notify(f"Displayed [$success]{matched_count}[/] matching row(s)", title="View Rows")

    def do_filter_rows_value(self) -> None:
        """Filter current dataframe rows by a condition on the current numeric column.

        For integer/float columns, opens FilterNumericColumn to collect conditions.
        The filtered result replaces self.df; the original is saved in self.df_view.
        For other dtypes, a warning is shown.
        """
        cidx = self.cursor_cidx
        col_name = self.cursor_col_name
        dtype = self.cursor_col_dtype
        dc = DtypeConfig(dtype)

        if dc.gtype in ("integer", "float"):
            self.app.push_screen(
                FilterNumericScreen(self.df[col_name], cidx, dc, self.cursor_value),
                callback=self.filter_row_value,
            )
        elif dc.gtype == "string":
            self.app.push_screen(
                FilterStringScreen(self.df[col_name], cidx, self.cursor_value),
                callback=self.filter_row_value,
            )
        elif dc.gtype == "boolean":
            self.app.push_screen(
                FilterBooleanScreen(self.df[col_name], cidx, self.cursor_value),
                callback=self.filter_row_value,
            )
        elif dc.gtype == "temporal":
            self.app.push_screen(
                FilterTemporalScreen(self.df[col_name], cidx, dc, self.cursor_value),
                callback=self.filter_row_value,
            )
        elif dtype == pl.List:
            self.app.push_screen(
                FilterListScreen(self.df[col_name], cidx, self.cursor_value),
                callback=self.filter_row_value,
            )
        else:
            self.notify(
                f"Filter by value not implemented for [$warning]{col_name}[/] with type of [$accent]{dtype}[/].",
                title="Filter Rows",
                severity="warning",
            )

    @with_full_df
    def filter_row_value(self, result: tuple[pl.Expr, int] | None) -> None:
        """Apply the filter expression in the current column.

        Args:
            result: A tuple containing a Polars expression to filter rows and the column index, or None if cancelled.
        """
        if result is None:
            return
        expr, cidx = result

        if expr is None:
            self.notify("No filter expression provided.", title="Filter Rows", severity="warning")
            return

        try:
            df_filtered = self.df.lazy().filter(expr).collect()
        except Exception as e:
            self.notify(f"Failed to apply filter [$error]{expr}[/]", title="Filter Rows", severity="error")
            self.log(f"Error applying filter `{expr}`: {e}")
            return

        if len(df_filtered) == 0:
            self.notify("Filter results in zero row. No changes applied.", title="Filter Rows", severity="warning")
            return

        col_name = self.cursor_col_name
        self.add_history(f"Filter rows on column [$success]{col_name}[/] by expression")

        # Store original dataframe in df_view if not already in a view
        if self.df_view is None:
            self.df_view = self.df

        ok_rids = set(df_filtered[RID])
        self.df = df_filtered

        if self.selected_rows:
            self.selected_rows.intersection_update(ok_rids)

        if self.matches:
            self.matches = {rid: cols for rid, cols in self.matches.items() if rid in ok_rids}

        self.setup_table()
        self.move_cursor(column=cidx)

        self.notify(
            f"Showing [$success]{len(df_filtered)}[/] matching row(s) in column [$accent]{col_name}[/]",
            title="Filter Rows",
        )

    def do_collect_rows_columns(self, cidx: int | None = None, term: Any | list[Any] = None) -> None:
        """Collect rows/columns to a new tab.

        If there are selected rows/columns, use those.
        Otherwise, use the current cell value as the search term to determine which rows to collect.
        """
        if self.selected_rows:
            filter_expr = pl.col(RID).is_in(self.selected_rows)
        elif self.selected_columns:
            filter_expr = pl.lit(True)  # No row filter, just select columns later
        else:  # Search cursor value in current column
            cidx = self.cursor_cidx if cidx is None else cidx
            col_name = self.df.columns[cidx]
            dtype = self.df.dtypes[cidx]
            term = self.cursor_value if term is None else term

            if isinstance(term, pl.Expr):
                filter_expr = term
            elif term is None or term == NULL:
                filter_expr = pl.col(col_name).is_null()
            elif isinstance(dtype, pl.List):
                filter_expr = pl.col(col_name) == term.to_list()
            elif isinstance(term, list):
                filter_expr = pl.col(col_name).is_in(term)
            else:
                filter_expr = pl.col(col_name) == term

        # Apply filter to dataframe with row indices
        lf_filtered = self.df.lazy().filter(filter_expr)

        # Apply column selection if any
        if self.selected_columns:
            lf_filtered = lf_filtered.select(self.selected_columns.copy().union({RID}))

        # Collect the filtered dataframe
        df_filtered = lf_filtered.collect()

        if len(df_filtered) == 0:
            self.notify("Filter results in zero rows. No new tab created.", title="Filter Rows", severity="warning")
            return
        elif len(df_filtered) == len(self.df) and len(df_filtered.columns) == len(self.df.columns):
            self.notify(
                "Filter does not reduce any rows/columns. No new tab created.", title="Filter Rows", severity="warning"
            )
            return

        self.app.add_tab(
            df_filtered,
            filename="filtered_results.csv",
            tabname="filtered-results",
            after=self.app.tabbed.active_pane,
        )

    # Row selection
    def do_select_rows(self) -> None:
        """Select rows.

        If there are existing cell matches, use those to select rows.
        Otherwise, use the current cell value as the search term and select rows matching that value.
        """
        cidx = self.cursor_cidx

        # Use existing cell matches if present
        if self.matches:
            term = pl.col(RID).is_in(self.matches)
        else:
            col_name = self.cursor_col_name
            dtype = self.cursor_col_dtype
            value = self.cursor_value

            # Get the value of the currently selected cell
            if value is None:
                term = pl.col(col_name).is_null()
            elif isinstance(dtype, pl.List):
                term = pl.col(col_name) == value.to_list()
            else:
                term = pl.col(col_name) == value

        self.select_rows(
            {
                "term": term,
                "cidx": cidx,
                "match_nocase": False,
                "match_whole": True,
                "match_literal": True,
                "match_reverse": False,
            }
        )

    def do_select_rows_expr(self) -> None:
        """Select rows by expression."""
        cidx = self.cursor_cidx
        dtype = self.cursor_col_dtype
        value = self.cursor_value

        # Use current cell value as default search term
        term = NULL if value is None else (str(value.to_list()) if isinstance(dtype, pl.List) else str(value))

        # Push the search modal screen
        self.app.push_screen(
            SearchScreen("Select Rows", self.df, cidx, term),
            callback=self.select_rows,
        )

    @with_full_df
    def select_rows(self, result: dict) -> None:
        """Select rows by value or expression.

        Args:
            result: A dictionary with keys "term", "cidx", "match_nocase", "match_whole", "match_literal", "match_reverse"
        """
        if result is None:
            return
        term = result.get("term")
        cidx = result.get("cidx", self.cursor_cidx)
        match_nocase = result.get("match_nocase")
        match_whole = result.get("match_whole")
        match_literal = result.get("match_literal")
        match_reverse = result.get("match_reverse")

        col_name = self.df.columns[cidx]
        dtype = self.df.dtypes[cidx]

        # Already a Polars expression
        if isinstance(term, pl.Expr):
            expr = term

        # bool list or Series
        elif isinstance(term, (list, pl.Series)):
            expr = term

        # Null case
        elif term == NULL:
            expr = pl.col(col_name).is_null()

        # Empty string case
        elif term == "":
            if dtype == pl.String:
                expr = pl.col(col_name) == ""
            else:
                expr = pl.col(col_name).is_null()

        # Expression in string form
        elif tentative_expr(term):
            try:
                expr = validate_expr(term, self.df.columns, cidx, self.df)
            except Exception as e:
                self.notify(f"Failed to validate expression [$error]{term}[/]", title="Select Rows", severity="error")
                self.log(f"Error validating expression `{term}`: {e}")
                return

        # Perform type-aware search based on column dtype
        else:
            if dtype == pl.String:
                expr = handle_term(term, col_name, match_nocase, match_whole, match_literal)
            elif dtype == pl.List and isinstance(term, str):
                # list
                if term.startswith("[") and term.endswith("]"):
                    try:
                        list_value = eval(term)
                        if isinstance(list_value, list):
                            expr = pl.col(col_name) == list_value
                        else:
                            expr = pl.col(col_name) == term
                            self.notify(
                                f"Invalid list format for column [$warning]{col_name}[/]. Cast to string.",
                                title="Select Rows",
                            )
                    except Exception as e:
                        expr = pl.col(col_name) == term
                        self.notify(
                            f"Failed to evaluate values for column [$warning]{col_name}[/]. Casting to string.",
                            title="Select Rows",
                        )
                        self.log(f"Error evaling term `{term}` for list column `{col_name}`: {e}")
                # element
                else:
                    expr = pl.col(col_name).list.contains(term)
            else:
                try:
                    value = DtypeConfig(dtype).convert(term)
                    expr = pl.col(col_name) == value
                except Exception:
                    expr = handle_term(term, col_name, match_nocase, match_whole, match_literal, cast_to_str=True)
                    self.notify(
                        f"Failed to convert [$warning]{term}[/] to [$accent]{dtype}[/]. Casting to string.",
                        title="Select Rows",
                        severity="warning",
                    )

        # Reverse the expression if requested
        if match_reverse:
            expr = ~expr

        # Lazyframe for filtering
        lf = self.df.lazy()

        # Apply filter to get matched row indices
        try:
            ok_rids = set(lf.filter(expr).collect()[RID])
        except Exception as e:
            self.notify(f"Failed to apply filter [$error]{term}[/]", title="Select Rows", severity="error")
            self.log(f"Error applying filter `{term}`: {e}")
            return

        match_count = len(ok_rids)
        if match_count == 0:
            self.notify(
                f"No matches found for [$warning]{term}[/]. Try other search options.",
                title="Select Rows",
                severity="warning",
            )
            return

        # Add to history
        self.add_history("Select rows by expression")

        # Update selected rows
        self.selected_rows = ok_rids

        # Show notification immediately, then start highlighting
        self.notify(f"Found [$success]{match_count}[/] matching row(s)", title="Select Rows")

        # Recreate table for display
        self.setup_table()

    def do_toggle_selections(self) -> None:
        """Toggle selected rows highlighting on/off."""
        # Add to history
        self.add_history("Toggle row selection")

        # Invert all selected rows
        self.selected_rows = {rid for rid in self.df[RID] if rid not in self.selected_rows}

        # Check if we're highlighting or un-highlighting
        if selected_count := len(self.selected_rows):
            self.notify(f"Toggled selection for [$success]{selected_count}[/] rows", title="Toggle Selection(s)")

        # Recreate table for display
        self.setup_table()

    def do_toggle_selection_current_row(self) -> None:
        """Select/deselect current row."""
        # Add to history
        self.add_history("Toggle row selection")

        # Get current row RID
        ridx = self.cursor_ridx
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

    def do_toggle_selection_current_column(self) -> None:
        """Select/deselect current column."""
        # Add to history
        self.add_history("Toggle column selection")

        # Get current column name
        col_name = self.cursor_col_name

        if col_name in self.selected_columns:
            self.selected_columns.discard(col_name)
        else:
            self.selected_columns.add(col_name)

        # Recreate table for display
        self.setup_table()

    def do_clear_selections_and_matches(self) -> None:
        """Clear all selected rows/columns and matches without changing the dataframe."""
        # Check if any selected rows or matches
        if not self.selected_rows and not self.selected_columns and not self.matches:
            self.notify("No selections to clear", title="Clear Selections and Matches", severity="warning")
            return

        # Add to history
        self.add_history("Clear all selections and matches")

        row_count = len(self.selected_rows | set(self.matches.keys()))

        # Clear all selections
        self.selected_rows = set()
        self.selected_columns = set()
        self.matches = defaultdict(set)

        # Recreate table for display
        self.setup_table()

        self.notify(f"Cleared selections for [$success]{row_count}[/] rows", title="Clear Selections and Matches")

    # Copy
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
            self.notify(message, title="Copy to Clipboard")
        except FileNotFoundError:
            self.notify("Failed to copy to clipboard", title="Copy to Clipboard", severity="error")

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
        columns, where, new_tab = result

        sql = f"SELECT {columns} FROM self"
        if where:
            sql += f" WHERE {where}"

        self.run_sql(sql, new_tab)

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
        sql, new_tab = result

        self.run_sql(sql, new_tab)

    @with_full_df
    def run_sql(self, sql: str, new_tab: bool = False) -> None:
        """Execute a SQL query directly.

        Args:
            sql: The SQL query string to execute.
            new_tab: Whether to show results in a new tab or update the current view.
        """
        # handle special internal row identifier column references
        sql = sql.replace("RID", RID).replace("$#", f"(`{RID}` + 1)")

        # Execute the SQL query
        try:
            df_filtered = add_rid_column(self.df.lazy().sql(sql)).collect()
            if len(df_filtered) == 0:
                self.notify(f"Query returned no results for [$warning]{sql}[/]", title="SQL Query", severity="warning")
                return

        except Exception as e:
            self.notify(f"Failed to execute SQL query [$error]{sql}[/]", title="SQL Query", severity="error")
            self.log(f"Error executing SQL query `{sql}`: {e}")
            return

        # Show results in new tab if requested
        if new_tab:
            return self.app.add_tab(
                df_filtered,
                filename="query_results.csv",
                tabname="query-results",
                after=self.app.tabbed.active_pane,
            )

        # Add to history
        self.add_history(f"Run SQL Query: [$success]{sql}[/]")

        # Create a view of self.df as a copy
        if self.df_view is None:
            self.df_view = self.df

        # Update dataframe
        self.df = df_filtered

        # Recreate table for display
        self.setup_table()

        self.notify(
            f"Query executed successfully. Now showing [$accent]{len(self.df)}[/] rows and [$accent]{len(self.df.columns)}[/] columns.",
            title="SQL Query",
        )
