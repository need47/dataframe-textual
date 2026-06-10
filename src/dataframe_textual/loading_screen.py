"""Loading and busy indicator modal screens."""

from typing import TYPE_CHECKING, Callable

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import LoadingIndicator

if TYPE_CHECKING:
    from .data_frame_table import DataFrameTable


class LoadingScreen(ModalScreen):
    """Modal overlay that polls for dataframe load completion and auto-dismisses."""

    BINDINGS = [
        ("q,escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
        LoadingScreen {
            align: center middle;
        }

        #loading-indicator {
            width: 17;
            height: 3;
            background: $surface-lighten-2 75%; /* close to that used in TableScreen */
        }
    """

    def __init__(self, dftable: "DataFrameTable", callback: Callable | None = None) -> None:
        """Initialize the loading screen.

        Args:
            dftable: The DataFrameTable being loaded.
            callback: Optional callable invoked after loading completes.
        """
        super().__init__()
        self.dftable = dftable
        self.callback = callback

    def compose(self) -> ComposeResult:
        """Compose the loading indicator widget."""
        yield LoadingIndicator(id="loading-indicator")

    def on_mount(self) -> None:
        """Start polling for load completion on mount."""
        self.set_interval(0.1, self.check_progress)

    def check_progress(self) -> None:
        """Check the loading progress of the dataframe."""
        if self.dftable.df_done:
            # fully loaded, dismiss the screen
            self.dismiss()

            if self.callback:
                self.callback()

    def action_cancel(self) -> None:
        """Dismiss the loading screen on cancel."""
        self.dismiss()


class BusyScreen(ModalScreen):
    """Modal overlay shown while a background task runs, polling for task completion."""

    BINDINGS = [
        ("q,escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
        BusyScreen {
            align: center middle;
        }

        #loading-indicator {
            width: 17;
            height: 3;
            background: $surface-lighten-2 75%; /* close to that used in TableScreen */
        }
    """

    def __init__(self, dftable: "DataFrameTable", task: Callable) -> None:
        """Initialize the busy screen.

        Args:
            dftable: The DataFrameTable associated with the running task.
            task: Callable to invoke on mount that starts the background work.
        """
        super().__init__()
        self.dftable = dftable
        self.run_task = task

    def compose(self) -> ComposeResult:
        """Compose the loading indicator widget."""
        yield LoadingIndicator(id="loading-indicator")

    def on_mount(self) -> None:
        """Start the task and begin polling for completion on mount."""
        self.run_task()
        self.set_interval(0.1, self.check_progress)

    def check_progress(self) -> None:
        """Check the loading progress of the dataframe."""
        if self.dftable.task_done:
            self.dismiss()

    def action_cancel(self) -> None:
        self.dismiss()
