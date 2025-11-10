"""DataFrame Viewer application and utilities."""

import os
import sys
from functools import partial
from pathlib import Path
from textwrap import dedent

import polars as pl
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.theme import BUILTIN_THEMES
from textual.widgets import TabbedContent, TabPane
from textual.widgets.tabbed_content import ContentTab, ContentTabs

from .common import get_next_item
from .data_frame_help_panel import DataFrameHelpPanel
from .data_frame_table import DataFrameTable
from .yes_no_screen import OpenFileScreen, SaveFileScreen


class DataFrameViewer(App):
    """A Textual app to interact with multiple Polars DataFrames via tabbed interface."""

    HELP = dedent("""
        # 📊 DataFrame Viewer - App Controls

        ## 🎯 File & Tab Management
        - **Ctrl+O** - 📁 Add a new tab
        - **Ctrl+Shift+S** - 💾 Save all tabs
        - **Ctrl+W** - ❌ Close current tab
        - **>** or **b** - ▶️ Next tab
        - **<** - ◀️ Previous tab
        - **B** - 👁️ Toggle tab bar visibility
        - **q** - 🚪 Quit application

        ## 🎨 View & Settings
        - **Ctrl+H** - ❓ Toggle this help panel
        - **k** - 🌙 Cycle through themes

        ## ⭐ Features
        - **Multi-file support** - 📂 Open multiple CSV/Excel files as tabs
        - **Excel sheets** - 📊 Excel files auto-expand sheets into tabs
        - **Lazy loading** - ⚡ Large files load on demand
        - **Sticky tabs** - 📌 Tab bar stays visible when scrolling
        - **Rich formatting** - 🎨 Color-coded data types
        - **Search & filter** - 🔍 Find and filter data quickly
        - **Sort & reorder** - ⬆️ Multi-column sort, drag rows/columns
        - **Undo/Redo** - 🔄 Full history of operations
        - **Freeze rows/cols** - 🔒 Pin header rows and columns
    """).strip()

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+h", "toggle_help_panel", "Help"),
        ("B", "toggle_tab_bar", "Toggle Tab Bar"),
        ("ctrl+o", "add_tab", "Add Tab"),
        ("ctrl+shift+s", "save_all_tabs", "Save All Tabs"),
        ("ctrl+w", "close_tab", "Close Tab"),
        ("greater_than_sign,b", "next_tab(1)", "Next Tab"),
        ("less_than_sign", "next_tab(-1)", "Prev Tab"),
    ]

    CSS = """
        TabbedContent {
            height: 100%;  /* Or a specific value, e.g., 20; */
        }
        TabbedContent > ContentTabs {
            dock: bottom;
        }
        TabbedContent > ContentSwitcher {
            overflow: auto;
            height: 1fr;  /* Takes the remaining space below tabs */
        }

        TabbedContent ContentTab.active {
            background: $primary;
            color: $text;
        }
    """

    def __init__(self, *filenames: str, file_format: str | None = None, has_header: bool = True) -> None:
        """Initialize the DataFrame Viewer application.

        Loads dataframes from provided filenames and prepares the tabbed interface.

        Args:
            *filenames: Variable number of file paths to load (CSV, Excel, Parquet, etc).
            file_format: Optional format specifier for input files (e.g., 'csv', 'excel').
            has_header: Whether the input files have a header row. Defaults to True.

        Returns:
            None
        """
        super().__init__()
        self.sources = _load_dataframe(filenames, file_format, has_header=has_header)
        self.tabs: dict[TabPane, DataFrameTable] = {}
        self.help_panel = None

    def compose(self) -> ComposeResult:
        """Compose the application widget structure.

        Creates a tabbed interface with one tab per file/sheet loaded. Each tab
        contains a DataFrameTable widget for displaying and interacting with the data.

        Yields:
            TabPane: One tab per file or sheet for the tabbed interface.
        """
        # Tabbed interface
        self.tabbed = TabbedContent(id="main_tabs")
        with self.tabbed:
            seen_names = set()
            for idx, (df, filename, tabname) in enumerate(self.sources, start=1):
                # Ensure unique tab names
                if tabname in seen_names:
                    tabname = f"{tabname}_{idx}"
                seen_names.add(tabname)

                tab_id = f"tab_{idx}"
                try:
                    table = DataFrameTable(df, filename, name=tabname, id=tab_id, zebra_stripes=True)
                    tab = TabPane(tabname, table, name=tabname, id=tab_id)
                    self.tabs[tab] = table
                    yield tab
                except Exception as e:
                    self.notify(f"Error loading {tabname}: {e}", severity="error")

    def on_mount(self) -> None:
        """Set up the application when it starts.

        Initializes the app by hiding the tab bar for single-file mode and focusing
        the active table widget.

        Returns:
            None
        """
        if len(self.tabs) == 1:
            self.query_one(ContentTabs).display = False
            self._get_active_table().focus()

    def on_key(self, event) -> None:
        """Handle key press events at the application level.

        Currently handles theme cycling with the 'k' key.

        Args:
            event: The key event object containing key information.

        Returns:
            None
        """
        if event.key == "k":
            self.theme = get_next_item(list(BUILTIN_THEMES.keys()), self.theme)
            self.notify(f"Switched to theme: [$success]{self.theme}[/]", title="Theme")

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation events.

        When a tab is activated, focuses the table widget and loads its data if not already loaded.
        Applies active styling to the clicked tab and removes it from others.

        Args:
            event: The tab activated event containing the activated tab pane.

        Returns:
            None
        """
        # Focus the table in the newly activated tab
        if table := self._get_active_table():
            table.focus()
        else:
            return

        if table.loaded_rows == 0:
            table._setup_table()

        # Apply background color to active tab
        event.tab.add_class("active")
        for tab in self.tabbed.query(ContentTab):
            if tab != event.tab:
                tab.remove_class("active")

    def action_toggle_help_panel(self) -> None:
        """Toggle the help panel on or off.

        Shows or hides the context-sensitive help panel. Creates it on first use.

        Returns:
            None
        """
        if self.help_panel:
            self.help_panel.display = not self.help_panel.display
        else:
            self.help_panel = DataFrameHelpPanel()
            self.mount(self.help_panel)

    def action_add_tab(self) -> None:
        """Open file browser to load a file in a new tab.

        Displays the file open dialog for the user to select a file to load
        as a new tab in the interface.

        Returns:
            None
        """
        self.push_screen(OpenFileScreen(), self._do_add_tab)

    def action_save_all_tabs(self) -> None:
        """Save all open tabs to a single Excel file.

        Displays a save dialog to choose filename and location, then saves all
        open tabs as separate sheets in a single Excel workbook.

        Returns:
            None
        """
        callback = partial(self._get_active_table()._do_save_file, all_tabs=True)
        self.push_screen(
            SaveFileScreen("all-tabs.xlsx", title="Save All Tabs"),
            callback=callback,
        )

    def action_close_tab(self) -> None:
        """Close the currently active tab.

        Closes the current tab. If this is the only tab, exits the application instead.

        Returns:
            None
        """
        if len(self.tabs) <= 1:
            self.app.exit()
            return
        self._close_tab()

    def action_next_tab(self, offset: int = 1) -> None:
        """Switch to the next tab or previous tab.

        Cycles through tabs by the specified offset. With offset=1, moves to next tab.
        With offset=-1, moves to previous tab. Wraps around when reaching edges.

        Args:
            offset: Number of tabs to advance (+1 for next, -1 for previous). Defaults to 1.

        Returns:
            None
        """
        if len(self.tabs) <= 1:
            return
        try:
            tabs: list[TabPane] = list(self.tabs.keys())
            next_tab = get_next_item(tabs, self.tabbed.active_pane, offset)
            self.tabbed.active = next_tab.id
        except (NoMatches, ValueError):
            pass

    def action_toggle_tab_bar(self) -> None:
        """Toggle the tab bar visibility.

        Shows or hides the tab bar at the bottom of the window. Useful for maximizing
        screen space in single-tab mode.

        Returns:
            None
        """
        tabs = self.query_one(ContentTabs)
        tabs.display = not tabs.display
        # status = "shown" if tabs.display else "hidden"
        # self.notify(f"Tab bar [$success]{status}[/]", title="Toggle")

    def _get_active_table(self) -> DataFrameTable | None:
        """Get the currently active DataFrameTable widget.

        Retrieves the table from the currently active tab. Returns None if no
        table is found or an error occurs.

        Returns:
            The active DataFrameTable widget, or None if not found.
        """
        try:
            tabbed: TabbedContent = self.query_one(TabbedContent)
            if active_pane := tabbed.active_pane:
                return active_pane.query_one(DataFrameTable)
        except (NoMatches, AttributeError):
            self.notify("No active table found", title="Locate", severity="error")
        return None

    def _do_add_tab(self, filename: str) -> None:
        """Add a tab for the opened file.

        Loads the specified file and creates one or more tabs for it. For Excel files,
        creates one tab per sheet. For other formats, creates a single tab.

        Args:
            filename: Path to the file to load and add as tab(s).

        Returns:
            None
        """
        if filename and os.path.exists(filename):
            try:
                n_tab = 0
                for lf, filename, tabname in _load_file(filename, prefix_sheet=True):
                    self._add_tab(lf.collect(), filename, tabname)
                    n_tab += 1
                self.notify(f"Added [$accent]{n_tab}[/] tab(s) for [$success]{filename}[/]", title="Open")
            except Exception as e:
                self.notify(f"Error: {e}", title="Open", severity="error")
        else:
            self.notify(f"File does not exist: [$warning]{filename}[/]", title="Open", severity="warning")

    def _add_tab(self, df: pl.DataFrame, filename: str, tabname: str) -> None:
        """Add new tab for the given DataFrame.

        Creates and adds a new tab with the provided DataFrame and configuration.
        Ensures unique tab names by appending an index if needed. Shows the tab bar
        if this is no longer the only tab.

        Args:
            df: The Polars DataFrame to display in the new tab.
            filename: The source filename for this data (used in table metadata).
            tabname: The display name for the tab.

        Returns:
            None
        """
        if any(tab.name == tabname for tab in self.tabs):
            tabname = f"{tabname}_{len(self.tabs) + 1}"

        # Find an available tab index
        tab_idx = f"tab_{len(self.tabs) + 1}"
        for idx in range(len(self.tabs)):
            pending_tab_idx = f"tab_{idx + 1}"
            if any(tab.id == pending_tab_idx for tab in self.tabs):
                continue

            tab_idx = pending_tab_idx
            break

        table = DataFrameTable(df, filename, zebra_stripes=True, id=tab_idx, name=tabname)
        tab = TabPane(tabname, table, name=tabname, id=tab_idx)
        self.tabbed.add_pane(tab)
        self.tabs[tab] = table

        if len(self.tabs) > 1:
            self.query_one(ContentTabs).display = True

        # Activate the new tab
        self.tabbed.active = tab.id
        table.focus()

    def _close_tab(self) -> None:
        """Close the currently active tab.

        Removes the active tab from the interface. If only one tab remains and no more
        can be closed, the application exits instead.

        Returns:
            None
        """
        try:
            if len(self.tabs) == 1:
                self.app.exit()
            else:
                if active_pane := self.tabbed.active_pane:
                    self.tabbed.remove_pane(active_pane.id)
                    self.tabs.pop(active_pane)
                    self.notify(f"Closed tab [$success]{active_pane.name}[/]", title="Close")
        except NoMatches:
            pass


def _load_dataframe(
    filenames: list[str], file_format: str | None = None, has_header: bool = True
) -> list[tuple[pl.LazyFrame, str, str]]:
    """Load DataFrames from file specifications.

    Handles loading from multiple files, single files, or stdin. For Excel files,
    loads all sheets as separate entries. For other formats, loads as single file.

    Args:
        filenames: List of filenames to load. If single filename is "-", read from stdin.
        file_format: Optional format specifier for input files (e.g., 'csv', 'excel').
        has_header: Whether the input files have a header row. Defaults to True.

    Returns:
        List of tuples of (LazyFrame, filename, tabname) ready for display.
    """
    sources = []

    prefix_sheet = len(filenames) > 1

    for filename in filenames:
        sources.extend(_load_file(filename, prefix_sheet=prefix_sheet, file_format=file_format, has_header=has_header))
    return sources


def _load_file(
    filename: str,
    first_sheet: bool = False,
    prefix_sheet: bool = False,
    file_format: str | None = None,
    has_header: bool = True,
) -> list[tuple[pl.LazyFrame, str, str]]:
    """Load a single file and return list of sources.

    For Excel files, when `first_sheet` is True, returns only the first sheet. Otherwise, returns one entry per sheet.
    For other files or multiple files, returns one entry per file.

    Args:
        filename: Path to file to load.
        first_sheet: If True, only load first sheet for Excel files. Defaults to False.
        prefix_sheet: If True, prefix filename to sheet name as the tab name for Excel files. Defaults to False.
        file_format: Optional format specifier for input files (e.g., 'csv', 'excel', 'tsv', 'parquet', 'json', 'ndjson').

    Returns:
        List of tuples of (LazyFrame, filename, tabname).
    """
    sources = []

    if filename == "-":
        from io import StringIO

        # Read from stdin into memory first (stdin is not seekable)
        stdin_data = sys.stdin.read()
        lf = pl.scan_csv(StringIO(stdin_data), has_header=has_header, separator="," if file_format == "csv" else "\t")

        # Reopen stdin to /dev/tty for proper terminal interaction
        try:
            tty = open("/dev/tty")
            os.dup2(tty.fileno(), sys.stdin.fileno())
        except (OSError, FileNotFoundError):
            pass

        sources.append((lf, "stdin.tsv" if file_format == "tsv" else "stdin.csv", "stdin"))
        return sources

    filepath = Path(filename)
    ext = filepath.suffix.lower()

    if file_format == "csv" or ext == ".csv":
        lf = pl.scan_csv(filename, has_header=has_header)
        sources.append((lf, filename, filepath.stem))
    elif file_format == "excel" or ext in (".xlsx", ".xls"):
        if first_sheet:
            # Read only the first sheet for multiple files
            lf = pl.read_excel(filename).lazy()
            sources.append((lf, filename, filepath.stem))
        else:
            # For single file, expand all sheets
            sheets = pl.read_excel(filename, sheet_id=0)
            for sheet_name, df in sheets.items():
                tabname = f"{filepath.stem}_{sheet_name}" if prefix_sheet else sheet_name
                sources.append((df.lazy(), filename, tabname))
    elif file_format == "tsv" or ext in (".tsv", ".tab"):
        lf = pl.scan_csv(filename, has_header=has_header, separator="\t")
        sources.append((lf, filename, filepath.stem))
    elif file_format == "parquet" or ext == ".parquet":
        lf = pl.scan_parquet(filename)
        sources.append((lf, filename, filepath.stem))
    elif file_format == "json" or ext == ".json":
        df = pl.read_json(filename)
        sources.append((df, filename, filepath.stem))
    elif file_format == "ndjson" or ext == ".ndjson":
        lf = pl.scan_ndjson(filename)
        sources.append((lf, filename, filepath.stem))
    else:
        # Treat other formats as TSV
        lf = pl.scan_csv(filename, has_header=has_header, separator="\t")
        sources.append((lf, filename, filepath.stem))

    return sources
