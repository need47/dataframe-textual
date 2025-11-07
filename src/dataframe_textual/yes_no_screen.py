"""Modal screens with Yes/No buttons and their specialized variants."""

import polars as pl
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from .common import NULL, DtypeConfig, validate_expr


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
            width: auto;
            min-width: 30;
            max-width: 60;
            height: auto;
            border: solid $primary;
            border-title-color: $primary-lighten-3;
            background: $surface;
            padding: 2;
        }

        YesNoScreen Label {
            width: 100%;
            text-wrap: wrap;
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
            on_yes_callback: Optional callable that takes no args and returns the value to dismiss with when Yes is pressed
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

    def __init__(self, filename: str, title="Save Tab"):
        super().__init__(
            title=title,
            input=filename,
            on_yes_callback=self.handle_save,
        )

    def handle_save(self):
        if self.input:
            input_filename = self.input.value.strip()
            if input_filename:
                return input_filename
            else:
                self.notify("Filename cannot be empty", title="Save", severity="error")
                return None

        return None


class ConfirmScreen(YesNoScreen):
    """Modal screen to confirm file overwrite."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "ConfirmScreen")

    def __init__(self, title: str):
        super().__init__(
            title=title,
            on_yes_callback=self.handle_confirm,
        )

    def handle_confirm(self) -> None:
        return True


class EditCellScreen(YesNoScreen):
    """Modal screen to edit a single cell value."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "EditCellScreen")

    def __init__(self, ridx: int, cidx: int, df: pl.DataFrame):
        self.ridx = ridx
        self.cidx = cidx
        self.dtype = df.dtypes[cidx]

        # Label
        content = f"[$success]{df.columns[cidx]}[/] ([$accent]{self.dtype}[/])"

        # Input
        df_value = df.item(ridx, cidx)
        self.input_value = "" if df_value is None else str(df_value).strip()

        super().__init__(
            title="Edit Cell",
            label=content,
            input={
                "value": self.input_value,
                "type": DtypeConfig(self.dtype).itype,
            },
            on_yes_callback=self._validate_input,
        )

    def _validate_input(self) -> None:
        """Validate and save the edited value."""
        new_value_str = self.input.value.strip()

        # Handle empty input
        if not new_value_str:
            new_value = None
            self.notify(
                "Empty value provided. If you want to clear the cell, press [$accent]x[/].",
                title="Edit",
                severity="warning",
            )
        # Check if value changed
        elif new_value_str == self.input_value:
            new_value = None
            self.notify("No changes made", title="Edit", severity="warning")
        else:
            # Parse and validate based on column dtype
            try:
                new_value = DtypeConfig(self.dtype).convert(new_value_str)
            except Exception as e:
                self.notify(
                    f"Failed to convert [$accent]{new_value_str}[/] to [$error]{self.dtype}[/]: {str(e)}",
                    title="Edit",
                    severity="error",
                )
                return None

        # New value
        return self.ridx, self.cidx, new_value


class RenameColumnScreen(YesNoScreen):
    """Modal screen to rename a column."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "RenameColumnScreen")

    def __init__(self, col_idx: int, col_name: str, existing_columns: list[str]):
        self.col_idx = col_idx
        self.col_name = col_name
        self.existing_columns = [c for c in existing_columns if c != col_name]

        # Label
        content = f"Rename header [$success]{col_name}[/]"

        super().__init__(
            title="Rename Column",
            label=content,
            input={"value": col_name},
            on_yes_callback=self._validate_input,
        )

    def _validate_input(self) -> None:
        """Validate and save the new column name."""
        new_name = self.input.value.strip()

        # Check if name is empty
        if not new_name:
            self.notify("Column name cannot be empty", title="Rename", severity="error")

        # Check if name changed
        elif new_name == self.col_name:
            self.notify("No changes made", title="Rename", severity="warning")
            new_name = None

        # Check if name already exists
        elif new_name in self.existing_columns:
            self.notify(
                f"Column [$accent]{new_name}[/] already exists",
                title="Rename",
                severity="error",
            )
            new_name = None

        # Return new name
        return self.col_idx, self.col_name, new_name


class SearchScreen(YesNoScreen):
    """Modal screen to search for values in a column."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "SearchScreen")

    def __init__(self, title, term, df: pl.DataFrame, cidx: int):
        self.cidx = cidx

        EXPR = f"ABC, (?i)abc, ^abc$, {NULL}, $_ > 50, $1 < $HP, $_.str.contains('sub')"

        if "Search" in title:
            col_name = df.columns[cidx]
            col_dtype = df.dtypes[cidx]
            label = f"{title} in [$success]{col_name}[/] ([$warning]{col_dtype}[/]) with value or Polars expression, e.g., {EXPR}"
        else:
            label = f"{title} by value or Polars expression, e.g., {EXPR}"

        super().__init__(
            title=title,
            label=label,
            input=term,
            on_yes_callback=self._validate_input,
        )

    def _validate_input(self) -> None:
        """Validate the input and return it."""
        term = self.input.value.strip()

        if not term:
            self.notify("Term cannot be empty", title=self.title, severity="error")
            return

        return term, self.cidx


class FilterScreen(YesNoScreen):
    """Modal screen to filter rows by column expression."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "FilterScreen")

    def __init__(self, df: pl.DataFrame, cidx: int, input_value: str | None = None):
        self.df = df
        self.cidx = cidx
        super().__init__(
            title="Filter by Expression",
            label="e.g., NULL, $1 > 50, $name == 'text', $_ > 100, $a < $b, $_.str.contains('sub')",
            input=input_value,
            on_yes_callback=self._get_input,
        )

    def _get_input(self) -> tuple[str, int]:
        """Get input."""
        term = self.input.value.strip()
        return term, self.cidx


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
                self.notify(f"Invalid fixed rows value: {str(e)}", title="Pin", severity="error")
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
                self.notify(f"Invalid input values: {str(e)}", title="Pin", severity="error")
                return None
        else:
            self.notify(
                "Provide one or two space-separated integers",
                title="Pin",
                severity="error",
            )
            return None


class OpenFileScreen(YesNoScreen):
    """Modal screen to open a CSV file."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "OpenFileScreen")

    def __init__(self):
        super().__init__(
            title="Open File",
            input="Enter relative or absolute file path",
            yes="Open",
            no="Cancel",
            on_yes_callback=self.handle_open,
        )

    def handle_open(self):
        if self.input:
            filename_input = self.input.value.strip()
            if filename_input:
                return filename_input
            else:
                self.notify("Filename cannot be empty", title="Open", severity="error")
                return None


class EditColumnScreen(YesNoScreen):
    """Modal screen to edit an entire column with an expression."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "EditColumnScreen")

    def __init__(self, cidx: int, df: pl.DataFrame):
        self.cidx = cidx
        self.df = df
        super().__init__(
            title="Edit Column",
            label=f"by value or Polars expression, e.g., abc, pl.lit(7), {NULL}, $_ * 2, $1 + $2, $_.str.to_uppercase(), pl.arange(0, pl.len())",
            input="$_",
            on_yes_callback=self._get_input,
        )

    def _get_input(self) -> tuple[str, int]:
        """Get input."""
        term = self.input.value.strip()
        return term, self.cidx


class AddColumnScreen(YesNoScreen):
    """Modal screen to add a new column with an expression."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "AddColumnScreen")

    def __init__(self, cidx: int, df: pl.DataFrame):
        self.cidx = cidx
        self.df = df
        self.existing_columns = set(df.columns)
        super().__init__(
            title="Add Column",
            label="Enter column name and Polars expression separated by ';' (e.g., 'col_name ; $_ * 2)",
            input="col_name",
            on_yes_callback=self._get_input,
        )

    def _get_input(self) -> tuple[int, str, str] | None:
        """Validate and return the new column configuration."""
        term = self.input.value.strip()

        if not term:
            self.notify("Input cannot be empty", title="Add Column", severity="error")
            return None

        # Split input into column name and expression
        # Format: "col_name ; expression" or just "col_name" (defaults to an empty column)
        parts = term.split(";")
        col_name = parts[0].strip()
        expression = parts[1].strip() if len(parts) > 1 else None

        # Validate column name
        if not col_name:
            self.notify("Column name cannot be empty", title="Add Column", severity="error")
            return None

        if col_name in self.existing_columns:
            self.notify(
                f"Column [$accent]{col_name}[/] already exists",
                title="Add Column",
                severity="error",
            )
            return None

        if expression is None:
            # No expression provided - add empty column
            return self.cidx, col_name, NULL, pl.lit(None)

        try:
            expr = validate_expr(expression, self.df, self.cidx)
            return self.cidx, col_name, expr
        except ValueError as ve:
            self.notify(f"Invalid expression: [$accent]{str(ve)}[/]", title="Add Column", severity="error")
            return None
