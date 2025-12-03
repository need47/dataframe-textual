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

from .common import NULL, NULL_DISPLAY, RID, DtypeConfig, format_float


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
            height: auto;
            border: solid $primary;
            max-width: 100%;
            overflow: auto;
        }
    """

    def __init__(self, dftable: "DataFrameTable") -> None:
        """Initialize the table screen.

        Sets up the base modal screen with reference to the main DataFrameTable widget
        and stores the DataFrame for display.

        Args:
            dftable: Reference to the parent DataFrameTable widget.
        """
        super().__init__()
        self.dftable = dftable  # DataFrameTable
        self.df: pl.DataFrame = dftable.df  # Polars DataFrame
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
        """
        raise NotImplementedError("Subclasses must implement build_table method.")

    def on_key(self, event) -> None:
        """Handle key press events in the table screen.

        Provides keyboard shortcuts for navigation and interaction, including q/Escape to close.
        Prevents propagation of non-navigation keys to parent screens.

        Args:
            event: The key event object.
        """
        if event.key in ("q", "escape"):
            self.app.pop_screen()
            event.stop()
        elif event.key == "comma":
            self.thousand_separator = not self.thousand_separator
            self.build_table()
            event.stop()

    def filter_or_view_selected_value(self, cidx_name_value: tuple[int, str, Any] | None, action: str = "view") -> None:
        """Apply filter or view action by the selected value.

        Filters or views rows in the main table based on a selected value from
        this table (typically frequency or row detail). Updates the main table's display
        and notifies the user of the action.

        Args:
            col_name_value: Tuple of (column_name, column_value) to filter/view by, or None.
            action: Either "filter" to hide non-matching rows, or "view" to show matching rows. Defaults to "view".
        """
        if cidx_name_value is None:
            return
        cidx, col_name, col_value = cidx_name_value
        self.log(f"Filtering or viewing by `{col_name} == {col_value}`")

        # Handle NULL values
        if col_value == NULL:
            # Create expression for NULL values
            expr = pl.col(col_name).is_null()
            value_display = f"[$success]{NULL_DISPLAY}[/]"
        else:
            # Create expression for the selected value
            expr = pl.col(col_name) == col_value
            value_display = f"[$success]{col_value}[/]"

        df_filtered = self.dftable.df.lazy().filter(expr).collect()
        self.log(f"Filtered dataframe has {len(df_filtered)} rows")

        ok_rids = set(df_filtered[RID].to_list())
        if not ok_rids:
            self.notify(
                f"No matches found for [$warning]{col_name}[/] == {value_display}",
                title="No Matches",
                severity="warning",
            )
            return

        # Action filter
        if action == "filter":
            self.dftable.do_filter_rows()

        # Action view
        else:
            self.dftable.view_rows((expr, cidx, False, True))

        # Dismiss the frequency screen
        self.app.pop_screen()


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
        """
        self.build_table()

    def build_table(self) -> None:
        """Build the row detail table."""
        self.table.clear(columns=True)
        self.table.add_column("Column")
        self.table.add_column("Value")

        # Get all columns and values from the dataframe row
        for col, val, dtype in zip(self.df.columns, self.df.row(self.ridx), self.df.dtypes):
            if col in self.dftable.hidden_columns or col == RID:
                continue  # Skip RID column
            formatted_row = []
            formatted_row.append(col)

            dc = DtypeConfig(dtype)
            formatted_row.append(dc.format(val, justify="", thousand_separator=self.thousand_separator))
            self.table.add_row(*formatted_row)

        self.table.cursor_type = "row"

    def on_key(self, event) -> None:
        """Handle key press events in the row detail screen.

        Supports 'v' for filtering and '"' for highlighting the main table
        by the value in the selected row.

        Args:
            event: The key event object.
        """
        if event.key == "v":
            # View the main table by the selected value
            self.filter_or_view_selected_value(self.get_cidx_name_value(), action="view")
            event.stop()
        elif event.key == "quotation_mark":  # '"'
            # Filter the main table by the selected value
            self.filter_or_view_selected_value(self.get_cidx_name_value(), action="filter")
            event.stop()
        elif event.key == "right_curly_bracket":  # '}'
            # Move to the next row
            ridx = self.ridx + 1
            if ridx < len(self.df):
                self.ridx = ridx
                self.dftable.move_cursor_to(self.ridx)
                self.build_table()
            event.stop()
        elif event.key == "left_curly_bracket":  # '{'
            # Move to the previous row
            ridx = self.ridx - 1
            if ridx >= 0:
                self.ridx = ridx
                self.dftable.move_cursor_to(self.ridx)
                self.build_table()
            event.stop()

    def get_cidx_name_value(self) -> tuple[int, str, Any] | None:
        cidx = self.table.cursor_row
        if cidx >= len(self.df.columns):
            return None  # Invalid row

        col_name = self.df.columns[cidx]
        col_value = self.df.item(self.ridx, cidx)

        return cidx, col_name, col_value


class StatisticsScreen(TableScreen):
    """Modal screen to display statistics for a column or entire dataframe."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "StatisticsScreen")

    def __init__(self, dftable: "DataFrameTable", col_idx: int | None = None):
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
            self.build_dataframe_stats()
            self.table.cursor_type = "column"
        else:
            # Column statistics
            self.build_column_stats()
            self.table.cursor_type = "row"

    def build_column_stats(self) -> None:
        """Build statistics for a single column."""
        col_name = self.df.columns[self.col_idx]
        lf = self.df.lazy()

        # Get column statistics
        stats_df = lf.select(pl.col(col_name)).describe()
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
            self.table.add_row(
                stat_label,
                dc.format(stat_value, thousand_separator=self.thousand_separator),
            )

    def build_dataframe_stats(self) -> None:
        """Build statistics for the entire dataframe."""
        lf = self.df.lazy().select(pl.exclude(RID))

        # Apply only to non-hidden columns
        if self.dftable.hidden_columns:
            lf = lf.select(pl.exclude(self.dftable.hidden_columns))

        # Get dataframe statistics
        stats_df = lf.describe()

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

                formatted_row.append(dc.format(stat_value, thousand_separator=self.thousand_separator))

            self.table.add_row(*formatted_row)


class FrequencyScreen(TableScreen):
    """Modal screen to display frequency of values in a column."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "FrequencyScreen")

    def __init__(self, cidx: int, dftable: "DataFrameTable") -> None:
        super().__init__(dftable)
        self.cidx = cidx
        self.sorted_columns = {1: True}  # Count sort by default
        self.total_count = len(dftable.df)

        col = dftable.df.columns[self.cidx]
        self.df: pl.DataFrame = dftable.df.lazy().select(pl.col(col).value_counts(sort=True)).unnest(col).collect()

    def on_mount(self) -> None:
        """Create the frequency table."""
        self.build_table()

    def on_key(self, event):
        if event.key == "left_square_bracket":  # '['
            # Sort by current column in ascending order
            self.sort_by_column(descending=False)
            event.stop()
        elif event.key == "right_square_bracket":  # ']'
            # Sort by current column in descending order
            self.sort_by_column(descending=True)
            event.stop()
        elif event.key == "v":
            # Filter the main table by the selected value
            self.filter_or_view_selected_value(self.get_cidx_name_value(), action="view")
            event.stop()
        elif event.key == "quotation_mark":  # '"'
            # Highlight the main table by the selected value
            self.filter_or_view_selected_value(self.get_cidx_name_value(), action="filter")
            event.stop()

    def build_table(self) -> None:
        """Build the frequency table."""
        self.table.clear(columns=True)

        # Create frequency table
        column = self.dftable.df.columns[self.cidx]
        dtype = self.dftable.df.dtypes[self.cidx]
        dc = DtypeConfig(dtype)

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
        dc_int = DtypeConfig(pl.Int64)
        dc_float = DtypeConfig(pl.Float64)

        # Add rows to the frequency table
        for row_idx, row in enumerate(self.df.rows()):
            column, count = row
            percentage = (count / self.total_count) * 100

            self.table.add_row(
                dc.format(column),
                dc_int.format(count, thousand_separator=self.thousand_separator),
                dc_float.format(percentage, thousand_separator=self.thousand_separator),
                Bar(
                    highlight_range=(0.0, percentage / 100 * 10),
                    width=10,
                ),
                key=str(row_idx + 1),
            )

        # Add a total row
        self.table.add_row(
            Text("Total", style="bold", justify=dc.justify),
            Text(
                f"{self.total_count:,}" if self.thousand_separator else str(self.total_count),
                style="bold",
                justify="right",
            ),
            Text(
                format_float(100.0, self.thousand_separator, precision=-2 if len(self.df) > 1 else 2),
                style="bold",
                justify="right",
            ),
            Bar(
                highlight_range=(0.0, 10),
                width=10,
            ),
            key="total",
        )

    def sort_by_column(self, descending: bool) -> None:
        """Sort the dataframe by the selected column and refresh the main table."""
        row_idx, col_idx = self.table.cursor_coordinate
        col_sort = col_idx if col_idx == 0 else 1

        if self.sorted_columns.get(col_sort) == descending:
            # If already sorted in the same direction, do nothing
            # self.notify("Already sorted in that order", title="Sort", severity="warning")
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

    def get_cidx_name_value(self) -> tuple[str, str, str] | None:
        row_idx = self.table.cursor_row
        if row_idx >= len(self.df[:, 0]):  # first column
            return None  # Skip the last `Total` row

        col_name = self.dftable.df.columns[self.cidx]
        col_dtype = self.dftable.df.dtypes[self.cidx]

        cell_value = self.table.get_cell_at(Coordinate(row_idx, 0))
        col_value = NULL if cell_value.plain == NULL_DISPLAY else DtypeConfig(col_dtype).convert(cell_value.plain)

        return self.cidx, col_name, col_value


class MetaShape(TableScreen):
    """Modal screen to display metadata about the dataframe."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "MetadataScreen")

    def on_mount(self) -> None:
        """Initialize the metadata screen.

        Populates the table with metadata information about the dataframe,
        including row and column counts.
        """
        self.build_table()

    def build_table(self) -> None:
        """Build the metadata table."""
        self.table.clear(columns=True)
        self.table.add_column("")
        self.table.add_column(Text("Count", justify="right"))

        # Get shape information
        num_rows, num_cols = self.df.shape if self.dftable.df_view is None else self.dftable.df_view.shape
        num_cols -= 1  # Exclude RID column
        dc_int = DtypeConfig(pl.Int64)

        # Add rows to the table
        self.table.add_row("Row", dc_int.format(num_rows, thousand_separator=self.thousand_separator))
        self.table.add_row("Column", dc_int.format(num_cols, thousand_separator=self.thousand_separator))

        self.table.cursor_type = "none"


class MetaColumnScreen(TableScreen):
    """Modal screen to display metadata about the columns in the dataframe."""

    CSS = TableScreen.DEFAULT_CSS.replace("TableScreen", "MetaColumnScreen")

    def on_mount(self) -> None:
        """Initialize the column metadata screen.

        Populates the table with information about each column in the dataframe,
        including ID (1-based index), Name, and Type.
        """
        self.build_table()

    def build_table(self) -> None:
        """Build the column metadata table."""
        self.table.clear(columns=True)
        self.table.add_column("Column")
        self.table.add_column("Name")
        self.table.add_column("Type")

        # Get schema information
        schema = self.df.schema
        dc_int = DtypeConfig(pl.Int64)
        dc_str = DtypeConfig(pl.String)

        # Add a row for each column
        for idx, (col_name, col_type) in enumerate(schema.items(), 1):
            if col_name == RID:
                continue  # Skip RID column

            dc = DtypeConfig(col_type)
            self.table.add_row(
                dc_int.format(idx, thousand_separator=self.thousand_separator),
                col_name,
                dc_str.format("Datetime" if str(col_type).startswith("Datetime") else col_type, style=dc.style),
            )

        self.table.cursor_type = "none"
