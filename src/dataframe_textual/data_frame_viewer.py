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

from .common import _next
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

    def __init__(self, *filenames):
        super().__init__()
        self.sources = _load_dataframe(filenames)
        self.tabs: dict[TabPane, DataFrameTable] = {}
        self.help_panel = None

    def compose(self) -> ComposeResult:
        """Create tabbed interface for multiple files or direct table for single file."""
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
        """Set up the app when it starts."""
        if len(self.tabs) == 1:
            self.query_one(ContentTabs).display = False
            self._get_active_table().focus()

    def on_key(self, event):
        if event.key == "k":
            self.theme = _next(list(BUILTIN_THEMES.keys()), self.theme)
            self.notify(f"Switched to theme: [$success]{self.theme}[/]", title="Theme")

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab changes (only for multiple tabs)."""
        # Only process if we have multiple files
        if len(self.tabs) <= 1:
            return

        # Apply background color to active tab
        event.tab.add_class("active")
        for tab in self.tabbed.query(ContentTab):
            if tab != event.tab:
                tab.remove_class("active")

        try:
            # Focus the table in the newly activated tab
            if table := self._get_active_table():
                table.focus()
        except NoMatches:
            pass

    def action_toggle_help_panel(self) -> None:
        """Toggle the HelpPanel on/off."""
        if self.help_panel:
            self.help_panel.display = not self.help_panel.display
        else:
            self.help_panel = DataFrameHelpPanel()
            self.mount(self.help_panel)

    def action_add_tab(self) -> None:
        """Open file dialog to load file to new tab."""
        self.push_screen(OpenFileScreen(), self._handle_file_open)

    def action_save_all_tabs(self) -> None:
        """Save all tabs to a Excel file."""
        callback = partial(self._get_active_table()._do_save_file, all_tabs=True)
        self.push_screen(
            SaveFileScreen("all-tabs.xlsx", title="Save All Tabs"),
            callback=callback,
        )

    def action_close_tab(self) -> None:
        """Close current tab (only for multiple files)."""
        if len(self.tabs) <= 1:
            self.app.exit()
            return
        self._close_tab()

    def action_next_tab(self, offset: int = 1) -> str:
        """Switch to next tab (only for multiple files)."""
        if len(self.tabs) <= 1:
            return
        try:
            tabs: list[TabPane] = list(self.tabs.keys())
            next_tab = _next(tabs, self.tabbed.active_pane, offset)
            self.tabbed.active = next_tab.id
        except (NoMatches, ValueError):
            pass

    def action_toggle_tab_bar(self) -> None:
        """Toggle tab bar visibility."""
        tabs = self.query_one(ContentTabs)
        tabs.display = not tabs.display
        status = "shown" if tabs.display else "hidden"
        self.notify(f"Tab bar [$success]{status}[/]", title="Toggle")

    def _get_active_table(self) -> DataFrameTable | None:
        """Get the currently active table."""
        try:
            tabbed: TabbedContent = self.query_one(TabbedContent)
            if active_pane := tabbed.active_pane:
                return active_pane.query_one(DataFrameTable)
        except (NoMatches, AttributeError):
            pass
        return None

    def _handle_file_open(self, filename: str) -> None:
        """Handle file selection from dialog."""
        if filename and os.path.exists(filename):
            try:
                df = pl.read_csv(filename)
                self._add_tab(df, filename)
                self.notify(f"Opened: [$success]{Path(filename).name}[/]", title="Open")
            except Exception as e:
                self.notify(f"Error: {e}", severity="error")

    def _add_tab(self, df: pl.DataFrame, filename: str) -> None:
        """Add new table tab. If single file, replace table; if multiple, add tab."""
        tabname = Path(filename).stem
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
        """Close current tab."""
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


def _load_file(filename: str, multi_sheets: bool = False) -> list[tuple[pl.DataFrame | pl.LazyFrame, str, str]]:
    """Load a single file and return list of sources.

    For Excel files, when single_file=True, returns one entry per sheet.
    For other files or multiple files, returns one entry per file.

    Args:
        filename: Path to file
        filepath: Path object for file
        ext: File extension (lowercase)
        multi_sheets: If True, only load first sheet for Excel files

    Returns:
        List of tuples of (DataFrame/LazyFrame, filename, tabname)
    """
    sources = []

    filepath = Path(filename)
    ext = filepath.suffix.lower()

    if ext == ".csv":
        lf = pl.scan_csv(filename)
        sources.append((lf, filename, filepath.stem))
    elif ext in (".xlsx", ".xls"):
        if multi_sheets:
            # Read only the first sheet for multiple files
            df = pl.read_excel(filename)
            sources.append((df, filename, filepath.stem))
        else:
            # For single file, expand all sheets
            sheets = pl.read_excel(filename, sheet_id=0)
            for sheet_name, df in sheets.items():
                sources.append((df, filename, sheet_name))
    elif ext in (".tsv", ".tab"):
        lf = pl.scan_csv(filename, separator="\t")
        sources.append((lf, filename, filepath.stem))
    elif ext == ".parquet":
        lf = pl.scan_parquet(filename)
        sources.append((lf, filename, filepath.stem))
    elif ext == ".json":
        df = pl.read_json(filename)
        sources.append((df, filename, filepath.stem))
    elif ext == ".ndjson":
        lf = pl.scan_ndjson(filename)
        sources.append((lf, filename, filepath.stem))
    else:
        # Treat other formats as CSV
        lf = pl.scan_csv(filename)
        sources.append((lf, filename, filepath.stem))

    return sources


def _load_dataframe(filenames: list[str]) -> list[tuple[pl.DataFrame | pl.LazyFrame, str, str]]:
    """Load a DataFrame from a file spec.

    Args:
        filenames: List of filenames to load. If single filename is "-", read from stdin.

    Returns:
        List of tuples of (DataFrame, filename, tabname)
    """
    sources = []

    # Single file
    if len(filenames) == 1:
        filename = filenames[0]

        # Handle stdin
        if filename == "-" or not sys.stdin.isatty():
            from io import StringIO

            # Read CSV from stdin into memory first (stdin is not seekable)
            stdin_data = sys.stdin.read()
            lf = pl.scan_csv(StringIO(stdin_data))

            # Reopen stdin to /dev/tty for proper terminal interaction
            try:
                tty = open("/dev/tty")
                os.dup2(tty.fileno(), sys.stdin.fileno())
            except (OSError, FileNotFoundError):
                pass

            sources.append((lf, "stdin.csv", "stdin"))
        else:
            sources.extend(_load_file(filename, multi_sheets=False))
    # Multiple files
    else:
        for filename in filenames:
            sources.extend(_load_file(filename, multi_sheets=True))

    return sources
