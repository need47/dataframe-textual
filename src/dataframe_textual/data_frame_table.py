"""DataFrameTable widget for displaying and interacting with Polars DataFrames."""

import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

import polars as pl
from rich.text import Text
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.widgets._data_table import (
    CellDoesNotExist,
    CellKey,
    ColumnKey,
    CursorType,
    RowKey,
)

from .common import (
    BATCH_SIZE,
    BOOLS,
    CURSOR_TYPES,
    INITIAL_BATCH_SIZE,
    SUBSCRIPT_DIGITS,
    DtypeConfig,
    _format_row,
    _next,
    _rindex,
)
from .table_screen import FrequencyScreen, RowDetailScreen
from .yes_no_screen import (
    ConfirmScreen,
    EditCellScreen,
    FilterScreen,
    FreezeScreen,
    SaveFileScreen,
    SearchScreen,
)


@dataclass
class History:
    """Class to track history of dataframe states for undo/redo functionality."""

    description: str
    df: pl.DataFrame
    filename: str
    loaded_rows: int
    sorted_columns: dict[str, bool]
    selected_rows: list[bool]
    visible_rows: list[bool]
    fixed_rows: int
    fixed_columns: int
    cursor_coordinate: Coordinate


class DataFrameTable(DataTable):
    """Custom DataTable to highlight row/column labels based on cursor position."""

    # Help text for the DataTable which will be shown in the HelpPanel
    HELP = dedent("""
        # 📊 DataFrame Viewer - Table Controls

        ## ⬆️ Navigation
        - **↑↓←→** - 🎯 Move cursor (cell/row/column)
        - **g** - ⬆️ Jump to first row
        - **G** - ⬇️ Jump to last row
        - **PgUp/PgDn** - 📜 Page up/down

        ## 👁️ View & Display
        - **Enter** - 📋 Show row details in modal
        - **F** - 📊 Show frequency distribution
        - **C** - 🔄 Cycle cursor (cell → row → column → cell)
        - **#** - 🏷️ Toggle row labels

        ## ↕️ Sorting
        - **[** - 🔼 Sort column ascending
        - **]** - 🔽 Sort column descending
        - *(Multi-column sort supported)*

        ## 🔍 Search
        - **|** - 🔎 Search in current column
        - **/** - 🌐 Global search (all columns)
        - **\\\\** - 🔍 Search using current cell value

        ## 🔧 Filter & Select
        - **s** - ✓️ Select/deselect current row
        - **t** - 💡 Toggle row selection (invert all)
        - **"** - 📍 Filter to selected rows only
        - **T** - 🧹 Clear all selections
        - **v** - 🎯 Filter by selected rows or current cell value
        - **V** - 🔧 Filter by Polars expression

        ## ✏️ Edit & Modify
        - **e** - ✍️ Edit current cell
        - **d** - 🗑️ Delete current row
        - **-** - ❌ Delete current column

        ## 🎯 Reorder
        - **Shift+↑↓** - ⬆️⬇️ Move row up/down
        - **Shift+←→** - ⬅️➡️ Move column left/right

        ## 💾 Data Management
        - **f** - 📌 Freeze rows/columns
        - **c** - 📋 Copy cell to clipboard
        - **Ctrl+S** - 💾 Save current tabto file
        - **u** - ↩️ Undo last action
        - **U** - 🔄 Reset to original data

        *Use `?` to see app-level controls*
    """).strip()

    def __init__(
        self,
        df: pl.DataFrame,
        filename: str = "",
        tabname: str = "",
        **kwargs,
    ):
        """Initialize the DataFrameTable with a dataframe and manage all state.

        Args:
            df: The Polars DataFrame to display
            filename: Optional filename of the source CSV
            kwargs: Additional keyword arguments for DataTable
        """
        super().__init__(**kwargs)

        # DataFrame state
        self.dataframe = df  # Original dataframe
        self.df = df  # Internal/working dataframe
        self.filename = filename  # Current filename
        self.tabname = tabname or Path(filename).stem  # Current tab name

        # Pagination & Loading
        self.loaded_rows = 0  # Track how many rows are currently loaded

        # State tracking (all 0-based indexing)
        self.sorted_columns: dict[str, bool] = {}  # col_name -> descending
        self.selected_rows: list[bool] = [False] * len(df)  # Track selected rows
        self.visible_rows: list[bool] = [True] * len(
            df
        )  # Track visible rows (for filtering)

        # Freezing
        self.fixed_rows = 0  # Number of fixed rows
        self.fixed_columns = 0  # Number of fixed columns

        # History stack for undo/redo
        self.histories: deque[History] = deque()

        # Pending filename for save operations
        self._pending_filename = ""

    @property
    def cursor_key(self) -> CellKey:
        """Get the current cursor position as a CellKey."""
        return self.coordinate_to_cell_key(self.cursor_coordinate)

    @property
    def cursor_row_key(self) -> RowKey:
        """Get the current cursor row as a CellKey."""
        return self.cursor_key.row_key

    @property
    def cursor_column_key(self) -> ColumnKey:
        """Get the current cursor column as a ColumnKey."""
        return self.cursor_key.column_key

    @property
    def cursor_row_index(self) -> int:
        """Get the current cursor row index (0-based)."""
        return int(self.cursor_row_key.value) - 1

    def on_mount(self) -> None:
        """Initialize table display when widget is mounted."""
        self._setup_table()

    def _should_highlight(
        self,
        cursor: Coordinate,
        target_cell: Coordinate,
        type_of_cursor: CursorType,
    ) -> bool:
        """Determine if the given cell should be highlighted because of the cursor.

        In "cell" mode, also highlights the row and column headers. In "row" and "column"
        modes, highlights the entire row or column respectively.

        Args:
            cursor: The current position of the cursor.
            target_cell: The cell we're checking for the need to highlight.
            type_of_cursor: The type of cursor that is currently active.

        Returns:
            Whether or not the given cell should be highlighted.
        """
        if type_of_cursor == "cell":
            # Return true if the cursor is over the target cell
            # This includes the case where the cursor is in the same row or column
            return (
                cursor == target_cell
                or (target_cell.row == -1 and target_cell.column == cursor.column)
                or (target_cell.column == -1 and target_cell.row == cursor.row)
            )
        elif type_of_cursor == "row":
            cursor_row, _ = cursor
            cell_row, _ = target_cell
            return cursor_row == cell_row
        elif type_of_cursor == "column":
            _, cursor_column = cursor
            _, cell_column = target_cell
            return cursor_column == cell_column
        else:
            return False

    def watch_cursor_coordinate(
        self, old_coordinate: Coordinate, new_coordinate: Coordinate
    ) -> None:
        """Refresh highlighting when cursor coordinate changes.

        This explicitly refreshes cells that need to change their highlight state
        to fix the delay issue with column label highlighting. Also emits CellSelected
        message when cursor type is "cell" for keyboard navigation only (mouse clicks
        already trigger the parent class's CellSelected message).
        """
        if old_coordinate != new_coordinate:
            # Emit CellSelected message for cell cursor type (keyboard navigation only)
            # Only emit if this is from keyboard navigation (flag is True when from keyboard)
            if self.cursor_type == "cell" and getattr(self, "_from_keyboard", False):
                self._from_keyboard = False  # Reset flag
                try:
                    self._post_selected_message()
                except CellDoesNotExist:
                    # This could happen when after calling clear(), the old coordinate is invalid
                    pass

            # For cell cursor type, refresh old and new row/column headers
            if self.cursor_type == "cell":
                old_row, old_col = old_coordinate
                new_row, new_col = new_coordinate

                # Refresh entire column (not just header) to ensure proper highlighting
                self.refresh_column(old_col)
                self.refresh_column(new_col)

                # Refresh entire row (not just header) to ensure proper highlighting
                self.refresh_row(old_row)
                self.refresh_row(new_row)
            elif self.cursor_type == "row":
                self.refresh_row(old_coordinate.row)
                self.refresh_row(new_coordinate.row)
            elif self.cursor_type == "column":
                self.refresh_column(old_coordinate.column)
                self.refresh_column(new_coordinate.column)

            # Handle scrolling if needed
            if self._require_update_dimensions:
                self.call_after_refresh(self._scroll_cursor_into_view)
            else:
                self._scroll_cursor_into_view()

    def on_key(self, event) -> None:
        """Handle keyboard events for table operations and navigation."""
        if event.key == "g":
            # Jump to top
            self.move_cursor(row=0)
        elif event.key == "G":
            # Load all remaining rows before jumping to end
            self._load_rows()
            self.move_cursor(row=self.row_count - 1)
        elif event.key in ("pagedown", "down"):
            # Let the table handle the navigation first
            self._check_and_load_more()
        elif event.key == "enter":
            # Open row detail modal
            self._view_row_detail()
        elif event.key == "minus":
            # Remove the current column
            self._delete_column()
        elif event.key == "left_square_bracket":  # '['
            # Sort by current column in ascending order
            self._sort_by_column(descending=False)
        elif event.key == "right_square_bracket":  # ']'
            # Sort by current column in descending order
            self._sort_by_column(descending=True)
        elif event.key == "ctrl+s":
            # Save dataframe to CSV
            self._save_to_file()
        elif event.key == "F":  # shift+f
            # Open frequency modal for current column
            self._show_frequency()
        elif event.key == "v":
            # Filter by current cell value
            self._filter_rows()
        elif event.key == "V":  # shift+v
            # Open filter screen for current column
            self._open_filter_screen()
        elif event.key == "e":
            # Open edit modal for current cell
            self._edit_cell()
        elif event.key == "backslash":  # '\' key
            # Search with current cell value and highlight matched rows
            self._search_with_cell_value()
        elif event.key == "vertical_line":  # '|' key
            # Open search modal for current column
            self._search_column()
        elif event.key == "slash":  # '/' key
            # Open search modal for all columns
            self._search_column(all_columns=True)
        elif event.key == "s":
            # Toggle selection for current row
            self._toggle_selected_rows(current_row=True)
        elif event.key == "t":
            # Toggle selected rows highlighting
            self._toggle_selected_rows()
        elif event.key == "quotation_mark":  # '"' key
            # Display selected rows only
            self._filter_selected_rows()
        elif event.key == "d":
            # Delete the current row
            self._delete_row()
        elif event.key == "u":
            # Undo last action
            self._undo()
        elif event.key == "U":
            # Undo all changes and restore original dataframe
            self._setup_table(reset=True)
            self.app.notify("Restored original display", title="Reset")
        elif event.key == "shift+left":  # shift + left arrow
            # Move current column to the left
            self._move_column("left")
        elif event.key == "shift+right":  # shift + right arrow
            # Move current column to the right
            self._move_column("right")
        elif event.key == "shift+up":  # shift + up arrow
            # Move current row up
            self._move_row("up")
        elif event.key == "shift+down":  # shift + down arrow
            # Move current row down
            self._move_row("down")
        elif event.key == "T":  # shift+t
            # Clear all selected rows
            self._clear_selected_rows()
        elif event.key == "C":  # shift+c
            # Cycle through cursor types
            self._cycle_cursor_type()
        elif event.key == "f":
            # Open pin screen to set fixed rows and columns
            self._open_freeze_screen()

    def on_mouse_scroll_down(self, event) -> None:
        """Load more rows when scrolling down with mouse."""
        self._check_and_load_more()

    # Setup & Loading
    def _setup_table(self, reset: bool = False) -> None:
        """Setup the table for display."""
        # Reset to original dataframe
        if reset:
            self.df = self.dataframe
            self.loaded_rows = 0
            self.sorted_columns = {}
            self.selected_rows = [False] * len(self.df)
            self.visible_rows = [True] * len(self.df)
            self.fixed_rows = 0
            self.fixed_columns = 0

        # Lazy load up to INITIAL_BATCH_SIZE visible rows
        stop, visible_count = len(self.df), 0
        for row_idx, visible in enumerate(self.visible_rows):
            if not visible:
                continue
            visible_count += 1
            if visible_count >= INITIAL_BATCH_SIZE:
                stop = row_idx + 1
                break

        self._setup_columns()
        self._load_rows(stop)
        self._highlight_rows()

        # Restore cursor position
        row_idx, col_idx = self.cursor_coordinate
        if row_idx < len(self.rows) and col_idx < len(self.columns):
            self.move_cursor(row=row_idx, column=col_idx)

    def _setup_columns(self) -> None:
        """Clear table and setup columns."""
        self.loaded_rows = 0
        self.clear(columns=True)
        self.show_row_labels = True

        # Add columns with justified headers
        for col, dtype in zip(self.df.columns, self.df.dtypes):
            for idx, c in enumerate(self.sorted_columns, 1):
                if c == col:
                    # Add sort indicator to column header
                    descending = self.sorted_columns[col]
                    sort_indicator = (
                        f" ▼{SUBSCRIPT_DIGITS.get(idx, '')}"
                        if descending
                        else f" ▲{SUBSCRIPT_DIGITS.get(idx, '')}"
                    )
                    header_text = col + sort_indicator
                    self.add_column(
                        Text(header_text, justify=DtypeConfig(dtype).justify), key=col
                    )

                    break
            else:  # No break occurred, so column is not sorted
                self.add_column(Text(col, justify=DtypeConfig(dtype).justify), key=col)

    def _check_and_load_more(self) -> None:
        """Check if we need to load more rows and load them."""
        # If we've loaded everything, no need to check
        if self.loaded_rows >= len(self.df):
            return

        visible_row_count = self.size.height - self.header_height
        bottom_visible_row = self.scroll_y + visible_row_count

        # If visible area is close to the end of loaded rows, load more
        if bottom_visible_row >= self.loaded_rows - 10:
            self._load_rows(self.loaded_rows + BATCH_SIZE)

    def _load_rows(self, stop: int | None = None) -> None:
        """Load a batch of rows into the table.

        Args:
            stop: Stop loading rows when this index is reached. If None, load until the end of the dataframe.
        """
        if stop is None or stop > len(self.df):
            stop = len(self.df)

        if stop <= self.loaded_rows:
            return

        start = self.loaded_rows
        df_slice = self.df.slice(start, stop - start)

        for row_idx, row in enumerate(df_slice.rows(), start):
            if not self.visible_rows[row_idx]:
                continue  # Skip hidden rows
            vals, dtypes = [], []
            for val, dtype in zip(row, self.df.dtypes):
                vals.append(val)
                dtypes.append(dtype)
            formatted_row = _format_row(vals, dtypes)
            # Always add labels so they can be shown/hidden via CSS
            self.add_row(*formatted_row, key=str(row_idx + 1), label=str(row_idx + 1))

        # Update loaded rows count
        self.loaded_rows = stop

        self.app.notify(
            f"Loaded [$accent]{self.loaded_rows}/{len(self.df)}[/] rows from [on $primary]{self.tabname}[/]",
            title="Load",
        )

    def _highlight_rows(self, clear: bool = False) -> None:
        """Update all rows, highlighting selected ones in red and restoring others to default.

        Args:
            clear: If True, clear all highlights.
        """
        if True not in self.selected_rows:
            return

        if clear:
            self.selected_rows = [False] * len(self.df)

        # Ensure all highlighted rows are loaded
        stop = _rindex(self.selected_rows, True) + 1
        self._load_rows(stop)

        # Update all rows based on selected state
        for row in self.ordered_rows:
            row_idx = int(row.key.value) - 1  # Convert to 0-based index
            is_selected = self.selected_rows[row_idx]

            # Update all cells in this row
            for col_idx, col in enumerate(self.ordered_columns):
                cell_text: Text = self.get_cell(row.key, col.key)
                dtype = self.df.dtypes[col_idx]

                # Get style config based on dtype
                dc = DtypeConfig(dtype)

                # Use red for selected rows, default style for others
                style = "red" if is_selected else dc.style
                cell_text.style = style

                # Update the cell in the table
                self.update_cell(row.key, col.key, cell_text)

    # History & Undo
    def _add_history(self, description: str) -> None:
        """Add the current state to the history stack.

        Args:
            description: Description of the action for this history entry.
        """
        history = History(
            description=description,
            df=self.df,
            filename=self.filename,
            loaded_rows=self.loaded_rows,
            sorted_columns=self.sorted_columns.copy(),
            selected_rows=self.selected_rows.copy(),
            visible_rows=self.visible_rows.copy(),
            fixed_rows=self.fixed_rows,
            fixed_columns=self.fixed_columns,
            cursor_coordinate=self.cursor_coordinate,
        )
        self.histories.append(history)

    def _undo(self) -> None:
        """Undo the last action."""
        if not self.histories:
            self.app.notify("No actions to undo", title="Undo", severity="warning")
            return

        history = self.histories.pop()

        # Restore state
        self.df = history.df
        self.filename = history.filename
        self.loaded_rows = history.loaded_rows
        self.sorted_columns = history.sorted_columns.copy()
        self.selected_rows = history.selected_rows.copy()
        self.visible_rows = history.visible_rows.copy()
        self.fixed_rows = history.fixed_rows
        self.fixed_columns = history.fixed_columns
        self.cursor_coordinate = history.cursor_coordinate

        # Recreate the table for display
        self._setup_table()

        self.app.notify(f"Reverted: {history.description}", title="Undo")

    # View
    def _view_row_detail(self) -> None:
        """Open a modal screen to view the selected row's details."""
        row_idx = self.cursor_row
        if row_idx >= len(self.df):
            return

        # Push the modal screen
        self.app.push_screen(RowDetailScreen(row_idx, self))

    def _show_frequency(self) -> None:
        """Show frequency distribution for the current column."""
        col_idx = self.cursor_column
        if col_idx >= len(self.df.columns):
            return

        # Push the frequency modal screen
        self.app.push_screen(FrequencyScreen(col_idx, self))

    def _open_freeze_screen(self) -> None:
        """Open the freeze screen to set fixed rows and columns."""
        self.app.push_screen(FreezeScreen(), callback=self._do_freeze)

    def _do_freeze(self, result: tuple[int, int] | None) -> None:
        """Handle result from FreezeScreen.

        Args:
            result: Tuple of (fixed_rows, fixed_columns) or None if cancelled.
        """
        if result is None:
            return

        fixed_rows, fixed_columns = result

        # Add to history
        self._add_history(
            f"Pinned [on $primary]{fixed_rows}[/] rows and [on $primary]{fixed_columns}[/] columns"
        )

        # Apply the pin settings to the table
        if fixed_rows > 0:
            self.fixed_rows = fixed_rows
        if fixed_columns > 0:
            self.fixed_columns = fixed_columns

        self.app.notify(
            f"Pinned [on $primary]{fixed_rows}[/] rows and [on $primary]{fixed_columns}[/] columns",
            title="Pin",
        )

    # Delete & Move
    def _delete_column(self) -> None:
        """Remove the currently selected column from the table."""
        col_idx = self.cursor_column
        if col_idx >= len(self.df.columns):
            return

        # Get the column name to remove
        col_to_remove = self.df.columns[col_idx]

        # Add to history
        self._add_history(f"Removed column [on $primary]{col_to_remove}[/]")

        # Remove the column from the table display using the column name as key
        self.remove_column(col_to_remove)

        # Move cursor left if we deleted the last column
        if col_idx >= len(self.columns):
            self.move_cursor(column=len(self.columns) - 1)

        # Remove from sorted columns if present
        if col_to_remove in self.sorted_columns:
            del self.sorted_columns[col_to_remove]

        # Remove from dataframe
        self.df = self.df.drop(col_to_remove)

        self.app.notify(
            f"Removed column [on $primary]{col_to_remove}[/] from display",
            title="Column",
        )

    def _delete_row(self) -> None:
        """Delete rows from the table and dataframe.

        Supports deleting multiple selected rows. If no rows are selected, deletes the row at the cursor.
        """
        old_count = len(self.df)
        filter_expr = [True] * len(self.df)

        # Delete all selected rows
        if selected_count := self.selected_rows.count(True):
            history_desc = f"Deleted {selected_count} selected row(s)"

            for i, is_selected in enumerate(self.selected_rows):
                if is_selected:
                    filter_expr[i] = False
        # Delete the row at the cursor
        else:
            row_key = self.cursor_row_key
            i = int(row_key.value) - 1  # Convert to 0-based index

            filter_expr[i] = False
            history_desc = f"Deleted row [on $primary]{row_key.value}[/]"

        # Add to history
        self._add_history(history_desc)

        # Apply the filter to remove rows
        df = self.df.with_row_index("__rid__").filter(filter_expr)
        self.df = df.drop("__rid__")

        # Update selected and visible rows tracking
        old_row_indices = set(df["__rid__"].to_list())
        self.selected_rows = [
            selected
            for i, selected in enumerate(self.selected_rows)
            if i in old_row_indices
        ]
        self.visible_rows = [
            visible
            for i, visible in enumerate(self.visible_rows)
            if i in old_row_indices
        ]

        # Recreate the table display
        self._setup_table()

        deleted_count = old_count - len(self.df)
        self.app.notify(f"Deleted {deleted_count} row(s)", title="Delete")

    def _move_column(self, direction: str) -> None:
        """Move the current column left or right.

        Args:
            direction: "left" to move left, "right" to move right.
        """
        row_idx, col_idx = self.cursor_coordinate
        col_key = self.cursor_column_key

        # Validate move is possible
        if direction == "left":
            if col_idx <= 0:
                self.app.notify(
                    "Cannot move column left", title="Move", severity="warning"
                )
                return
            swap_idx = col_idx - 1
        elif direction == "right":
            if col_idx >= len(self.columns) - 1:
                self.app.notify(
                    "Cannot move column right", title="Move", severity="warning"
                )
                return
            swap_idx = col_idx + 1

        # Get column names to swap
        col_name = self.df.columns[col_idx]
        swap_name = self.df.columns[swap_idx]

        # Add to history
        self._add_history(
            f"Moved column [on $primary]{col_name}[/] {direction} (swapped with [on $primary]{swap_name}[/])"
        )

        # Swap columns in the table's internal column locations
        self.check_idle()
        swap_key = self.df.columns[swap_idx]  # str as column key

        (
            self._column_locations[col_key],
            self._column_locations[swap_key],
        ) = (
            self._column_locations.get(swap_key),
            self._column_locations.get(col_key),
        )

        self._update_count += 1
        self.refresh()

        # Restore cursor position on the moved column
        self.move_cursor(row=row_idx, column=swap_idx)

        # Update the dataframe column order
        cols = list(self.df.columns)
        cols[col_idx], cols[swap_idx] = cols[swap_idx], cols[col_idx]
        self.df = self.df.select(cols)

        self.app.notify(
            f"Moved column [on $primary]{col_name}[/] {direction}",
            title="Move",
        )

    def _move_row(self, direction: str) -> None:
        """Move the current row up or down.

        Args:
            direction: "up" to move up, "down" to move down.
        """
        row_idx, col_idx = self.cursor_coordinate

        # Validate move is possible
        if direction == "up":
            if row_idx <= 0:
                self.app.notify("Cannot move row up", title="Move", severity="warning")
                return
            swap_idx = row_idx - 1
        elif direction == "down":
            if row_idx >= len(self.rows) - 1:
                self.app.notify(
                    "Cannot move row down", title="Move", severity="warning"
                )
                return
            swap_idx = row_idx + 1
        else:
            self.app.notify(
                f"Invalid direction: {direction}", title="Move", severity="error"
            )
            return

        row_key = self.coordinate_to_cell_key((row_idx, 0)).row_key
        swap_key = self.coordinate_to_cell_key((swap_idx, 0)).row_key

        # Add to history
        self._add_history(
            f"Moved row [on $primary]{row_key.value}[/] {direction} (swapped with row [on $primary]{swap_key.value}[/])"
        )

        # Swap rows in the table's internal row locations
        self.check_idle()

        (
            self._row_locations[row_key],
            self._row_locations[swap_key],
        ) = (
            self._row_locations.get(swap_key),
            self._row_locations.get(row_key),
        )

        self._update_count += 1
        self.refresh()

        # Restore cursor position on the moved row
        self.move_cursor(row=swap_idx, column=col_idx)

        # Swap rows in the dataframe
        rid = int(row_key.value) - 1  # 0-based
        swap_rid = int(swap_key.value) - 1  # 0-based
        first, second = sorted([rid, swap_rid])

        self.df = pl.concat(
            [
                self.df.slice(0, first),
                self.df.slice(second, 1),
                self.df.slice(first + 1, second - first - 1),
                self.df.slice(first, 1),
                self.df.slice(second + 1),
            ]
        )

        self.app.notify(
            f"Moved row [on $primary]{row_key.value}[/] {direction}", title="Move"
        )

    # Sort
    def _sort_by_column(self, descending: bool = False) -> None:
        """Sort by the currently selected column.

        Supports multi-column sorting:
        - First press on a column: sort by that column only
        - Subsequent presses on other columns: add to sort order

        Args:
            descending: If True, sort in descending order. If False, ascending order.
        """
        col_idx = self.cursor_column
        if col_idx >= len(self.df.columns):
            return

        col_to_sort = self.df.columns[col_idx]

        # Check if this column is already in the sort keys
        old_desc = self.sorted_columns.get(col_to_sort)
        if old_desc == descending:
            # Same direction - remove this column from sort
            self.app.notify(
                f"Already sorted by [on $primary]{col_to_sort}[/] ({'desc' if descending else 'asc'})",
                title="Sort",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(f"Sorted on column [on $primary]{col_to_sort}[/]")
        if old_desc is None:
            # Add new column to sort
            self.sorted_columns[col_to_sort] = descending
        else:
            # Toggle direction and move to end of sort order
            del self.sorted_columns[col_to_sort]
            self.sorted_columns[col_to_sort] = descending

        # Apply multi-column sort
        sort_cols = list(self.sorted_columns.keys())
        descending_flags = list(self.sorted_columns.values())
        df_sorted = self.df.with_row_index("__rid__").sort(
            sort_cols, descending=descending_flags, nulls_last=True
        )

        # Updated selected_rows and visible_rows to match new order
        old_row_indices = df_sorted["__rid__"].to_list()
        self.selected_rows = [self.selected_rows[i] for i in old_row_indices]
        self.visible_rows = [self.visible_rows[i] for i in old_row_indices]

        # Update the dataframe
        self.df = df_sorted.drop("__rid__")

        # Recreate the table for display
        self._setup_table()

        # Restore cursor position on the sorted column
        self.move_cursor(column=col_idx, row=0)

    # Edit
    def _edit_cell(self) -> None:
        """Open modal to edit the selected cell."""
        row_key = self.cursor_row_key
        row_idx = int(row_key.value) - 1  # Convert to 0-based
        col_idx = self.cursor_column

        if row_idx >= len(self.df) or col_idx >= len(self.df.columns):
            return
        col_name = self.df.columns[col_idx]

        # Save current state to history
        self._add_history(f"Edited cell [on $primary]({row_idx + 1}, {col_name})[/]")

        # Push the edit modal screen
        self.app.push_screen(
            EditCellScreen(row_key, col_idx, self.df),
            callback=self._do_edit_cell,
        )

    def _do_edit_cell(self, result) -> None:
        """Handle result from EditCellScreen."""
        if result is None:
            return

        row_key, col_idx, new_value = result
        row_idx = int(row_key.value) - 1  # Convert to 0-based
        col_name = self.df.columns[col_idx]

        # Update the cell in the dataframe
        try:
            self.df = self.df.with_columns(
                pl.when(pl.arange(0, len(self.df)) == row_idx)
                .then(pl.lit(new_value))
                .otherwise(pl.col(col_name))
                .alias(col_name)
            )

            # Update the display
            cell_value = self.df.item(row_idx, col_idx)
            if cell_value is None:
                cell_value = "-"
            dtype = self.df.dtypes[col_idx]
            dc = DtypeConfig(dtype)
            formatted_value = Text(str(cell_value), style=dc.style, justify=dc.justify)

            row_key = str(row_idx + 1)
            col_key = str(col_name)
            self.update_cell(row_key, col_key, formatted_value)

            self.app.notify(
                f"Cell updated to [on $primary]{cell_value}[/]", title="Edit"
            )
        except Exception as e:
            self.app.notify(
                f"Failed to update cell: {str(e)}", title="Edit", severity="error"
            )
            raise e

    def _copy_cell(self) -> None:
        """Copy the current cell to clipboard."""
        import subprocess

        row_idx = self.cursor_row
        col_idx = self.cursor_column

        try:
            cell_str = str(self.df.item(row_idx, col_idx))
            subprocess.run(
                [
                    "pbcopy" if sys.platform == "darwin" else "xclip",
                    "-selection",
                    "clipboard",
                ],
                input=cell_str,
                text=True,
            )
            self.app.notify(f"Copied: {cell_str[:50]}", title="Clipboard")
        except (FileNotFoundError, IndexError):
            self.app.notify("Error copying cell", title="Clipboard", severity="error")

    def _search_column(self, all_columns: bool = False) -> None:
        """Open modal to search in the selected column."""
        row_idx, col_idx = self.cursor_coordinate
        if col_idx >= len(self.df.columns):
            self.app.notify("Invalid column selected", title="Search", severity="error")
            return

        col_name = None if all_columns else self.df.columns[col_idx]
        col_dtype = self.df.dtypes[col_idx]

        # Get current cell value as default search term
        term = self.df.item(row_idx, col_idx)
        term = "NULL" if term is None else str(term)

        # Push the search modal screen
        self.app.push_screen(
            SearchScreen(term, col_dtype, col_name),
            callback=self._do_search_column,
        )

    def _do_search_column(self, result) -> None:
        """Handle result from SearchScreen."""
        if result is None:
            return

        term, col_dtype, col_name = result
        if col_name:
            # Perform search in the specified column
            self._search_single_column(term, col_dtype, col_name)
        else:
            # Perform search in all columns
            self._search_all_columns(term)

    def _search_single_column(
        self, term: str, col_dtype: pl.DataType, col_name: str
    ) -> None:
        """Search for a term in a single column and update selected rows.

        Args:
            term: The search term to find
            col_dtype: The data type of the column
            col_name: The name of the column to search in
        """
        df_rid = self.df.with_row_index("__rid__")
        if False in self.visible_rows:
            df_rid = df_rid.filter(self.visible_rows)

        # Perform type-aware search based on column dtype
        if term.lower() == "null":
            masks = df_rid[col_name].is_null()
        elif col_dtype == pl.String:
            masks = df_rid[col_name].str.contains(term)
        elif col_dtype == pl.Boolean:
            masks = df_rid[col_name] == BOOLS[term.lower()]
        elif col_dtype in (pl.Int32, pl.Int64):
            masks = df_rid[col_name] == int(term)
        elif col_dtype in (pl.Float32, pl.Float64):
            masks = df_rid[col_name] == float(term)
        else:
            self.app.notify(
                f"Search not yet supported for column type: [on $primary]{col_dtype}[/]",
                title="Search",
                severity="warning",
            )
            return

        # Apply filter to get matched row indices
        matches = set(df_rid.filter(masks)["__rid__"].to_list())

        match_count = len(matches)
        if match_count == 0:
            self.app.notify(
                f"No matches found for: [on $primary]{term}[/]",
                title="Search",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(
            f"Searched and highlighted [on $primary]{term}[/] in column [on $primary]{col_name}[/]"
        )

        # Update selected rows to include new matches
        for m in matches:
            self.selected_rows[m] = True

        # Highlight selected rows
        self._highlight_rows()

        self.app.notify(
            f"Found [on $primary]{match_count}[/] matches for [on $primary]{term}[/]",
            title="Search",
        )

    def _search_all_columns(self, term: str) -> None:
        """Search for a term across all columns and highlight matching cells.

        Args:
            term: The search term to find
        """
        df_rid = self.df.with_row_index("__rid__")
        if False in self.visible_rows:
            df_rid = df_rid.filter(self.visible_rows)

        matches: dict[int, set[int]] = {}
        match_count = 0
        if term.lower() == "null":
            # Search for NULL values across all columns
            for col_idx, col in enumerate(df_rid.columns[1:]):
                masks = df_rid[col].is_null()
                matched_rids = set(df_rid.filter(masks)["__rid__"].to_list())
                for rid in matched_rids:
                    if rid not in matches:
                        matches[rid] = set()
                    matches[rid].add(col_idx)
                    match_count += 1
        else:
            # Search for the term in all columns
            for col_idx, col in enumerate(df_rid.columns[1:]):
                col_series = df_rid[col].cast(pl.String)
                masks = col_series.str.contains(term)
                matched_rids = set(df_rid.filter(masks)["__rid__"].to_list())
                for rid in matched_rids:
                    if rid not in matches:
                        matches[rid] = set()
                    matches[rid].add(col_idx)
                    match_count += 1

        if match_count == 0:
            self.app.notify(
                f"No matches found for: [on $primary]{term}[/] in any column",
                title="Global Search",
                severity="warning",
            )
            return

        # Ensure all matching rows are loaded
        self._load_rows(max(matches.keys()) + 1)

        # Add to history
        self._add_history(
            f"Searched and highlighted [on $primary]{term}[/] across all columns"
        )

        # Highlight matching cells directly
        for row in self.ordered_rows:
            row_idx = int(row.key.value) - 1  # Convert to 0-based index
            if row_idx not in matches:
                continue

            for col_idx in matches[row_idx]:
                row_key = row.key
                col_key = self.df.columns[col_idx]

                cell_text: Text = self.get_cell(row_key, col_key)
                cell_text.style = "red"

                # Update the cell in the table
                self.update_cell(row_key, col_key, cell_text)

        self.app.notify(
            f"Found [on $success]{match_count}[/] matches for [on $primary]{term}[/] across all columns",
            title="Global Search",
        )

    def _search_with_cell_value(self) -> None:
        """Search in the current column using the value of the currently selected cell."""
        row_key = self.cursor_row_key
        row_idx = int(row_key.value) - 1  # Convert to 0-based index
        col_idx = self.cursor_column

        # Get the value of the currently selected cell
        term = self.df.item(row_idx, col_idx)
        term = "NULL" if term is None else str(term)

        col_dtype = self.df.dtypes[col_idx]
        col_name = self.df.columns[col_idx]
        self._do_search_column((term, col_dtype, col_name))

    def _toggle_selected_rows(self, current_row=False) -> None:
        """Toggle selected rows highlighting on/off."""
        # Save current state to history
        self._add_history("Toggled row selection")

        # Select current row if no rows are currently selected
        if current_row:
            cursor_row_idx = int(self.cursor_row_key.value) - 1
            self.selected_rows[cursor_row_idx] = not self.selected_rows[cursor_row_idx]
        else:
            # Invert all selected rows
            self.selected_rows = [not match for match in self.selected_rows]

        # Check if we're highlighting or un-highlighting
        if new_selected_count := self.selected_rows.count(True):
            self.app.notify(
                f"Toggled selection - now showing [on $primary]{new_selected_count}[/] rows",
                title="Toggle",
            )

        # Refresh the highlighting (also restores default styles for unselected rows)
        self._highlight_rows()

    def _clear_selected_rows(self) -> None:
        """Clear all selected rows without removing them from the dataframe."""
        # Check if any rows are currently selected
        selected_count = self.selected_rows.count(True)
        if selected_count == 0:
            self.app.notify(
                "No rows selected to clear", title="Clear", severity="warning"
            )
            return

        # Save current state to history
        self._add_history("Cleared all selected rows")

        # Clear all selections and refresh highlighting
        self._highlight_rows(clear=True)

        self.app.notify(
            f"Cleared [on $primary]{selected_count}[/] selected rows", title="Clear"
        )

    def _filter_selected_rows(self) -> None:
        """Display only the selected rows."""
        selected_count = self.selected_rows.count(True)
        if selected_count == 0:
            self.app.notify(
                "No rows selected to filter", title="Filter", severity="warning"
            )
            return

        # Save current state to history
        self._add_history("Filtered to selected rows")

        # Update dataframe to only include selected rows
        self.df = self.df.filter(self.selected_rows)
        self.selected_rows = [True] * len(self.df)

        # Recreate the table for display
        self._setup_table()

        self.app.notify(
            f"Removed unselected rows. Now showing [on $primary]{selected_count}[/] rows",
            title="Filter",
        )

    def _open_filter_screen(self) -> None:
        """Open the filter screen to enter a filter expression."""
        row_key = self.cursor_row_key
        row_idx = int(row_key.value) - 1  # Convert to 0-based index
        col_idx = self.cursor_column

        cell_value = self.df.item(row_idx, col_idx)
        if self.df.dtypes[col_idx] == pl.String and cell_value is not None:
            cell_value = repr(cell_value)

        self.app.push_screen(
            FilterScreen(
                self.df, current_col_idx=col_idx, current_cell_value=cell_value
            ),
            callback=self._do_filter,
        )

    def _do_filter(self, result) -> None:
        """Handle result from FilterScreen.

        Args:
            expression: The filter expression or None if cancelled.
        """
        if result is None:
            return
        expr, expr_str = result

        # Add a row index column to track original row indices
        df_with_rid = self.df.with_row_index("__rid__")

        # Apply existing visibility filter first
        if False in self.visible_rows:
            df_with_rid = df_with_rid.filter(self.visible_rows)

        # Apply the filter expression
        df_filtered = df_with_rid.filter(expr)

        matched_count = len(df_filtered)
        if not matched_count:
            self.app.notify(
                f"No rows match the expression: [on $primary]{expr_str}[/]",
                title="Filter",
                severity="warning",
            )
            return

        # Add to history
        self._add_history(f"Filtered by expression [on $primary]{expr_str}[/]")

        # Mark unfiltered rows as invisible and unselected
        filtered_row_indices = set(df_filtered["__rid__"].to_list())
        if filtered_row_indices:
            for rid in range(len(self.visible_rows)):
                if rid not in filtered_row_indices:
                    self.visible_rows[rid] = False
                    self.selected_rows[rid] = False

        # Recreate the table for display
        self._setup_table()

        self.app.notify(
            f"Filtered to [on $primary]{matched_count}[/] matching rows",
            title="Filter",
        )

    def _filter_rows(self) -> None:
        """Filter rows.

        If there are selected rows, filter to those rows.
        Otherwise, filter based on the value of the currently selected cell.
        """

        if True in self.selected_rows:
            expr = self.selected_rows
            expr_str = "selected rows"
        else:
            row_key = self.cursor_row_key
            row_idx = int(row_key.value) - 1  # Convert to 0-based index
            col_idx = self.cursor_column

            cell_value = self.df.item(row_idx, col_idx)

            if cell_value is None:
                expr = pl.col(self.df.columns[col_idx]).is_null()
                expr_str = "NULL"
            else:
                expr = pl.col(self.df.columns[col_idx]) == cell_value
                expr_str = f"$_ == {repr(cell_value)}"

        self._do_filter((expr, expr_str))

    def _cycle_cursor_type(self) -> None:
        """Cycle through cursor types: cell -> row -> column -> cell."""
        next_type = _next(CURSOR_TYPES, self.cursor_type)
        self.cursor_type = next_type

        self.app.notify(
            f"Changed cursor type to [on $primary]{next_type}[/]", title="Cursor"
        )

    def _toggle_row_labels(self) -> None:
        """Toggle row labels visibility."""
        self.show_row_labels = not self.show_row_labels
        status = "shown" if self.show_row_labels else "hidden"
        self.app.notify(f"Row labels {status}", title="Labels")

    def _save_to_file(self) -> None:
        """Open save file dialog."""
        self.app.push_screen(
            SaveFileScreen(self.filename), callback=self._on_save_file_screen
        )

    def _on_save_file_screen(
        self, filename: str | None, all_tabs: bool = False
    ) -> None:
        """Handle result from SaveFileScreen."""
        if filename is None:
            return
        filepath = Path(filename)
        ext = filepath.suffix.lower()

        # Whether to save all tabs (for Excel files)
        self._all_tabs = all_tabs

        # Check if file exists
        if filepath.exists():
            self._pending_filename = filename
            self.app.push_screen(
                ConfirmScreen("File already exists. Overwrite?"),
                callback=self._on_overwrite_screen,
            )
        elif ext in (".xlsx", ".xls"):
            self._do_save_excel(filename)
        else:
            self._do_save(filename)

    def _on_overwrite_screen(self, should_overwrite: bool) -> None:
        """Handle result from ConfirmScreen."""
        if should_overwrite:
            self._do_save(self._pending_filename)
        else:
            # Go back to SaveFileScreen to allow user to enter a different name
            self.app.push_screen(
                SaveFileScreen(self._pending_filename),
                callback=self._on_save_file_screen,
            )

    def _do_save(self, filename: str) -> None:
        """Actually save the dataframe to a file."""
        filepath = Path(filename)
        ext = filepath.suffix.lower()

        try:
            if ext in (".xlsx", ".xls"):
                self._do_save_excel(filename)
            elif ext in (".tsv", ".tab"):
                self.df.write_csv(filename, separator="\t")
            elif ext == ".json":
                self.df.write_json(filename)
            elif ext == ".parquet":
                self.df.write_parquet(filename)
            else:
                self.df.write_csv(filename)

            self.dataframe = self.df  # Update original dataframe
            self.filename = filename  # Update current filename
            if not self._all_tabs:
                self.app.notify(
                    f"Saved [$accent]{len(self.df)}[/] rows to [on $primary]{filename}[/]",
                    title="Save",
                )
        except Exception as e:
            self.app.notify(f"Failed to save: {str(e)}", title="Save", severity="error")
            raise e

    def _do_save_excel(self, filename: str) -> None:
        """Save to an Excel file."""
        import xlsxwriter

        if not self._all_tabs or len(self.app.tabs) == 1:
            # Single tab - save directly
            self.df.write_excel(filename)
        else:
            # Multiple tabs - use xlsxwriter to create multiple sheets
            with xlsxwriter.Workbook(filename) as wb:
                for table in self.app.tabs.values():
                    table.df.write_excel(wb, worksheet=table.tabname[:31])

        # From ConfirmScreen callback, so notify accordingly
        if self._all_tabs is True:
            self.app.notify(
                f"Saved all tabs to [on $primary]{filename}[/]",
                title="Save",
            )
        else:
            self.app.notify(
                f"Saved current tab with [$accent]{len(self.df)}[/] rows to [on $primary]{filename}[/]",
                title="Save",
            )
