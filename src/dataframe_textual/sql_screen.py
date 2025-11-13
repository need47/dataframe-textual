"""Modal screens for Polars sql manipulation"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data_frame_table import DataFrameTable

import polars as pl
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, TextArea
from textual.widgets.selection_list import Selection


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

    def __init__(self, dftable: "DataFrameTable", on_yes_callback=None) -> None:
        """Initialize the SQL screen."""
        super().__init__()
        self.dftable = dftable  # DataFrameTable
        self.df: pl.DataFrame = dftable.df  # Polars DataFrame
        self.on_yes_callback = on_yes_callback

    def compose(self) -> ComposeResult:
        """Compose the SQL screen widget structure."""
        # Shared by subclasses
        with Horizontal(id="button-container"):
            yield Button("Apply", id="yes", variant="success")
            yield Button("Cancel", id="no", variant="error")

    def on_key(self, event) -> None:
        """Handle key press events in the SQL screen"""
        if event.key in ("q", "escape"):
            self.app.pop_screen()
            event.stop()
        elif event.key == "enter":
            self._handle_yes()
            event.stop()
        elif event.key == "escape":
            self.dismiss(None)
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events in the SQL screen."""
        if event.button.id == "yes":
            self._handle_yes()
        elif event.button.id == "no":
            self.dismiss(None)

    def _handle_yes(self) -> None:
        """Handle Yes button/Enter key press."""
        if self.on_yes_callback:
            result = self.on_yes_callback()
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

        Returns:
            None
        """
        super().__init__(dftable, on_yes_callback=self._handle_simple)

    def compose(self) -> ComposeResult:
        """Compose the simple SQL screen widget structure."""
        with Container(id="sql-container") as container:
            container.border_title = "SQL Query"
            yield Label("Select columns (default to all):", id="select-label")
            yield SelectionList(*[Selection(col, col) for col in self.df.columns], id="column-selection")
            yield Label("Where condition (optional)", id="where-label")
            yield Input(placeholder="e.g., age > 30 and height < 180", id="where-input")
            yield from super().compose()

    def _handle_simple(self) -> None:
        """Handle Yes button/Enter key press."""
        selections = self.query_one(SelectionList).selected
        columns = ", ".join(f"`{s}`" for s in selections) if selections else "*"
        where = self.query_one(Input).value.strip()

        return columns, where


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

        Returns:
            None
        """
        super().__init__(dftable, on_yes_callback=self._handle_advanced)

    def compose(self) -> ComposeResult:
        """Compose the advanced SQL screen widget structure."""
        with Container(id="sql-container") as container:
            container.border_title = "Advanced SQL Query"
            yield TextArea.code_editor(
                placeholder="Enter SQL query (use `self` as the table name), e.g., \n\nSELECT * \nFROM self \nWHERE age > 30",
                id="sql-textarea",
                language="sql",
            )
            yield from super().compose()

    def _handle_advanced(self) -> None:
        """Handle Yes button/Enter key press."""
        return self.query_one(TextArea).text.strip()
