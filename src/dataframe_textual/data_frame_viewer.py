"""DataFrame Viewer application and utilities."""

from functools import partial
from pathlib import Path
from textwrap import dedent
from typing import Any

import polars as pl
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.events import Click
from textual.widgets import TabbedContent, TabPane
from textual.widgets.tabbed_content import ContentTab, ContentTabs

from dataframe_textual.theme_screen import ThemeScreen

from .common import RID, SUPPORTED_FORMATS, Source, get_next_item, guess_file_format, load_file, validate_expr
from .console_panel import ConsolePanel
from .data_frame_help_panel import DataFrameHelpPanel
from .data_frame_table import DataFrameTable
from .file_picker_screen import OpenFileScreen, SaveFileScreen
from .status_bar import StatusBar
from .yes_no_screen import ConfirmScreen, NewTabScreen, RenameTabScreen


class DataFrameViewer(App):
    """A Textual app to interact with multiple Polars DataFrames via tabbed interface."""

    HELP = dedent("""
        # 📊 DataFrame Viewer - App Controls

        ## ⚙️ File & Tab Management
        - **q** - ❌ Quit current tab (prompts to save unsaved changes)
        - **Q** - ❌ Quit all tabs (prompts to save unsaved changes)
        - **Ctrl+Q** - 🚪 Force to quit app (discards unsaved changes)
        - **Esc** - ❌ Force to quit current tab or view (discards unsaved changes)
        - **Space** - 👁️ Toggle tab bar visibility
        - **b** - ⏭️ Next Tab
        - **B** - ⏮️ Previous Tab
        - **>** - ▶️ Move current tab right (wrap to first)
        - **<** - ◀️ Move current tab left (wrap to last)
        - **Ctrl+T** - 💾 Save current tab to file
        - **Ctrl+S** - 💾 Save all tabs to file
        - **Ctrl+V** - 💾 Save current view to file
        - **w** - 💾 Save current tab to file (overwrite without prompt)
        - **W** - 💾 Save all tabs to file (overwrite without prompt)
        - **Ctrl+D** - 📋 Duplicate current tab
        - **Ctrl+O** - 📁 Open a file
        - **Ctrl+N** - 📋 Create new tab from Polars expression
        - **Double-click** - ✏️ Rename tab

        ## 🎨 View & Settings
        - **F1** - ❓ Toggle this help panel
        - **k** - 🌙 Select theme
        - **` (backtick)** - 🐍 Toggle Python console
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
        ("q", "close", "Quit current tab or view"),
        ("Q", "close_all", "Quit all tabs and quit"),
        ("escape", "force_close", "Force to quit current tab or view"),
        ("space", "toggle_tab_bar", "Toggle Tab Bar"),
        ("b", "next_tab(1)", "Next Tab"),
        ("B", "next_tab(-1)", "Previous Tab"),
        ("greater_than_sign", "move_tab(1)", "Move tab right"),  # '>'
        ("less_than_sign", "move_tab(-1)", "Move tab left"),  # '<'
        ("f1", "toggle_help_panel", "Help"),
        ("ctrl+o", "open_file", "Open File"),
        ("ctrl+v", "save_current_view", "Save Current View"),
        ("ctrl+t", "save_current_tab", "Save Current Tab"),
        ("ctrl+s", "save_all_tabs", "Save All Tabs"),
        ("ctrl+n", "new_tab", "New Tab"),
        ("w", "save_current_tab_overwrite", "Save Current Tab (overwrite)"),
        ("W", "save_all_tabs_overwrite", "Save All Tabs (overwrite)"),
        ("ctrl+d", "duplicate_tab", "Duplicate Tab"),
        ("k", "select_theme", "Select Theme"),
        ("grave_accent", "toggle_python_console", "Python Console"),  # '`'
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

        #status_bar {
            dock: bottom;
            height: 1;
            background: $surface;
            color: $text-muted;
        }

        #status_context {
            width: auto;
            min-width: 24;
            padding: 0 1;
        }

        #status_message {
            width: 1fr;
            padding: 0 1;
            content-align: right middle;
            text-align: right;
        }
        #status_message.is-success {
            background: $success-darken-2;
        }
        #status_message.is-warning {
            background: $warning-darken-2;
        }
        #status_message.is-error {
            background: $error-darken-2;
        }
    """

    def __init__(self, *sources: Source, theme: str | None = None) -> None:
        """Initialize the DataFrame Viewer application.

        Loads data from provided sources and prepares the tabbed interface.

        Args:
            sources: sources to load dataframes from, each as a tuple of
                     (DataFrame, filename, tabname).
            theme: Optional; The theme to use for the application.
        """
        super().__init__()
        self.sources = sources
        self.theme = theme
        self.tabs: dict[TabPane, DataFrameTable] = {}
        self.help_panel: DataFrameHelpPanel | None = None

    @property
    def active_table(self) -> DataFrameTable | None:
        """Get the currently active DataFrameTable widget.

        Returns:
            The active DataFrameTable widget, or None if not found.
        """
        try:
            if active_pane := self.tabbed.active_pane:
                return self.tabs.get(active_pane)
        except AttributeError:
            return None

        return None

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
                lf, filename, tabname = source.lf, source.filename, source.tabname
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
                    table = DataFrameTable(lf, filename, tabname=tabname, id=tab_id, zebra_stripes=True)
                    tab = TabPane(tabname, table, id=tab_id)
                    self.tabs[tab] = table
                    yield tab
                except Exception as e:
                    self.notify(
                        f"Failed to load [$error]{filename}[/]: Try [$accent]-I[/] to disable schema inference",
                        title="Load File",
                        severity="error",
                    )
                    self.log(f"Error loading `{filename}`: {e}")

        # Python console panel
        self.console_panel = ConsolePanel(self._get_console_context, self._apply_console_context, id="console_panel")
        yield self.console_panel

        # Status bar
        self.status_bar = StatusBar()
        yield self.status_bar

    def on_mount(self) -> None:
        """Set up the application when it starts.

        Initializes the app by hiding the tab bar for single-file mode and focusing
        the active table widget.
        """
        self._set_status(self.status_bar.message, severity=self.status_bar.severity)

        if len(self.tabs) == 1:
            self.query_one(ContentTabs).display = False
            if table := self.active_table:
                table.focus()

    def on_ready(self) -> None:
        """Called when the app is ready."""
        # self.log(self.tree)
        pass

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
                self.log(f"Error handling tab rename click: {e}")

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation events.

        When a tab is activated, focuses the table widget and loads its data if not already loaded.
        Applies active styling to the clicked tab and removes it from others.

        Args:
            event: The tab activated event containing the activated tab pane.
        """
        # Focus the table in the newly activated tab
        if table := self.active_table:
            self._set_status()
            table.focus()

            if table.loaded_rows == 0:
                table.init_table()

    def _set_status_context(self, table: DataFrameTable | None = None) -> None:
        """Update the fixed left-side status context.

        Args:
            table: Optional active table to render context from.
        """
        table = table or self.active_table

        row_count, column_count = 0, 0
        if table is not None:
            if table.df is not None:
                row_count = len(table.df)
                column_count = len(table.df.columns) - 1  # Exclude the hidden RID column
            else:
                row_count = table.loaded_rows
                column_count = len(table.lf.collect_schema().names()) - 1  # Exclude the hidden RID column

        filename = Path(table.filename).name if table else "No file"
        main_or_view = "Main" if table is None or table.df_view is None else "View"
        context = f"{filename} | {main_or_view} | {row_count:,} rows x {column_count:,} cols"

        self.status_bar.set_context(context)

    def _set_status(
        self,
        message: str = "",
        title: str = "",
        severity: str = "information",
        markup: bool = True,
    ) -> None:
        """Update the persistent bottom status bar.

        Args:
            message: Plain-text message to display.
            title: Optional title prefix.
            severity: Severity used for styling.
            markup: Whether the message should be interpreted as Rich markup.
        """
        self._set_status_context()

        if not message:
            return
        full_message = f"[b]{title}[/]: {message}" if title else message

        self.status_bar.set_message(full_message, severity=severity, markup=markup)

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        """Show a notification, falling back to plain text on invalid markup.

        Args:
            message: The notification message.
            title: The notification title.
            severity: Notification severity.
            timeout: Optional notification timeout in seconds.
            markup: Whether the message should be interpreted as Rich markup.
        """
        self._set_status(message, title=title, severity=severity, markup=markup)

        # if severity in {"warning", "error"}:
        #     super().notify(
        #         status_message,
        #         title=title,
        #         severity=severity,
        #         timeout=timeout,
        #         markup=markup,
        #     )

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

    def action_close(self) -> None:
        """Close current tab or view.

        Checks for unsaved changes and prompts the user to save if needed.
        If this is the last tab, exits the app.
        """
        self.do_close()

    def action_force_close(self) -> None:
        """Force close current tab or view without save prompts."""
        self.do_close(force=True)

    def action_close_all(self) -> None:
        """Close all tabs and quit.

        Checks if any tabs have unsaved changes. If yes, opens a confirmation dialog.
        Otherwise, quits immediately.
        """
        self.do_close_all()

    def action_save_current_view(self) -> None:
        """Open a save dialog to save current view to file."""
        self.do_save_view_to_file()

    def action_save_current_tab(self) -> None:
        """Open a save dialog to save current tab to file."""
        self.do_save_to_file(all_tabs=False)

    def action_save_all_tabs(self) -> None:
        """Open a save dialog to save all tabs to file."""
        self.do_save_to_file(all_tabs=True)

    def action_save_current_tab_overwrite(self) -> None:
        """Save current tab to file, overwrite if exists."""
        if table := self.active_table:
            if len(self.tabs) > 1:
                filenames = {t.filename for t in self.tabs.values()}
                if len(filenames) > 1:
                    # Different filenames across tabs
                    filepath = Path(table.filename)
                    filename = filepath.with_stem(table.tabname)
                else:
                    filename = table.filename
            else:
                filename = table.filename

            filename = Path(filename).resolve()
            self.save_to_file(filename, all_tabs=False, overwrite_prompt=False)

    def action_save_all_tabs_overwrite(self) -> None:
        """Save all tabs to file, overwrite if exists."""
        if table := self.active_table:
            if len(self.tabs) > 1:
                filenames = {t.filename for t in self.tabs.values()}
                if len(filenames) > 1:
                    # Different filenames across tabs - use generic name
                    filename = "all-tabs.xlsx"
                else:
                    filename = table.filename
            else:
                filename = table.filename

            filename = Path(filename).resolve()
            self.save_to_file(filename, all_tabs=True, overwrite_prompt=False)

    def action_duplicate_tab(self) -> None:
        """Duplicate the currently active tab.

        Creates a copy of the current tab with the same data and filename.
        The new tab is named with '_copy' suffix and inserted after the current tab.
        """
        self.do_duplicate_tab()

    def action_new_tab(self) -> None:
        """Open screen to create a new tab from a Polars expression.

        Opens NewTabScreen to allow the user to input a Polars expression.
        The expression is evaluated on the active table's data to create a new tab.
        """
        if not (table := self.active_table):
            self.notify("No active table found", title="New Tab", severity="error")
            return

        self.push_screen(NewTabScreen(), callback=partial(self.new_tab, dftable=table))

    def new_tab(self, result: str | None, dftable: "DataFrameTable") -> None:
        """Handle result from NewTabScreen.

        Args:
            result: The Polars expression string provided by the user, or None if cancelled.
            dftable: Reference to the active DataFrameTable.
        """
        if not result:
            return

        try:
            # Validate and evaluate the expression
            expr = validate_expr(result, dftable.df.columns, dftable.cursor_cidx, df=dftable.df)

            if isinstance(expr, pl.Expr):
                df = dftable.df.filter(expr)
            elif isinstance(expr, pl.DataFrame):
                df = expr
            elif isinstance(expr, pl.Series):
                df = expr.to_frame()
            else:
                self.notify(
                    f"Expression returned [$error]{type(expr).__name__}[/], expected a DataFrame or Series",
                    title="New Tab",
                    severity="error",
                )
                return

            # Add the new tab
            self.add_tab(
                df,
                filename="expr_result.csv",
                tabname="expr-result",
                after=self.tabbed.active_pane,
            )
            self.notify(
                f"Created new tab with [$accent]{len(df)}[/] rows and [$accent]{len(df.columns)}[/] columns",
                title="New Tab",
            )
        except Exception as e:
            self.notify(f"Failed to evaluate expression [$error]{result}[/]: {e}", title="New Tab", severity="error")

    def action_select_theme(self) -> None:
        """Open the theme selection screen."""
        self.push_screen(ThemeScreen())

    def action_toggle_python_console(self) -> None:
        """Toggle the embedded Python console for the current tab."""
        if not self.console_panel:
            return

        if self.console_panel.display:
            self.console_panel.display = False
            if table := self.active_table:
                table.focus()
            return

        if not self.active_table:
            self.notify("No active table found", title="Python Console", severity="error")
            return

        self.console_panel.display = True
        self.console_panel.focus_input()

    def _get_console_context(self) -> dict[str, Any]:
        """Build the execution context for the Python console.

        Returns:
            Console locals for the active table.
        """
        table = self.active_table
        return {
            "pl": pl,
            "app": self,
            "table": table,
            "df": None if table is None else table.df,
            "RID": RID,
        }

    def _apply_console_context(self, locals_dict: dict[str, Any], previous_df: Any) -> None:
        """Sync dataframe assignments from the Python console back into the active tab.

        Args:
            locals_dict: Console locals after command execution.
            previous_df: The dataframe bound to the active tab before execution.
        """
        table = locals_dict.get("self") or self.active_table
        if not isinstance(table, DataFrameTable):
            return

        candidate = None
        if table.df is not previous_df and isinstance(table.df, (pl.DataFrame, pl.LazyFrame)):
            candidate = table.df
        else:
            df = locals_dict.get("df")
            if df is not previous_df and isinstance(df, (pl.DataFrame, pl.LazyFrame, pl.Series)):
                candidate = df

        if candidate is None:
            return

        table.apply_frame(candidate, dirty=True)
        locals_dict["table"] = table
        locals_dict["df"] = table.df

        self.notify("Updated table from console", title="Python Console")

    def action_next_tab(self, offset: int = 1) -> None:
        """Switch to the next tab or previous tab.

        Cycles through tabs by the specified offset. With offset=1, moves to next tab.
        With offset=-1, moves to previous tab. Wraps around when reaching edges.

        Args:
            offset: Number of tabs to advance (+1 for next, -1 for previous). Defaults to 1.
        """
        self.do_next_tab(offset)

    def action_move_tab(self, offset: int = 1) -> None:
        """Move the current tab left or right with wrap.

        Args:
            offset: Direction to move (+1 right, -1 left). Defaults to 1.
        """

        self.do_move_tab(offset)

    def action_toggle_tab_bar(self) -> None:
        """Toggle the tab bar visibility.

        Shows or hides the tab bar at the bottom of the window. Useful for maximizing
        screen space in single-tab mode.
        """
        tabs = self.query_one(ContentTabs)
        tabs.display = not tabs.display
        status = "on" if tabs.display else "off"
        self.notify(f"Tab bar is [$success]{status}[/]", title="Toggle Tab Bar")

    def do_duplicate_tab(self) -> None:
        """Duplicate the currently active tab.

        Creates a copy of the current tab with the same data and filename.
        The new tab is named with '_copy' suffix and inserted after the current tab.
        """
        if not (table := self.active_table):
            return

        # Get current tab info
        current_tabname = table.tabname
        new_tabname = f"{current_tabname}_copy"
        new_tabname = self.get_unique_tabname(new_tabname)

        # Create new table with the same DataFrame and filename
        new_table = DataFrameTable(
            table.df.clone(),  # Clone the DataFrame to ensure independent state
            filename=Path(table.filename).with_stem(new_tabname),  # Update filename stem to match new tab name
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

    def do_move_tab(self, offset: int = 1) -> None:
        """Move the active tab left or right with wrap.

        Args:
            offset: Direction to move (+1 right, -1 left). Defaults to 1.
        """

        if len(self.tabs) <= 1:
            return

        try:
            tabs = list(self.tabs.keys())
            active_pane = self.tabbed.active_pane
            current_index = tabs.index(active_pane)

            tabs.pop(current_index)
            # len(tabs) is now len(self.tabs) - 1, but we want modulo len(self.tabs)
            new_index = (current_index + offset) % (len(tabs) + 1)
            tabs.insert(new_index, active_pane)

            # Rebuild self.tabs to preserve new order
            self.tabs = {pane: self.tabs[pane] for pane in tabs}

            active_tab = self.tabbed.get_tab(active_pane.id)

            if new_index == 0:
                reference_pane = tabs[1]
                reference_tab = self.tabbed.get_tab(reference_pane.id)
                active_tab.parent.move_child(active_tab, before=reference_tab)
                active_pane.parent.move_child(active_pane, before=reference_pane)
            else:
                reference_pane = tabs[new_index - 1]
                reference_tab = self.tabbed.get_tab(reference_pane.id)
                active_tab.parent.move_child(active_tab, after=reference_tab)
                active_pane.parent.move_child(active_pane, after=reference_pane)

            # Reset the active pane highlight visually
            tabs_widget = self.query_one(ContentTabs)
            self.call_after_refresh(lambda: tabs_widget._highlight_active())

        except Exception as e:
            self.log(f"Error moving tab: {e}")

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

    def do_open_file(self, filename: str | Path | None) -> None:
        """Open a file.

        Loads the specified file and creates one or more tabs for it. For Excel files,
        creates one tab per sheet. For other formats, creates a single tab.

        Args:
            filename: Path to the file to load and add as tab(s).
        """
        if filename is None:
            return

        filepath = Path(filename)
        filename = str(filepath)

        if filepath.exists():
            try:
                n_tab = 0
                for source in load_file(filename, prefix_sheet=True):
                    self.add_tab(source.lf, filename, source.tabname, after=self.tabbed.active_pane)
                    n_tab += 1
                self.notify(f"Added [$accent]{n_tab}[/] tab(s) for [$success]{filename}[/]", title="Open File")
            except Exception as e:
                self.notify(f"Failed to load [$error]{filename}[/]: {e}", title="Open File", severity="error")
        else:
            self.notify(f"File does not exist: [$warning]{filename}[/]", title="Open File", severity="warning")

    def add_tab(
        self,
        frame: pl.DataFrame | pl.LazyFrame,
        filename: str,
        tabname: str,
        before: TabPane | str | None = None,
        after: TabPane | str | None = None,
    ) -> None:
        """Add new tab for the given DataFrame or LazyFrame.

        Creates and adds a new tab with the provided DataFrame or LazyFrame and configuration.
        Ensures unique tab names by appending an index if needed. Shows the tab bar
        if this is no longer the only tab.

        Args:
            frame: The DataFrame or LazyFrame to add in the new tab.
            filename: The source filename for this data (used in table metadata).
            tabname: The display name for the tab.
            before: Optional; If specified, insert the new tab before this tab.
            after: Optional; If specified, insert the new tab after this tab.
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

        table = DataFrameTable(frame, filename, tabname=tabname, zebra_stripes=True, id=tab_idx)
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

    def do_close(self, force=False) -> None:
        """Close current tab or view.

        When in a view, return to main table. Otherwise, close the active tab.
        If only one tab remains and no more tabs can be closed, exits the application.

        Args:
            force: If True, forces the close without prompting to save unsaved changes.
        """
        try:
            if not (table := self.active_table):
                return

            # In a view - return to main table
            if table.df_view is not None:
                # Remove from history
                while table.histories_undo:
                    h = table.histories_undo[-1]
                    if h.description.startswith("Viewed rows by expression"):
                        table.histories_undo.pop()
                    else:
                        break

                table.add_history("Return to main table")
                table.df = table.df_view
                table.df_view = None
                table.setup_table()

                self.notify("Returned to main table", title="Quit View")
                return

            def _on_save_confirm(result: bool) -> None:
                """Handle the "save before closing?" confirmation."""
                if result:
                    # User wants to save - close after save dialog opens
                    self.do_save_to_file(all_tabs=False, task_after_save="close_tab")
                elif result is None:
                    # User cancelled - do nothing
                    return
                else:
                    # User wants to discard - close immediately
                    self.close_tab()

            if table.dirty and not force:
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
            elif len(self.tabs) == 1:
                self.query_one(ContentTabs).display = False
        except Exception:
            pass

    def do_close_all(self) -> None:
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
                    self.do_save_to_file(all_tabs=True, task_after_save="quit_app")
                elif result is None:
                    # User cancelled - do nothing
                    return
                else:
                    # User wants to discard - quit immediately
                    self.exit()

            tab_count = len(self.tabs)
            tab_list = "\n".join(f"  - [$warning]{name}[/]" for name in dirty_tabnames)
            label = (
                f"The following tabs have unsaved changes:\n\n{tab_list}\n\nSave all changes?"
                if len(dirty_tabnames) > 1
                else f"The tab [$warning]{dirty_tabnames[0]}[/] has unsaved changes.\n\nSave changes?"
            )

            self.push_screen(
                ConfirmScreen(
                    f"Close {tab_count} Tabs" if tab_count > 1 else "Close Tab",
                    label=label,
                    yes="Save",
                    maybe="Discard",
                    no="Cancel",
                ),
                callback=_save_and_quit,
            )

        except Exception as e:
            self.log(f"Error quitting all tabs: {e}")

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

        self.notify(f"Renamed tab [$accent]{old_name}[/] to [$success]{new_name}[/]", title="Rename Tab")

    def do_save_to_file(self, all_tabs: bool = True, task_after_save: str | None = None) -> None:
        """Open screen to save file."""
        if not (table := self.active_table):
            return

        self._task_after_save = task_after_save
        tab_count = len(self.tabs)
        all_tabs = all_tabs is True and tab_count > 1

        if all_tabs:
            filenames = {t.filename for t in self.tabs.values()}
            if len(filenames) > 1:
                # Different filenames across tabs - use generic name
                filename = "all-tabs.xlsx"
            else:
                filename = table.filename
        elif tab_count == 1:
            filename = table.filename
        else:
            filepath = Path(table.filename)
            filename = str(filepath.with_stem(table.tabname))

        self.push_screen(
            SaveFileScreen(filename=filename),
            callback=partial(self.save_to_file, all_tabs=all_tabs),
        )

    def do_save_view_to_file(self) -> None:
        """Open screen to save current view to file."""
        if not (table := self.active_table):
            return

        if table.df_view is None:
            self.notify("No active view to save", title="Save View", severity="warning")
            return

        filepath = Path(table.filename)
        filename = str(filepath.with_stem(f"{table.tabname}_view"))

        self.push_screen(
            SaveFileScreen(filename=filename),
            callback=partial(self.save_to_file, all_tabs=False, use_view=True),
        )

    def save_to_file(
        self,
        filename: str | Path | None,
        all_tabs: bool = True,
        overwrite_prompt: bool = True,
        use_view=False,
        use_df: pl.DataFrame | None = None,
    ) -> None:
        """Save to file"""
        if filename is None:
            return

        # Check if file exists
        if overwrite_prompt and Path(filename).exists():
            self.push_screen(
                ConfirmScreen("File already exists. Overwrite?"),
                callback=partial(
                    self.confirm_overwrite, filename=filename, all_tabs=all_tabs, use_view=use_view, use_df=use_df
                ),
            )
        else:
            self.save_file(filename, all_tabs=all_tabs, use_view=use_view, use_df=use_df)

    def confirm_overwrite(
        self,
        should_overwrite: bool,
        filename: str,
        all_tabs: bool = True,
        use_view: bool = False,
        use_df: pl.DataFrame | None = None,
    ) -> None:
        """Handle result from ConfirmScreen."""
        if should_overwrite:
            self.save_file(filename, all_tabs=all_tabs, use_view=use_view, use_df=use_df)
        else:
            # Go back to SaveFilePicker to allow user to enter a different name
            self.push_screen(
                SaveFileScreen(filename=filename),
                callback=partial(self.save_to_file, all_tabs=all_tabs, use_view=use_view, use_df=use_df),
            )

    def save_file(
        self,
        filepath: str | Path,
        all_tabs: bool = True,
        use_view: bool = False,
        use_df: pl.DataFrame | None = None,
    ) -> None:
        """
        Actually save to a file.

        Args:
            filepath: The filepath to save to.
            use_view: Whether to save the current view (True) or main table (False).
            use_df: Optional DataFrame to save instead of the current table/view.
        """
        if not (table := self.active_table):
            return

        filename = str(Path(filepath))
        if not (fmt := guess_file_format(filename)):
            self.notify(
                f"Unsupported file format [$error]{fmt}[/] for [$accent]{filename}[/]. Supported formats are: {', '.join(SUPPORTED_FORMATS)}",
                title="Save to File",
                severity="warning",
            )
            return

        if use_df is not None:
            lf = use_df.lazy()
        else:
            lf = (table.df if table.df_view is None else table.df if use_view else table.df_view).lazy()

        df: pl.DataFrame = lf.select(pl.exclude(RID)).collect()
        compression = "gzip" if filename.endswith(".gz") else "uncompressed"

        try:
            if fmt == "csv":
                df.write_csv(filename, compression=compression)
            elif fmt == "tsv":
                df.write_csv(filename, separator="\t", compression=compression)
            elif fmt == "psv":
                df.write_csv(filename, separator="|", compression=compression)
            elif fmt == "parquet":
                df.write_parquet(filename)
            elif fmt in ("jsonl", "ndjson"):
                df.write_ndjson(filename, compression=compression)
            elif fmt == "json":
                df.write_json(filename)
            elif fmt == "vortex":
                import vortex as vx

                vx.io.write(df.to_arrow(), filename)
            elif fmt == "xlsx":
                self.save_excel(filename, all_tabs=all_tabs, use_view=use_view)
            else:
                pass

            if use_view:
                self.notify(f"Saved current view to [$success]{filename}[/]", title="Save to File")
            else:
                # Reset dirty flag and update filename after save
                if all_tabs:
                    for table in self.tabs.values():
                        table.dirty = False
                        table.filename = filename
                else:
                    table.dirty = False
                    table.filename = filename

                # From ConfirmScreen callback, so notify accordingly
                if all_tabs:
                    self.notify(f"Saved all tabs to [$success]{filename}[/]", title="Save to File")
                elif len(self.tabs) > 1:
                    self.notify(f"Saved current tab to [$success]{filename}[/]", title="Save to File")
                else:
                    self.notify(f"Saved to [$success]{filename}[/]", title="Save to File")

                if hasattr(self, "_task_after_save"):
                    if self._task_after_save == "close_tab":
                        self.do_close_tab()
                    elif self._task_after_save == "quit_app":
                        self.exit()

        except Exception as e:
            self.notify(f"Failed to save [$error]{filename}[/]", title="Save to File", severity="error")
            self.log(f"Error saving file `{filename}`: {e}")

    def save_excel(self, filename: str, all_tabs: bool = True, use_view: bool = False) -> None:
        """Save to an Excel file."""
        import xlsxwriter

        if not all_tabs or len(self.tabs) == 1:
            # Single tab - save directly
            if not (table := self.active_table):
                return

            df = (table.df if table.df_view is None else table.df if use_view else table.df_view).select(
                pl.exclude(RID)
            )
            df.write_excel(filename, worksheet=table.tabname)
        else:
            # Multiple tabs - use xlsxwriter to create multiple sheets
            with xlsxwriter.Workbook(filename) as wb:
                tabs: dict[TabPane, DataFrameTable] = self.tabs
                for table in tabs.values():
                    worksheet = wb.add_worksheet(table.tabname)
                    df = (table.df if table.df_view is None else table.df if use_view else table.df_view).select(
                        pl.exclude(RID)
                    )
                    df.write_excel(workbook=wb, worksheet=worksheet)
