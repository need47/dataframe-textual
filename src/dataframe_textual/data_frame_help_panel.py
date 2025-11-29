"""Help panel widget for displaying context-sensitive help."""

from textwrap import dedent

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Markdown


class DataFrameHelpPanel(Widget):
    """
    Shows context sensitive help for the currently focused widget.

    Modified from Textual's built-in HelpPanel with KeyPanel removed.
    """

    DEFAULT_CSS = """
        DataFrameHelpPanel {
            split: right;
            width: 33%;
            min-width: 40;
            max-width: 80;
            border-left: vkey $foreground 30%;
            padding: 0 1;
            height: 1fr;
            padding-right: 1;
            layout: vertical;
            height: 100%;

            &:ansi {
                background: ansi_default;
                border-left: vkey ansi_black;

                Markdown {
                    background: ansi_default;
                }
                .bindings-table--divide {
                    color: transparent;
                }
            }

            #widget-help {
                height: auto;
                width: 1fr;
                padding: 0;
                margin: 0;
                padding: 1 0;
                margin-top: 1;
                display: none;
                background: $panel;

                &:ansi {
                    background: ansi_default;
                }

                MarkdownBlock {
                    padding-left: 2;
                    padding-right: 2;
                }
            }

            &.-show-help #widget-help {
                display: block;
            }
        }
    """

    DEFAULT_CLASSES = "-textual-system"

    def on_mount(self) -> None:
        """Set up help panel when mounted.

        Initializes the help panel by setting up a watcher for focused widget changes
        to dynamically update help text based on which widget has focus.
        """

        # def update_help(focused_widget: Widget | None):
        #     self.update_help(focused_widget)

        # self.watch(self.screen, "focused", update_help)

        self.update_help(self.screen.focused)

    def update_help(self, focused_widget: Widget | None) -> None:
        """Update the help for the focused widget.

        Args:
            focused_widget: The currently focused widget, or `None` if no widget was focused.
        """
        if not self.app.app_focus:
            return
        if not self.screen.is_active:
            return
        self.set_class(focused_widget is not None, "-show-help")
        if focused_widget is not None:
            help = (self.app.HELP or "") + "\n" + (focused_widget.HELP or "")
            if not help:
                self.remove_class("-show-help")
            try:
                self.query_one(Markdown).update(dedent(help))
            except NoMatches:
                pass

    def compose(self) -> ComposeResult:
        """Compose the help panel widget structure.

        Creates and returns the widget hierarchy for the help panel,
        including a VerticalScroll container with a Markdown display area.

        Yields:
            VerticalScroll: The main container with Markdown widget for help text.
        """
        yield VerticalScroll(Markdown(id="widget-help"))
