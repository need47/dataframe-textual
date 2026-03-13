"""A theme screen to select theme from a list of available themes."""

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import LoadingIndicator

if TYPE_CHECKING:
    from .data_frame_table import DataFrameTable


class LoadingScreen(ModalScreen):
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
            background: $surface;
        }
    """

    def __init__(self, dftable: "DataFrameTable", callback: callable = None) -> None:
        super().__init__()
        self.dftable = dftable
        self.callback = callback

    def compose(self) -> ComposeResult:
        yield LoadingIndicator(id="loading-indicator")

    def on_mount(self) -> None:
        self.set_interval(0.1, self.check_progress)

    def check_progress(self) -> None:
        """Check the loading progress of the dataframe."""
        if self.dftable.df_done:
            # self.notify("Dataframe loaded fully")
            self.dismiss()
            if self.callback:
                self.callback()

    def action_cancel(self) -> None:
        self.dismiss()
