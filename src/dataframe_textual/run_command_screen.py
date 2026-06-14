"""Modal screen for running commands by name."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Input


class InputScreen(ModalScreen):
    """Modal screen to get user input.
    Enter to submit, Escape to cancel.
    """

    DEFAULT_CSS = """
        InputScreen {
            align: center middle;
        }

        InputScreen #generic-input {
            width: auto;
            min-width: 48;
            border: solid $primary;
        }
    """

    def __init__(self, placeholder: str = "Your input (Enter to submit, Esc to cancel)") -> None:
        self.placeholder = placeholder
        super().__init__()

    def compose(self) -> ComposeResult:
        """Compose the run command modal screen."""
        self.input = Input(
            id="generic-input",
            placeholder=self.placeholder,
        )
        yield self.input

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in the input."""
        value = event.value  # Don't strip
        self.dismiss(value if value else None)

    def on_key(self, event) -> None:
        """Handle Escape key."""
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.dismiss(None)


class RunCommandScreen(InputScreen):
    """Modal screen to run a command by name with optional arguments.

    Accepts command names like 'show-frequency' or 'show_frequency',
    optionally followed by space-separated arguments.
    Enter to submit, Escape to cancel.
    """

    DEFAULT_CSS = """
        RunCommandScreen {
            align: center bottom;
        }

        RunCommandScreen > #generic-input {
            width: 60%;
            border: solid $primary;
        }
    """

    def __init__(self) -> None:
        """Initialize the run command screen."""
        super().__init__(
            placeholder="command [arg1 arg2 ...] (Enter to run, Esc to cancel)",
        )
