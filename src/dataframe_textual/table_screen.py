"""Modal screens for displaying data in tables (row details and frequency)."""

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from textual.widgets.data_table import ColumnKey

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
    HIGHLIGHT_COLOR,
    NULL,
    NULL_DISPLAY,
    RID,
    DtypeConfig,
    format_float,
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

        Sets up the base modal screen and stores the DataFrame for display.

        Args:
            df: The DataFrame to display in this screen.
        """
        super().__init__()
        self.df = df  # DataFrame for this screen, to be set by subclasses
        self.thousand_separator = False  # Whether to use thousand separators in numbers
        self.selected_rows: set[int] = set()  # Track selected row indices for potential multi-row actions
        self.sorted_columns: dict[str, bool] = {}  # Track sorted columns and their sort order
        self.sort_ignore_last = False  # Whether to ignore the last column (e.g., Total) when sorting
        self.col_style = None
        self.col_justify = None

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
        elif event.key == "s":
            event.stop()
            self.toggele_row_selection()
            self.df2table()  # Rebuild table to update row styling based on selection

    def build_table(self) -> None:
        """Build the table content.

        Subclasses should implement this method to populate the DataTable
        with appropriate columns and rows based on the specific screen's purpose.
        """
        raise NotImplementedError("Subclasses must implement build_table method.")

    def df2table(
        self,
        col_style: str | dict[str, str | list[str]] | None = None,
        col_justify: str | dict[str, str] | None = None,
    ) -> None:
        """Convert a Polars DataFrame to a DataTable for display.


        Args:
            col_style: Optional style(s) to apply to all cells. Can be a single string, or a dict mapping column names to styles (which can be strings or lists for per-row styling).
            col_justify: Optional justification(s) for all cells. Can be a single string, or a dict mapping column names to justification.
        """
        if self.df is None:
            return

        if col_style is None:
            col_style = self.col_style
        else:
            self.col_style = col_style

        if col_justify is None:
            col_justify = self.col_justify
        else:
            self.col_justify = col_justify

        # Store the current cursor coordinate to restore it after rebuilding the table
        row_idx, col_idx = self.table.cursor_coordinate

        self.table.clear(columns=True)

        # Add columns with proper justification based on data types
        for cidx, (col, dtype) in enumerate(zip(self.df.columns, self.df.dtypes)):
            if col == RID:
                continue

            dc = DtypeConfig(dtype)
            justify = col_justify.get(col) if isinstance(col_justify, dict) else col_justify

            for c in self.sorted_columns:
                if c == col:
                    # Add sort indicator to column header
                    descending = self.sorted_columns[col]
                    sort_indicator = " ▼" if descending else " ▲"
                    cell_value = col + sort_indicator
                    break
            else:  # No break occurred, so column is not sorted
                cell_value = col

            self.table.add_column(Text(cell_value, justify=justify), key=col)

        # Add rows with proper formatting based on data types
        for ridx, row in enumerate(self.df.iter_rows()):
            # Skip the row containing the RID value
            if row[0] == RID or (isinstance(row[0], Text) and row[0].plain == RID):
                continue

            is_selected = ridx in self.selected_rows

            formatted_row = []
            for cidx, c in enumerate(row):
                col = self.df.columns[cidx]
                if col == RID:
                    continue
                dc = DtypeConfig(self.df.dtypes[cidx])
                style = col_style.get(col) if isinstance(col_style, dict) else col_style
                justify = col_justify.get(col) if isinstance(col_justify, dict) else col_justify

                formatted_row.append(
                    dc.format(
                        c,
                        style=HIGHLIGHT_COLOR if is_selected else style[ridx] if isinstance(style, list) else style,
                        justify=justify,
                        thousand_separator=self.thousand_separator,
                    )
                )

            self.table.add_row(*formatted_row, key=str(ridx), label=str(ridx + 1))

        # Restore the old cursor coordinate
        self.table.move_cursor(row=row_idx, column=col_idx)

    def sort_by_column_key(self, col_key: ColumnKey, descending: bool) -> None:
        """Sort the table by the specified column."""
        if self.sort_ignore_last and self.table.row_count > 1:
            # Detach the last row, sort the rest, then re-append it
            last_row = self.table.ordered_rows[-1]
            last_cells = self.table.get_row(last_row.key)
            self.table.remove_row(last_row.key)
            self.table.sort(col_key, key=lambda c: c.plain if isinstance(c, Text) else c, reverse=descending)
            self.table.add_row(*last_cells, key=last_row.key.value, label=last_row.label)
        else:
            self.table.sort(col_key, key=lambda c: c.plain if isinstance(c, Text) else c, reverse=descending)

    def sort_by_column(self, descending: bool) -> None:
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

        # If no DataFrame is available (e.g., not yet populated), use built-in sort to sort the table directly
        if self.df is None:
            self.sort_by_column_key(col_key, descending)
            return

        if self.df.is_empty():
            return

        try:
            self.df = self.df.sort(col_name, descending=descending, nulls_last=True)
        except Exception as e:
            self.log(f"Error sorting by column '{col_name}': {e}")

            # Fallback to built-in sort if dataframe sorting fails (e.g. due to unsupported data types)
            self.sort_by_column_key(col_key, descending)
            return

        # Rebuild the table
        self.df2table()

        # Move cursor back to the same column and approximate row position after sorting
        self.table.move_cursor(row=ridx, column=cidx)

    def toggele_row_selection(self) -> None:
        """Toggle selection of the currently focused row."""
        ridx, _ = self.table.cursor_coordinate
        if ridx in self.selected_rows:
            self.selected_rows.remove(ridx)
        else:
            self.selected_rows.add(ridx)

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

    def sort_by_column(self, descending: bool) -> None:
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
        elif event.key == "left_curly_bracket":  # '{'
            # Move to the previous row
            ridx = self.ridx - 1
            if ridx >= 0:
                self.ridx = ridx
                self.dftable.move_cursor_to(self.ridx)
                self.build_table()
            event.stop()
        elif event.key == "right_curly_bracket":  # '}'
            # Move to the next row
            ridx = self.ridx + 1
            if ridx < len(self.dftable.df):
                self.ridx = ridx
                self.dftable.move_cursor_to(self.ridx)
                self.build_table()
            event.stop()
        elif event.key == "F":
            # Show frequency for the selected value
            self.show_frequency(self.get_cidx_name_value())
            event.stop()
        elif event.key == "S":
            # Show statistics for the selected value
            self.show_statistics(self.get_cidx_name_value())
            event.stop()
        elif event.key == "tab":
            ridx = self.ridx
            cidx = self.table.cursor_row
            col_name = self.dftable.df.columns[cidx]
            dtype = self.dftable.df.dtypes[cidx]
            cell_value = self.dftable.df.item(ridx, cidx)

            if dtype == pl.String:
                # String contains the delimiter '|' (indicating a potential list of values)
                if "|" in cell_value:
                    self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))
                # Show long string in a text screen for better readability
                elif len(cell_value) > COLUMN_WIDTH_CAP:
                    self.app.push_screen(TextScreen(cell_value))

            # Show cell detail screen if the value is a non-empty list
            elif dtype == pl.List and not cell_value.is_empty():
                if len(cell_value) == 1 and isinstance(cell_value[0], str) and len(cell_value[0]) > COLUMN_WIDTH_CAP:
                    self.app.push_screen(TextScreen(cell_value[0]))
                else:
                    self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))

            # or a non-empty dict (struct)
            elif dtype == pl.Struct and cell_value:
                self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))

            event.stop()

    def build_table(self) -> None:
        """Build the row detail table."""
        self.df = pl.DataFrame(
            {
                "Column": self.dftable.df.columns,
                "Value": [str(c) for c in self.dftable.df.row(self.ridx)],
            }
        )

        col2style = defaultdict(list)
        col2style["Column"] = ""  # No specific style for the "Column" header
        for dtype in self.dftable.df.dtypes:
            col2style["Value"].append(DtypeConfig(dtype).style)

        self.df2table(col_style=col2style)

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

            self.table.add_row(*formatted_row, key=str(ridx), label=str(ridx + 1))

        # Set cursor type based on whether this is dataframe stats (column cursor) or column stats (row cursor)
        self.table.cursor_type = "column" if self.cidx is None else "row"

    def build_df(self) -> None:
        """Get the dataframe to use for statistics."""
        # all columns
        if self.cidx is None:
            lf = self.dftable.df.lazy().select(pl.exclude(RID))

            # Apply only to non-hidden columns
            if self.dftable.hidden_columns:
                lf = lf.select(pl.exclude(self.dftable.hidden_columns))

            source_schema = lf.collect_schema()

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

            # sum
            sum_exprs: list[pl.Expr] = [pl.lit("sum").alias("statistic")]
            for col_name, dtype in source_schema.items():
                dc = DtypeConfig(dtype)
                if dc.gtype in ("integer", "float"):
                    sum_exprs.append(pl.col(col_name).sum().alias(col_name))
                else:
                    sum_exprs.append(pl.lit(None).alias(col_name))

            df_sum = lf.select(sum_exprs).collect().cast(stats_df.schema)

            # min_length and max_length
            min_length_exprs: list[pl.Expr] = [pl.lit("min_length").alias("statistic")]
            max_length_exprs: list[pl.Expr] = [pl.lit("max_length").alias("statistic")]
            for col_name, dtype in source_schema.items():
                if dtype == pl.String:
                    min_length_exprs.append(pl.col(col_name).str.len_chars().min().alias(col_name))
                    max_length_exprs.append(pl.col(col_name).str.len_chars().max().alias(col_name))
                elif dtype == pl.List:
                    min_length_exprs.append(pl.col(col_name).list.len().min().alias(col_name))
                    max_length_exprs.append(pl.col(col_name).list.len().max().alias(col_name))
                else:
                    try:
                        min_length_exprs.append(pl.col(col_name).cast(pl.String).str.len_chars().min().alias(col_name))
                        max_length_exprs.append(pl.col(col_name).cast(pl.String).str.len_chars().max().alias(col_name))
                    except Exception:
                        min_length_exprs.append(pl.lit(None).alias(col_name))
                        max_length_exprs.append(pl.lit(None).alias(col_name))

            df_min_length = lf.select(min_length_exprs).collect().cast(stats_df.schema)
            df_max_length = lf.select(max_length_exprs).collect().cast(stats_df.schema)

            # fill rate
            fill_exprs: list[pl.Expr] = [pl.lit("fill%").alias("statistic")]
            for col_name, dtype in source_schema.items():
                fill_expr = pl.col(col_name).count().truediv(pl.len()) * 100
                dc = DtypeConfig(dtype)
                if dc.gtype in ("integer", "float"):
                    fill_exprs.append(fill_expr.alias(col_name))
                else:
                    fill_exprs.append(fill_expr.round(1).cast(pl.String).alias(col_name))

            df_fill = lf.select(fill_exprs).collect().cast(stats_df.schema)

            # vstack
            self.df = pl.concat(
                [
                    df_n_unique,
                    df_n_total,
                    stats_df,
                    df_sum,
                    df_min_length,
                    df_max_length,
                    df_fill,
                ]
            )

        # single column
        else:
            col_name = self.dftable.df.columns[self.cidx]
            dtype = self.dftable.df.dtypes[self.cidx]
            this_col = self.dftable.df[col_name]
            lf = self.dftable.df.lazy()

            # Get column statistics
            stats_df = lf.select(pl.col(col_name)).describe()
            if len(stats_df) == 0:
                return

            # unique count
            n_unique = this_col.n_unique()
            df_n_unique = pl.DataFrame({"statistic": ["n_unique"], col_name: n_unique}, schema=stats_df.schema)

            # total count
            n_total = len(this_col)
            df_n_total = pl.DataFrame({"statistic": ["n_total"], col_name: n_total}, schema=stats_df.schema)

            # sum
            dc = DtypeConfig(self.dftable.df.dtypes[self.cidx])
            if dc.gtype in ("integer", "float"):
                sum_value = this_col.sum()
                df_sum = pl.DataFrame({"statistic": ["sum"], col_name: sum_value}, schema=stats_df.schema)
            else:
                df_sum = pl.DataFrame({"statistic": ["sum"], col_name: None}, schema=stats_df.schema)

            # min_length and max_length
            if dtype == pl.String:
                min_length = this_col.str.len_chars().min()
                max_length = this_col.str.len_chars().max()
            elif dtype == pl.List:
                min_length = this_col.list.len().min()
                max_length = this_col.list.len().max()
            else:
                try:
                    min_length = this_col.cast(pl.String).str.len_chars().min()
                    max_length = this_col.cast(pl.String).str.len_chars().max()
                except Exception:
                    min_length = None
                    max_length = None

            df_min_length = pl.DataFrame({"statistic": ["min_length"], col_name: min_length}, schema=stats_df.schema)
            df_max_length = pl.DataFrame({"statistic": ["max_length"], col_name: max_length}, schema=stats_df.schema)

            # fill rate
            fill_rate = this_col.count() / n_total * 100
            if dc.gtype in ("integer", "float"):
                df_fill = pl.DataFrame({"statistic": ["fill%"], col_name: fill_rate}, schema=stats_df.schema)
            else:
                df_fill = pl.DataFrame(
                    {"statistic": ["fill%"], col_name: str(round(fill_rate, 1))}, schema=stats_df.schema
                )

            # total first, then n_unique, then describe stats
            self.df = pl.concat(
                [
                    df_n_unique,
                    df_n_total,
                    stats_df,
                    df_sum,
                    df_min_length,
                    df_max_length,
                    df_fill,
                ]
            )

        # Rename the first column to "Statistic" for better display
        self.df = self.df.rename({"statistic": "Statistic"})

        # No specific styling for the "Statistics" header
        self.col_style = {"Statistic": ""}


class FrequencyScreen(TableScreen):
    """Modal screen to display frequency of values in a column."""

    def __init__(self, dftable: "DataFrameTable", cidx: int) -> None:
        super().__init__(dftable)
        self.cidx = cidx
        self.sorted_columns["Count"] = True  # Count sort by default
        self.total_count = len(dftable.df)
        self.col = self.dftable.df.columns[self.cidx]
        self.columns = [
            (self.col, "Value"),
            ("Count", "Count"),
            ("%", "%"),
            ("Histogram", "Histogram"),
        ]

    def on_mount(self) -> None:
        """Start frequency calculation."""
        self.table.loading = True
        self._calculate_frequency()

    @work(thread=True)
    def _calculate_frequency(self) -> None:
        """Calculate frequency."""
        self.df = self.dftable.df.lazy().select(pl.col(self.col).value_counts(sort=True)).unnest(self.col).collect()
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
        dtype = self.dftable.df.dtypes[self.cidx]
        dc = DtypeConfig(dtype)

        for display_name, col in self.columns:
            # Check if this column is sorted and add indicator
            if col in self.sorted_columns:
                descending = self.sorted_columns[col]
                sort_indicator = " ▼" if descending else " ▲"
                header_text = display_name + sort_indicator
            else:
                header_text = display_name

            justify = dc.justify if col == "Value" else "right"
            self.table.add_column(Text(header_text, justify=justify), key=col)

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
                key=str(row_idx),
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
            key="total",
        )

    def sort_by_column(self, descending: bool) -> None:
        """Sort the dataframe by the selected column and refresh the main table."""
        row_idx, col_idx = self.table.cursor_coordinate
        col_sort = self.columns[col_idx][1]

        if self.sorted_columns.get(col_sort) == descending:
            return

        self.sorted_columns.clear()
        self.sorted_columns[col_sort] = descending

        # Percentage and Histogram use Count for sorting
        col_name = self.df.columns[1 if col_idx >= 1 else 0]
        self.df = self.df.sort(col_name, descending=descending, nulls_last=True)

        # Rebuild the frequency table
        self.build_table()

        self.table.move_cursor(row=row_idx, column=col_idx)

    def get_cidx_name_value(self) -> tuple[int, str, Any] | None:
        row_idx = self.table.cursor_row
        if row_idx >= len(self.df):
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

    def __init__(
        self, dftable: "DataFrameTable", bins: list[float] | None = None, bin_count: int | None = None
    ) -> None:
        super().__init__(dftable)
        self.cidx = dftable.cursor_cidx
        self.bins = bins
        self.bin_count = bin_count
        self.total_count = len(dftable.df)
        self.df: pl.DataFrame | None = None

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
                key=str(row_idx),
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
            key="total",
        )

    def save_histogram_table(self) -> None:
        """Save the histogram table to file."""
        column = self.dftable.df.columns[self.cidx]
        filename = f"{column}_hist.csv"

        self.app.push_screen(
            SaveFileScreen(filename=filename),
            callback=partial(self.app.save_to_file, all_tabs=False, use_df=self.df),
        )


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
        elif event.key == "S":
            # Show statistics for the selected value
            self.show_statistics(self.get_cidx_name_value())
            event.stop()

    def build_table(self) -> None:
        """Build the column metadata table."""
        self.df = pl.DataFrame(
            {
                "Column": self.dftable.df.columns,
                "Type": self.dftable.df.dtypes,
            }
        )

        col2style = defaultdict(list)
        col2style["Column"] = ""  # No specific style for the "Column" header
        for dtype in self.dftable.df.dtypes:
            col2style["Type"].append(DtypeConfig(dtype).style)

        self.df2table(col_style=col2style)

        self.table.cursor_type = "row"

    def get_cidx_name_value(self) -> tuple[int, str, Any] | None:
        """Get the current column info."""
        cidx = self.table.cursor_row
        if cidx >= len(self.dftable.df.columns):
            return None  # Invalid row

        col_name = self.dftable.df.columns[cidx]
        col_value = None

        return cidx, col_name, col_value


class CellDetailScreen(TableModalScreen):
    """Modal screen to display details of a cell value, including support for nested structures like lists and dicts."""

    def __init__(self, col_name: str, dtype: pl.DataType, cell_value: Any, delimiter: str | None = "|") -> None:
        super().__init__()
        self.col_name = col_name
        self.dtype = dtype
        self.cell_value = cell_value
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
            col_name = self.df.columns[cidx]
            dtype = self.df.dtypes[cidx]
            cell_value = self.df.item(ridx, cidx)

            if dtype == pl.String:
                # String contains the delimiter '|' (indicating a potential list of values)
                if "|" in cell_value:
                    self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))
                # Show long string in a text screen for better readability
                elif len(cell_value) > COLUMN_WIDTH_CAP:
                    self.app.push_screen(TextScreen(cell_value))

            # Show cell detail screen if the value is a non-empty list
            elif dtype == pl.List and not cell_value.is_empty():
                if len(cell_value) == 1 and isinstance(cell_value[0], str) and len(cell_value[0]) > COLUMN_WIDTH_CAP:
                    self.app.push_screen(TextScreen(cell_value[0]))
                else:
                    self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))

            # or a non-empty dict (struct)
            elif dtype == pl.Struct and cell_value:
                self.app.push_screen(CellDetailScreen(col_name, dtype, cell_value))

            event.stop()

    def build_table(self) -> None:
        """Build the list table."""
        col_name = self.col_name
        dtype = self.dtype
        cell_value = self.cell_value

        # Get the column values as a list
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

    def __init__(self, df: pl.DataFrame, cidx: int, cidx_label: int) -> None:
        super().__init__()
        self.df = df
        self.cidx = cidx
        self.cidx_label = cidx_label
        self.sort_ignore_last = True  # Ignore the last column (Total) when sorting

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
        label_col = self.df.columns[self.cidx_label]
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
                key=str(row_idx),
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
            key="total",
        )
