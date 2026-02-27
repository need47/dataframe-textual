"""Modal screens for Polars sql manipulation"""

from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data_frame_table import DataFrameTable

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Input, Label, SelectionList, TextArea
from textual.widgets.selection_list import Selection

from .common import RID
from .yes_no_screen import YMNScreen


class SimpleSqlScreen(YMNScreen):
    """Simple SQL query screen."""

    CSS = """
        SimpleSqlScreen {
            align: center middle;
        }

        SimpleSqlScreen > Container {
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

        SimpleSqlScreen SelectionList {
            width: auto;
            min-width: 60;
            margin: 0 0 1 0;
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
            min-width: 30;
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
            yes="Query",
            maybe="Query to Tab",
            no="Cancel",
            on_yes_callback=self.handle_simple,
            on_maybe_callback=partial(self.handle_simple, new_tab=True),
        )
        self.dftable = dftable  # DataFrameTable

    def compose(self) -> ComposeResult:
        """Compose the simple SQL screen widget structure."""
        with Container(id="sql-container") as container:
            container.border_title = "SQL Query Builder"
            yield Label("SELECT columns (default to all if none selected)", id="select-label")
            yield SelectionList(
                *[
                    Selection(col, col)
                    for col in self.dftable.df.columns
                    if col not in self.dftable.hidden_columns and col != RID
                ],
                id="column-selection",
            )
            yield Label("WHERE condition (optional)", id="where-label")
            yield Input(placeholder="e.g., age > 30 and height < 180", id="where-input")
            yield from super().compose()

    def handle_simple(self, new_tab: bool = False) -> None:
        """Handle Yes button/Enter key press."""
        selections = self.query_one(SelectionList).selected
        if not selections:
            selections = [
                col for col in self.dftable.df.columns if col not in self.dftable.hidden_columns and col != RID
            ]

        columns = ", ".join(f"`{s}`" for s in selections)
        where = self.query_one(Input).value.strip()

        return columns, where, new_tab


class AdvancedSqlScreen(YMNScreen):
    """Advanced SQL query screen."""

    CSS = """
        AdvancedSqlScreen {
            align: center middle;
        }

        AdvancedSqlScreen > Container {
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
            yes="Query",
            maybe="Query to Tab",
            no="Cancel",
            on_yes_callback=self.handle_advanced,
            on_maybe_callback=partial(self.handle_advanced, new_tab=True),
        )
        self.dftable = dftable  # DataFrameTable

    def compose(self) -> ComposeResult:
        """Compose the advanced SQL screen widget structure."""
        with Container(id="sql-container") as container:
            container.border_title = "Advanced SQL Query Builder"
            yield TextArea.code_editor(
                placeholder="Enter SQL query, e.g., \n\nSELECT * \nFROM self \nWHERE age > 30\n\n- use 'self' as the table name\n- use backticks (`) for column names with spaces.",
                id="sql-textarea",
                language="sql",
            )
            yield from super().compose()

    def handle_advanced(self, new_tab: bool = False) -> None:
        """Handle Yes button/Enter key press."""
        return self.query_one(TextArea).text.strip(), new_tab
