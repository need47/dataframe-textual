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
            height: auto;
            min-width: 60;
            max-height: 100%;
            border: solid $primary;
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
