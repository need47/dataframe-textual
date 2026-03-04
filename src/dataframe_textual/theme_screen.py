"""A theme screen to select theme from a list of available themes."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.theme import BUILTIN_THEMES
from textual.widgets import OptionList


class ThemeScreen(ModalScreen):
    BINDINGS = [
        ("q", "cancel", "Cancel"),
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
        ThemeScreen {
            align: center middle;
        }

        #theme-container {
            width: 40;
            height: auto;
            padding: 0 1;
            border: solid $accent;
            border-title-color: $accent;
        }

        #theme-list {
            height: 20;
            border: none;
        }
    """

    def __init__(self) -> None:
        super().__init__()
        self.themes = list(BUILTIN_THEMES.keys())
        self.original_theme = ""
        self._confirmed = False

    def compose(self) -> ComposeResult:
        with Container(id="theme-container") as container:
            container.border_title = "Select Theme"
            yield OptionList(*self.themes, id="theme-list")

    def on_mount(self) -> None:
        self.original_theme = self.app.theme
        options = self.query_one(OptionList)
        if self.original_theme in self.themes:
            options.highlighted = self.themes.index(self.original_theme)
        options.focus()

    def _set_theme(self, theme: str) -> None:
        if theme in BUILTIN_THEMES:
            self.app.theme = theme

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._set_theme(str(event.option.prompt))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._confirmed = True
        self._set_theme(str(event.option.prompt))
        self.app.pop_screen()

    def action_cancel(self) -> None:
        self.app.theme = self.original_theme
        self.app.pop_screen()

    def on_unmount(self) -> None:
        if not self._confirmed:
            self.app.theme = self.original_theme
