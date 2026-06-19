"""DataFrame Viewer application and utilities."""

from functools import partial
from pathlib import Path
from typing import Any

import polars as pl
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.events import Click, Key
from textual.timer import Timer
from textual.widgets import TabbedContent, TabPane
from textual.widgets.tabbed_content import ContentTab, ContentTabs

from dataframe_textual.theme_screen import ThemeScreen

from .commands import Scope
from .common import (
    RID,
    SUPPORTED_FORMATS,
    THOUSAND_SEPARATOR,
    Source,
    get_next_item,
    guess_file_format,
    load_file,
    validate_expr,
)
from .console_panel import ConsolePanel
from .data_frame_table import DataFrameTable
from .file_picker_screen import OpenFileScreen, SaveFileScreen
from .help_panel import DataFrameHelpPanel
from .keybindings import key_registry
from .status_bar import StatusBar
from .table_screen import SheetScreen
from .yes_no_screen import ConfirmScreen, JoinTableScreen, NewTabScreen, RenameTabScreen


class DataFrameViewer(App):
    """A Textual app to interact with multiple Polars DataFrames via tabbed interface."""

    @property
    def HELP(self) -> str:
        """Generate dynamic help text from the key binding registry."""
        return key_registry.generate_help_text(Scope.APP)

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
            background: $success-darken-3;
        }
        #status_message.is-warning {
            background: $warning-darken-3;
        }
        #status_message.is-error {
            background: $error-darken-3;
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

        # Key binding registry
        self.key_registry = key_registry

        # Global leader mode state
        self.leader_key = ""
        self.leader_timer: Timer | None = None

    def on_key(self, event: Key) -> None:
        """Handle leader-mode activation and app-scope command dispatch.

        Intercepts ``g`` and ``z`` keystrokes to enter leader mode, which allows
        two-key sequences (e.g., ``gq``, ``gw``, ``z^``) to be dispatched.

        Attempts to dispatch app-scope bindings via the registry. If leader mode
        is active and no binding matches the second key, shows an error message
        and resets leader mode. Leader mode also resets after a short timeout.

        Args:
            event: The key event object.
        """
        # Try dispatching as an app-scope command
        if key_registry.dispatch(event.key, leader=self.leader_key, scope=Scope.APP, target=self):
            event.stop()
            event.prevent_default()
            self.reset_leader()
            return

        # Already in leader mode, no matching command found
        if self.leader_key:
            event.stop()
            event.prevent_default()
            self.notify(
                f"Command not found for [$warning]{self.leader_key}[/][$accent]{event.key}[/] key binding",
                title="Key Binding",
                severity="warning",
            )
            self.reset_leader()
            return

        # Enter leader mode on `g` or `z` key
        elif event.key in ("g", "z"):
            event.stop()
            event.prevent_default()
            self.leader_key = event.key
            self.notify(
                f"Leader mode activated with [$success]{event.key}[/], waiting for next key in 3 seconds",
                title="Leader Mode",
            )
            self.leader_timer = self.set_timer(3, callback=lambda: self.reset_leader("Leader mode timed out"))
            return

        # No relevant key binding, allow event to propagate normally
        else:
            return

    def reset_leader(self, message: str = "") -> None:
        """Cancel leader mode and reset the timeout timer."""
        self.leader_key = ""
        if message:
            self.notify(message, title="Leader Mode")

        if self.leader_timer:
            self.leader_timer.stop()
            self.leader_timer = None

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
        """Initialize the active table when the app is ready, then load others in background."""
        # Initialize the active table first to ensure quick startup and immediate interactivity
        if actable := self.active_table:
            if actable.loaded_rows == 0:
                actable.init_table()
            self._set_status()
            actable.focus()

        # Schedule background initialization of remaining tabs without blocking the UI
        bg_tables = [t for t in self.tabs.values() if t is not actable and t.loaded_rows == 0]
        if bg_tables:
            self._init_background_tables(iter(bg_tables))

    def _init_background_tables(self, tables_iter) -> None:
        """Initialize one background table per event loop tick to avoid blocking.

        Args:
            tables_iter: Iterator over DataFrameTable instances to initialize.
        """
        table = next(tables_iter, None)
        if table is None:
            return

        table.init_table()
        self.call_later(self._init_background_tables, tables_iter)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation events.

        When a tab is activated, initializes the table if needed, updates status,
        and focuses the table widget.

        Args:
            event: The tab activated event containing the activated tab pane.
        """
        if table := self.active_table:
            if table.loaded_rows == 0:
                table.init_table()

            self._set_status()
            table.focus()

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
                column_count = len(table.lf.collect_schema().names())

        filename = Path(table.filename).name if table else "No file"
        view_or_main = "View" if table.in_view else "Main"
        context = f"{filename} | {view_or_main} | {row_count:,} rows x {column_count:,} cols"

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

    def cmd_show_sheets(self) -> None:
        """Show a modal with information about all currently opened tables."""
        self.push_screen(SheetScreen(self.tabs))

    def cmd_show_commands(self) -> None:
        """Show all commands and key bindings in a new tab."""
        from .commands import COMMANDS
        from .keybindings import format_key_display

        seen = set()
        rows = []
        for binding, cmd in sorted(
            self.key_registry._bindings.items(),
            key=lambda kv: (kv[1].category.value, kv[0].scope.value, kv[1].cmd, kv[0].leader, kv[0].key),
        ):
            seen.add(cmd)
            rows.append(
                {
                    "Leader": binding.leader if binding.leader else "",
                    "Key": format_key_display(binding.key),
                    "Command": cmd.cmd,
                    "Description": f"{cmd.emoji} {cmd.description}" if cmd.emoji else cmd.description,
                    "Scope": binding.scope.value,
                    "Category": cmd.category.value,
                }
            )

        # Include unbound commands that have no key bindings
        for cmd in COMMANDS.values():
            if cmd in seen:
                continue

            rows.append(
                {
                    "Leader": "",
                    "Key": "",
                    "Command": cmd.cmd,
                    "Description": f"{cmd.emoji} {cmd.description}" if cmd.emoji else cmd.description,
                    "Scope": cmd.scope.value,
                    "Category": cmd.category.value,
                }
            )

        df = pl.DataFrame(rows)
        self.add_tab(df, filename="commands.csv", tabname="commands", after=self.tabbed.active_pane)

        # Mark the newly created commands tab for keybindings save behavior
        if table := self.active_table:
            table.for_keybindings = True

        self.notify(f"Showing [$accent]{len(rows):{THOUSAND_SEPARATOR}}[/] commands", title="List Commands")

    def cmd_toggle_help_panel(self) -> None:
        """Toggle the help panel on or off.

        Shows or hides the context-sensitive help panel. Creates it on first use.
        """
        if self.help_panel:
            self.help_panel.display = not self.help_panel.display
        else:
            self.help_panel = DataFrameHelpPanel()
            self.mount(self.help_panel)

    def cmd_open_file(self) -> None:
        """Open file browser to load a file in a new tab.

        Displays the file open dialog for the user to select a file to load
        as a new tab in the interface.
        """
        self.push_screen(OpenFileScreen(), self.do_open_file)

    def cmd_close(self) -> None:
        """Close current tab or view.

        Checks for unsaved changes and prompts the user to save if needed.
        If this is the last tab, exits the app.
        """
        self.close_current()

    def cmd_close_all(self) -> None:
        """Close all tabs."""
        self.close_all()

    def cmd_force_quit(self) -> None:
        """Force quit the app, discarding unsaved changes."""
        self.exit()

    def cmd_save_current_tab(self) -> None:
        """Open a save dialog for the active tab or active view.

        When currently in a derived view, this action saves that view.
        For keybindings tabs, saves modified bindings as JSON to config dir.
        Otherwise, it saves the active tab dataframe.
        """
        if table := self.active_table:
            if table.for_keybindings:
                self.save_keybindings()
            elif table.in_view:
                self.do_save_view_to_file()
            else:
                self.do_save_to_file(all_tabs=False)

    def cmd_save_all_tabs(self) -> None:
        """Open a save dialog to save all tabs to file."""
        self.do_save_to_file(all_tabs=True)

    def cmd_save_tab_overwrite(self) -> None:
        """Save current tab to file, overwriting without prompt."""
        self._save_current_tab_overwrite()

    def cmd_save_all_tabs_overwrite(self) -> None:
        """Save all tabs to file, overwriting without prompt."""
        self._save_all_tabs_overwrite()

    def _save_current_tab_overwrite(self) -> None:
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

    def _save_all_tabs_overwrite(self) -> None:
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

    def cmd_duplicate_tab(self) -> None:
        """Duplicate the currently active tab.

        Creates a copy of the current tab with the same data and filename.
        The new tab is named with '_copy' suffix and inserted after the current tab.
        """
        self.do_duplicate_tab()

    def cmd_new_tab(self) -> None:
        """Open screen to create a new tab from a Polars expression.

        Opens NewTabScreen to allow the user to input a Polars expression.
        The expression is evaluated on the active table's data to create a new tab.
        """
        if not (table := self.active_table):
            self.notify("No active table found", title="New Tab", severity="error")
            return

        self.push_screen(NewTabScreen(), callback=partial(self.new_tab, dftable=table))

    def cmd_join_table(self) -> None:
        """Open the join table screen to join two tables.

        Opens JoinTableScreen pre-selecting the active table as the left table.
        The join result is added as a new tab.
        """
        self.push_screen(JoinTableScreen(), callback=self._join_table)

    def _join_table(self, result: pl.DataFrame | None) -> None:
        """Handle the result from JoinTableScreen.

        Args:
            result: The joined DataFrame, or None if the user cancelled or join failed.
        """
        if result is None:
            return
        self.add_tab(
            result,
            filename="join_results.csv",
            tabname="join-results",
            after=self.tabbed.active_pane,
        )
        self.notify(
            f"Joined table: [$success]{len(result)}[/] rows, [$accent]{len(result.columns)}[/] columns",
            title="Join Tables",
        )

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
            expr = validate_expr(result, dftable.df.columns, dftable.cursor_col_name, df=dftable.df)

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

    def cmd_select_theme(self) -> None:
        """Open the theme selection screen."""
        self.push_screen(ThemeScreen())

    def cmd_toggle_python_console(self) -> None:
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
            "self": table,
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

    def cmd_next_tab(self) -> None:
        """Switch to the next tab."""
        self.do_next_tab(1)

    def cmd_prev_tab(self) -> None:
        """Switch to the previous tab."""
        self.do_next_tab(-1)

    def cmd_move_tab_left(self) -> None:
        """Move current tab to the left."""
        self.do_move_tab(-1)

    def cmd_move_tab_right(self) -> None:
        """Move current tab to the right."""
        self.do_move_tab(1)

    def cmd_toggle_tab_bar(self) -> None:
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
                self.notify(f"Added [$success]{n_tab}[/] tab(s) for [$accent]{filename}[/]", title="Open File")
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

    def close_current(self, force=False) -> None:
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
            if table.in_view:
                # Remove from history
                while table.histories_undo:
                    h = table.histories_undo[-1]
                    if h.description.startswith("Viewed rows by expression"):
                        table.histories_undo.pop()
                    else:
                        break

                table.add_history("Return to main table")
                table.df = table.dfull
                table.dfull = None
                table.setup_table()

                self.notify("Returned to main table", title="Quit View")
                return

            def _on_save_confirm(result: bool) -> None:
                """Handle the "save before closing?" confirmation."""
                if result:
                    # User wants to save - close after save dialog opens
                    self.do_save_to_file(all_tabs=False, task_after_save="close_tab")
                # elif result is None:
                #     # User cancelled - do nothing
                #     return
                else:
                    # User wants to discard - close immediately
                    self.close_tab()

            if table.dirty and not force:
                self.push_screen(
                    ConfirmScreen(
                        "Close Tab",
                        label="This tab has unsaved changes. Save changes?",
                        yes="Save",
                        no="Discard",
                    ),
                    callback=_on_save_confirm,
                )
            else:
                # No unsaved changes - close immediately
                self.close_tab()
        except Exception:
            pass

    def close_tab(self, pane: TabPane | None = None) -> None:
        """Actually close the tab."""
        try:
            if pane is None:
                pane = self.tabbed.active_pane
            if not pane:
                return

            self.tabbed.remove_pane(pane.id)
            self.tabs.pop(pane)

            # Quit app if no tabs remain
            if len(self.tabs) == 0:
                self.exit()
            elif len(self.tabs) == 1:
                self.query_one(ContentTabs).display = False
        except Exception:
            pass

    def close_all(self) -> None:
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
                """Handle confirmation response for save-and-quit dialog."""
                if result:
                    self.do_save_to_file(all_tabs=True, task_after_save="quit_app")
                # elif result is None:
                #     # User cancelled - do nothing
                #     return
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
                    no="Discard",
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

        self.notify(f"Renamed tab [$success]{old_name}[/] to [$accent]{new_name}[/]", title="Rename Tab")

    def save_keybindings(self) -> None:
        """Save modified keybindings to the user config directory as JSON."""
        import json

        from .commands import COMMANDS, Command
        from .keybindings import KeyBinding, format_key_display, get_config_dir, parse_key_display

        table = self.active_table
        if not table or not table.for_keybindings:
            return

        # Use the full dataframe with defaults for saving, so that unmodified bindings are preserved in the output.
        df = table.dfull if table.in_view else table.df

        # Table: KeyBinding -> Command
        table_keybindings: dict[KeyBinding, Command] = {}

        for row in df.iter_rows(named=True):
            command_id = row["Command"]
            if not (command := COMMANDS.get(command_id)):
                self.notify(f"Unknown command: {command_id}", title="Save Keybindings", severity="error")
                return

            # Skip empty keybindings
            if not (key := row["Key"]):
                continue

            # Parse the keybinding from the table row
            binding = KeyBinding(
                key=parse_key_display(key),
                leader=row["Leader"],
                scope=Scope(row["Scope"]),
                command_id=command_id,
            )

            # Check for duplicate bindings
            if binding in table_keybindings:
                self.notify(
                    f"Duplicate binding for {binding.display_key} ({binding.scope.value})",
                    title="Keybindings",
                    severity="error",
                )
                return

            table_keybindings[binding] = command

        if not table_keybindings:
            self.notify("No keybindings found to save", title="Save Keybindings", severity="warning")
            return

        # Update the app's key registry with the new bindings
        self.key_registry._bindings = table_keybindings

        # Serialize the new keybindings to JSON format for saving. Only include bindings that differ from defaults.
        json_rows = [
            {
                "key": format_key_display(binding.key),
                "leader": binding.leader,
                "command": command.cmd,
                "scope": binding.scope.value,
            }
            for binding, command in table_keybindings.items()
        ]

        config_dir = get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        filepath = config_dir / "keybindings.json"
        try:
            filepath.write_text(json.dumps(json_rows, indent=2) + "\n", encoding="utf-8")
            self.notify(f"Saved keybindings to [$success]{filepath}[/]", title="Save Keybindings")
        except OSError as e:
            self.notify(f"Failed to save keybindings: {e}", title="Save Keybindings", severity="error")

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

        if not table.in_view:
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
            all_tabs: Whether to save all tabs (True) or just the current tab (False). Defaults to True.
            use_view: Whether to save the current view (True) or main table (False).
            use_df: Optional DataFrame to save instead of the current table/view.
        """
        if not (table := self.active_table):
            return

        filename = str(Path(filepath))
        if not (fmt := guess_file_format(filename)):
            self.notify(
                f"Unsupported file format [$warning]{fmt}[/] for [$accent]{filename}[/]. Supported formats are: {', '.join(SUPPORTED_FORMATS)}",
                title="Save File",
                severity="warning",
            )
            return

        if use_df is not None:
            lf = use_df.lazy()
        else:
            lf = (table.df if use_view else (table.dfull if table.in_view else table.df)).lazy()

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
                self.notify(f"Saved current view to [$success]{filename}[/]", title="Save File")
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
                    self.notify(f"Saved all tabs to [$success]{filename}[/]", title="Save File")
                elif len(self.tabs) > 1:
                    self.notify(f"Saved current tab to [$success]{filename}[/]", title="Save File")
                else:
                    self.notify(f"Saved to [$success]{filename}[/]", title="Save File")

                if hasattr(self, "_task_after_save"):
                    if self._task_after_save == "close_tab":
                        self.close_tab()
                    elif self._task_after_save == "quit_app":
                        self.exit()

        except Exception as e:
            self.notify(f"Failed to save [$error]{filename}[/]", title="Save File", severity="error")
            self.log(f"Error saving file `{filename}`: {e}")

    def save_excel(self, filename: str, all_tabs: bool = True, use_view: bool = False) -> None:
        """Save to an Excel file."""
        import xlsxwriter

        if not all_tabs or len(self.tabs) == 1:
            # Single tab - save directly
            if not (table := self.active_table):
                return

            # Ensure DataFrame is collected before writing to Excel
            if table.df is None:
                table.df = table.lf.collect()

            df = (table.df if use_view else (table.dfull if table.in_view else table.df)).select(pl.exclude(RID))
            df.write_excel(filename, worksheet=table.tabname)
        else:
            # Multiple tabs - use xlsxwriter to create multiple sheets
            with xlsxwriter.Workbook(filename) as wb:
                tabs: dict[TabPane, DataFrameTable] = self.tabs
                for table in tabs.values():
                    worksheet = wb.add_worksheet(table.tabname)

                    # Ensure DataFrame is collected before writing to Excel
                    if table.df is None:
                        table.df = table.lf.collect()

                    df = (table.df if use_view else (table.dfull if table.in_view else table.df)).select(
                        pl.exclude(RID)
                    )
                    df.write_excel(workbook=wb, worksheet=worksheet)
