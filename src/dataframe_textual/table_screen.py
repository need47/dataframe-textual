"""Modal screens for displaying data in tables (row details and frequency)."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .data_frame_table import DataFrameTable

import polars as pl
from rich.text import Text
from textual.app import ComposeResult
from textual.coordinate import Coordinate
from textual.renderables.bar import Bar
from textual.screen import ModalScreen
from textual.widgets import DataTable

from .common import DtypeConfig, _format_row


class TableScreen(ModalScreen):
    """Base class for modal screens displaying data in a DataTable.

    Provides common functionality for screens that show tabular data with
    keyboard shortcuts and styling.
    """

    DEFAULT_CSS = """
        TableScreen {
            align: center middle;
        }

        TableScreen > DataTable {
            width: auto;
            min-width: 30;
            height: auto;
            border: solid $primary;
        }
    """

    def __init__(self, dftable: DataFrameTable):
        super().__init__()
        self.df: pl.DataFrame = dftable.df  # Polars DataFrame
        self.dftable = dftable  # DataFrameTable

    def compose(self) -> ComposeResult:
        """Create the table. Must be overridden by subclasses."""
        self.table = DataTable(zebra_stripes=True)
        yield self.table

    def on_key(self, event):
        if event.key in ("q", "escape"):
            self.app.pop_screen()
            event.stop()
        # Prevent key events from propagating to parent screen,
        # except for the following default key bindings for DataTable
        elif event.key not in (
            "up",
            "down",
            "right",
            "left",
            "pageup",
            "pagedown",
            "ctrl+home",
            "ctrl+end",
            "home",
            "end",
        ):
            event.stop()

    def _filter_or_highlight_selected_value(
        self, col_name_value: tuple[str, str] | None, action: str = "filter"
    ) -> None:
        """Apply filter or highlight action by the selected value from the frequency table.

        Args:
            col_name: The name of the column to filter/highlight.
            col_value: The value to filter/highlight by.
            action: Either "filter" to filter visible rows, or "highlight" to select matching rows.
        """
        if col_name_value is None:
            return
        col_name, col_value = col_name_value

        # Handle NULL values
        if col_value == "-":
            # Create expression for NULL values
            expr = pl.col(col_name).is_null()
            value_display = "[on $primary]NULL[/]"
        else:
            # Create expression for the selected value
            expr = pl.col(col_name) == col_value
            value_display = f"[on $primary]{col_value}[/]"

        matched_indices = set(
            self.dftable.df.with_row_index("__rid__").filter(expr)["__rid__"].to_list()
        )

        # Apply the action
        if action == "filter":
            # Update visible_rows to reflect the filter
            for i in range(len(self.dftable.visible_rows)):
                self.dftable.visible_rows[i] = i in matched_indices
            title = "Filter"
            message = f"Filtered by [on $primary]{col_name}[/] = {value_display}"
        else:  # action == "highlight"
            # Update selected_rows to reflect the highlights
            for i in range(len(self.dftable.selected_rows)):
                self.dftable.selected_rows[i] = i in matched_indices
            title = "Highlight"
            message = f"Highlighted [on $primary]{col_name}[/] = {value_display}"

        # Recreate the table display with updated data in the main app
        self.dftable._setup_table()

        # Dismiss the frequency screen
        self.app.pop_screen()

        self.notify(message, title=title)


class RowDetailScreen(TableScreen):
    """Modal screen to display a single row's details."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "RowDetailScreen")

    def __init__(self, row_idx: int, dftable):
        super().__init__(dftable)
        self.row_idx = row_idx

    def on_mount(self) -> None:
        """Create the detail table."""
        self.table.add_column("Column")
        self.table.add_column("Value")

        # Get all columns and values from the dataframe row
        for col, val, dtype in zip(
            self.df.columns, self.df.row(self.row_idx), self.df.dtypes
        ):
            self.table.add_row(
                *_format_row([col, val], [None, dtype], apply_justify=False)
            )

        self.table.cursor_type = "row"

    def on_key(self, event):
        if event.key == "v":
            # Filter the main table by the selected value
            self._filter_or_highlight_selected_value(
                self._get_col_name_value(), action="filter"
            )
            event.stop()
        elif event.key == "quotation_mark":  # '"'
            # Highlight the main table by the selected value
            self._filter_or_highlight_selected_value(
                self._get_col_name_value(), action="highlight"
            )
            event.stop()

    def _get_col_name_value(self) -> tuple[str, Any] | None:
        row_idx = self.table.cursor_row
        if row_idx >= len(self.df.columns):
            return None  # Invalid row

        col_name = self.df.columns[row_idx]
        col_value = self.df.item(self.row_idx, row_idx)

        return col_name, col_value


class FrequencyScreen(TableScreen):
    """Modal screen to display frequency of values in a column."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "FrequencyScreen")

    def __init__(self, col_idx: int, dftable: DataFrameTable):
        super().__init__(dftable)
        self.col_idx = col_idx
        self.sorted_columns = {
            1: True,  # Count
            2: True,  # %
        }
        self.df: pl.DataFrame = (
            dftable.df[dftable.df.columns[self.col_idx]]
            .value_counts(sort=True)
            .sort("count", descending=True)
        )

    def on_mount(self) -> None:
        """Create the frequency table."""
        self.build_table()

    def on_key(self, event):
        if event.key == "left_square_bracket":  # '['
            # Sort by current column in ascending order
            self._sort_by_column(descending=False)
            event.stop()
        elif event.key == "right_square_bracket":  # ']'
            # Sort by current column in descending order
            self._sort_by_column(descending=True)
            event.stop()
        elif event.key == "v":
            # Filter the main table by the selected value
            self._filter_or_highlight_selected_value(
                self._get_col_name_value(), action="filter"
            )
            event.stop()
        elif event.key == "quotation_mark":  # '"'
            # Highlight the main table by the selected value
            self._filter_or_highlight_selected_value(
                self._get_col_name_value(), action="highlight"
            )
            event.stop()

    def build_table(self) -> None:
        # Create frequency table
        column = self.dftable.df.columns[self.col_idx]
        dtype = str(self.dftable.df.dtypes[self.col_idx])
        dc = DtypeConfig(dtype)

        # Calculate frequencies using Polars
        total_count = len(self.dftable.df)

        self.table.add_column(Text(column, justify=dc.justify), key=column)
        self.table.add_column(Text("Count", justify="right"), key="Count")
        self.table.add_column(Text("%", justify="right"), key="%")
        self.table.add_column(Text("Histogram", justify="left"), key="Histogram")

        # Get style config for Int64 and Float64
        ds_int = DtypeConfig("Int64")
        ds_float = DtypeConfig("Float64")

        # Add rows to the frequency table
        for row_idx, row in enumerate(self.df.rows()):
            value, count = row
            percentage = (count / total_count) * 100

            self.table.add_row(
                Text(
                    "-" if value is None else str(value),
                    style=dc.style,
                    justify=dc.justify,
                ),
                Text(str(count), style=ds_int.style, justify=ds_int.justify),
                Text(
                    f"{percentage:.2f}",
                    style=ds_float.style,
                    justify=ds_float.justify,
                ),
                Bar(
                    highlight_range=(0.0, percentage / 100 * 10),
                    width=10,
                ),
                key=str(row_idx + 1),
            )

        # Add a total row
        self.table.add_row(
            Text("Total", style="bold", justify=dc.justify),
            Text(f"{total_count:,}", style="bold", justify="right"),
            Text("100.00", style="bold", justify="right"),
            Bar(
                highlight_range=(0.0, 10),
                width=10,
            ),
            key="total",
        )

    def _sort_by_column(self, descending: bool) -> None:
        """Sort the dataframe by the selected column and refresh the main table."""

        self.log(self.df)

        row_idx, col_idx = self.table.cursor_coordinate
        col_sort = col_idx if col_idx == 0 else 1

        sort_dir = self.sorted_columns.get(col_sort)
        if sort_dir is not None:
            # If already sorted in the same direction, do nothing
            if sort_dir == descending:
                self.notify(
                    "Already sorted in that order", title="Sort", severity="warning"
                )
                return

        self.sorted_columns.clear()
        self.sorted_columns[col_sort] = descending

        col_name = self.df.columns[col_sort]
        self.df = self.df.sort(col_name, descending=descending)

        # Rebuild the frequency table
        self.table.clear(columns=True)
        self.build_table()

        self.table.move_cursor(row=row_idx, column=col_idx)

        # Notify the user
        order = "desc" if descending else "asc"
        self.notify(f"Sorted by [on $primary]{col_name}[/] ({order})", title="Sort")

    def _get_col_name_value(self) -> tuple[str, str] | None:
        row_idx = self.table.cursor_row
        if row_idx >= len(self.df.columns):
            return None  # Skip total row

        col_name = self.df.columns[self.col_idx]
        col_dtype = self.df.dtypes[self.col_idx]

        cell_value = self.table.get_cell_at(Coordinate(row_idx, 0))
        col_value = cell_value.plain

        return col_name, DtypeConfig(col_dtype).convert(col_value)
