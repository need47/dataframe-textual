"""A theme screen to select theme from a list of available themes."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.theme import BUILTIN_THEMES
from textual.widgets import OptionList


class ThemeScreen(ModalScreen):
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
        super().__init__()
        self.themes = list(BUILTIN_THEMES.keys())
        self.original_theme = self.app.theme

    def compose(self) -> ComposeResult:
        with Container(id="theme-container") as container:
            container.border_title = "Select Theme"
            yield OptionList(*self.themes, id="theme-list")

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        if self.original_theme in self.themes:
            options.highlighted = self.themes.index(self.original_theme)
        options.focus()

    def _set_theme(self, theme: str) -> None:
        if theme in self.themes:
            self.app.theme = theme

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._set_theme(str(event.option.prompt))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._set_theme(str(event.option.prompt))
        self.app.pop_screen()

    def action_cancel(self) -> None:
        self.app.theme = self.original_theme
        self.app.pop_screen()
