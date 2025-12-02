"""Modal screens with Yes/No buttons and their specialized variants."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data_frame_table import DataFrameTable


import polars as pl
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static, TabPane
from textual.widgets.tabbed_content import ContentTab

from .common import NULL, DtypeConfig, tentative_expr, validate_expr


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
            min-width: 40;
            max-width: 60;
            height: auto;
            border: heavy $accent;
            border-title-color: $accent;
            border-title-background: $panel;
            border-title-style: bold;
            background: $background;
            padding: 1 2;
        }

        YesNoScreen Container {
            margin: 1 0 0 0;
            height: auto;
            width: 100%;
        }

        YesNoScreen Label {
            width: 100%;
            text-wrap: wrap;
        }

        YesNoScreen Input {
            margin: 1 0 0 0;
        }

        YesNoScreen Input:blur {
            border: solid $secondary;
        }

        YesNoScreen #checkbox-container {
            margin: 1 0 0 0;
            height: auto;
            align: left middle;
        }

        YesNoScreen Checkbox {
            margin: 0;
        }

        YesNoScreen Checkbox:blur {
            border: solid $secondary;
        }

        YesNoScreen #button-container {
            margin: 1 0 0 0;
            width: 100%;
            height: 3;
            align: center middle;
        }

        YesNoScreen Button {
            margin: 0 2;
        }
    """

    def __init__(
        self,
        title: str = None,
        label: str | dict | Label = None,
        input: str | dict | Input = None,
        label2: str | dict | Label = None,
        input2: str | dict | Input = None,
        checkbox: str | dict | Checkbox = None,
        checkbox2: str | dict | Checkbox = None,
        yes: str | dict | Button = "Yes",
        maybe: str | dict | Button = None,
        no: str | dict | Button = "No",
        on_yes_callback=None,
        on_maybe_callback=None,
    ) -> None:
        """Initialize the modal screen.

        Creates a customizable Yes/No dialog with optional input fields, labels, and checkboxes.

        Args:
            title: The title to display in the border. Defaults to None.
            label: Optional label to display below title as a Label. Defaults to None.
            input: Optional input widget or value to pre-fill. If None, no Input is shown. Defaults to None.
            label2: Optional second label widget. Defaults to None.
            input2: Optional second input widget or value. Defaults to None.
            checkbox: Optional checkbox widget or label. Defaults to None.
            checkbox2: Optional second checkbox widget or label. Defaults to None.
            yes: Text or dict for the Yes button. If None, hides the Yes button. Defaults to "Yes".
            maybe: Optional Maybe button text/dict. Defaults to None.
            no: Text or dict for the No button. If None, hides the No button. Defaults to "No".
            on_yes_callback: Optional callable that takes no args and returns the value to dismiss with when Yes is pressed. Defaults to None.
        """
        super().__init__()
        self.title = title
        self.label = label
        self.input = input
        self.label2 = label2
        self.input2 = input2
        self.checkbox = checkbox
        self.checkbox2 = checkbox2
        self.yes = yes
        self.maybe = maybe
        self.no = no
        self.on_yes_callback = on_yes_callback
        self.on_maybe_callback = on_maybe_callback

    def compose(self) -> ComposeResult:
        """Compose the modal screen widget structure.

        Builds the widget hierarchy with optional title, labels, inputs, checkboxes,
        and action buttons based on initialization parameters.

        Yields:
            Widget: The components of the modal screen in rendering order.
        """
        with Static(id="modal-container") as container:
            if self.title:
                container.border_title = self.title

            if self.label or self.input:
                with Container(id="input-container"):
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

            if self.label2 or self.input2:
                with Container(id="input-container-2"):
                    if self.label2:
                        if isinstance(self.label2, Label):
                            pass
                        elif isinstance(self.label2, dict):
                            self.label2 = Label(**self.label2)
                        else:
                            self.label2 = Label(self.label2)
                        yield self.label2

                    if self.input2:
                        if isinstance(self.input2, Input):
                            pass
                        elif isinstance(self.input2, dict):
                            self.input2 = Input(**self.input2)
                        else:
                            self.input2 = Input(self.input2)
                        self.input2.select_all()
                        yield self.input2

            if self.checkbox or self.checkbox2:
                with Horizontal(id="checkbox-container"):
                    if self.checkbox:
                        if isinstance(self.checkbox, Checkbox):
                            pass
                        elif isinstance(self.checkbox, dict):
                            self.checkbox = Checkbox(**self.checkbox)
                        else:
                            self.checkbox = Checkbox(self.checkbox)
                        yield self.checkbox

                    if self.checkbox2:
                        if isinstance(self.checkbox2, Checkbox):
                            pass
                        elif isinstance(self.checkbox2, dict):
                            self.checkbox2 = Checkbox(**self.checkbox2)
                        else:
                            self.checkbox2 = Checkbox(self.checkbox2)
                        yield self.checkbox2

            if self.yes or self.no or self.maybe:
                with Horizontal(id="button-container"):
                    if self.yes:
                        if isinstance(self.yes, Button):
                            pass
                        elif isinstance(self.yes, dict):
                            self.yes = Button(**self.yes, id="yes", variant="success")
                        else:
                            self.yes = Button(self.yes, id="yes", variant="success")

                        yield self.yes

                    if self.maybe:
                        if isinstance(self.maybe, Button):
                            pass
                        elif isinstance(self.maybe, dict):
                            self.maybe = Button(**self.maybe, id="maybe", variant="warning")
                        else:
                            self.maybe = Button(self.maybe, id="maybe", variant="warning")

                        yield self.maybe

                    if self.no:
                        if isinstance(self.no, Button):
                            pass
                        elif isinstance(self.no, dict):
                            self.no = Button(**self.no, id="no", variant="error")
                        else:
                            self.no = Button(self.no, id="no", variant="error")

                        yield self.no

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events in the Yes/No screen."""
        if event.button.id == "yes":
            self._handle_yes()
        elif event.button.id == "maybe":
            self._handle_maybe()
        elif event.button.id == "no":
            self.dismiss(None)

    def on_key(self, event) -> None:
        """Handle key press events in the table screen."""
        if event.key == "enter":
            for button in self.query(Button):
                if button.has_focus:
                    if button.id == "yes":
                        self._handle_yes()
                    elif button.id == "maybe":
                        self._handle_maybe()
                    elif button.id == "no":
                        self.dismiss(None)
                    break
            else:
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

    def _handle_maybe(self) -> None:
        """Handle Maybe button press."""
        if self.on_maybe_callback:
            result = self.on_maybe_callback()
            self.dismiss(result)
        else:
            self.dismiss(False)


class SaveFileScreen(YesNoScreen):
    """Modal screen to save the dataframe to a CSV file."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "SaveFileScreen")

    def __init__(self, filename: str, save_all: bool = False, tab_count: int = 1):
        self.save_all = save_all
        super().__init__(
            title="Save to File",
            label="Filename",
            input=filename,
            yes=f"Save {tab_count} Tabs" if self.save_all else "Save Current Tab" if tab_count > 1 else "Save",
            no="Cancel",
            on_yes_callback=self.handle_save,
        )

    def handle_save(self):
        if self.input:
            input_filename = self.input.value.strip()
            if input_filename:
                return input_filename, self.save_all, True  # Overwrite prompt
            else:
                self.notify("Filename cannot be empty", title="Save", severity="error")
                return None


class ConfirmScreen(YesNoScreen):
    """Modal screen to ask for confirmation."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "ConfirmScreen")

    def __init__(self, title: str, label=None, yes="Yes", maybe: str = None, no="No"):
        super().__init__(
            title=title,
            label=label,
            yes=yes,
            maybe=maybe,
            no=no,
            on_yes_callback=self.handle_yes,
        )

    def handle_yes(self) -> bool:
        return True

    def handle_maybe(self) -> bool:
        return False


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
        self.input_value = NULL if df_value is None else str(df_value)

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
        new_value_str = self.input.value  # Do not strip to preserve spaces

        # Handle empty input
        if not new_value_str:
            new_value = ""
            self.notify(
                "Empty value provided. If you want to clear the cell, press [$accent]Delete[/].",
                title="Edit Cell",
                severity="warning",
            )
        # Check if value changed
        elif new_value_str == self.input_value:
            new_value = None
            self.notify("No changes made", title="Edit Cell", severity="warning")
        else:
            # Parse and validate based on column dtype
            try:
                new_value = DtypeConfig(self.dtype).convert(new_value_str)
            except Exception as e:
                self.notify(
                    f"Failed to convert [$accent]{new_value_str}[/] to [$error]{self.dtype}[/]: {str(e)}",
                    title="Edit Cell",
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
            checkbox="Match Nocase",
            checkbox2="Match Whole",
            on_yes_callback=self._validate_input,
        )

    def _validate_input(self) -> tuple[str, int, bool, bool]:
        """Validate the input and return it."""
        term = self.input.value  # Do not strip to preserve spaces

        if not term:
            self.notify("Term cannot be empty", title=self.title, severity="error")
            return

        match_nocase = self.checkbox.value
        match_whole = self.checkbox2.value

        return term, self.cidx, match_nocase, match_whole


class FilterScreen(YesNoScreen):
    """Modal screen to filter rows by column expression."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "FilterScreen")

    def __init__(self, df: pl.DataFrame, cidx: int, term: str | None = None):
        self.df = df
        self.cidx = cidx
        super().__init__(
            title="Filter by Expression",
            label="e.g., NULL, $1 > 50, $name == 'text', $_ > 100, $a < $b, $_.str.contains('sub')",
            input=term,
            checkbox="Match Nocase",
            checkbox2="Match Whole",
            on_yes_callback=self._get_input,
        )

    def _get_input(self) -> tuple[str, int, bool, bool]:
        """Get input."""
        term = self.input.value  # Do not strip to preserve spaces
        match_nocase = self.checkbox.value
        match_whole = self.checkbox2.value

        return term, self.cidx, match_nocase, match_whole


class FreezeScreen(YesNoScreen):
    """Modal screen to pin rows and columns.

    Accepts one value for fixed rows, or two space-separated values for fixed rows and columns.
    """

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "PinScreen")

    def __init__(self):
        super().__init__(
            title="Pin Rows / Columns",
            label="Enter number of fixed rows",
            input={"value": "0", "type": "number"},
            label2="Enter number of fixed columns",
            input2={"value": "0", "type": "number"},
            on_yes_callback=self._get_input,
        )

    def _get_input(self) -> tuple[int, int] | None:
        """Parse and validate the pin input.

        Returns:
            Tuple of (fixed_rows, fixed_columns) or None if invalid.
        """
        fixed_rows = int(self.input.value.strip())
        fixed_cols = int(self.input2.value.strip())

        if fixed_rows < 0 or fixed_cols < 0:
            self.notify("Values must be non-negative", title="Pin", severity="error")
            return None

        return fixed_rows, fixed_cols


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
            label=f"By value or Polars expression, e.g., abc, pl.lit(7), {NULL}, $_ * 2, $1 + $2, $_.str.to_uppercase(), pl.arange(0, pl.len())",
            input="$_",
            on_yes_callback=self._get_input,
        )

    def _get_input(self) -> tuple[str, int]:
        """Get input."""
        term = self.input.value  # Do not strip to preserve spaces
        return term, self.cidx


class AddColumnScreen(YesNoScreen):
    """Modal screen to add a new column with an expression."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "AddColumnScreen")

    def __init__(self, cidx: int, df: pl.DataFrame, link: bool = False):
        self.cidx = cidx
        self.df = df
        self.link = link
        self.existing_columns = set(df.columns)
        super().__init__(
            title="Add Column",
            label="Column name",
            input="Link" if link else "New column",
            label2="Link template, e.g., https://example.com/$1/id/$_, PC/compound/$cid"
            if link
            else "Value or Polars expression, e.g., abc, pl.lit(123), NULL, $_ * 2, $1 + $total, $_ + '_suffix', $_.str.to_uppercase()",
            input2="Link template" if link else "Value or expression",
            on_yes_callback=self._get_input,
        )

    def _get_input(self) -> tuple[int, str, str] | None:
        """Validate and return the new column configuration."""
        col_name = self.input.value.strip()
        term = self.input2.value  # Do not strip to preserve spaces

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

        if term == NULL:
            return self.cidx, col_name, pl.lit(None)
        elif self.link:
            # Treat as link template
            return self.cidx, col_name, term
        elif tentative_expr(term):
            try:
                expr = validate_expr(term, self.df.columns, self.cidx)
                return self.cidx, col_name, expr
            except ValueError as e:
                self.notify(f"Invalid expression [$error]{term}[/]: {str(e)}", title="Add Column", severity="error")
            return None
        else:
            # Treat as literal value
            dtype = self.df.dtypes[self.cidx]
            try:
                value = DtypeConfig(dtype).convert(term)
                return self.cidx, col_name, pl.lit(value)
            except Exception:
                self.notify(
                    f"Unable to convert [$accent]{term}[/] to [$warning]{dtype}[/]. Cast to string.",
                    title="Add Column",
                    severity="warning",
                )
                return self.cidx, col_name, pl.lit(term)


class AddLinkScreen(AddColumnScreen):
    """Modal screen to add a new link column with user-provided expressions.

    Allows user to specify a column name and a value or Polars expression that will be
    evaluated to create links. A new column is created with the resulting link values.
    Inherits column name and expression validation from AddColumnScreen.
    """

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "AddLinkScreen")

    def __init__(self, cidx: int, df: pl.DataFrame):
        super().__init__(cidx, df, link=True)


class FindReplaceScreen(YesNoScreen):
    """Modal screen to replace column values with an expression."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "ReplaceScreen")

    def __init__(self, dftable: "DataFrameTable", title: str = "Find and Replace"):
        if (cursor_value := dftable.cursor_value) is None:
            term_find = NULL
        else:
            term_find = str(cursor_value)

        super().__init__(
            title=title,
            label="Find",
            input=term_find,
            label2="Replace with",
            input2="new value or expression",
            checkbox="Match Nocase",
            checkbox2="Match Whole",
            yes="Replace",
            maybe="Replace All",
            no="Cancel",
            on_yes_callback=self._get_input,
            on_maybe_callback=self._get_input_replace_all,
        )

    def _get_input(self) -> tuple[str, str, bool, bool, bool]:
        """Get input."""
        term_find = self.input.value  # Do not strip to preserve spaces
        term_replace = self.input2.value  # Do not strip to preserve spaces
        match_nocase = self.checkbox.value
        match_whole = self.checkbox2.value
        replace_all = False

        return term_find, term_replace, match_nocase, match_whole, replace_all

    def _get_input_replace_all(self) -> tuple[str, str, bool, bool, bool]:
        """Get input for 'Replace All'."""
        term_find = self.input.value  # Do not strip to preserve spaces
        term_replace = self.input2.value  # Do not strip to preserve spaces
        match_nocase = self.checkbox.value
        match_whole = self.checkbox2.value
        replace_all = True

        return term_find, term_replace, match_nocase, match_whole, replace_all


class RenameTabScreen(YesNoScreen):
    """Modal screen to rename a tab."""

    CSS = YesNoScreen.DEFAULT_CSS.replace("YesNoScreen", "RenameTabScreen")

    def __init__(self, content_tab: ContentTab, existing_tabs: list[TabPane]):
        self.content_tab = content_tab
        self.existing_tabs = existing_tabs
        tab_name = content_tab.label_text

        super().__init__(
            title="Rename Tab",
            label="New tab name",
            input={"value": tab_name},
            on_yes_callback=self._validate_input,
        )

    def _validate_input(self) -> None:
        """Validate and save the new tab name."""
        new_name = self.input.value.strip()

        # Check if name is empty
        if not new_name:
            self.notify("Tab name cannot be empty", title="Rename Tab", severity="error")
            return None

        # Check if name changed
        if new_name == self.content_tab.label_text:
            self.notify("No changes made", title="Rename Tab", severity="warning")
            return None

        # Check if name already exists
        if new_name in self.existing_tabs:
            self.notify(f"Tab [$accent]{new_name}[/] already exists", title="Rename Tab", severity="error")
            return None

        # Return new name
        return self.content_tab, new_name
