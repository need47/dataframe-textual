"""A screen to display long text in a TextArea widget."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import TextArea


class TextScreen(ModalScreen):
    """Modal screen to display long read-only text in a scrollable TextArea."""

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
        """Initialize the text screen.

        Args:
            text: The text content to display.
        """
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        """Compose the read-only TextArea widget."""
        yield TextArea(self.text, id="text-area", read_only=True, show_cursor=False)

    def on_key(self, event) -> None:
        """Close the screen on q or Escape."""
        if event.key in ("q", "escape"):
            self.dismiss()
            event.stop()
