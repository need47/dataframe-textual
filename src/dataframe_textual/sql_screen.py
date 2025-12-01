"""Modal screens for Polars sql manipulation"""

from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data_frame_table import DataFrameTable

import polars as pl
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, TextArea
from textual.widgets.selection_list import Selection

from .common import RID


class SqlScreen(ModalScreen):
    """Base class for modal screens handling SQL query."""

    DEFAULT_CSS = """
        SqlScreen {
            align: center middle;
        }

        SqlScreen > Container {
            width: auto;
            height: auto;
            border: heavy $accent;
            border-title-color: $accent;
            border-title-background: $panel;
            border-title-style: bold;
            background: $background;
            padding: 1 2;
            overflow: auto;
        }

        #button-container {
            width: auto;
            margin: 1 0 0 0;
            height: 3;
            align: center middle;
        }

        Button {
            margin: 0 2;
        }

    """

    def __init__(self, dftable: "DataFrameTable", on_yes_callback=None, on_maybe_callback=None) -> None:
        """Initialize the SQL screen."""
        super().__init__()
        self.dftable = dftable  # DataFrameTable
        self.df: pl.DataFrame = dftable.df  # Polars DataFrame
        self.on_yes_callback = on_yes_callback
        self.on_maybe_callback = on_maybe_callback

    def compose(self) -> ComposeResult:
        """Compose the SQL screen widget structure."""
        # Shared by subclasses
        with Horizontal(id="button-container"):
            yield Button("View", id="yes", variant="success")
            yield Button("Filter", id="maybe", variant="warning")
            yield Button("Cancel", id="no", variant="error")

    def on_key(self, event) -> None:
        """Handle key press events in the SQL screen"""
        if event.key in ("q", "escape"):
            self.app.pop_screen()
            event.stop()
        elif event.key == "enter":
            for button in self.query(Button):
                if button.has_focus:
                    if button.id == "yes":
                        self._handle_yes()
                    elif button.id == "maybe":
                        self._handle_maybe()
                    break
            else:
                self._handle_yes()

            event.stop()
        elif event.key == "escape":
            self.dismiss(None)
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events in the SQL screen."""
        if event.button.id == "yes":
            self._handle_yes()
        elif event.button.id == "maybe":
            self._handle_maybe()
        elif event.button.id == "no":
            self.dismiss(None)

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
            self.dismiss(True)


class SimpleSqlScreen(SqlScreen):
    """Simple SQL query screen."""

    DEFAULT_CSS = SqlScreen.DEFAULT_CSS.replace("SqlScreen", "SimpleSqlScreen")

    CSS = """
        SimpleSqlScreen SelectionList {
            width: auto;
            min-width: 40;
            margin: 1 0;
        }

        SimpleSqlScreen SelectionList:blur {
            border: solid $secondary;
        }

        SimpleSqlScreen Label {
            width: auto;
        }

        SimpleSqlScreen Input {
            width: auto;
        }

        SimpleSqlScreen Input:blur {
            border: solid $secondary;
        }

        #button-container {
            min-width: 40;
        }
    """

    def __init__(self, dftable: "DataFrameTable") -> None:
        """Initialize the simple SQL screen.

        Sets up the modal screen with reference to the main DataFrameTable widget
        and stores the DataFrame for display.

        Args:
            dftable: Reference to the parent DataFrameTable widget.
        """
        super().__init__(
            dftable,
            on_yes_callback=self.handle_simple,
            on_maybe_callback=partial(self.handle_simple, view=False),
        )

    def compose(self) -> ComposeResult:
        """Compose the simple SQL screen widget structure."""
        with Container(id="sql-container") as container:
            container.border_title = "SQL Query"
            yield Label("SELECT columns (all if none selected):", id="select-label")
            yield SelectionList(
                *[
                    Selection(col, col)
                    for col in self.df.columns
                    if col not in self.dftable.hidden_columns and col != RID
                ],
                id="column-selection",
            )
            yield Label("WHERE condition (optional)", id="where-label")
            yield Input(placeholder="e.g., age > 30 and height < 180", id="where-input")
            yield from super().compose()

    def handle_simple(self, view: bool = True) -> None:
        """Handle Yes button/Enter key press."""
        selections = self.query_one(SelectionList).selected
        if not selections:
            selections = [col for col in self.df.columns if col not in self.dftable.hidden_columns and col != RID]

        columns = ", ".join(f"`{s}`" for s in selections)
        where = self.query_one(Input).value.strip()

        return columns, where, view


class AdvancedSqlScreen(SqlScreen):
    """Advanced SQL query screen."""

    DEFAULT_CSS = SqlScreen.DEFAULT_CSS.replace("SqlScreen", "AdvancedSqlScreen")

    CSS = """
        AdvancedSqlScreen TextArea {
            width: auto;
            min-width: 60;
            height: auto;
            min-height: 10;
        }

        #button-container {
            min-width: 60;
        }
    """

    def __init__(self, dftable: "DataFrameTable") -> None:
        """Initialize the simple SQL screen.

        Sets up the modal screen with reference to the main DataFrameTable widget
        and stores the DataFrame for display.

        Args:
            dftable: Reference to the parent DataFrameTable widget.
        """
        super().__init__(
            dftable,
            on_yes_callback=self.handle_advanced,
            on_maybe_callback=partial(self.handle_advanced, view=False),
        )

    def compose(self) -> ComposeResult:
        """Compose the advanced SQL screen widget structure."""
        with Container(id="sql-container") as container:
            container.border_title = "Advanced SQL Query"
            yield TextArea.code_editor(
                placeholder="Enter SQL query, e.g., \n\nSELECT * \nFROM self \nWHERE age > 30\n\n- use 'self' as the table name\n- use backticks (`) for column names with spaces.",
                id="sql-textarea",
                language="sql",
            )
            yield from super().compose()

    def handle_advanced(self, view: bool = True) -> None:
        """Handle Yes button/Enter key press."""
        return self.query_one(TextArea).text.strip(), view
