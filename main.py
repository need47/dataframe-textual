import os
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from io import StringIO
from textwrap import dedent

import polars as pl
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.coordinate import Coordinate
from textual.css.query import NoMatches
from textual.reactive import Reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, Markdown, Static
from textual.widgets._data_table import (
    CellDoesNotExist,
    CellKey,
    ColumnKey,
    CursorType,
    RowKey,
)

# itype is used by Input widget for input validation
STYLES = {
    "Int64": {"style": "cyan", "justify": "right", "itype": "integer"},
    "Float64": {"style": "magenta", "justify": "right", "itype": "number"},
    "String": {"style": "green", "justify": "left", "itype": "text"},
    "Boolean": {"style": "blue", "justify": "center", "itype": "text"},
    "Date": {"style": "blue", "justify": "center", "itype": "text"},
    "Datetime": {"style": "blue", "justify": "center", "itype": "text"},
}


@dataclass
class DtypeConfig:
    style: str
    justify: str
    itype: str

    def __init__(self, dtype: pl.DataType):
        dc = STYLES.get(str(dtype), {"style": "", "justify": "", "itype": "text"})
        self.style = dc["style"]
        self.justify = dc["justify"]
        self.itype = dc["itype"]


# Subscript digits mapping for sort indicators
SUBSCRIPT_DIGITS = {
    0: "₀",
    1: "₁",
    2: "₂",
    3: "₃",
    4: "₄",
    5: "₅",
    6: "₆",
    7: "₇",
    8: "₈",
    9: "₉",
}

# Boolean string mappings
BOOLS = {
    "true": True,
    "t": True,
    "yes": True,
    "y": True,
    "1": True,
    "false": False,
    "f": False,
    "no": False,
    "n": False,
    "0": False,
}

CURSOR_TYPES = ["row", "column", "cell", "none"]


def _format_row(vals, dtypes, apply_justify=True) -> list[Text]:
    """Format a single row with proper styling and justification.

    Args:
        vals: The list of values in the row.
        dtypes: The list of data types corresponding to each value.
        apply_justify: Whether to apply justification styling. Defaults to True.
    """
    formatted_row = []

    for val, dtype in zip(vals, dtypes, strict=True):
        dc = DtypeConfig(dtype)

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
                style=dc.style,
                justify=dc.justify if apply_justify else "",
            )
        )

    return formatted_row


def _rindex(lst: list, value) -> int:
    """Return the last index of value in lst. Return -1 if not found."""
    for i, item in enumerate(reversed(lst)):
        if item == value:
            return len(lst) - 1 - i
    return -1


def parse_filter_expression(
    expression: str, df: pl.DataFrame, current_col_idx: int
) -> str:
    """Parse and convert a filter expression to Polars syntax.

    Supports:
    - $_ - Current selected column
    - $1, $2, etc. - Column by 1-based index
    - $col_name - Column by name
    - Comparison operators: ==, !=, <, >, <=, >=
    - Logical operators: &&, ||
    - String literals: 'text', "text"
    - Numeric literals: integers and floats

    Examples:
    - "$_ > 50" -> "pl.col('current_col') > 50"
    - "$1 > 50" -> "pl.col('col0') > 50"
    - "$name == 'Alex'" -> "pl.col('name') == 'Alex'"
    - "$1 > 3 && $name == 'Alex'" -> "(pl.col('col0') > 3) & (pl.col('name') == 'Alex')"
    - "$age < $salary" -> "pl.col('age') < pl.col('salary')"

    Args:
        expression: The filter expression as a string.
        df: The DataFrame to validate column references.
        current_col_idx: The index of the currently selected column (0-based). Used for $_ reference.

    Returns:
        A Python expression string that can be eval'd with Polars symbols.

    Raises:
        ValueError: If the expression contains invalid column references.
        SyntaxError: If the expression has invalid syntax.
    """
    import re

    # Tokenize the expression
    # Pattern matches: $_, $index, $identifier, strings, operators, numbers, etc.
    token_pattern = r'\$_|\$\d+|\$\w+|\'[^\']*\'|"[^"]*"|&&|\|\||<=|>=|!=|==|[+\-*/%<>=()]|\d+\.?\d*|\w+|.'

    tokens = re.findall(token_pattern, expression)

    if not tokens:
        raise ValueError("Expression is empty")

    # Convert tokens to Polars expression syntax
    converted_tokens = []
    for token in tokens:
        if token.startswith("$"):
            # Column reference
            col_ref = token[1:]

            # Special case: $_ refers to the current selected column
            if col_ref == "_":
                col_name = df.columns[current_col_idx]
            # Check if it's a numeric index
            elif col_ref.isdigit():
                col_idx = int(col_ref) - 1  # Convert to 0-based index
                if col_idx < 0 or col_idx >= len(df.columns):
                    raise ValueError(f"Column index out of range: ${col_ref}")
                col_name = df.columns[col_idx]
            else:
                # It's a column name
                if col_ref not in df.columns:
                    raise ValueError(f"Column not found: ${col_ref}")
                col_name = col_ref

            converted_tokens.append(f"pl.col('{col_name}')")

        elif token in ("&&", "||"):
            # Convert logical operators and wrap surrounding expressions in parentheses
            if token == "&&":
                converted_tokens.append(") & (")
            else:
                converted_tokens.append(") | (")

        else:
            # Keep as-is (operators, numbers, strings, parentheses)
            converted_tokens.append(token)

    # Join tokens with space to ensure proper separation
    result = "(" + " ".join(converted_tokens) + ")"
    return result


class YesNoScreen(ModalScreen):
    """Reusable modal screen with Yes/No buttons and customizable label and input.

    This widget handles:
    - Yes/No button responses
    - Enter key for Yes, Escape for No
    - Optional callback function for Yes action
    """

    DEFAULT_CSS = """
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
        label: str | dict | Label = None,
        input: str | dict | Input = None,
        yes: str | dict | Button = "Yes",
        no: str | dict | Button = "No",
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
                if isinstance(self.label, Label):
                    pass
                elif isinstance(self.label, dict):
                    self.label = Label(**self.label)
                else:
                    self.label = Label(self.label)
                yield self.label

            if self.input:
                if isinstance(self.input, Input):
                    pass
                elif isinstance(self.input, dict):
                    self.input = Input(**self.input)
                else:
                    self.input = Input(self.input)
                self.input.select_all()
                yield self.input

            if self.yes or self.no:
                with Horizontal(id="button-container"):
                    if self.yes:
                        if isinstance(self.yes, Button):
                            pass
                        elif isinstance(self.yes, dict):
                            self.yes = Button(**self.yes, id="yes", variant="success")
                        else:
                            self.yes = Button(self.yes, id="yes", variant="success")

                        yield self.yes
                    if self.no:
                        if isinstance(self.no, Button):
                            pass
                        elif isinstance(self.no, dict):
                            self.no = Button(**self.no, id="no", variant="error")
                        else:
                            self.no = Button(self.no, id="no", variant="error")

                        yield self.no

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

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "SaveFileScreen")

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
                self.notify("Filename cannot be empty", title="Save", severity="error")
                return None

        return None


class OverwriteFileScreen(YesNoScreen):
    """Modal screen to confirm file overwrite."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "OverwriteFileScreen")

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
        dc = DtypeConfig(dtype)

        # Create frequency table
        freq_table = DataTable(zebra_stripes=True)
        freq_table.add_column(Text(column, justify=dc.justify), key=column)
        freq_table.add_column(Text("Count", justify="right"), key="Count")
        freq_table.add_column(Text("%", justify="right"), key="%")

        # Calculate frequencies using Polars
        freq_df = self.df[column].value_counts(sort=True).sort("count", descending=True)
        total_count = len(self.df)

        # Get style config for Int64 and Float64
        ds_int = DtypeConfig("Int64")
        ds_float = DtypeConfig("Float64")

        # Add rows to the frequency table
        for row in freq_df.rows():
            value, count = row
            percentage = (count / total_count) * 100

            freq_table.add_row(
                Text(
                    "-" if value is None else str(value),
                    style=dc.style,
                    justify=dc.justify,
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
                self.notify(
                    "Already sorted in that order", title="Sort", severity="warning"
                )
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
                return BOOLS[col_value]
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

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "EditCellScreen")

    def __init__(self, row_key: str, col_idx: int, df: pl.DataFrame):
        self.row_key = row_key
        self.col_idx = col_idx
        self.col_name = df.columns[col_idx]
        self.col_dtype = str(df.dtypes[col_idx])

        row_idx = int(row_key.value) - 1  # Convert to 0-based

        # Label
        content = f"[$primary]{self.col_name}[/] ([$accent]{self.col_dtype}[/])"

        # Input
        df_value = df.item(row_idx, col_idx)
        self.input_value = str(df_value) if df_value is not None else ""

        super().__init__(
            title="Edit Cell",
            label=content,
            input={
                "value": self.input_value,
                "type": DtypeConfig(self.col_dtype).itype,
            },
            on_yes_callback=self._save_edit,
        )

    def _save_edit(self) -> None:
        """Validate and save the edited value."""
        new_value_str = self.input.value.strip()

        # Check if value changed
        if new_value_str == self.input_value:
            self.dismiss(None)
            self.notify("No changes made", title="Edit", severity="warning")
            return

        # Parse and validate based on column dtype
        try:
            new_value = self._parse_value(new_value_str)
        except Exception as e:
            self.dismiss(None)  # Dismiss without changes
            self.notify(f"Invalid value: {str(e)}", title="Edit", severity="error")
            return

        # Dismiss with the new value
        self.dismiss((self.row_key, self.col_idx, new_value))

    def _parse_value(self, value: str):
        """Parse string value based on column dtype."""
        dtype = self.col_dtype

        if value == "":
            return None
        elif dtype == "Int64":
            return int(value)
        elif dtype == "Float64":
            return float(value)
        elif dtype == "String":
            return value
        elif dtype == "Boolean":
            try:
                return BOOLS[value.lower()]
            except KeyError:
                raise ValueError(f"Invalid boolean value: [on $primary]{value}[/]")
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

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "SearchScreen")

    def __init__(
        self,
        term,
        col_dtype: pl.DataType,
        col_name: str | None = None,
    ):
        col_dtype = col_dtype if col_name else pl.String
        label = f"Search [$primary]{term}[/] ([$accent]{col_dtype}[/])"
        self.col_name = col_name
        self.col_dtype = col_dtype

        super().__init__(
            title="Search" if col_name else "Global Search",
            label=f"{label} in [$primary]{col_name}[/]" if col_name else label,
            input={"value": term, "type": DtypeConfig(col_dtype).itype},
            on_yes_callback=self._do_search,
        )

    def _do_search(self) -> None:
        """Perform the search."""
        term = self.input.value.strip()

        if not term:
            self.notify("Search term cannot be empty", title="Search", severity="error")
            return

        # Dismiss with the search term
        self.dismiss((term, self.col_dtype, self.col_name))


class FilterScreen(YesNoScreen):
    """Modal screen to filter rows by column expression."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "FilterScreen")

    def __init__(
        self,
        df: pl.DataFrame,
        current_col_idx: int | None = None,
        current_cell_value: str | None = None,
    ):
        self.df = df
        self.current_col_idx = current_col_idx
        super().__init__(
            title="Filter by Expression",
            label="Enter filter expression, e.g., $1 > 50, $name == 'text', $_ > 100, $a < $b",
            input=f"$_ == {current_cell_value}",
            on_yes_callback=self._validate_filter,
        )

    def _validate_filter(self) -> pl.Expr | None:
        """Validate and return the filter expression."""
        expression = self.input.value.strip()

        try:
            # Try to parse the expression to ensure it's valid
            expr_str = parse_filter_expression(
                expression, self.df, self.current_col_idx
            )

            try:
                # Test the expression by evaluating it
                expr = eval(expr_str, {"pl": pl})

                # Dismiss with the expression
                self.dismiss((expr, expr_str))
            except Exception as e:
                self.notify(
                    f"Error evaluating expression: {str(e)}",
                    title="Filter",
                    severity="error",
                )
                self.dismiss(None)
        except ValueError as ve:
            self.notify(
                f"Invalid expression: {str(ve)}", title="Filter", severity="error"
            )
            self.dismiss(None)


class PinScreen(YesNoScreen):
    """Modal screen to pin rows and columns.

    Accepts one value for fixed rows, or two space-separated values for fixed rows and columns.
    """

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "PinScreen")

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
            self.notify("Input cannot be empty", title="Pin", severity="error")
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
                self.notify(
                    f"Invalid fixed rows value: {str(e)}", title="Pin", severity="error"
                )
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
                self.notify(
                    f"Invalid input values: {str(e)}", title="Pin", severity="error"
                )
                return None
        else:
            self.notify(
                "Provide one or two space-separated integers",
                title="Pin",
                severity="error",
            )
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
    visible_rows: list[bool]
    fixed_rows: int
    fixed_columns: int
    cursor_coordinate: Coordinate


class MyDataTable(DataTable):
    """Custom DataTable to highlight row/column labels based on cursor position."""

    # Help text for the DataTable which will be shown in the HelpPanel
    HELP = dedent("""
        # 📊 DataFrame Viewer - Quick Help

        ## ⬆️ Navigation
        - **q** - 🚪 Quit
        - **Arrow Keys** - 🎯 Move cursor
        - **g** - ⬆️ First row
        - **G** - ⬇️ Last row
        - **PgUp/Dn** - 📜 Scroll

        ## 👁️ View & Cursor
        - **Enter** - 📋 Row details
        - **C** - 🔄 Cycle cursor type (cell/row/col)
        - **#** - 🏷️ Toggle labels
        - **k** - 🌙 Toggle dark mode

        ## ✏️ Editing
        - **e** - ✍️ Edit cell
        - **d** - 🗑️ Delete row
        - **-** - ❌ Delete column

        ## 🔍 Search & Filter
        - **|** - 🔎 Search column
        - **\\\\** - 🎯 Search cell value
        - **/** - 🌐 Global search (all columns)
        - **t** - 💡 Toggle selection
        - **"** - 📍 Filter to selected
        - **T** - 🧹 Clear selection
        - **f** - 🔧 Filter by Polars expression

        ## 📊 Sort & Reorder
        - **[** - 🔼 Sort ascending
        - **]** - 🔽 Sort descending
        - **F** - 📈 Frequency table of column
        - **Shift+↑↓←→** - 🔀 Move row/column

        ## 💾 Data Management
        - **p** - 📌 Pin rows/cols
        - **c** - 📋 Copy cell
        - **Ctrl+S** - 💾 Save
        - **u** - ↩️ Undo
        - **U** - 🔄 Reset all
    """).strip()

    @property
    def cursor_key(self) -> CellKey:
        """Get the current cursor position as a CellKey."""
        return self.coordinate_to_cell_key(self.cursor_coordinate)

    @property
    def cursor_row_key(self) -> RowKey:
        """Get the current cursor row as a CellKey."""
        return self.cursor_key.row_key

    @property
    def cursor_column_key(self) -> ColumnKey:
        """Get the current cursor column as a ColumnKey."""
        return self.cursor_key.column_key

    @property
    def cursor_row_idx(self) -> int:
        """Get the current cursor row index (0-based) corresponding to the DataFrame."""
        return int(self.cursor_row_key.value) - 1

    def _should_highlight(
        self,
        cursor: Coordinate,
        target_cell: Coordinate,
        type_of_cursor: CursorType,
    ) -> bool:
        """Determine if the given cell should be highlighted because of the cursor.

        In "cell" mode, also highlights the row and column headers. In "row" and "column"
        modes, highlights the entire row or column respectively.

        Args:
            cursor: The current position of the cursor.
            target_cell: The cell we're checking for the need to highlight.
            type_of_cursor: The type of cursor that is currently active.

        Returns:
            Whether or not the given cell should be highlighted.
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

    def watch_cursor_coordinate(
        self, old_coordinate: Coordinate, new_coordinate: Coordinate
    ) -> None:
        """Refresh highlighting when cursor coordinate changes.

        This explicitly refreshes cells that need to change their highlight state
        to fix the delay issue with column label highlighting. Also emits CellSelected
        message when cursor type is "cell" for keyboard navigation only (mouse clicks
        already trigger the parent class's CellSelected message).
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
                self.refresh_row(new_coordinate.row)
            elif self.cursor_type == "column":
                self.refresh_column(old_coordinate.column)
                self.refresh_column(new_coordinate.column)

            # Handle scrolling if needed
            if self._require_update_dimensions:
                self.call_after_refresh(self._scroll_cursor_into_view)
            else:
                self._scroll_cursor_into_view()

    def on_key(self, event) -> None:
        """Handle keyboard events to set flag for keyboard-driven cursor changes.

        When arrow keys are pressed, set _from_keyboard flag so watcher emits CellSelected.
        """
        if event.key in (
            "up",
            "down",
            "left",
            "right",
            "home",
            "end",
            "pageup",
            "pagedown",
            "ctrl+home",
            "ctrl+end",
        ):
            self._from_keyboard = True

            # Let parent handle the actual key event
            parent = super()
            if hasattr(parent, "on_key"):
                parent.on_key(event)


class MyHelpPanel(Widget):
    """
    Shows context sensitive help for the currently focused widget.

    Modified from Textual's built-in HelpPanel with KeyPanel removed.
    """

    DEFAULT_CSS = """
        MyHelpPanel {
            split: right;
            width: 33%;
            min-width: 30;
            max-width: 60;
            border-left: vkey $foreground 30%;
            padding: 0 1;
            height: 1fr;
            padding-right: 1;
            layout: vertical;
            height: 100%;

            &:ansi {
                background: ansi_default;
                border-left: vkey ansi_black;

                Markdown {
                    background: ansi_default;
                }
                .bindings-table--divide {
                    color: transparent;
                }
            }

            #widget-help {
                height: auto;
                width: 1fr;
                padding: 0;
                margin: 0;
                padding: 1 0;
                margin-top: 1;
                display: none;
                background: $panel;

                &:ansi {
                    background: ansi_default;
                }

                MarkdownBlock {
                    padding-left: 2;
                    padding-right: 2;
                }
            }

            &.-show-help #widget-help {
                display: block;
            }
        }
    """

    DEFAULT_CLASSES = "-textual-system"

    def on_mount(self):
        def update_help(focused_widget: Widget | None):
            self.update_help(focused_widget)

        self.watch(self.screen, "focused", update_help)

    def update_help(self, focused_widget: Widget | None) -> None:
        """Update the help for the focused widget.

        Args:
            focused_widget: The currently focused widget, or `None` if no widget was focused.
        """
        if not self.app.app_focus:
            return
        if not self.screen.is_active:
            return
        self.set_class(focused_widget is not None, "-show-help")
        if focused_widget is not None:
            help = focused_widget.HELP or ""
            if not help:
                self.remove_class("-show-help")
            try:
                self.query_one(Markdown).update(dedent(help))
            except NoMatches:
                pass

    def compose(self) -> ComposeResult:
        yield Markdown(id="widget-help")


class DataFrameApp(App):
    """A Textual app to interact with a Polars DataFrame."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("h,?", "toggle_help_panel", "Help"),
        ("k", "toggle_dark", "Toggle Dark Mode"),
        ("number_sign", "toggle_row_labels", "Toggle Row Labels"),
        ("c", "copy_cell", "Copy Cell"),
    ]

    CSS = """
        /* Make it scrollable */
        Markdown {
            height: 1fr;          /* Fill available vertical space */
            width: 1fr;           /* Fill available horizontal space */
            overflow-y: auto;     /* Enable vertical scrolling */
            overflow-x: auto;     /* (optional) Enable horizontal scrolling */
        }
    """

    # Reactive cursor coordinate to highlight row label and column header
    cursor_coordinate: Reactive[Coordinate] = Reactive(
        Coordinate(0, 0), always_update=True
    )

    def __init__(self, df: pl.DataFrame, filename: str = ""):
        super().__init__()
        self.dataframe = df  # Original dataframe
        self.df = df  # Internal dataframe
        self.filename = filename  # Current filename
        self.loaded_rows = 0  # Track how many rows are currently loaded
        self.sorted_columns = {}  # Track sort keys as dict of col_name -> descending
        self.selected_rows = [False] * len(df)  # Track selected rows (0-based)
        self.visible_rows = [True] * len(df)  # Track visible rows (0-based)
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
        self.table = MyDataTable(zebra_stripes=True)
        yield self.table
        self.help_panel = None

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
        elif event.key == "ctrl+s":
            # Save dataframe to CSV
            self._save_to_file()
        elif event.key == "F":  # shift+f
            # Open frequency modal for current column
            self._show_frequency()
        elif event.key == "f":
            # Open filter screen for current column
            self._open_filter_screen()
        elif event.key == "v":
            # Filter by current cell value
            self._filter_by_cell_value()
        elif event.key == "e":
            # Open edit modal for current cell
            self._edit_cell()
        elif event.key == "vertical_line":  # '|' key
            # Open search modal for current column
            self._search_column()
        elif event.key == "slash":  # '/' key
            # Open search modal for all columns
            self._search_column(all_columns=True)
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
        elif event.key == "U":
            # Undo all changes and restore original dataframe
            self._setup_table(reset=True)
            self.notify("Restored original display", title="Reset")
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
        elif event.key == "T":  # shift+t
            # Clear all selected rows
            self._clear_selected_rows()
        elif event.key == "C":  # shift+c
            # Cycle through cursor types
            self._cycle_cursor_type()
        elif event.key == "p":
            # Open pin screen to set fixed rows and columns
            self._open_pin_screen()

    def on_mouse_scroll_down(self, event) -> None:
        """Load more rows when scrolling down with mouse."""
        self._check_and_load_more()

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Update reactive cursor coordinate when cell is selected.

        Notes: cursor movement via keyboard does not trigger this event.

        See `MyDataTable.watch_cursor_coordinate()` above.
        """
        self.cursor_coordinate = event.coordinate

    def action_toggle_row_labels(self) -> None:
        """Toggle row labels visibility using CSS property."""
        self.table.show_row_labels = not self.table.show_row_labels

    def action_toggle_help_panel(self) -> None:
        """Toggle the HelpPanel on/off."""
        if self.help_panel:
            # Toggle display
            self.help_panel.display = not self.help_panel.display
        else:
            # Add HelpPanel
            self.help_panel = MyHelpPanel()
            self.mount(self.help_panel, after=self.table)

            # Schedule the update for the next iteration of the event loop
            def update_markdown():
                markdown = self.query_one(Markdown)
                markdown.update(self.table.HELP)

            self.call_later(update_markdown)

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
            self.notify(
                "clipboard tool not available", title="Clipboard", severity="error"
            )

    # Load
    def _setup_table(self, reset: bool = False) -> None:
        """Setup the table for display."""
        # Reset to original dataframe
        if reset:
            self.df = self.dataframe
            self.loaded_rows = 0
            self.sorted_columns = {}
            self.selected_rows = [False] * len(self.df)
            self.visible_rows = [True] * len(self.df)
            self.fixed_rows = 0
            self.fixed_columns = 0

        # Lazy load up to INITIAL_BATCH_SIZE visible rows
        stop, visible_count = len(self.df), 0
        for row_idx, visible in enumerate(self.visible_rows):
            if not visible:
                continue
            visible_count += 1
            if visible_count >= INITIAL_BATCH_SIZE:
                stop = row_idx + 1
                break

        self._setup_columns()
        self._load_rows(stop)
        self._highlight_rows()

        self.table.fixed_rows = self.fixed_rows
        self.table.fixed_columns = self.fixed_columns

        # Restore cursor position
        row_idx, col_idx = self.cursor_coordinate
        if row_idx < len(self.table.rows) and col_idx < len(self.table.columns):
            self.table.move_cursor(row=row_idx, column=col_idx)

    def _setup_columns(self) -> None:
        """Clear table and setup columns."""
        self.loaded_rows = 0
        self.table.clear(columns=True)
        self.table.show_row_labels = True

        # Add columns with justified headers
        for col, dtype in zip(self.df.columns, self.df.dtypes):
            for idx, c in enumerate(self.sorted_columns, 1):
                if c == col:
                    # Add sort indicator to column header
                    descending = self.sorted_columns[col]
                    sort_indicator = (
                        f" ▼{SUBSCRIPT_DIGITS.get(idx, '')}"
                        if descending
                        else f" ▲{SUBSCRIPT_DIGITS.get(idx, '')}"
                    )
                    header_text = col + sort_indicator
                    self.table.add_column(
                        Text(header_text, justify=DtypeConfig(dtype).justify), key=col
                    )

                    break
            else:  # No break occurred, so column is not sorted
                self.table.add_column(
                    Text(col, justify=DtypeConfig(dtype).justify), key=col
                )

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
            if not self.visible_rows[row_idx]:
                continue  # Skip hidden rows
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
        self.push_screen(FrequencyScreen(col_idx, self.df.filter(self.visible_rows)))

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

    # Delete & Move
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
        """
        old_count = len(self.df)
        filter_expr = [True] * len(self.df)

        # Delete all selected rows
        if selected_count := self.selected_rows.count(True):
            history_desc = f"Deleted {selected_count} selected row(s)"

            for i, is_selected in enumerate(self.selected_rows):
                if is_selected:
                    filter_expr[i] = False
        # Delete the row at the cursor
        else:
            row_key = self.table.cursor_row_key
            i = int(row_key.value) - 1  # Convert to 0-based index

            filter_expr[i] = False
            history_desc = f"Deleted row [on $primary]{row_key.value}[/]"

        # Add to history
        self._add_history(history_desc)

        # Apply the filter to remove rows
        df = self.df.with_row_index("__rid__").filter(filter_expr)
        self.df = df.drop("__rid__")

        # Update selected and visible rows tracking
        old_row_indices = set(df["__rid__"].to_list())
        self.selected_rows = [
            selected
            for i, selected in enumerate(self.selected_rows)
            if i in old_row_indices
        ]
        self.visible_rows = [
            visible
            for i, visible in enumerate(self.visible_rows)
            if i in old_row_indices
        ]

        # Recreate the table display
        self._setup_table()

        deleted_count = old_count - len(self.df)
        self.notify(f"Deleted {deleted_count} row(s)", title="Delete")

    def _move_column(self, direction: str) -> None:
        """Move the current column left or right.

        Args:
            direction: "left" to move left, "right" to move right.
        """
        row_idx, col_idx = self.table.cursor_coordinate
        col_key = self.table.cursor_column_key

        # Validate move is possible
        if direction == "left":
            if col_idx <= 0:
                self.notify("Cannot move column left", title="Move", severity="warning")
                return
            swap_idx = col_idx - 1
        elif direction == "right":
            if col_idx >= len(self.table.columns) - 1:
                self.notify(
                    "Cannot move column right", title="Move", severity="warning"
                )
                return
            swap_idx = col_idx + 1

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

        # Update the dataframe column order
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
                self.notify("Cannot move row up", title="Move", severity="warning")
                return
            swap_idx = row_idx - 1
        elif direction == "down":
            if row_idx >= len(self.table.rows) - 1:
                self.notify("Cannot move row down", title="Move", severity="warning")
                return
            swap_idx = row_idx + 1
        else:
            self.notify(
                f"Invalid direction: {direction}", title="Move", severity="error"
            )
            return

        row_key = self.table.coordinate_to_cell_key((row_idx, 0)).row_key
        swap_key = self.table.coordinate_to_cell_key((swap_idx, 0)).row_key

        # Add to history
        self._add_history(
            f"Moved row [on $primary]{row_key.value}[/] {direction} (swapped with row [on $primary]{swap_key.value}[/])"
        )

        # Swap rows in the table's internal row locations
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

        # Swap rows in the dataframe
        rid = int(row_key.value) - 1  # 0-based
        swap_rid = int(swap_key.value) - 1  # 0-based
        first, second = sorted([rid, swap_rid])

        self.df = pl.concat(
            [
                self.df.slice(0, first),
                self.df.slice(second, 1),
                self.df.slice(first + 1, second - first - 1),
                self.df.slice(first, 1),
                self.df.slice(second + 1),
            ]
        )

        self.notify(
            f"Moved row [on $primary]{row_key.value}[/] {direction}", title="Move"
        )

    # Sort
    def _sort_by_column(self, descending: bool = False) -> None:
        """Sort by the currently selected column.

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

        # Check if this column is already in the sort keys
        old_desc = self.sorted_columns.get(col_to_sort)
        if old_desc == descending:
            # Same direction - remove this column from sort
            self.notify(
                f"Already sorted by [on $primary]{col_to_sort}[/] ({'desc' if descending else 'asc'})",
                title="Sort",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(f"Sorted on column [on $primary]{col_to_sort}[/]")
        if old_desc is None:
            # Add new column to sort
            self.sorted_columns[col_to_sort] = descending
        else:
            # Toggle direction and move to end of sort order
            del self.sorted_columns[col_to_sort]
            self.sorted_columns[col_to_sort] = descending

        # Apply multi-column sort
        sort_cols = list(self.sorted_columns.keys())
        descending_flags = list(self.sorted_columns.values())
        df_sorted = self.df.with_row_index("__rid__").sort(
            sort_cols, descending=descending_flags, nulls_last=True
        )

        # Updated selected_rows and visible_rows to match new order
        old_row_indices = df_sorted["__rid__"].to_list()
        self.selected_rows = [self.selected_rows[i] for i in old_row_indices]
        self.visible_rows = [self.visible_rows[i] for i in old_row_indices]

        # Update the dataframe
        self.df = df_sorted.drop("__rid__")

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
            SaveFileScreen(self.filename), callback=self._on_save_file_screen
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
            self.df.write_csv(filename, separator=separator)
            self.dataframe = self.df  # Update original dataframe
            self.filename = filename  # Update current filename
            self.notify(f"Saved to [on $primary]{filename}[/]", title="Save")
        except Exception as e:
            self.notify(f"Failed to save: {str(e)}", title="Save", severity="error")
            raise e

    # Edit
    def _edit_cell(self) -> None:
        """Open modal to edit the selected cell."""
        row_key = self.table.cursor_row_key
        row_idx = int(row_key.value) - 1  # Convert to 0-based
        col_idx = self.table.cursor_column

        if row_idx >= len(self.df) or col_idx >= len(self.df.columns):
            return
        col_name = self.df.columns[col_idx]

        # Save current state to history
        self._add_history(f"Edited cell [on $primary]({row_idx + 1}, {col_name})[/]")

        # Push the edit modal screen
        self.push_screen(
            EditCellScreen(row_key, col_idx, self.df),
            callback=self._do_edit_cell,
        )

    def _do_edit_cell(self, result) -> None:
        """Handle result from EditCellScreen."""
        if result is None:
            return

        row_key, col_idx, new_value = result
        row_idx = int(row_key.value) - 1  # Convert to 0-based
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
            if cell_value is None:
                cell_value = "-"
            dtype = self.df.dtypes[col_idx]
            dc = DtypeConfig(dtype)
            formatted_value = Text(str(cell_value), style=dc.style, justify=dc.justify)

            row_key = str(row_idx + 1)
            col_key = str(col_name)
            self.table.update_cell(row_key, col_key, formatted_value)

            self.notify(f"Cell updated to [on $primary]{cell_value}[/]", title="Edit")
        except Exception as e:
            self.notify(
                f"Failed to update cell: {str(e)}", title="Edit", severity="error"
            )
            raise e

    # Search & Highlight
    def _search_column(self, all_columns: bool = False) -> None:
        """Open modal to search in the selected column."""
        row_idx, col_idx = self.table.cursor_coordinate
        if col_idx >= len(self.df.columns):
            self.notify("Invalid column selected", title="Search", severity="error")
            return

        col_name = None if all_columns else self.df.columns[col_idx]
        col_dtype = self.df.dtypes[col_idx]

        # Get current cell value as default search term
        term = self.df.item(row_idx, col_idx)
        term = "NULL" if term is None else str(term)

        # Push the search modal screen
        self.push_screen(
            SearchScreen(term, col_dtype, col_name),
            callback=self._do_search_column,
        )

    def _do_search_column(self, result) -> None:
        """Handle result from SearchScreen."""
        if result is None:
            return

        term, col_dtype, col_name = result
        if col_name:
            # Perform search in the specified column
            self._search_single_column(term, col_dtype, col_name)
        else:
            # Perform search in all columns
            self._search_all_columns(term)

    def _search_single_column(
        self, term: str, col_dtype: pl.DataType, col_name: str
    ) -> None:
        """Search for a term in a single column and update selected rows.

        Args:
            term: The search term to find
            col_dtype: The data type of the column
            col_name: The name of the column to search in
        """
        df_rid = self.df.with_row_index("__rid__")
        if False in self.visible_rows:
            df_rid = df_rid.filter(self.visible_rows)

        # Perform type-aware search based on column dtype
        if term.lower() == "null":
            masks = df_rid[col_name].is_null()
        elif col_dtype == pl.String:
            masks = df_rid[col_name].str.contains(term)
        elif col_dtype == pl.Boolean:
            masks = df_rid[col_name] == BOOLS[term.lower()]
        elif col_dtype in (pl.Int32, pl.Int64):
            masks = df_rid[col_name] == int(term)
        elif col_dtype in (pl.Float32, pl.Float64):
            masks = df_rid[col_name] == float(term)
        else:
            self.notify(
                f"Search not yet supported for column type: [on $primary]{col_dtype}[/]",
                title="Search",
                severity="warning",
            )
            return

        # Apply filter to get matched row indices
        matches = set(df_rid.filter(masks)["__rid__"].to_list())

        match_count = len(matches)
        if match_count == 0:
            self.notify(
                f"No matches found for: [on $primary]{term}[/]",
                title="Search",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(
            f"Searched and highlighted [on $primary]{term}[/] in column [on $primary]{col_name}[/]"
        )

        # Update selected rows to include new matches
        for m in matches:
            self.selected_rows[m] = True

        # Highlight selected rows
        self._highlight_rows()

        self.notify(
            f"Found [on $primary]{match_count}[/] matches for [on $primary]{term}[/]",
            title="Search",
        )

    def _search_all_columns(self, term: str) -> None:
        """Search for a term across all columns and highlight matching cells.

        Args:
            term: The search term to find
        """
        df_rid = self.df.with_row_index("__rid__")
        if False in self.visible_rows:
            df_rid = df_rid.filter(self.visible_rows)

        matches: dict[int, set[int]] = defaultdict(set)
        match_count = 0
        if term.lower() == "null":
            # Search for NULL values across all columns
            for col_idx, col in enumerate(df_rid.columns[1:]):
                masks = df_rid[col].is_null()
                matched_rids = set(df_rid.filter(masks)["__rid__"].to_list())
                for rid in matched_rids:
                    matches[rid].add(col_idx)
                    match_count += 1
        else:
            # Search for the term in all columns
            for col_idx, col in enumerate(df_rid.columns[1:]):
                col_series = df_rid[col].cast(pl.String)
                masks = col_series.str.contains(term)
                matched_rids = set(df_rid.filter(masks)["__rid__"].to_list())
                for rid in matched_rids:
                    matches[rid].add(col_idx)
                    match_count += 1

        if match_count == 0:
            self.notify(
                f"No matches found for: [on $primary]{term}[/] in any column",
                title="Global Search",
                severity="warning",
            )
            return

        # Ensure all matching rows are loaded
        self._load_rows(max(matches.keys()) + 1)

        # Add to history
        self._add_history(
            f"Searched and highlighted [on $primary]{term}[/] across all columns"
        )

        # Highlight matching cells directly
        for row in self.table.ordered_rows:
            row_idx = int(row.key.value) - 1  # Convert to 0-based index
            if row_idx not in matches:
                continue

            for col_idx in matches[row_idx]:
                row_key = row.key
                col_key = self.df.columns[col_idx]

                cell_text: Text = self.table.get_cell(row_key, col_key)
                cell_text.style = "red"

                # Update the cell in the table
                self.table.update_cell(row_key, col_key, cell_text)

        self.notify(
            f"Found [on $success]{match_count}[/] matches for [on $primary]{term}[/] across all columns",
            title="Global Search",
        )

    def _search_with_cell_value(self) -> None:
        """Search in the current column using the value of the currently selected cell."""
        row_key = self.table.cursor_row_key
        row_idx = int(row_key.value) - 1  # Convert to 0-based index
        col_idx = self.table.cursor_column

        # Get the value of the currently selected cell
        term = self.df.item(row_idx, col_idx)
        term = "NULL" if term is None else str(term)

        col_dtype = self.df.dtypes[col_idx]
        col_name = self.df.columns[col_idx]
        self._do_search_column((term, col_dtype, col_name))

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
        for row in self.table.ordered_rows:
            row_idx = int(row.key.value) - 1  # Convert to 0-based index
            is_selected = self.selected_rows[row_idx]

            # Update all cells in this row
            for col_idx, col in enumerate(self.table.ordered_columns):
                cell_text: Text = self.table.get_cell(row.key, col.key)
                dtype = self.df.dtypes[col_idx]

                # Get style config based on dtype
                dc = DtypeConfig(dtype)

                # Use red for selected rows, default style for others
                style = "red" if is_selected else dc.style
                cell_text.style = style

                # cell_value = cell_text.plain
                # formatted_value = Text(
                #     str(cell_value) if cell_value is not None else "-",
                #     style=style,
                #     justify=dc.justify,
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

        # Update dataframe to only include selected rows
        self.df = self.df.filter(self.selected_rows)
        self.selected_rows = [True] * len(self.df)

        # Recreate the table for display
        self._setup_table()

        self.notify(
            f"Removed unselected rows. Now showing [on $primary]{selected_count}[/] rows",
            title="Filter",
        )

    # Filter
    def _open_filter_screen(self) -> None:
        """Open the filter screen to enter a filter expression."""
        row_key = self.table.cursor_row_key
        row_idx = int(row_key.value) - 1  # Convert to 0-based index
        col_idx = self.table.cursor_column

        cell_value = self.df.item(row_idx, col_idx)
        if self.df.dtypes[col_idx] == pl.String and cell_value is not None:
            cell_value = repr(cell_value)

        self.push_screen(
            FilterScreen(
                self.df, current_col_idx=col_idx, current_cell_value=cell_value
            ),
            callback=self._do_filter,
        )

    def _do_filter(self, result) -> None:
        """Handle result from FilterScreen.

        Args:
            expression: The filter expression or None if cancelled.
        """
        if result is None:
            return
        expr, expr_str = result

        # Add a row index column to track original row indices
        df_with_rid = self.df.with_row_index("__rid__")

        # Apply existing visibility filter first
        if False in self.visible_rows:
            df_with_rid = df_with_rid.filter(self.visible_rows)

        # Apply the filter expression
        df_filtered = df_with_rid.filter(expr)

        matched_count = len(df_filtered)
        if not matched_count:
            self.notify(
                f"No rows match the expression: [on $primary]{expr_str}[/]",
                title="Filter",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(f"Filtered by expression [on $primary]{expr_str}[/]")

        # Mark unfiltered rows as invisible and unselected
        filtered_row_indices = set(df_filtered["__rid__"].to_list())
        if filtered_row_indices:
            for rid in range(len(self.visible_rows)):
                if rid not in filtered_row_indices:
                    self.visible_rows[rid] = False
                    self.selected_rows[rid] = False

        # Recreate the table for display
        self._setup_table()

        self.notify(
            f"Filtered to [on $primary]{matched_count}[/] matching rows",
            title="Filter",
        )

    def _filter_by_cell_value(self) -> None:
        """Filter rows based on the value of the currently selected cell."""
        row_key = self.table.cursor_row_key
        row_idx = int(row_key.value) - 1  # Convert to 0-based index
        col_idx = self.table.cursor_column

        cell_value = self.df.item(row_idx, col_idx)

        if cell_value is None:
            expr = pl.col(self.df.columns[col_idx]).is_null()
            expr_str = "NULL"
        else:
            expr = pl.col(self.df.columns[col_idx]) == cell_value
            expr_str = f"$_ == {repr(cell_value)}"

        self._do_filter((expr, expr_str))

    # Misc
    def _cycle_cursor_type(self) -> None:
        """Cycle through cursor types: cell -> row -> column -> cell."""
        current_type = self.table.cursor_type
        next_type = CURSOR_TYPES[
            (CURSOR_TYPES.index(current_type) + 1) % len(CURSOR_TYPES)
        ]
        self.table.cursor_type = next_type

        self.notify(
            f"Changed cursor type to [on $primary]{next_type}[/]", title="Cursor"
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
            visible_rows=self.visible_rows.copy(),
            fixed_rows=self.fixed_rows,
            fixed_columns=self.fixed_columns,
            cursor_coordinate=self.table.cursor_coordinate,
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
        self.selected_rows = history.selected_rows.copy()
        self.visible_rows = history.visible_rows.copy()
        self.fixed_rows = history.fixed_rows
        self.fixed_columns = history.fixed_columns
        self.cursor_coordinate = history.cursor_coordinate

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
    filename = "stdin.csv"

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
