"""Modal screens for displaying data in tables (row details and frequency)."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .data_frame_table import DataFrameTable

from functools import partial

import polars as pl
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.coordinate import Coordinate
from textual.renderables.bar import Bar
from textual.screen import ModalScreen
from textual.widgets import DataTable

from .common import (
    COLUMN_WIDTH_CAP,
    CURSOR_TYPES,
    NULL,
    NULL_DISPLAY,
    RID,
    DtypeConfig,
    format_float,
    format_row,
    get_next_item,
)
from .file_picker_screen import SaveFileScreen
from .text_screen import TextScreen


class TableModalScreen(ModalScreen):
    """Base class for modal screens displaying data in a DataTable.

    Provides common functionality for screens that show tabular data with
    keyboard shortcuts and styling.
    """

    DEFAULT_CSS = """
        TableModalScreen {
            align: center middle;
        }

        TableModalScreen > DataTable {
            width: auto;
            max-width: 100%;
            height: auto;
            min-width: 17; /* for LoadIndicator */
            min-height: 3; /* for LoadIndicator */
            border: solid $primary;
            overflow: auto;
        }
    """

    def __init__(self, df: pl.DataFrame | None = None) -> None:
        """Initialize the table screen.

        Sets up the base modal screen with reference to the main DataFrameTable widget
        and stores the DataFrame for display.

        Args:
            df: The DataFrame to display in this screen.
        """
        super().__init__()
        self.df = df  # DataFrame for this screen, to be set by subclasses
        self.thousand_separator = False  # Whether to use thousand separators in numbers
        self.sorted_columns: dict[int, bool] = {}  # Track sorted columns and their sort order

    def compose(self) -> ComposeResult:
        """Compose the table screen widget structure.

        Creates and yields a DataTable widget for displaying tabular data.
        Subclasses should override to customize table configuration.

        Yields:
            DataTable: The table widget for this screen.
        """
        self.table = DataTable(zebra_stripes=True)
        yield self.table

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
        elif event.key == "g":
            self.table.action_scroll_top()
            event.stop()
        elif event.key == "G":
            self.table.action_scroll_bottom()
            event.stop()
        elif event.key == "left_square_bracket":  # '['
            self.sort_by_column(descending=False)
            event.stop()
        elif event.key == "right_square_bracket":  # ']'
            self.sort_by_column(descending=True)
            event.stop()
        elif event.key == "K":
            next_type = get_next_item(CURSOR_TYPES, self.table.cursor_type)
            self.table.cursor_type = next_type
            event.stop()

    def build_table(self) -> None:
        """Build the table content.

        Subclasses should implement this method to populate the DataTable
        with appropriate columns and rows based on the specific screen's purpose.
        """
        raise NotImplementedError("Subclasses must implement build_table method.")

    def df2table(self) -> None:
        """Convert a Polars DataFrame to a DataTable for display."""
        if self.df is None:
            return

        self.table.clear(columns=True)

        # Add columns with proper justification based on data types
        for col, dtype in zip(self.df.columns, self.df.dtypes):
            if col == RID:
                continue

            for c in self.sorted_columns:
                if c == col:
                    # Add sort indicator to column header
                    descending = self.sorted_columns[col]
                    sort_indicator = " ▼" if descending else " ▲"
                    cell_value = col + sort_indicator
                    break
            else:  # No break occurred, so column is not sorted
                cell_value = col

            dc = DtypeConfig(dtype)
            self.table.add_column(Text(cell_value, justify=dc.justify), key=col)

        # Add rows with proper formatting based on data types
        for ridx, row in enumerate(self.df.iter_rows()):
            # Skip the row containing the RID value
            if row[0] == RID or (isinstance(row[0], Text) and row[0].plain == RID):
                continue

            formatted_row = []
            for cidx, c in enumerate(row):
                if self.df.columns[cidx] == RID:
                    continue

                # If the value is already a Text object (e.g. with styling), keep it as is. Otherwise, format based on dtype.
                if isinstance(c, Text):
                    formatted_row.append(c)
                else:
                    dtype = self.df.dtypes[cidx]
                    dc = DtypeConfig(dtype)
                    formatted_row.append(dc.format(c, thousand_separator=self.thousand_separator))

            self.table.add_row(*formatted_row, label=str(ridx + 1))

    def sort_by_column(self, descending: bool = False) -> None:
        """Sort the table by the current column.

        Args:
            descending: Whether to sort in descending order. Defaults to False (ascending).
        """
        # Get the current column index and name
        ridx, cidx = self.table.cursor_coordinate
        col_key = self.table.coordinate_to_cell_key((ridx, cidx)).column_key
        col_name = col_key.value

        # Already sorted by this column in the same order, do nothing
        if self.sorted_columns.get(col_name) == descending:
            return

        # Update sorted columns tracking and sort the dataframe
        self.sorted_columns.clear()
        self.sorted_columns[col_name] = descending

        # If no DataFrame is available (e.g., not yet populated), sort the table directly
        if self.df is None:
            self.table.sort(col_key, key=lambda c: c.plain if isinstance(c, Text) else c, reverse=descending)
            return

        if self.df.is_empty():
            return

        try:
            self.df = self.df.sort(col_name, descending=descending, nulls_last=True)
        except Exception as e:
            self.log(f"Error sorting by column '{col_name}': {e}")

            # Fallback to sorting the table directly if dataframe sorting fails (e.g. due to unsupported data types)
            self.table.sort(col_key, key=lambda c: c.plain if isinstance(c, Text) else c, reverse=descending)
            return

        # Rebuild the table
        self.df2table()

        # Move cursor back to the same column and approximate row position after sorting
        self.table.move_cursor(row=ridx, column=cidx)

    def _on_calc_ready(self) -> None:
        self.build_table()
        self.table.loading = False
        self.table.focus()


class TableScreen(TableModalScreen):
    """Base class for modal screens displaying data in a DataTable.

    Provides common functionality for screens that show tabular data with
    keyboard shortcuts and styling.
    """

    DEFAULT_CSS = TableModalScreen.DEFAULT_CSS.replace("TableModalScreen", "TableScreen")

    def __init__(self, dftable: "DataFrameTable") -> None:
        """Initialize the table screen.

        Sets up the base modal screen with reference to the main DataFrameTable widget
        and stores the DataFrame for display.

        Args:
            dftable: Reference to the parent DataFrameTable widget, if applicable.
        """
        super().__init__()
        self.dftable = dftable

    def sort_by_column(self, descending=False):
        # Override to disable sorting in TableScreen, but subclasses can still implement their own sorting if desired.
        pass

    def filter_or_collect_selected_value(
        self, cidx_name_value: tuple[int, str, Any] | None, action: str = "filter"
    ) -> None:
        """Apply filter or collect action by the selected value.

        Filter or collect rows in the main table based on a selected value from
        this table (typically frequency or row detail). Updates the main table's display
        and notifies the user of the action.

        Args:
            col_name_value: Tuple of (column_index, column_name, column_value) to filter/collect by, or None.
            action: Either "filter" to filter rows, or "collect" to collect rows. Defaults to "filter".
        """
        if cidx_name_value is None:
            return
        cidx, col_name, col_value = cidx_name_value
        # self.log(f"Filtering or collecting by `{col_name} == {col_value}`")

        # Handle NULL values
        if col_value is None or col_value == NULL:
            # Create expression for NULL values
            expr = pl.col(col_name).is_null()
            value_display = f"[$success]{NULL_DISPLAY}[/]"
        else:
            # Create expression for the selected value
            expr = pl.col(col_name) == col_value
            value_display = f"[$success]{col_value}[/]"

        df_filtered = self.dftable.df.lazy().filter(expr).collect()
        # self.log(f"Filtered dataframe has {len(df_filtered)} rows")

        ok_rids = set(df_filtered[RID].to_list())
        if not ok_rids:
            self.notify(
                f"No matches found for [$warning]{col_name}[/] == {value_display}",
                title="No Matches",
                severity="warning",
            )
            return

        # Action collect
        if action == "collect":
            self.dftable.action_collect_rows(cidx, col_value)

        # Action filter
        else:
            self.dftable.action_filter_rows(
                {
                    "term": expr,
                    "cidx": cidx,
                    "match_nocase": False,
                    "match_whole": True,
                    "match_literal": True,
                    "match_reverse": False,
                }
            )

        # Dismiss modal screen(s) to return to main table
        while len(self.app._screen_stack) > 1:
            self.app.pop_screen()
            break

        self.dftable.move_cursor(column=cidx)

    def show_frequency(self, cidx_name_value: tuple[int, str, Any] | None) -> None:
        """Show frequency by the selected value.

        Args:
            col_name_value: Tuple of (column_index, column_name, column_value).
        """
        if cidx_name_value is None:
            return
        cidx, col_name, col_value = cidx_name_value
        # self.log(f"Showing frequency for `{col_name} == {col_value}`")

        # Do not dismiss the current modal screen so it can be returned to
        # when frequency screen is closed.
        # self.app.pop_screen()

        # Show frequency screen
        self.dftable.action_show_frequency(cidx)

    def show_statistics(self, cidx_name_value: tuple[int, str, Any] | None) -> None:
        """Show frequency by the selected value.

        Args:
            col_name_value: Tuple of (column_index, column_name, column_value).
        """
        if cidx_name_value is None:
            return
        cidx, col_name, col_value = cidx_name_value
        # self.log(f"Showing statistics for `{col_name} == {col_value}`")

        # Do not dismiss the current modal screen so it can be returned to
        # when frequency screen is closed.
        # self.app.pop_screen()

        # Show statistics screen
        self.dftable.action_show_statistics(cidx)


class RowDetailScreen(TableScreen):
    """Modal screen to display a single row's details."""

    def __init__(self, dftable: "DataFrameTable", ridx: int) -> None:
        super().__init__(dftable)
        self.ridx = ridx

    def on_mount(self) -> None:
        """Initialize the row detail screen.

        Populates the table with column names and values from the selected row
        of the main DataFrame. Sets the table cursor type to "row".
        """
        self.build_table()

    def on_key(self, event) -> None:
        """Handle key press events on the row detail screen.

        Supported keys:
          - 'v': Filter the main table by the selected value.
          - '"': Collect the selected value in the main table to a new tab.
          - '{': Move to the previous row.
          - '}': Move to the next row.
          - 'F': Show frequency for the selected value.
          - 's': Show statistics for the selected value.

        Args:
            event: The key event object.
        """
        if event.key == "v":
            self.filter_or_collect_selected_value(self.get_cidx_name_value(), action="filter")
            event.stop()
        elif event.key == "quotation_mark":  # '"'
            self.filter_or_collect_selected_value(self.get_cidx_name_value(), action="collect")
            event.stop()
        elif event.key == "right_curly_bracket":  # '}'
            # Move to the next row
            ridx = self.ridx + 1
            if ridx < len(self.dftable.df):
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
        elif event.key == "F":
            # Show frequency for the selected value
            self.show_frequency(self.get_cidx_name_value())
            event.stop()
        elif event.key == "s":
            # Show statistics for the selected value
            self.show_statistics(self.get_cidx_name_value())
            event.stop()
        elif event.key == "tab":
            ridx = self.ridx
            cidx = self.table.cursor_row
            dtype = self.dftable.df.dtypes[cidx]
            cell_value = self.dftable.df.item(ridx, cidx)

            if dtype == pl.String:
                # String contains the delimiter '|' (indicating a potential list of values)
                if "|" in cell_value:
                    self.app.push_screen(CellDetailScreen(self.dftable.df, ridx, cidx))
                # Show long string in a text screen for better readability
                elif len(cell_value) > COLUMN_WIDTH_CAP:
                    self.app.push_screen(TextScreen(cell_value))

            # Show cell detail screen if the value is a non-empty list
            elif dtype == pl.List and not cell_value.is_empty():
                if len(cell_value) == 1 and isinstance(cell_value[0], str) and len(cell_value[0]) > COLUMN_WIDTH_CAP:
                    self.app.push_screen(TextScreen(cell_value[0]))
                else:
                    self.app.push_screen(CellDetailScreen(self.dftable.df, ridx, cidx))

            # or a non-empty dict (struct)
            elif dtype == pl.Struct and cell_value:
                self.app.push_screen(CellDetailScreen(self.dftable.df, ridx, cidx))

            event.stop()

    def build_table(self) -> None:
        """Build the row detail table."""
        self.df = pl.DataFrame(
            {
                # Use pl.Object dtype to disable styling for the column names.
                "Column": format_row(
                    self.dftable.df.columns,
                    dtypes=[pl.Object] * len(self.dftable.df.columns),
                ),
                "Value": format_row(
                    self.dftable.df.row(self.ridx),
                    self.dftable.df.dtypes,
                    justify="left",
                    thousand_separator=self.thousand_separator,
                ),
            }
        )

        self.df2table()
        self.table.cursor_type = "row"

    def get_cidx_name_value(self) -> tuple[int, str, Any] | None:
        """Get the current column info."""
        cidx = self.table.cursor_row
        if cidx >= len(self.dftable.df.columns):
            return None  # Invalid row

        col_name = self.dftable.df.columns[cidx]
        col_value = self.dftable.df.item(self.ridx, cidx)
        return cidx, col_name, col_value


class StatisticsScreen(TableScreen):
    """Modal screen to display statistics for a column or entire dataframe."""

    def __init__(self, dftable: "DataFrameTable", cidx: int | None = None):
        super().__init__(dftable)
        self.cidx = cidx  # None for dataframe statistics, otherwise column index

    def on_mount(self) -> None:
        """Create the statistics table."""
        self.table.loading = True
        self.calculate_statistics()

    @work(thread=True)
    def calculate_statistics(self) -> None:
        """Calculate statistics."""
        self.build_df()
        self.app.call_from_thread(self._on_calc_ready)

    def build_table(self) -> None:
        """Build the statistics table."""
        self.table.clear(columns=True)

        # Add columns
        for col_name, col_dtype in zip(self.df.columns, self.df.dtypes):
            if col_name == "statistic":  # no styling
                self.table.add_column("Statistic", key=col_name)
                continue

            dc = DtypeConfig(col_dtype)
            self.table.add_column(Text(col_name, justify=dc.justify), key=col_name)

        # Add rows
        for ridx, row in enumerate(self.df.iter_rows()):
            formatted_row = []

            # Format remaining values with appropriate styling
            for idx, stat_value in enumerate(row):
                # First element is the statistic label, no styling needed
                if idx == 0:
                    formatted_row.append(stat_value)
                    continue

                col_dtype = self.df.dtypes[idx]
                dc = DtypeConfig(col_dtype)

                if ridx < 4 and col_dtype == pl.String and self.thousand_separator:
                    stat_value = f"{int(stat_value):,}"

                formatted_row.append(dc.format(stat_value, thousand_separator=self.thousand_separator))

            self.table.add_row(*formatted_row)

        # Set cursor type based on whether this is dataframe stats (column cursor) or column stats (row cursor)
        self.table.cursor_type = "column" if self.cidx is None else "row"

    def build_df(self) -> pl.DataFrame:
        """Get the dataframe to use for statistics, applying any necessary filters."""
        if self.cidx is None:
            lf = self.dftable.df.lazy().select(pl.exclude(RID))

            # Apply only to non-hidden columns
            if self.dftable.hidden_columns:
                lf = lf.select(pl.exclude(self.dftable.hidden_columns))

            # Get dataframe statistics
            stats_df = lf.describe()

            # total
            df_n_total = lf.select(pl.all().len()).collect()
            df_n_total.insert_column(0, pl.Series("statistic", ["n_total"]))
            df_n_total = df_n_total.cast(stats_df.schema)

            # unique count for each column
            df_n_unique = lf.select(pl.all().n_unique()).collect()
            df_n_unique.insert_column(0, pl.Series("statistic", ["n_unique"]))
            df_n_unique = df_n_unique.cast(stats_df.schema)

            # total first, then n_unique, then describe stats
            self.df = df_n_total.vstack(df_n_unique).vstack(stats_df)
        else:
            col_name = self.dftable.df.columns[self.cidx]
            lf = self.dftable.df.lazy()

            # Get column statistics
            stats_df = lf.select(pl.col(col_name)).describe()
            if len(stats_df) == 0:
                return

            # unique count
            n_unique = lf.select(pl.col(col_name)).collect().n_unique()
            df_n_unique = pl.DataFrame({"statistic": ["n_unique"], col_name: n_unique}, schema=stats_df.schema)

            # total count
            n_total = len(self.dftable.df[col_name])
            df_n_total = pl.DataFrame({"statistic": ["n_total"], col_name: n_total}, schema=stats_df.schema)

            # total first, then n_unique, then describe stats
            self.df = df_n_total.vstack(df_n_unique).vstack(stats_df)


class FrequencyScreen(TableScreen):
    """Modal screen to display frequency of values in a column."""

    def __init__(self, dftable: "DataFrameTable", cidx: int) -> None:
        super().__init__(dftable)
        self.cidx = cidx
        self.sorted_columns[1] = True  # Count sort by default
        self.total_count = len(dftable.df)
        self.df: pl.DataFrame = None

    def on_mount(self) -> None:
        """Start frequency calculation."""
        self.table.loading = True
        self._calculate_frequency()

    @work(thread=True)
    def _calculate_frequency(self) -> None:
        """Calculate frequency."""
        col = self.dftable.df.columns[self.cidx]
        self.df = self.dftable.df.lazy().select(pl.col(col).value_counts(sort=True)).unnest(col).collect()
        self.app.call_from_thread(self._on_calc_ready)

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
            self.filter_or_collect_selected_value(self.get_cidx_name_value(), action="filter")
            event.stop()
        elif event.key == "quotation_mark":  # '"'
            self.filter_or_collect_selected_value(self.get_cidx_name_value(), action="collect")
            event.stop()
        elif event.key == "ctrl+s":
            # Save the frequency table to file
            self.save_frequency_table()
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
        bar_width = 10

        # Add rows to the frequency table
        for row_idx, row in enumerate(self.df.iter_rows()):
            column, count = row
            percentage = (count / self.total_count) * 100

            self.table.add_row(
                dc.format(column),
                dc_int.format(count, thousand_separator=self.thousand_separator),
                dc_float.format(percentage, thousand_separator=self.thousand_separator),
                Bar(
                    highlight_range=(0.0, percentage / 100 * bar_width),
                    width=bar_width,
                ),
                label=str(row_idx + 1),
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
                highlight_range=(0.0, bar_width),
                width=bar_width,
            ),
        )

    def sort_by_column(self, descending: bool) -> None:
        """Sort the dataframe by the selected column and refresh the main table."""
        row_idx, col_idx = self.table.cursor_coordinate
        col_sort = col_idx

        if self.sorted_columns.get(col_sort) == descending:
            # self.notify("Already sorted in that order", title="Sort", severity="warning")
            return

        self.sorted_columns.clear()
        self.sorted_columns[col_sort] = descending

        # Percentage and Histogram use Count for sorting
        col_name = self.df.columns[col_sort if col_sort in (0, 1) else 1]
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

    def save_frequency_table(self) -> None:
        """Save the frequency table to file."""
        column = self.dftable.df.columns[self.cidx]
        filename = f"{column}_freq.csv"

        self.app.push_screen(
            SaveFileScreen(filename=filename),
            callback=partial(self.app.save_to_file, all_tabs=False, use_df=self.df),
        )


class HistogramScreen(TableScreen):
    """Modal screen to display histogram of values in a column."""

    def __init__(self, dftable: "DataFrameTable", bins: list[float] = None, bin_count: int = None) -> None:
        super().__init__(dftable)
        self.cidx = dftable.cursor_cidx
        self.bins = bins
        self.bin_count = bin_count
        self.total_count = len(dftable.df)
        self.df: pl.DataFrame = None

    def on_mount(self) -> None:
        """Start histogram calculation."""
        self.table.loading = True
        self._calculate_histogram()

    @work(thread=True)
    def _calculate_histogram(self) -> None:
        """Calculate histogram."""
        col = self.dftable.df.columns[self.cidx]
        self.df = self.dftable.df.lazy().select(col).collect()[col].hist(bins=self.bins, bin_count=self.bin_count)
        self.app.call_from_thread(self._on_calc_ready)

    def on_key(self, event):
        if event.key == "ctrl+s":
            # Save the histogram table to file
            self.save_histogram_table()
            event.stop()

    def build_table(self) -> None:
        """Build the histogram table."""
        self.table.clear(columns=True)

        # Create histogram table
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
            header_text = display_name

            justify = dc.justify if col_idx_num == 0 else ("right" if col_idx_num in (1, 2) else "left")
            self.table.add_column(Text(header_text, justify=justify), key=key)

        # Get style config for Int64 and Float64
        dc_int = DtypeConfig(pl.Int64)
        dc_float = DtypeConfig(pl.Float64)
        bar_width = 10

        # Add rows to the histogram table
        for row_idx, row in enumerate(self.df.iter_rows()):
            _breakpoint, column, count = row
            percentage = (count / self.total_count) * 100

            self.table.add_row(
                Text(column, style=dc.style, justify=dc.justify),
                dc_int.format(count, thousand_separator=self.thousand_separator),
                dc_float.format(percentage, thousand_separator=self.thousand_separator),
                Bar(
                    highlight_range=(0.0, percentage / 100 * bar_width),
                    width=bar_width,
                ),
                label=str(row_idx + 1),
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
                highlight_range=(0.0, bar_width),
                width=bar_width,
            ),
        )

    def save_histogram_table(self) -> None:
        """Save the histogram table to file."""
        column = self.dftable.df.columns[self.cidx]
        filename = f"{column}_hist.csv"

        self.app.push_screen(
            SaveFileScreen(filename=filename),
            callback=partial(self.app.save_to_file, all_tabs=False, use_df=self.df),
        )


class MetaShape(TableScreen):
    """Modal screen to display metadata about the dataframe."""

    def on_mount(self) -> None:
        """Initialize the metadata screen.

        Populates the table with metadata information about the dataframe,
        including row and column counts.
        """
        self.table.loading = True
        self._calc_metashape()

    @work(thread=True)
    def _calc_metashape(self) -> None:
        """Calculate metadata shape."""
        self.app.call_from_thread(self._on_calc_ready)

    def build_table(self) -> None:
        """Build the metadata table."""
        self.table.clear(columns=True)
        self.table.add_column("", key="metadata")
        self.table.add_column(Text("Value", justify="right"), key="value")

        # Get shape information
        num_rows, num_cols = self.dftable.df.shape
        num_cols -= 1  # Exclude RID column
        dc_int = DtypeConfig(pl.Int64)
        dc_str = DtypeConfig(pl.String)

        # Add rows to the table
        self.table.add_row("File Name", dc_str.format(self.dftable.filename, justify="right"))
        self.table.add_row("Row Count", dc_int.format(num_rows, thousand_separator=self.thousand_separator))
        self.table.add_row("Column Count", dc_int.format(num_cols, thousand_separator=self.thousand_separator))

        self.table.cursor_type = "none"


class MetaColumnScreen(TableScreen):
    """Modal screen to display metadata about the columns in the dataframe."""

    def on_mount(self) -> None:
        """Initialize the column metadata screen.

        Populates the table with information about each column in the dataframe,
        including ID (1-based index), Name, and Type.
        """
        self.build_table()

    def on_key(self, event) -> None:
        """Handle key press events on the column metadata screen.

        Supports keys:
          - 'F': Show frequency for the selected value.
          - 's': Show statistics for the selected value.

        Args:
            event: The key event object.
        """
        if event.key == "F":
            # Show frequency for the selected value
            self.show_frequency(self.get_cidx_name_value())
            event.stop()
        elif event.key == "s":
            # Show statistics for the selected value
            self.show_statistics(self.get_cidx_name_value())
            event.stop()

    def build_table(self) -> None:
        """Build the column metadata table."""
        self.table.clear(columns=True)
        self.table.add_column("Column", key="column")
        self.table.add_column("Type", key="type")

        # Get schema information
        schema = self.dftable.df.schema
        dc_str = DtypeConfig(pl.String)

        # Add a row for each column
        for idx, (col_name, col_type) in enumerate(schema.items()):
            if col_name == RID:
                continue  # Skip RID column

            dc = DtypeConfig(col_type)
            self.table.add_row(
                col_name,
                dc_str.format("Datetime" if str(col_type).startswith("Datetime") else col_type, style=dc.style),
                label=str(idx + 1),
            )

        self.table.cursor_type = "row"

    def get_cidx_name_value(self) -> int | None:
        """Get the current column info."""
        cidx = self.table.cursor_row
        if cidx >= len(self.dftable.df.columns):
            return None  # Invalid row

        col_name = self.dftable.df.columns[cidx]
        col_value = None

        return cidx, col_name, col_value


class CellDetailScreen(TableModalScreen):
    """Modal screen to display details of a cell value, including support for nested structures like lists and dicts."""

    def __init__(self, dfsrc: pl.DataFrame, ridx: int, cidx: int, delimiter: str | None = "|") -> None:
        super().__init__()
        self.dfsrc = dfsrc
        self.cidx = cidx
        self.ridx = ridx
        self.delimiter = delimiter

    def on_mount(self) -> None:
        """Initialize the cell detail screen."""
        self.build_table()

    def on_key(self, event) -> None:
        """Handle key press events on the column metadata screen.

        Supports keys:
          - 'tab': Show cell details for the selected value.

        Args:
            event: The key event object.
        """
        if event.key == "tab":
            cidx = self.table.cursor_column
            ridx = self.table.cursor_row
            dtype = self.df.dtypes[cidx]
            cell_value = self.df.item(ridx, cidx)

            if dtype == pl.String:
                # String contains the delimiter '|' (indicating a potential list of values)
                if "|" in cell_value:
                    self.app.push_screen(CellDetailScreen(self.df, ridx, cidx))
                # Show long string in a text screen for better readability
                elif len(cell_value) > COLUMN_WIDTH_CAP:
                    self.app.push_screen(TextScreen(cell_value))

            # Show cell detail screen if the value is a non-empty list
            elif dtype == pl.List and not cell_value.is_empty():
                if len(cell_value) == 1 and isinstance(cell_value[0], str) and len(cell_value[0]) > COLUMN_WIDTH_CAP:
                    self.app.push_screen(TextScreen(cell_value[0]))
                else:
                    self.app.push_screen(CellDetailScreen(self.df, ridx, cidx))

            # or a non-empty dict (struct)
            elif dtype == pl.Struct and cell_value:
                self.app.push_screen(CellDetailScreen(self.df, ridx, cidx))

            event.stop()

    def build_table(self) -> None:
        """Build the list table."""
        # Get the column values as a list
        col_name = self.dfsrc.columns[self.cidx]
        dtype = self.dfsrc.dtypes[self.cidx]
        cell_value = self.dfsrc.item(self.ridx, self.cidx)

        if isinstance(cell_value, pl.Series) and not cell_value.is_empty():
            self.df = pl.DataFrame({col_name: cell_value})
            self.df2table()
        elif isinstance(cell_value, dict) and cell_value:
            self.df = pl.DataFrame(
                {
                    f"{col_name} (Key)": pl.Series(cell_value.keys(), strict=False),
                    f"{col_name} (Value)": pl.Series(cell_value.values(), strict=False),
                }
            )
            self.df2table()
        elif dtype == pl.String and cell_value:
            self.df = pl.DataFrame({col_name: [c for c in cell_value.split(self.delimiter) if c]})
            self.df2table()
        else:
            self.df = pl.DataFrame({col_name: [cell_value]})
            self.df2table()


class BarScreen(TableModalScreen):
    """Modal screen to display labels and values of a DataFrame as bars."""

    def __init__(self, df: pl.DataFrame, cidx: int) -> None:
        super().__init__()
        self.df = df
        self.cidx = cidx

    def on_mount(self) -> None:
        """Start bar calculation."""
        self.table.loading = True
        self._calculate_bar()

    @work(thread=True)
    def _calculate_bar(self) -> None:
        """Calculate bar."""
        self.app.call_from_thread(self._on_calc_ready)

    def build_table(self) -> None:
        """Build the bar table."""
        self.table.clear(columns=True)

        # Create bar table
        label_col = self.df.columns[0]
        data_col = self.df.columns[self.cidx]
        dtype = self.df.dtypes[self.cidx]
        dc = DtypeConfig(dtype)

        # Add column headers with sort indicators
        columns = [
            (label_col, "Value", 0, dc.justify),
            (data_col, "Count", 1, "right"),
            ("%", "%", 2, "right"),
            ("Histogram", "Histogram", 3, "left"),
        ]

        for display_name, key, col_idx_num, justify in columns:
            header_text = display_name
            self.table.add_column(Text(header_text, justify=justify), key=key)

        # Get style config for Int64 and Float64
        dc_int = DtypeConfig(pl.Int64)
        dc_float = DtypeConfig(pl.Float64)
        bar_width = 10
        total = self.df[data_col].sum()

        # Add rows to the histogram table
        for row_idx, (column, count) in enumerate(zip(self.df[label_col], self.df[data_col])):
            percentage = (count / total) * 100

            self.table.add_row(
                dc.format(column),
                dc_int.format(count, thousand_separator=self.thousand_separator),
                dc_float.format(percentage, thousand_separator=self.thousand_separator),
                Bar(
                    highlight_range=(0.0, percentage / 100 * bar_width),
                    width=bar_width,
                ),
                label=str(row_idx + 1),
            )

        # Add a total row
        self.table.add_row(
            Text("Total", style="bold", justify=dc.justify),
            Text(
                f"{total:,}" if self.thousand_separator else str(total),
                style="bold",
                justify="right",
            ),
            Text(
                format_float(100.0, self.thousand_separator, precision=-2 if len(self.df) > 1 else 2),
                style="bold",
                justify="right",
            ),
            Bar(
                highlight_range=(0.0, bar_width),
                width=bar_width,
            ),
        )
