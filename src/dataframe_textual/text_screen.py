"""A screen to display long text in a TextArea widget."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import TextArea


class TextScreen(ModalScreen):
    DEFAULT_CSS = """
        TextScreen {
            align: center middle;
        }

        #text-area {
            width: auto;
            min-width: 40;
            max-width: 50%;
            height: auto;
            border: solid $primary;
            border-title-color: $primary;
        }
    """

    def __init__(self, text) -> None:
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        yield TextArea(self.text, id="text-area", read_only=True, show_cursor=False)

    def on_key(self, event) -> None:
        if event.key in ("q", "escape"):
            self.dismiss()
            event.stop()
