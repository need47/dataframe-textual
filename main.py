import os
import sys
from collections import deque
from dataclasses import dataclass
from io import StringIO

import polars as pl
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.coordinate import Coordinate
from textual.reactive import Reactive
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Static

STYLES = {
    "Int64": {"style": "cyan", "justify": "right"},
    "Float64": {"style": "magenta", "justify": "right"},
    "String": {"style": "green", "justify": "left"},
    "Boolean": {"style": "blue", "justify": "center"},
    "Date": {"style": "blue", "justify": "center"},
    "Datetime": {"style": "blue", "justify": "center"},
}


@dataclass
class DtypeStyle:
    style: str
    justify: str

    def __init__(self, dtype: pl.DataType):
        ds = STYLES.get(str(dtype), {"style": "", "justify": ""})
        self.style = ds["style"]
        self.justify = ds["justify"]


def _format_row(vals, dtypes, apply_justify=True) -> list[Text]:
    """Format a single row with proper styling and justification.

    Args:
        vals: The list of values in the row.
        dtypes: The list of data types corresponding to each value.
        apply_justify: Whether to apply justification styling. Defaults to True.
    """
    formatted_row = []

    for val, dtype in zip(vals, dtypes, strict=True):
        ds = DtypeStyle(dtype)

        # Format the value
        if val is None:
            text_val = "-"
        elif str(dtype).startswith("Float"):
            text_val = f"{val:.4g}"
        else:
            text_val = str(val)

        formatted_row.append(
            Text(
                text_val,
                style=ds.style,
                justify=ds.justify if apply_justify else "",
            )
        )

    return formatted_row


def _rindex(lst: list, value) -> int:
    """Return the last index of value in lst. Return -1 if not found."""
    for i, item in enumerate(reversed(lst)):
        if item == value:
            return len(lst) - 1 - i
    return -1


class YesNoScreen(ModalScreen):
    """Reusable modal screen with Yes/No buttons and customizable label and input.

    This widget handles:
    - Yes/No button responses
    - Enter key for Yes, Escape for No
    - Optional callback function for Yes action
    """

    CSS = """
    YesNoScreen {
        align: center middle;
    }

    YesNoScreen > Static {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 2;
    }

    YesNoScreen Input {
        margin: 1 0;
    }

    YesNoScreen #button-container {
        width: 100%;
        height: 3;
        align: center middle;
    }

    YesNoScreen Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        title: str = None,
        label: str = None,
        input: str = None,
        yes: str = "Yes",
        no: str = "No",
        on_yes_callback=None,
    ):
        """Initialize the modal screen.

        Args:
            title: The title to display in the border
            label: Optional label to display below title as a Label
            input: Optional input value to pre-fill an Input widget. If None, no Input is shown. If it is a 2-value tuple, the first value is the pre-filled input, and the second value is the type of input (e.g., "integer", "number", "text")
            yes: Text for the Yes button. If None, hides the Yes button
            no: Text for the No button. If None, hides the No button
            on_yes_callback: Optional callable that takes no args and returns the value to dismiss with
        """
        super().__init__()
        self.title = title
        self.label = label
        self.input = input
        self.yes = yes
        self.no = no
        self.on_yes_callback = on_yes_callback

    def compose(self) -> ComposeResult:
        with Static(id="modal-container") as container:
            if self.title:
                container.border_title = self.title

            if self.label:
                yield Label(self.label, id="label")

            if self.input:
                if isinstance(self.input, tuple) and len(self.input) == 2:
                    self.input, self.input_type = self.input
                else:
                    self.input_type = "text"
                self.input = Input(value=self.input, id="input", type=self.input_type)
                self.input.select_all()
                yield self.input

            if self.yes or self.no:
                with Horizontal(id="button-container"):
                    if self.yes:
                        yield Button(self.yes, id="yes", variant="success")
                    if self.no:
                        yield Button(self.no, id="no", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self._handle_yes()
        elif event.button.id == "no":
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "enter":
            self._handle_yes()
            event.stop()
        elif event.key == "escape":
            self.dismiss(None)
            event.stop()

    def _handle_yes(self) -> None:
        """Handle Yes button/Enter key press."""
        if self.on_yes_callback:
            result = self.on_yes_callback()
            self.dismiss(result)
        else:
            self.dismiss(True)


class SaveFileScreen(YesNoScreen):
    """Modal screen to save the dataframe to a CSV file."""

    CSS = YesNoScreen.CSS.replace("YesNoScreen", "SaveFileScreen")

    def __init__(self, filename: str):
        super().__init__(
            title="Save DataFrame",
            input=filename,
            on_yes_callback=self.handle_save,
        )

    def handle_save(self):
        if self.input:
            filename_input = self.input.value.strip()
            if filename_input:
                return filename_input
            else:
                self.notify("Filename cannot be empty", title="Error")
                return None
        return None


class OverwriteFileScreen(YesNoScreen):
    """Modal screen to confirm file overwrite."""

    CSS = YesNoScreen.CSS.replace("YesNoScreen", "OverwriteFileScreen")

    def __init__(self):
        super().__init__(
            title="File already exists. Overwrite?",
            on_yes_callback=self.handle_overwrite,
        )

    def handle_overwrite(self) -> None:
        self.dismiss(True)


class RowDetailScreen(ModalScreen):
    """Modal screen to display a single row's details."""

    BINDINGS = [
        ("q,escape", "app.pop_screen", "Close"),
    ]

    CSS = """
    RowDetailScreen {
        align: center middle;
    }

    RowDetailScreen > DataTable {
        width: 80;
        border: solid $primary;
    }
    """

    def __init__(
        self,
        row_idx: int,
        df: pl.DataFrame,
    ):
        super().__init__()
        self.row_idx = row_idx
        self.df = df

    def on_key(self, event) -> None:
        """Handle key events."""
        # Prevent Enter from propagating to parent screen
        if event.key == "enter":
            event.stop()

    def compose(self) -> ComposeResult:
        """Create the detail table."""
        detail_table = DataTable(zebra_stripes=True)

        # Add two columns: Column Name and Value
        detail_table.add_column("Column")
        detail_table.add_column("Value")

        # Get all columns and values from the dataframe row
        for col, val, dtype in zip(
            self.df.columns, self.df.row(self.row_idx), self.df.dtypes
        ):
            detail_table.add_row(
                *_format_row([col, val], [None, dtype], apply_justify=False)
            )

        yield detail_table


class FrequencyScreen(ModalScreen):
    """Modal screen to display frequency of values in a column."""

    BINDINGS = [
        ("q,escape", "app.pop_screen", "Close"),
    ]

    CSS = """
    FrequencyScreen {
        align: center middle;
    }

    FrequencyScreen > DataTable {
        width: 60;
        height: auto;
        border: solid $primary;
    }
    """

    def __init__(self, col_idx: int, df: pl.DataFrame):
        super().__init__()
        self.col_idx = col_idx
        self.df = df
        self.sorted_columns = {
            1: True,  # Count
            2: True,  # %
        }

    def compose(self) -> ComposeResult:
        """Create the frequency table."""
        column = self.df.columns[self.col_idx]
        dtype = str(self.df.dtypes[self.col_idx])
        ds = DtypeStyle(dtype)

        # Create frequency table
        freq_table = DataTable(zebra_stripes=True)
        freq_table.add_column(Text(column, justify=ds.justify), key=column)
        freq_table.add_column(Text("Count", justify="right"), key="Count")
        freq_table.add_column(Text("%", justify="right"), key="%")

        # Calculate frequencies using Polars
        freq_df = self.df[column].value_counts(sort=True).sort("count", descending=True)
        total_count = len(self.df)

        # Get style config for Int64 and Float64
        ds_int = DtypeStyle("Int64")
        ds_float = DtypeStyle("Float64")

        # Add rows to the frequency table
        for row in freq_df.rows():
            value, count = row
            percentage = (count / total_count) * 100

            freq_table.add_row(
                Text(
                    "-" if value is None else str(value),
                    style=ds.style,
                    justify=ds.justify,
                ),
                Text(
                    str(count),
                    style=ds_int.style,
                    justify=ds_int.justify,
                ),
                Text(
                    f"{percentage:.2f}",
                    style=ds_float.style,
                    justify=ds_float.justify,
                ),
            )

        yield freq_table

    def _on_key(self, event):
        if event.key == "left_square_bracket":  # '['
            # Sort by current column in ascending order
            self._sort_by_column(descending=False)
            event.stop()
        elif event.key == "right_square_bracket":  # ']'
            # Sort by current column in descending order
            self._sort_by_column(descending=True)
            event.stop()

    def _sort_by_column(self, descending: bool) -> None:
        """Sort the dataframe by the selected column and refresh the main table."""
        freq_table = self.query_one(DataTable)

        col_idx = freq_table.cursor_column
        col_dtype = "String"

        sort_dir = self.sorted_columns.get(col_idx)
        if sort_dir is not None:
            # If already sorted in the same direction, do nothing
            if sort_dir == descending:
                self.notify("Already sorted in that order", title="Sort")
                return

        self.sorted_columns.clear()
        self.sorted_columns[col_idx] = descending

        if col_idx == 0:
            col_name = self.df.columns[self.col_idx]
            col_dtype = str(self.df.dtypes[self.col_idx])
        elif col_idx == 1:
            col_name = "Count"
            col_dtype = "Int64"
        elif col_idx == 2:
            col_name = "%"
            col_dtype = "Float64"

        def key_fun(freq_col):
            col_value = freq_col.plain

            if col_dtype == "Int64":
                return int(col_value)
            elif col_dtype == "Float64":
                return float(col_value)
            elif col_dtype == "Boolean":
                return eval(col_value)
            else:
                return col_value

        # Sort the table
        freq_table.sort(
            col_name, key=lambda freq_col: key_fun(freq_col), reverse=descending
        )

        # Notify the user
        order = "desc" if descending else "asc"
        self.notify(f"Sorted by [on $primary]{col_name}[/] ({order})", title="Sort")


class EditCellScreen(YesNoScreen):
    """Modal screen to edit a single cell value."""

    CSS = YesNoScreen.CSS.replace("YesNoScreen", "EditCellScreen")

    def __init__(self, row_idx: int, col_idx: int, df: pl.DataFrame):
        self.row_idx = row_idx
        self.col_idx = col_idx
        self.col_name = df.columns[col_idx]
        self.col_dtype = str(df.dtypes[col_idx])
        self.original_value = df.item(row_idx, col_idx)

        content = f"{self.col_name} ({self.col_dtype})"
        input = str(self.original_value) if self.original_value is not None else ""

        # For input validation
        if self.col_dtype == "Int64":
            input_type = "integer"
        elif self.col_dtype == "Float64":
            input_type = "number"
        else:
            input_type = "text"

        super().__init__(
            title="Edit Cell",
            label=content,
            input=(input, input_type),
            on_yes_callback=self._save_edit,
        )

    def _save_edit(self) -> None:
        """Validate and save the edited value."""
        new_value_str = self.input.value.strip()

        # Check if value changed
        old_value_str = (
            str(self.original_value) if self.original_value is not None else ""
        )
        if new_value_str == old_value_str:
            self.dismiss(None)
            self.notify("No changes made", title="Edit")
            return

        # Parse and validate based on column dtype
        try:
            new_value = self._parse_value(new_value_str)
        except ValueError as e:
            self.dismiss(None)
            self.notify(f"Invalid value: {str(e)}", title="Error")
            return

        # Dismiss with the new value
        self.dismiss((self.row_idx, self.col_idx, new_value))

    def _parse_value(self, value: str):
        """Parse string value based on column dtype."""
        dtype = self.col_dtype

        if dtype == "Int64":
            return int(value)
        elif dtype == "Float64":
            return float(value)
        elif dtype == "String":
            return value
        elif dtype == "Boolean":
            if value.lower() in ("true", "t", "yes", "y", "1"):
                return True
            elif value.lower() in ("false", "f", "no", "n", "0"):
                return False
            else:
                raise ValueError(
                    "Boolean must be 'true', 'false', 't', 'f', 'yes', 'no', 'y', 'n', '1', or '0'"
                )
        elif dtype == "Date":
            # Try to parse ISO date format (YYYY-MM-DD)
            return pl.col(self.col_name).str.to_date().to_list()[0].__class__(value)
        elif dtype == "Datetime":
            # Try to parse ISO datetime format
            return pl.col(self.col_name).str.to_datetime().to_list()[0].__class__(value)
        else:
            # For unknown types, return as string
            return value


class SearchScreen(YesNoScreen):
    """Modal screen to search for values in a column."""

    CSS = YesNoScreen.CSS.replace("YesNoScreen", "SearchScreen")

    def __init__(self, col_name: str, default_value: str = ""):
        super().__init__(
            title="Search",
            label=f"Search in: {col_name}",
            input=default_value,
            on_yes_callback=self._do_search,
        )

    def _do_search(self) -> None:
        """Perform the search."""
        search_term = self.input.value.strip()

        if not search_term:
            self.notify("Search term cannot be empty", title="Error")
            return

        # Dismiss with the search term
        self.dismiss(search_term)


class PinScreen(YesNoScreen):
    """Modal screen to pin rows and columns.

    Accepts one value for fixed rows, or two space-separated values for fixed rows and columns.
    """

    CSS = YesNoScreen.CSS.replace("YesNoScreen", "PinScreen")

    def __init__(self):
        super().__init__(
            title="Pin Rows and Columns",
            label="Enter number of fixed rows and columns (space-separated)",
            input="1",
            on_yes_callback=self._parse_pin_input,
        )

    def _parse_pin_input(self) -> tuple[int, int] | None:
        """Parse and validate the pin input.

        Returns:
            Tuple of (fixed_rows, fixed_columns) or None if invalid.
        """
        input_str = self.input.value.strip()

        if not input_str:
            self.notify("Input cannot be empty", title="Error")
            return None

        parts = input_str.split()

        if len(parts) == 1:
            # Only fixed rows provided
            try:
                fixed_rows = int(parts[0])
                if fixed_rows < 0:
                    raise ValueError("must be non-negative")
                return (fixed_rows, 0)
            except ValueError as e:
                self.notify(f"Invalid fixed rows value: {str(e)}", title="Error")
                return None
        elif len(parts) == 2:
            # Both fixed rows and columns provided
            try:
                fixed_rows = int(parts[0])
                fixed_cols = int(parts[1])
                if fixed_rows < 0 or fixed_cols < 0:
                    raise ValueError("values must be non-negative")
                return (fixed_rows, fixed_cols)
            except ValueError as e:
                self.notify(f"Invalid input values: {str(e)}", title="Error")
                return None
        else:
            self.notify("Provide one or two space-separated integers", title="Error")
            return None


# Pagination settings
INITIAL_BATCH_SIZE = 100  # Load this many rows initially
BATCH_SIZE = 50  # Load this many rows when scrolling


@dataclass
class History:
    """Class to track history of dataframe states for undo/redo functionality."""

    description: str
    df: pl.DataFrame
    filename: str
    loaded_rows: int
    sorted_columns: dict[str, bool]
    selected_rows: list[bool]
    deleted_rows: list[bool]
    fixed_rows: int
    fixed_columns: int


class DataFrameApp(App):
    """A Textual app to interact with a Polars DataFrame."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("k", "toggle_dark", "Toggle Dark Mode"),
        ("l", "toggle_row_labels", "Toggle Row Labels"),
        ("c", "copy_cell", "Copy Cell"),
    ]

    # Reactive cursor coordinate to highlight row label and column header
    cursor_coordinate: Reactive[Coordinate] = Reactive(None)

    def __init__(self, df: pl.DataFrame, filename: str = ""):
        super().__init__()
        self.dataframe = df  # Original dataframe
        self.df = df  # Internal dataframe
        self.filename = filename  # Current filename
        self.loaded_rows = 0  # Track how many rows are currently loaded
        self.sorted_columns = {}  # Track sort keys as dict of col_name -> descending
        self.selected_rows = [False] * len(df)  # Track selected rows (0-based)
        self.deleted_rows = [False] * len(df)  # Track deleted row indices (0-based)
        self.fixed_rows = 0  # Number of fixed rows
        self.fixed_columns = 0  # Number of fixed columns

        # History stack for undo/redo
        self.histories: deque[History] = deque()

        # Reopen stdin to /dev/tty for proper terminal interaction
        if not sys.stdin.isatty():
            tty = open("/dev/tty")
            os.dup2(tty.fileno(), sys.stdin.fileno())

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        self.table = DataTable(zebra_stripes=True)
        yield self.table

    def on_mount(self) -> None:
        """Set up the DataTable when app starts."""
        self._setup_table()
        # # Hide labels by default after initial load
        # self.call_later(lambda: setattr(self.table, "show_row_labels", False))

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "g":
            # Jump to top
            self.table.move_cursor(row=0)
        elif event.key == "G":
            # Load all remaining rows before jumping to end
            self._load_rows()
            self.table.move_cursor(row=self.table.row_count - 1)
        elif event.key in ("pagedown", "down"):
            # Let the table handle the navigation first
            self._check_and_load_more()
        elif event.key == "enter":
            # Open row detail modal
            self._view_row_detail()
        elif event.key == "minus":
            # Remove the current column
            self._delete_column()
        elif event.key == "left_square_bracket":  # '['
            # Sort by current column in ascending order
            self._sort_by_column(descending=False)
        elif event.key == "right_square_bracket":  # ']'
            # Sort by current column in descending order
            self._sort_by_column(descending=True)
        elif event.key == "r":
            # Restore original display
            self._setup_table(reset=True)
            # # Hide labels by default after initial load
            # self.call_later(lambda: setattr(self.table, "show_row_labels", False))

            self.notify("Restored original display", title="Reset")
        elif event.key == "ctrl+s":
            # Save dataframe to CSV
            self._save_to_file()
        elif event.key == "F":  # shift+f
            # Open frequency modal for current column
            self._show_frequency()
        elif event.key == "e":
            # Open edit modal for current cell
            self._edit_cell()
        elif event.key == "vertical_line":  # '|' key
            # Open search modal for current column
            self._search_column()
        elif event.key == "t":
            # Toggle selected rows highlighting
            self._toggle_selected_rows()
        elif event.key == "quotation_mark":  # '"' key
            # Display selected rows only
            self._filter_selected_rows()
        elif event.key == "d":
            # Delete the current row
            self._delete_row()
        elif event.key == "u":
            # Undo last action
            self._undo()
        elif event.key == "backslash":  # '\' key
            # Search with current cell value and highlight matched rows
            self._search_with_cell_value()
        elif event.key == "shift+left":  # shift + left arrow
            # Move current column to the left
            self._move_column("left")
        elif event.key == "shift+right":  # shift + right arrow
            # Move current column to the right
            self._move_column("right")
        elif event.key == "shift+up":  # shift + up arrow
            # Move current row up
            self._move_row("up")
        elif event.key == "shift+down":  # shift + down arrow
            # Move current row down
            self._move_row("down")
        elif event.key == "C":  # shift+c
            # Clear all selected rows
            self._clear_selected_rows()
        elif event.key == "p":
            # Open pin screen to set fixed rows and columns
            self._open_pin_screen()

    def on_mouse_scroll_down(self, event) -> None:
        """Load more rows when scrolling down with mouse."""
        self._check_and_load_more()

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        """Handle cell highlight changes."""
        self.cursor_coordinate = event.coordinate

    def watch_cursor_coordinate(self, old: Coordinate, new: Coordinate) -> None:
        """Update the style of row label and column label for highlighted cell."""
        # Reset old style
        if old is not None:
            old_row_idx, old_col_idx = old
            # e.g., the last row/column might have been deleted
            if old_row_idx >= len(self.table.rows):
                old_row_idx = len(self.table.rows) - 1
            if old_col_idx >= len(self.table.columns):
                old_col_idx = len(self.table.columns) - 1
            old_row_key, old_col_key = self.table.coordinate_to_cell_key(
                Coordinate(old_row_idx, old_col_idx)
            )
            self.table.rows[old_row_key].label.style = ""
            self.table.columns[old_col_key].label.style = ""

        # Set new style
        new_row_key, new_col_key = self.table.coordinate_to_cell_key(new)
        self.table.rows[new_row_key].label.style = "yellow"
        self.table.columns[new_col_key].label.style = "yellow"

        # Refresh table to show updated styles
        self.table._update_count += 1
        self.table.refresh()

    def action_toggle_row_labels(self) -> None:
        """Toggle row labels visibility using CSS property."""
        self.table.show_row_labels = not self.table.show_row_labels

    def action_copy_cell(self) -> None:
        """Copy the current cell to clipboard."""
        import subprocess

        row_idx = self.table.cursor_row
        col_idx = self.table.cursor_column

        # Get the cell value from the sorted dataframe
        cell_str = str(self.df.item(row_idx, col_idx))

        # Copy to clipboard using xclip or pbcopy (macOS)
        try:
            subprocess.run(
                [
                    "pbcopy" if sys.platform == "darwin" else "xclip",
                    "-selection",
                    "clipboard",
                ],
                input=cell_str,
                text=True,
            )
            self.notify(f"Copied: {cell_str[:50]}", title="Clipboard")
        except FileNotFoundError:
            self.notify("clipboard tool not available", title="FileNotFound")

    # Load
    def _setup_table(self, reset: bool = False) -> None:
        """Setup the table for display."""
        # Reset to original dataframe
        if reset:
            self.df = self.dataframe
            self.loaded_rows = 0
            self.sorted_columns = {}
            self.selected_rows = [False] * len(self.df)
            self.deleted_rows = [False] * len(self.df)
            self.fixed_rows = 0
            self.fixed_columns = 0

        self._setup_columns()
        self._load_rows(INITIAL_BATCH_SIZE)
        self._highlight_rows()

        self.table.fixed_rows = self.fixed_rows
        self.table.fixed_columns = self.fixed_columns

    def _setup_columns(self) -> None:
        """Clear table and setup columns."""
        self.loaded_rows = 0
        self.table.clear(columns=True)
        self.table.show_row_labels = True

        # Add columns with justified headers
        for col, dtype in zip(self.df.columns, self.df.dtypes):
            self.table.add_column(Text(col, justify=DtypeStyle(dtype).justify), key=col)

        self.table.cursor_type = "cell"
        self.table.focus()

    def _check_and_load_more(self) -> None:
        """Check if we need to load more rows and load them."""
        # If we've loaded everything, no need to check
        if self.loaded_rows >= len(self.df):
            return

        visible_row_count = self.table.size.height - self.table.header_height
        bottom_visible_row = self.table.scroll_y + visible_row_count

        # If visible area is close to the end of loaded rows, load more
        if bottom_visible_row >= self.loaded_rows - 10:
            self._load_rows(self.loaded_rows + BATCH_SIZE)

    def _load_rows(self, stop: int | None = None) -> None:
        """Load a batch of rows into the table.

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
            if self.deleted_rows[row_idx]:
                continue  # Skip deleted rows

            vals, dtypes = [], []
            for val, dtype in zip(row, self.df.dtypes):
                vals.append(val)
                dtypes.append(dtype)
            formatted_row = _format_row(vals, dtypes)
            # Always add labels so they can be shown/hidden via CSS
            self.table.add_row(
                *formatted_row, key=str(row_idx + 1), label=str(row_idx + 1)
            )

        # Update loaded rows count
        self.loaded_rows = stop

        if stop != INITIAL_BATCH_SIZE:
            self.notify(f"Loaded {self.loaded_rows}/{len(self.df)} rows", title="Load")

    # View
    def _view_row_detail(self) -> None:
        """Open a modal screen to view the selected row's details."""
        row_idx = self.table.cursor_row
        if row_idx >= len(self.df):
            return

        # Push the modal screen
        self.push_screen(RowDetailScreen(row_idx, self.df))

    def _show_frequency(self) -> None:
        """Show frequency distribution for the current column."""
        col_idx = self.table.cursor_column
        if col_idx >= len(self.df.columns):
            return

        # Push the frequency modal screen
        self.push_screen(FrequencyScreen(col_idx, self.df))

    def _open_pin_screen(self) -> None:
        """Open the pin screen to set fixed rows and columns."""
        self.push_screen(PinScreen(), callback=self._on_pin_screen)

    def _on_pin_screen(self, result: tuple[int, int] | None) -> None:
        """Handle result from PinScreen.

        Args:
            result: Tuple of (fixed_rows, fixed_columns) or None if cancelled.
        """
        if result is None:
            return

        fixed_rows, fixed_columns = result

        # Add to history
        self._add_history(
            f"Pinned [on $primary]{fixed_rows}[/] rows and [on $primary]{fixed_columns}[/] columns"
        )

        # Apply the pin settings to the table
        if fixed_rows > 0:
            self.table.fixed_rows = fixed_rows
        if fixed_columns > 0:
            self.table.fixed_columns = fixed_columns

        # Update internal state
        self.fixed_rows = fixed_rows
        self.fixed_columns = fixed_columns

        self.notify(
            f"Pinned [on $primary]{fixed_rows}[/] rows and [on $primary]{fixed_columns}[/] columns",
            title="Pin",
        )

    # Delete
    def _delete_column(self) -> None:
        """Remove the currently selected column from the table."""
        col_idx = self.table.cursor_column
        if col_idx >= len(self.df.columns):
            return

        # Get the column name to remove
        col_to_remove = self.df.columns[col_idx]

        # Add to history
        self._add_history(f"Removed column [on $primary]{col_to_remove}[/]")

        # Remove the column from the table display using the column name as key
        self.table.remove_column(col_to_remove)

        # Move cursor left if we deleted the last column
        if col_idx >= len(self.table.columns):
            self.table.move_cursor(column=len(self.table.columns) - 1)

        # Remove from sorted columns if present
        if col_to_remove in self.sorted_columns:
            del self.sorted_columns[col_to_remove]

        # Remove from dataframe
        self.df = self.df.drop(col_to_remove)

        self.notify(
            f"Removed column [on $primary]{col_to_remove}[/] from display",
            title="Column",
        )

    def _delete_row(self) -> None:
        """Delete rows from the table and dataframe.

        Supports deleting multiple selected rows. If no rows are selected, deletes the row at the cursor.

        Do not remove rows from the dataframe to allow for undo functionality (especially for row labels).
        """
        # Delete all selected rows
        if selected_count := self.selected_rows.count(True):
            # Add to history
            self._add_history(f"Deleted {selected_count} selected row(s)")

            for row_idx, is_selected in enumerate(self.selected_rows):
                if not is_selected:
                    continue

                # Add to deleted rows list
                self.deleted_rows[row_idx] = True

                # Update selected_rows list to maintain alignment
                self.selected_rows[row_idx] = False

                # Remove from table
                row_key = str(row_idx + 1)  # Convert to 1-based key
                self.table.remove_row(row_key)

            self.notify(f"Deleted {selected_count} selected row(s)", title="Delete")
        # Delete the row at the cursor
        else:
            row_key, _ = self.table.coordinate_to_cell_key(self.table.cursor_coordinate)
            row_idx = int(row_key.value) - 1  # Convert to 0-based index

            if row_idx >= len(self.df):
                self.notify("Cannot delete row: invalid row index", title="Error")
                return

            # Add to history
            self._add_history(f"Deleted row [on $primary]{row_key.value}[/]")

            # Add to deleted rows list
            self.deleted_rows[row_idx] = True

            # Update selected_rows list to maintain alignment
            self.selected_rows[row_idx] = False

            # Remove from table
            self.table.remove_row(row_key)

            # Move cursor up if we deleted the last row
            if row_idx >= len(self.table.rows):
                self.table.move_cursor(row=len(self.table.rows) - 1)

            self.notify(f"Row [on $primary]{row_key.value}[/] deleted", title="Delete")

    def _move_column(self, direction: str) -> None:
        """Move the current column left or right.

        Args:
            direction: "left" to move left, "right" to move right.
        """
        row_idx, col_idx = self.table.cursor_coordinate
        _, col_key = self.table.coordinate_to_cell_key(self.table.cursor_coordinate)

        # Validate move is possible
        if direction == "left":
            if col_idx <= 0:
                self.notify("Cannot move column left", title="Move")
                return
            swap_idx = col_idx - 1
        elif direction == "right":
            if col_idx >= len(self.table.columns) - 1:
                self.notify("Cannot move column right", title="Move")
                return
            swap_idx = col_idx + 1
        else:
            self.notify(f"Invalid direction: {direction}", title="Move")
            return

        # Get column names to swap
        col_name = self.df.columns[col_idx]
        swap_name = self.df.columns[swap_idx]

        # Add to history
        self._add_history(
            f"Moved column [on $primary]{col_name}[/] {direction} (swapped with [on $primary]{swap_name}[/])"
        )

        # Swap columns in the table's internal column locations
        self.table.check_idle()
        swap_key = self.df.columns[swap_idx]  # str as column key

        (
            self.table._column_locations[col_key],
            self.table._column_locations[swap_key],
        ) = (
            self.table._column_locations.get(swap_key),
            self.table._column_locations.get(col_key),
        )

        self.table._update_count += 1
        self.table.refresh()

        # Restore cursor position on the moved column
        self.table.move_cursor(row=row_idx, column=swap_idx)

        # Swap columns in the dataframe
        cols = list(self.df.columns)
        cols[col_idx], cols[swap_idx] = cols[swap_idx], cols[col_idx]
        self.df = self.df.select(cols)

        self.notify(
            f"Moved column [on $primary]{col_name}[/] {direction}",
            title="Move",
        )

    def _move_row(self, direction: str) -> None:
        """Move the current row up or down.

        Args:
            direction: "up" to move up, "down" to move down.
        """
        row_idx, col_idx = self.table.cursor_coordinate

        # Validate move is possible
        if direction == "up":
            if row_idx <= 0:
                self.notify("Cannot move row up", title="Move")
                return
            swap_idx = row_idx - 1
        elif direction == "down":
            if row_idx >= len(self.table.rows) - 1:
                self.notify("Cannot move row down", title="Move")
                return
            swap_idx = row_idx + 1
        else:
            self.notify(f"Invalid direction: {direction}", title="Move")
            return

        # Add to history
        self._add_history(
            f"Moved row [on $primary]{row_idx + 1}[/] {direction} (swapped with row [on $primary]{swap_idx + 1}[/])"
        )

        # Swap rows in the dataframe
        row_key = str(row_idx + 1)  # Convert to 1-based key
        swap_key = str(swap_idx + 1)  # Convert to 1-based key

        self.table.check_idle()
        (
            self.table._row_locations[row_key],
            self.table._row_locations[swap_key],
        ) = (
            self.table._row_locations.get(swap_key),
            self.table._row_locations.get(row_key),
        )

        self.table._update_count += 1
        self.table.refresh()

        # Restore cursor position on the moved row
        self.table.move_cursor(row=swap_idx, column=col_idx)

        self.notify(
            f"Moved row [on $primary]{row_idx + 1}[/] {direction}", title="Move"
        )

    # Sort
    def _sort_by_column(self, descending: bool = False) -> None:
        """Sort the dataframe by the currently selected column.

        Supports multi-column sorting:
        - First press on a column: sort by that column only
        - Subsequent presses on other columns: add to sort order

        Args:
            descending: If True, sort in descending order. If False, ascending order.
        """
        col_idx = self.table.cursor_column
        if col_idx >= len(self.df.columns):
            return

        col_to_sort = self.df.columns[col_idx]

        # Add to history
        self._add_history(f"Sorted dataframe on column [on $primary]{col_to_sort}[/]")

        # Check if this column is already in the sort keys
        old_desc = self.sorted_columns.get(col_to_sort)
        if old_desc is not None:
            del self.sorted_columns[col_to_sort]

            if old_desc == descending:
                # Same direction - remove this column from sort
                self.notify(
                    f"Already sorted. Removed [on $primary]{col_to_sort}[/] from the sorted list",
                    title="Sort",
                )
                return
            else:
                # Toggle direction
                self.sorted_columns[col_to_sort] = descending
        else:
            # Add new column to sort
            self.sorted_columns[col_to_sort] = descending

        # If no sort keys, reset to original order
        if not self.sorted_columns:
            self.df = self.dataframe
        else:
            # Apply multi-column sort
            sort_cols = list(self.sorted_columns.keys())
            descending_flags = list(self.sorted_columns.values())
            self.df = self.dataframe.sort(
                sort_cols, descending=descending_flags, nulls_last=True
            )

        # Recreate the table for display
        self._setup_table()

        # Restore cursor position on the sorted column
        self.table.move_cursor(column=col_idx, row=0)

        sort_by = ", ".join(
            f"[on $primary]{col}[/] ({'desc' if desc else 'asc'})"
            for col, desc in self.sorted_columns.items()
        )
        self.notify(f"Sorted by: {sort_by}", title="Sort")

    # Save
    def _save_to_file(self) -> None:
        """Open save file dialog."""
        self.push_screen(
            SaveFileScreen(self.filename or "dataframe.csv"),
            callback=self._on_save_file_screen,
        )

    def _on_save_file_screen(self, filename: str | None) -> None:
        """Handle result from SaveFileScreen."""
        if filename is None:
            return

        # Check if file exists
        if os.path.exists(filename):
            self._pending_filename = filename
            self.push_screen(OverwriteFileScreen(), callback=self._on_overwrite_screen)
        else:
            self._do_save(filename)

    def _on_overwrite_screen(self, should_overwrite: bool) -> None:
        """Handle result from OverwriteFileScreen."""
        if should_overwrite:
            self._do_save(self._pending_filename)
        else:
            # Go back to SaveFileScreen to allow user to enter a different name
            self.push_screen(
                SaveFileScreen(self._pending_filename),
                callback=self._on_save_file_screen,
            )

    def _do_save(self, filename: str) -> None:
        """Actually save the dataframe to a file."""
        ext = os.path.splitext(filename)[1].lower()
        if ext in (".tsv", ".tab"):
            separator = "\t"
        else:
            separator = ","
        try:
            if True in self.deleted_rows:
                rows_to_keep = [not deleted for deleted in self.deleted_rows]
                self.df = self.df.filter(rows_to_keep)
            self.df.write_csv(filename, separator=separator)

            self.dataframe = self.df  # Update original dataframe
            self.filename = filename  # Update current filename
            self.notify(f"Saved to [on $primary]{filename}[/]", title="Save")
        except Exception as e:
            self.notify(f"Failed to save: {str(e)}", title="Error")
            raise e

    # Edit
    def _edit_cell(self) -> None:
        """Open modal to edit the selected cell."""
        row_idx = self.table.cursor_row
        col_idx = self.table.cursor_column

        if row_idx >= len(self.df) or col_idx >= len(self.df.columns):
            return
        col_name = self.df.columns[col_idx]

        # Save current state to history
        self._add_history(f"Edited cell [on $primary]({row_idx + 1}, {col_name})[/]")

        # Push the edit modal screen
        self.push_screen(
            EditCellScreen(row_idx, col_idx, self.df),
            callback=self._on_edit_cell_screen,
        )

    def _on_edit_cell_screen(self, result) -> None:
        """Handle result from EditCellScreen."""
        if result is None:
            return

        row_idx, col_idx, new_value = result
        col_name = self.df.columns[col_idx]

        # Update the cell in the dataframe
        try:
            self.df = self.df.with_columns(
                pl.when(pl.arange(0, len(self.df)) == row_idx)
                .then(pl.lit(new_value))
                .otherwise(pl.col(col_name))
                .alias(col_name)
            )

            # Update the display
            cell_value = self.df.item(row_idx, col_idx)
            dtype = self.df.dtypes[col_idx]
            ds = DtypeStyle(dtype)
            formatted_value = Text(str(cell_value), style=ds.style, justify=ds.justify)

            row_key = str(row_idx + 1)
            col_key = str(col_name)
            self.table.update_cell(row_key, col_key, formatted_value)

            self.notify(f"Cell updated to [on $primary]{cell_value}[/]", title="Edit")
        except Exception as e:
            self.notify(f"Failed to update cell: {str(e)}", title="Edit")
            raise e

    # Search & Highlight
    def _search_column(self) -> None:
        """Open modal to search in the selected column."""
        row_idx = self.table.cursor_row
        col_idx = self.table.cursor_column

        if col_idx >= len(self.df.columns):
            return

        col_name = self.df.columns[col_idx]
        col_dtype = self.df.dtypes[col_idx]

        # Get current cell value as default search term
        cell_value = self.df.item(row_idx, col_idx)
        if cell_value is None:
            self.notify("Cannot use null value for search", title="Error")
            return

        search_term = str(cell_value)
        if col_dtype == pl.Boolean:
            search_term = search_term.lower()

        # Push the search modal screen
        self.push_screen(
            SearchScreen(col_name, search_term),
            callback=self._on_search_screen,
        )

    def _on_search_screen(self, search_term: str | None) -> None:
        """Handle result from SearchScreen."""
        if search_term is None:
            return

        col_idx = self.table.cursor_column
        col_name = self.df.columns[col_idx]

        try:
            # Convert column to string for searching
            col_series = self.df[col_name].cast(pl.String)

            # Use Polars str.contains() to find matching rows
            # Returns a boolean Series, convert to list
            # Add to existing selected rows
            matches = col_series.str.contains(search_term).to_list()
            match_count = matches.count(True)
            if match_count == 0:
                self.notify(
                    f"No matches found for: [on $primary]{search_term}[/]",
                    title="Search",
                )
                return

            # Add to history
            self._add_history(
                f"Searched and highlighted [on $primary]{search_term}[/] in column [on $primary]{col_name}[/]"
            )

            # Update selected rows to include new matches
            self.selected_rows = [
                old or new for old, new in zip(self.selected_rows, matches)
            ]

            # Highlight selected rows
            self._highlight_rows()

            self.notify(
                f"Found [on $primary]{match_count}[/] matches for [on $primary]{search_term}[/]",
                title="Search",
            )
        except Exception as e:
            self.notify(f"Search failed for {search_term}: {str(e)}", title="Error")
            raise e

    def _search_with_cell_value(self) -> None:
        """Search in the current column using the value of the currently selected cell."""
        row_idx = self.table.cursor_row
        col_idx = self.table.cursor_column

        if col_idx >= len(self.df.columns) or row_idx >= len(self.df):
            self.notify("Invalid cell position", title="Error")
            return

        # Get the value of the currently selected cell
        cell_value = self.df.item(row_idx, col_idx)
        if cell_value is None:
            self.notify("Cannot search with null value", title="Error")
            return

        col_dtype = self.df.dtypes[col_idx]
        search_term = str(cell_value)
        if col_dtype == pl.Boolean:
            search_term = search_term.lower()

        self._on_search_screen(search_term)

    def _highlight_rows(self, clear: bool = False) -> None:
        """Update all rows, highlighting selected ones in red and restoring others to default.

        Args:
            clear: If True, clear all highlights.
        """
        if True not in self.selected_rows:
            return

        if clear:
            self.selected_rows = [False] * len(self.df)

        # Ensure all highlighted rows are loaded
        stop = _rindex(self.selected_rows, True) + 1
        self._load_rows(stop)

        # Update all rows based on selected state
        for row_idx, row in enumerate(self.table.ordered_rows):
            is_selected = self.selected_rows[row_idx]

            # Update all cells in this row
            for col_idx, col in enumerate(self.table.ordered_columns):
                cell_text: Text = self.table.get_cell(row.key, col.key)
                dtype = self.df.dtypes[col_idx]

                # Get style config based on dtype
                ds = DtypeStyle(dtype)

                # Use red for selected rows, default style for others
                style = "red" if is_selected else ds.style
                cell_text.style = style

                # cell_value = cell_text.plain
                # formatted_value = Text(
                #     str(cell_value) if cell_value is not None else "-",
                #     style=style,
                #     justify=ds.justify,
                # )

                # Update the cell in the table
                self.table.update_cell(row.key, col.key, cell_text)

    def _toggle_selected_rows(self) -> None:
        """Toggle selected rows highlighting on/off."""
        # Check if any rows are currently selected
        if True not in self.selected_rows:
            self.notify(
                "No rows selected to toggle", title="Toggle", severity="warning"
            )
            return

        # Save current state to history
        self._add_history("Toggled row selection")

        # Invert all selected rows
        self.selected_rows = [not match for match in self.selected_rows]

        # Check if we're highlighting or un-highlighting
        if new_selected_count := self.selected_rows.count(True):
            self.notify(
                f"Toggled selection - now showing [on $primary]{new_selected_count}[/] rows",
                title="Toggle",
            )

        # Refresh the highlighting (also restores default styles for unselected rows)
        self._highlight_rows()

    def _clear_selected_rows(self) -> None:
        """Clear all selected rows without removing them from the dataframe."""
        # Check if any rows are currently selected
        selected_count = self.selected_rows.count(True)
        if selected_count == 0:
            self.notify("No rows selected to clear", title="Clear", severity="warning")
            return

        # Save current state to history
        self._add_history("Cleared all selected rows")

        # Clear all selections and refresh highlighting
        self._highlight_rows(clear=True)

        self.notify(
            f"Cleared [on $primary]{selected_count}[/] selected rows", title="Clear"
        )

    def _filter_selected_rows(self) -> None:
        """Display only the selected rows."""
        selected_count = self.selected_rows.count(True)
        if selected_count == 0:
            self.notify(
                "No rows selected to filter", title="Filter", severity="warning"
            )
            return

        # Save current state to history
        self._add_history("Filtered to selected rows")

        # Update all rows based on selected state
        for row_idx in range(self.loaded_rows):
            is_selected = self.selected_rows[row_idx]
            if not is_selected:
                self.table.remove_row(str(row_idx + 1))
                continue

        # Update deleted rows list to maintain alignment
        self.deleted_rows = [not selected for selected in self.selected_rows]

        # Do not actually remove from the dataframe so it can be restored via undo
        # self.df = self.df.filter(self.selected_rows)

        self.notify(
            f"Removed unselected rows. Now showing [on $primary]{selected_count}[/] rows",
            title="Filter",
        )

    # History & Undo
    def _add_history(self, description: Text | str) -> None:
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
            selected_rows=self.selected_rows.copy(),
            deleted_rows=self.deleted_rows.copy(),
            fixed_rows=self.fixed_rows,
            fixed_columns=self.fixed_columns,
        )
        self.histories.append(history)

        self.log(self.histories[-1], description)

    def _undo(self) -> None:
        """Undo the last action."""
        if not self.histories:
            self.notify("No actions to undo", title="Undo")
            return

        history = self.histories.pop()
        self.log(history, f"Restoring history: {history.description}")

        # Restore state
        self.df = history.df
        self.filename = history.filename
        self.loaded_rows = history.loaded_rows
        self.sorted_columns = history.sorted_columns.copy()
        self.selected_rows = history.selected_rows.copy()
        self.deleted_rows = history.deleted_rows.copy()
        self.fixed_rows = history.fixed_rows
        self.fixed_columns = history.fixed_columns

        # Recreate the table for display
        self._setup_table()

        self.notify(f"Reverted: {history.description}", title="Undo")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Interactive CSV viewer for the terminal (Textual version)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  python main.py data.csv\n"
        "  cat data.csv | python main.py\n",
    )
    parser.add_argument("file", nargs="?", help="CSV file to view (or read from stdin)")

    args = parser.parse_args()
    filename = ""

    # Check if reading from stdin (pipe or redirect)
    if not sys.stdin.isatty():
        # Read CSV from stdin into memory first (stdin is not seekable)
        stdin_data = sys.stdin.read()
        df = pl.read_csv(StringIO(stdin_data))
    elif args.file:
        # Read from file
        filename = args.file
        if not os.path.exists(filename):
            print(f"File not found: {filename}")
            sys.exit(1)
        df = pl.read_csv(filename)
    else:
        parser.print_help()
        sys.exit(1)

    # Run the app
    app = DataFrameApp(df, filename)
    app.run()
