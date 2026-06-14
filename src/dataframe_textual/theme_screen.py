"""A theme screen to select theme from a list of available themes."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Key
from textual.screen import ModalScreen
from textual.theme import BUILTIN_THEMES
from textual.widgets import OptionList


class ThemeScreen(ModalScreen):
    """Modal screen to preview and select a Textual built-in theme."""

    BINDINGS = [
        ("q,escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
        ThemeScreen {
            align: center middle;
        }

        #theme-container {
            width: 40;
            height: auto;
            border: solid $primary;
            border-title-color: $primary;
        }

        #theme-list {
            height: 20;
            border: none;
        }
    """

    def __init__(self) -> None:
        """Initialize the theme screen and store the current theme so it can be restored on cancel."""
        super().__init__()
        self.themes = sorted(list(BUILTIN_THEMES.keys()))
        self.original_theme = self.app.theme

    def compose(self) -> ComposeResult:
        """Compose the theme selection list."""
        with Container(id="theme-container") as container:
            container.border_title = "Select Theme"
            yield OptionList(*self.themes, id="theme-list")

    def on_mount(self) -> None:
        """Pre-select the current theme and focus the list on mount."""
        options = self.query_one(OptionList)
        if self.original_theme in self.themes:
            options.highlighted = self.themes.index(self.original_theme)
        options.focus()

    def on_key(self, event: Key) -> None:
        if event.key in ("q", "escape"):
            event.stop()
            event.prevent_default()
            self.cmd_restore_theme()

    def _set_theme(self, theme: str) -> None:
        """Apply the given theme to the app if it is a known built-in."""
        if theme in self.themes:
            self.app.theme = theme
            self.app.notify(f"Switched to theme [$success]{theme}[/]", title="Switch Theme")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Preview theme as the user navigates the list."""
        self._set_theme(str(event.option.prompt))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Apply the selected theme and close the screen."""
        self._set_theme(str(event.option.prompt))
        self.app.pop_screen()

    def cmd_restore_theme(self) -> None:
        """Restore the original theme and close the screen."""
        self.app.theme = self.original_theme
        self.app.notify(f"Switched back to theme [$success]{self.original_theme}[/]", title="Switch Theme")
        self.app.pop_screen()
