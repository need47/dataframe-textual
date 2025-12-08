"""DataFrame Viewer application and utilities."""

import os
from pathlib import Path
from textwrap import dedent

import polars as pl
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.events import Click
from textual.theme import BUILTIN_THEMES
from textual.widgets import TabbedContent, TabPane
from textual.widgets.tabbed_content import ContentTab, ContentTabs

from .common import Source, get_next_item, load_file
from .data_frame_help_panel import DataFrameHelpPanel
from .data_frame_table import DataFrameTable
from .yes_no_screen import ConfirmScreen, OpenFileScreen, RenameTabScreen


class DataFrameViewer(App):
    """A Textual app to interact with multiple Polars DataFrames via tabbed interface."""

    HELP = dedent("""
        # 📊 DataFrame Viewer - App Controls

        ## 🎯 File & Tab Management
        - **>** - ▶️ Next tab
        - **<** - ◀️ Previous tab
        - **b** - 🔄 Cycle through tabs
        - **B** - 👁️ Toggle tab bar visibility
        - **q** - ❌ Close current tab (prompts to save unsaved changes)
        - **Q** - ❌ Close all tabs (prompts to save unsaved changes)
        - **Ctrl+Q** - 🚪 Force to quit app (discards unsaved changes)
        - **Ctrl+T** - 💾 Save current tab to file
        - **w** - 💾 Save current tab to file (overwrite without prompt)
        - **Ctrl+A** - 💾 Save all tabs to file
        - **W** - 💾 Save all tabs to file (overwrite without prompt)
        - **Ctrl+D** - 📋 Duplicate current tab
        - **Ctrl+O** - 📁 Open a file
        - **Double-click** - ✏️ Rename tab

        ## 🎨 View & Settings
        - **F1** - ❓ Toggle this help panel
        - **k** - 🌙 Cycle through themes
        - **Ctrl+P -> Screenshot** - 📸 Capture terminal view as a SVG image

        ## ⭐ Features
        - **Multi-file support** - 📂 Open multiple CSV/Excel files as tabs
        - **Lazy loading** - ⚡ Large files load on demand
        - **Sticky tabs** - 📌 Tab bar stays visible when scrolling
        - **Unsaved changes** - 🔴 Tabs with unsaved changes have a bright bottom border
        - **Rich formatting** - 🎨 Color-coded data types
        - **Search & filter** - 🔍 Find and filter data quickly
        - **Sort & reorder** - ⬆️ Multi-column sort, reorder rows/columns
        - **Undo/Redo/Reset** - 🔄 Full history of operations
        - **Freeze rows/cols** - 🔒 Pin header rows and columns
    """).strip()

    BINDINGS = [
        ("q", "close_tab", "Close current tab"),
        ("Q", "close_all_tabs", "Close all tabs and quit app"),
        ("B", "toggle_tab_bar", "Toggle Tab Bar"),
        ("f1", "toggle_help_panel", "Help"),
        ("ctrl+o", "open_file", "Open File"),
        ("ctrl+t", "save_current_tab", "Save Current Tab"),
        ("ctrl+a", "save_all_tabs", "Save All Tabs"),
        ("w", "save_current_tab_overwrite", "Save Current Tab (overwrite)"),
        ("W", "save_all_tabs_overwrite", "Save All Tabs (overwrite)"),
        ("ctrl+d", "duplicate_tab", "Duplicate Tab"),
        ("greater_than_sign,b", "next_tab(1)", "Next Tab"),  # '>' and 'b'
        ("less_than_sign", "next_tab(-1)", "Prev Tab"),  # '<'
    ]

    CSS = """
        TabbedContent > ContentTabs {
            dock: bottom;
        }
        TabbedContent > ContentSwitcher {
            overflow: auto;
            height: 1fr;
        }
        ContentTab.-active {
            background: $block-cursor-background; /* Same as underline */
        }
        ContentTab.dirty {
            background: $warning-darken-3;
        }
    """

    def __init__(self, *sources: Source) -> None:
        """Initialize the DataFrame Viewer application.

        Loads data from provided sources and prepares the tabbed interface.

        Args:
            sources: sources to load dataframes from, each as a tuple of
                     (DataFrame, filename, tabname).
        """
        super().__init__()
        self.sources = sources
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
            for idx, source in enumerate(self.sources, start=1):
                df, filename, tabname = source.frame, source.filename, source.tabname
                tab_id = f"tab-{idx}"

                if not tabname:
                    tabname = Path(filename).stem or tab_id

                # Ensure unique tab names
                counter = 1
                while tabname in seen_names:
                    tabname = f"{tabname}_{counter}"
                    counter += 1
                seen_names.add(tabname)

                try:
                    table = DataFrameTable(df, filename, tabname=tabname, id=tab_id, zebra_stripes=True)
                    tab = TabPane(tabname, table, id=tab_id)
                    self.tabs[tab] = table
                    yield tab
                except Exception as e:
                    self.notify(
                        f"Error loading [$error]{filename}[/]: Try [$accent]-I[/] to disable schema inference",
                        severity="error",
                    )
                    self.log(f"Error loading `{filename}`: {str(e)}")

    def on_mount(self) -> None:
        """Set up the application when it starts.

        Initializes the app by hiding the tab bar for single-file mode and focusing
        the active table widget.
        """
        if len(self.tabs) == 1:
            self.query_one(ContentTabs).display = False
            self.get_active_table().focus()

    def on_ready(self) -> None:
        """Called when the app is ready."""
        # self.log(self.tree)
        pass

    def on_key(self, event) -> None:
        """Handle key press events at the application level.

        Currently handles theme cycling with the 'k' key.

        Args:
            event: The key event object containing key information.
        """
        if event.key == "k":
            self.theme = get_next_item(list(BUILTIN_THEMES.keys()), self.theme)
            self.notify(f"Switched to theme: [$success]{self.theme}[/]", title="Theme")

    def on_click(self, event: Click) -> None:
        """Handle mouse click events on tabs.

        Detects double-clicks on tab headers and opens the rename screen.

        Args:
            event: The click event containing position information.
        """
        # Check if this is a double-click (chain > 1) on a tab header
        if event.chain > 1:
            try:
                # Get the widget that was clicked
                content_tab = event.widget

                # Check if it's a ContentTab (tab header)
                if isinstance(content_tab, ContentTab):
                    self.do_rename_tab(content_tab)
            except Exception as e:
                self.log(f"Error handling tab rename click: {str(e)}")
                pass

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation events.

        When a tab is activated, focuses the table widget and loads its data if not already loaded.
        Applies active styling to the clicked tab and removes it from others.

        Args:
            event: The tab activated event containing the activated tab pane.
        """
        # Focus the table in the newly activated tab
        if table := self.get_active_table():
            table.focus()
        else:
            return

        if table.loaded_rows == 0:
            table.setup_table()

    def action_toggle_help_panel(self) -> None:
        """Toggle the help panel on or off.

        Shows or hides the context-sensitive help panel. Creates it on first use.
        """
        if self.help_panel:
            self.help_panel.display = not self.help_panel.display
        else:
            self.help_panel = DataFrameHelpPanel()
            self.mount(self.help_panel)

    def action_open_file(self) -> None:
        """Open file browser to load a file in a new tab.

        Displays the file open dialog for the user to select a file to load
        as a new tab in the interface.
        """
        self.push_screen(OpenFileScreen(), self.do_open_file)

    def action_close_tab(self) -> None:
        """Close the current tab.

        Checks for unsaved changes and prompts the user to save if needed.
        If this is the last tab, exits the app.
        """
        self.do_close_tab()

    def action_close_all_tabs(self) -> None:
        """Close all tabs and exit the app.

        Checks if any tabs have unsaved changes. If yes, opens a confirmation dialog.
        Otherwise, quits immediately.
        """
        self.do_close_all_tabs()

    def action_save_current_tab(self) -> None:
        """Save the currently active tab to file.

        Opens the save dialog for the active tab's DataFrameTable to save its data.
        """
        if table := self.get_active_table():
            table.do_save_to_file(all_tabs=False)

    def action_save_all_tabs(self) -> None:
        """Save all open tabs to their respective files.

        Iterates through all DataFrameTable widgets and opens the save dialog for each.
        """
        if table := self.get_active_table():
            table.do_save_to_file(all_tabs=True)

    def action_save_current_tab_overwrite(self) -> None:
        """Save the currently active tab to file, overwriting if it exists."""
        if table := self.get_active_table():
            filepath = Path(table.filename)
            filename = filepath.with_stem(table.tabname)
            table.save_to_file((filename, False, False))

    def action_save_all_tabs_overwrite(self) -> None:
        """Save all open tabs to their respective files, overwriting if they exist."""
        if table := self.get_active_table():
            filepath = Path(table.filename)
            if filepath.suffix.lower() in [".xlsx", ".xls"]:
                filename = table.filename
            else:
                filename = "all-tabs.xlsx"

            table.save_to_file((filename, True, False))

    def action_duplicate_tab(self) -> None:
        """Duplicate the currently active tab.

        Creates a copy of the current tab with the same data and filename.
        The new tab is named with '_copy' suffix and inserted after the current tab.
        """
        self.do_duplicate_tab()

    def do_duplicate_tab(self) -> None:
        """Duplicate the currently active tab.

        Creates a copy of the current tab with the same data and filename.
        The new tab is named with '_copy' suffix and inserted after the current tab.
        """
        if not (table := self.get_active_table()):
            return

        # Get current tab info
        current_tabname = table.tabname
        new_tabname = f"{current_tabname}_copy"
        new_tabname = self.get_unique_tabname(new_tabname)

        # Create new table with the same dataframe and filename
        new_table = DataFrameTable(
            table.df.clone(),
            table.filename,
            tabname=new_tabname,
            zebra_stripes=True,
            id=f"tab-{len(self.tabs) + 1}",
        )
        new_pane = TabPane(new_tabname, new_table, id=new_table.id)

        # Add the new tab
        active_pane = self.tabbed.active_pane
        self.tabbed.add_pane(new_pane, after=active_pane)
        self.tabs[new_pane] = new_table

        # Show tab bar if needed
        if len(self.tabs) > 1:
            self.query_one(ContentTabs).display = True

        # Activate and focus the new tab
        self.tabbed.active = new_pane.id
        new_table.focus()
        new_table.dirty = True  # Mark as dirty since it's a new unsaved tab

    def action_next_tab(self, offset: int = 1) -> None:
        """Switch to the next tab or previous tab.

        Cycles through tabs by the specified offset. With offset=1, moves to next tab.
        With offset=-1, moves to previous tab. Wraps around when reaching edges.

        Args:
            offset: Number of tabs to advance (+1 for next, -1 for previous). Defaults to 1.
        """
        self.do_next_tab(offset)

    def do_next_tab(self, offset: int = 1) -> None:
        """Switch to the next tab or previous tab.

        Cycles through tabs by the specified offset. With offset=1, moves to next tab.
        With offset=-1, moves to previous tab. Wraps around when reaching edges.

        Args:
            offset: Number of tabs to advance (+1 for next, -1 for previous). Defaults to 1.
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
        """
        tabs = self.query_one(ContentTabs)
        tabs.display = not tabs.display
        # status = "shown" if tabs.display else "hidden"
        # self.notify(f"Tab bar [$success]{status}[/]", title="Toggle")

    def get_active_table(self) -> DataFrameTable | None:
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

    def get_unique_tabname(self, tab_name: str) -> str:
        """Generate a unique tab name based on the given base name.

        If the base name already exists among current tabs, appends an index
        to make it unique.

        Args:
            tab_name: The desired base name for the tab.

        Returns:
            A unique tab name.
        """
        tabname = tab_name
        counter = 1
        while any(table.tabname == tabname for table in self.tabs.values()):
            tabname = f"{tab_name}_{counter}"
            counter += 1

        return tabname

    def do_open_file(self, filename: str) -> None:
        """Open a file.

        Loads the specified file and creates one or more tabs for it. For Excel files,
        creates one tab per sheet. For other formats, creates a single tab.

        Args:
            filename: Path to the file to load and add as tab(s).
        """
        if filename and os.path.exists(filename):
            try:
                n_tab = 0
                for source in load_file(filename, prefix_sheet=True):
                    self.add_tab(source.frame, filename, source.tabname, after=self.tabbed.active_pane)
                    n_tab += 1
                # self.notify(f"Added [$accent]{n_tab}[/] tab(s) for [$success]{filename}[/]", title="Open")
            except Exception as e:
                self.notify(f"Error loading [$error]{filename}[/]: {str(e)}", title="Open", severity="error")
        else:
            self.notify(f"File does not exist: [$warning]{filename}[/]", title="Open", severity="warning")

    def add_tab(
        self,
        df: pl.DataFrame,
        filename: str,
        tabname: str,
        before: TabPane | str | None = None,
        after: TabPane | str | None = None,
    ) -> None:
        """Add new tab for the given DataFrame.

        Creates and adds a new tab with the provided DataFrame and configuration.
        Ensures unique tab names by appending an index if needed. Shows the tab bar
        if this is no longer the only tab.

        Args:
            lf: The Polars DataFrame to display in the new tab.
            filename: The source filename for this data (used in table metadata).
            tabname: The display name for the tab.
        """
        tabname = self.get_unique_tabname(tabname)

        # Find an available tab index
        tab_idx = f"tab-{len(self.tabs) + 1}"
        for idx in range(len(self.tabs)):
            pending_tab_idx = f"tab-{idx + 1}"
            if any(tab.id == pending_tab_idx for tab in self.tabs):
                continue

            tab_idx = pending_tab_idx
            break

        table = DataFrameTable(df, filename, tabname=tabname, zebra_stripes=True, id=tab_idx)
        tab = TabPane(tabname, table, id=tab_idx)
        self.tabbed.add_pane(tab, before=before, after=after)

        # Insert tab at specified position
        tabs = list(self.tabs.keys())

        if before and (idx := tabs.index(before)) != -1:
            self.tabs = {
                **{tab: self.tabs[tab] for tab in tabs[:idx]},
                tab: table,
                **{tab: self.tabs[tab] for tab in tabs[idx:]},
            }
        elif after and (idx := tabs.index(after)) != -1:
            self.tabs = {
                **{tab: self.tabs[tab] for tab in tabs[: idx + 1]},
                tab: table,
                **{tab: self.tabs[tab] for tab in tabs[idx + 1 :]},
            }
        else:
            self.tabs[tab] = table

        if len(self.tabs) > 1:
            self.query_one(ContentTabs).display = True

        # Activate the new tab
        self.tabbed.active = tab.id
        table.focus()

    def do_close_tab(self) -> None:
        """Close the currently active tab.

        Removes the active tab from the interface. If only one tab remains and no more
        can be closed, the application exits instead.
        """
        try:
            if not (active_pane := self.tabbed.active_pane):
                return

            if not (active_table := self.tabs.get(active_pane)):
                return

            def _on_save_confirm(result: bool) -> None:
                """Handle the "save before closing?" confirmation."""
                if result:
                    # User wants to save - close after save dialog opens
                    active_table.do_save_to_file(task_after_save="close_tab")
                elif result is None:
                    # User cancelled - do nothing
                    return
                else:
                    # User wants to discard - close immediately
                    self.close_tab()

            if active_table.dirty:
                self.push_screen(
                    ConfirmScreen(
                        "Close Tab",
                        label="This tab has unsaved changes. Save changes?",
                        yes="Save",
                        maybe="Discard",
                        no="Cancel",
                    ),
                    callback=_on_save_confirm,
                )
            else:
                # No unsaved changes - close immediately
                self.close_tab()
        except Exception:
            pass

    def close_tab(self) -> None:
        """Actually close the tab."""
        try:
            if not (active_pane := self.tabbed.active_pane):
                return

            self.tabbed.remove_pane(active_pane.id)
            self.tabs.pop(active_pane)

            # Quit app if no tabs remain
            if len(self.tabs) == 0:
                self.exit()
        except Exception:
            pass

    def do_close_all_tabs(self) -> None:
        """Close all tabs and quit the app.

        Checks if any tabs have unsaved changes. If yes, opens a confirmation dialog.
        Otherwise, quits immediately.
        """
        try:
            # Check for dirty tabs
            dirty_tabnames = [table.tabname for table in self.tabs.values() if table.dirty]
            if not dirty_tabnames:
                self.exit()
                return

            def _save_and_quit(result: bool) -> None:
                if result:
                    self.get_active_table()._save_to_file(task_after_save="quit_app")
                elif result is None:
                    # User cancelled - do nothing
                    return
                else:
                    # User wants to discard - quit immediately
                    self.exit()

            tab_list = "\n".join(f"  - [$warning]{name}[/]" for name in dirty_tabnames)
            label = (
                f"The following tabs have unsaved changes:\n\n{tab_list}\n\nSave all changes?"
                if len(dirty_tabnames) > 1
                else f"The tab [$warning]{dirty_tabnames[0]}[/] has unsaved changes.\n\nSave changes?"
            )
            self.push_screen(
                ConfirmScreen(
                    "Close All Tabs" if len(self.tabs) > 1 else "Close Tab",
                    label=label,
                    yes="Save",
                    maybe="Discard",
                    no="Cancel",
                ),
                callback=_save_and_quit,
            )

        except Exception as e:
            self.log(f"Error quitting all tabs: {str(e)}")
            pass

    def do_rename_tab(self, content_tab: ContentTab) -> None:
        """Open the rename tab screen.

        Allows the user to rename the current tab and updates the table name accordingly.

        Args:
            content_tab: The ContentTab to rename.
        """
        if content_tab is None:
            return

        # Get list of existing tab names (excluding current tab)
        existing_tabs = self.tabs.keys()

        # Push the rename screen
        self.push_screen(
            RenameTabScreen(content_tab, existing_tabs),
            callback=self.rename_tab,
        )

    def rename_tab(self, result) -> None:
        """Handle result from RenameTabScreen."""
        if result is None:
            return

        content_tab: ContentTab
        content_tab, new_name = result

        # Update the tab name
        old_name = content_tab.label_text
        content_tab.label = new_name

        # Mark tab as dirty to indicate name change
        tab_id = content_tab.id.removeprefix("--content-tab-")
        for tab, table in self.tabs.items():
            if tab.id == tab_id:
                table.tabname = new_name
                table.dirty = True
                table.focus()
                break

        self.notify(f"Renamed tab [$accent]{old_name}[/] to [$success]{new_name}[/]", title="Rename")
