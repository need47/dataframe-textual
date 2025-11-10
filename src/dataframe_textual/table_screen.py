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

from .common import NULL, NULL_DISPLAY, RIDX, DtypeConfig, format_float, format_row


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
            min-width: 20;
            border: solid $primary;
        }
    """

    def __init__(self, dftable: DataFrameTable) -> None:
        """Initialize the table screen.

        Sets up the base modal screen with reference to the main DataFrameTable widget
        and stores the DataFrame for display.

        Args:
            dftable: Reference to the parent DataFrameTable widget.

        Returns:
            None
        """
        super().__init__()
        self.df: pl.DataFrame = dftable.df  # Polars DataFrame
        self.dftable = dftable  # DataFrameTable
        self.thousand_separator = False  # Whether to use thousand separators in numbers

    def compose(self) -> ComposeResult:
        """Compose the table screen widget structure.

        Creates and yields a DataTable widget for displaying tabular data.
        Subclasses should override to customize table configuration.

        Yields:
            DataTable: The table widget for this screen.
        """
        self.table = DataTable(zebra_stripes=True)
        yield self.table

    def build_table(self) -> None:
        """Build the table content.

        Subclasses should implement this method to populate the DataTable
        with appropriate columns and rows based on the specific screen's purpose.

        Returns:
            None
        """
        raise NotImplementedError("Subclasses must implement build_table method.")

    def on_key(self, event) -> None:
        """Handle key press events in the table screen.

        Provides keyboard shortcuts for navigation and interaction, including q/Escape to close.
        Prevents propagation of non-navigation keys to parent screens.

        Args:
            event: The key event object.

        Returns:
            None
        """
        if event.key in ("q", "escape"):
            self.app.pop_screen()
            event.stop()
        elif event.key == "comma":
            self.thousand_separator = not self.thousand_separator
            self.build_table()
            event.stop()

    def _filter_or_highlight_selected_value(
        self, col_name_value: tuple[str, Any] | None, action: str = "filter"
    ) -> None:
        """Apply filter or highlight action by the selected value.

        Filters or highlights rows in the main table based on a selected value from
        this table (typically frequency or row detail). Updates the main table's display
        and notifies the user of the action.

        Args:
            col_name_value: Tuple of (column_name, column_value) to filter/highlight by, or None.
            action: Either "filter" to hide non-matching rows, or "highlight" to select matching rows. Defaults to "filter".

        Returns:
            None
        """
        if col_name_value is None:
            return
        col_name, col_value = col_name_value

        # Handle NULL values
        if col_value == NULL:
            # Create expression for NULL values
            expr = pl.col(col_name).is_null()
            value_display = "[$success]NULL[/]"
        else:
            # Create expression for the selected value
            expr = pl.col(col_name) == col_value
            value_display = f"[$success]{col_value}[/]"

        matched_indices = set(self.dftable.df.with_row_index(RIDX).filter(expr)[RIDX].to_list())

        # Apply the action
        if action == "filter":
            # Update visible_rows to reflect the filter
            for i in range(len(self.dftable.visible_rows)):
                self.dftable.visible_rows[i] = i in matched_indices
            title = "Filter"
            message = f"Filtered by [$accent]{col_name}[/] == [$success]{value_display}[/]"
        else:  # action == "highlight"
            # Update selected_rows to reflect the highlights
            for i in range(len(self.dftable.selected_rows)):
                self.dftable.selected_rows[i] = i in matched_indices
            title = "Highlight"
            message = f"Highlighted [$accent]{col_name}[/] == [$success]{value_display}[/]"

        # Recreate the table display with updated data in the main app
        self.dftable._setup_table()

        # Dismiss the frequency screen
        self.app.pop_screen()

        self.notify(message, title=title)


class RowDetailScreen(TableScreen):
    """Modal screen to display a single row's details."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "RowDetailScreen")

    def __init__(self, ridx: int, dftable):
        super().__init__(dftable)
        self.ridx = ridx

    def on_mount(self) -> None:
        """Initialize the row detail screen.

        Populates the table with column names and values from the selected row
        of the main DataFrame. Sets the table cursor type to "row".

        Returns:
            None
        """
        self.build_table()

    def build_table(self) -> None:
        """Build the row detail table."""
        self.table.clear(columns=True)
        self.table.add_column("Column")
        self.table.add_column("Value")

        # Get all columns and values from the dataframe row
        for col, val, dtype in zip(self.df.columns, self.df.row(self.ridx), self.df.dtypes):
            self.table.add_row(
                *format_row([col, val], [None, dtype], apply_justify=False, thousand_separator=self.thousand_separator)
            )

        self.table.cursor_type = "row"

    def on_key(self, event) -> None:
        """Handle key press events in the row detail screen.

        Supports 'v' for filtering and '"' for highlighting the main table
        by the value in the selected row.

        Args:
            event: The key event object.

        Returns:
            None
        """
        if event.key == "v":
            # Filter the main table by the selected value
            self._filter_or_highlight_selected_value(self._get_col_name_value(), action="filter")
            event.stop()
        elif event.key == "quotation_mark":  # '"'
            # Highlight the main table by the selected value
            self._filter_or_highlight_selected_value(self._get_col_name_value(), action="highlight")
            event.stop()
        elif event.key == "comma":
            event.stop()

    def _get_col_name_value(self) -> tuple[str, Any] | None:
        row_idx = self.table.cursor_row
        if row_idx >= len(self.df.columns):
            return None  # Invalid row

        col_name = self.df.columns[row_idx]
        col_value = self.df.item(self.ridx, row_idx)

        return col_name, col_value


class StatisticsScreen(TableScreen):
    """Modal screen to display statistics for a column or entire dataframe."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "StatisticsScreen")

    def __init__(self, dftable: DataFrameTable, col_idx: int | None = None):
        super().__init__(dftable)
        self.col_idx = col_idx  # None for dataframe statistics, otherwise column index

    def on_mount(self) -> None:
        """Create the statistics table."""
        self.build_table()

    def build_table(self) -> None:
        """Build the statistics table."""
        self.table.clear(columns=True)

        if self.col_idx is None:
            # Dataframe statistics
            self._build_dataframe_stats()
        else:
            # Column statistics
            self._build_column_stats()

    def _build_column_stats(self) -> None:
        """Build statistics for a single column."""
        col_name = self.df.columns[self.col_idx]
        lf = self.df.lazy()

        # Apply only to visible rows
        if False in self.dftable.visible_rows:
            lf = lf.filter(self.dftable.visible_rows)

        # Get column statistics
        stats_df = lf.select(pl.col(col_name)).collect().describe()
        if len(stats_df) == 0:
            return

        col_dtype = stats_df.dtypes[1]  # 'value' column
        dc = DtypeConfig(col_dtype)

        # Add statistics label column
        self.table.add_column(Text("Statistic", justify="left"), key="statistic")

        # Add value column with appropriate styling
        self.table.add_column(Text(col_name, justify=dc.justify), key=col_name)

        # Add rows
        for row in stats_df.rows():
            stat_label, stat_value = row
            value = stat_value
            if stat_value is None:
                value = NULL_DISPLAY
            elif dc.gtype == "integer" and self.thousand_separator:
                value = f"{stat_value:,}"
            elif dc.gtype == "float":
                value = format_float(stat_value, self.thousand_separator)
            else:
                value = str(stat_value)

            self.table.add_row(
                Text(stat_label, justify="left"),
                Text(value, style=dc.style, justify=dc.justify),
            )

    def _build_dataframe_stats(self) -> None:
        """Build statistics for the entire dataframe."""
        lf = self.df.lazy()

        # Apply only to visible rows
        if False in self.dftable.visible_rows:
            lf = lf.filter(self.dftable.visible_rows)

        # Get dataframe statistics
        stats_df = lf.collect().describe()

        # Add columns for each dataframe column with appropriate styling
        for idx, (col_name, col_dtype) in enumerate(zip(stats_df.columns, stats_df.dtypes), 0):
            if idx == 0:
                # Add statistics label column (first column, no styling)
                self.table.add_column("Statistic", key="statistic")
                continue

            dc = DtypeConfig(col_dtype)
            self.table.add_column(Text(col_name, justify=dc.justify), key=col_name)

        # Add rows
        for row in stats_df.rows():
            formatted_row = []

            # Format remaining values with appropriate styling
            for idx, stat_value in enumerate(row):
                # First element is the statistic label
                if idx == 0:
                    formatted_row.append(stat_value)
                    continue

                col_dtype = stats_df.dtypes[idx]
                dc = DtypeConfig(col_dtype)

                value = stat_value
                if stat_value is None:
                    value = NULL_DISPLAY
                elif dc.gtype == "integer" and self.thousand_separator:
                    value = f"{stat_value:,}"
                elif dc.gtype == "float":
                    value = format_float(stat_value, self.thousand_separator)
                else:
                    value = str(stat_value)

                formatted_row.append(Text(value, style=dc.style, justify=dc.justify))

            self.table.add_row(*formatted_row)


class FrequencyScreen(TableScreen):
    """Modal screen to display frequency of values in a column."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "FrequencyScreen")

    def __init__(self, col_idx: int, dftable: DataFrameTable):
        super().__init__(dftable)
        self.col_idx = col_idx
        self.sorted_columns = {
            1: True,  # Count
        }
        self.df: pl.DataFrame = (
            dftable.df[dftable.df.columns[self.col_idx]].value_counts(sort=True).sort("count", descending=True)
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
            self._filter_or_highlight_selected_value(self._get_col_name_value(), action="filter")
            event.stop()
        elif event.key == "quotation_mark":  # '"'
            # Highlight the main table by the selected value
            self._filter_or_highlight_selected_value(self._get_col_name_value(), action="highlight")
            event.stop()

    def build_table(self) -> None:
        """Build the frequency table."""
        self.table.clear(columns=True)

        # Create frequency table
        column = self.dftable.df.columns[self.col_idx]
        dtype = self.dftable.df.dtypes[self.col_idx]
        dc = DtypeConfig(dtype)

        # Calculate frequencies using Polars
        total_count = len(self.dftable.df)

        # Add column headers with sort indicators
        columns = [
            (column, "Value", 0),
            ("Count", "Count", 1),
            ("%", "%", 2),
            ("Histogram", "Histogram", 3),
        ]

        for display_name, key, col_idx_num in columns:
            # Check if this column is sorted and add indicator
            if col_idx_num in self.sorted_columns:
                descending = self.sorted_columns[col_idx_num]
                sort_indicator = " ▼" if descending else " ▲"
                header_text = display_name + sort_indicator
            else:
                header_text = display_name

            justify = dc.justify if col_idx_num == 0 else ("right" if col_idx_num in (1, 2) else "left")
            self.table.add_column(Text(header_text, justify=justify), key=key)

        # Get style config for Int64 and Float64
        ds_int = DtypeConfig(pl.Int64)
        ds_float = DtypeConfig(pl.Float64)

        # Add rows to the frequency table
        for row_idx, row in enumerate(self.df.rows()):
            column, count = row
            percentage = (count / total_count) * 100

            if column is None:
                value = NULL_DISPLAY
            elif dc.gtype == "integer" and self.thousand_separator:
                value = f"{column:,}"
            elif dc.gtype == "float":
                value = format_float(column, self.thousand_separator)
            else:
                value = str(column)

            self.table.add_row(
                Text(value, style=dc.style, justify=dc.justify),
                Text(
                    f"{count:,}" if self.thousand_separator else str(count), style=ds_int.style, justify=ds_int.justify
                ),
                Text(
                    f"{percentage:,.3f}" if self.thousand_separator else f"{percentage:.3f}",
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
        row_idx, col_idx = self.table.cursor_coordinate
        col_sort = col_idx if col_idx == 0 else 1

        sort_dir = self.sorted_columns.get(col_sort)
        if sort_dir is not None:
            # If already sorted in the same direction, do nothing
            if sort_dir == descending:
                self.notify("Already sorted in that order", title="Sort", severity="warning")
                return

        self.sorted_columns.clear()
        self.sorted_columns[col_sort] = descending

        col_name = self.df.columns[col_sort]
        self.df = self.df.sort(col_name, descending=descending, nulls_last=True)

        # Rebuild the frequency table
        self.table.clear(columns=True)
        self.build_table()

        self.table.move_cursor(row=row_idx, column=col_idx)

        # order = "desc" if descending else "asc"
        # self.notify(f"Sorted by [on $primary]{col_name}[/] ({order})", title="Sort")

    def _get_col_name_value(self) -> tuple[str, str] | None:
        row_idx = self.table.cursor_row
        if row_idx >= len(self.df[:, 0]):  # first column
            return None  # Skip the last `Total` row

        col_name = self.dftable.df.columns[self.col_idx]
        col_dtype = self.dftable.df.dtypes[self.col_idx]

        cell_value = self.table.get_cell_at(Coordinate(row_idx, 0))
        col_value = NULL if cell_value.plain == NULL_DISPLAY else DtypeConfig(col_dtype).convert(cell_value.plain)

        return col_name, col_value
