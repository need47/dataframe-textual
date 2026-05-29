"""Status bar widget for DataFrame viewer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.content import Content
from textual.markup import MarkupError
from textual.widgets import Static


def _normalize_message(message: str, markup: bool) -> tuple[str, bool]:
    """Normalize status text and fall back to plain text if markup is invalid."""
    if not markup:
        return message, False

    try:
        Content.from_markup(message)
    except MarkupError:
        plain_message = (
            message.replace("[/]", "")
            .replace("[b]", "")
            .replace("[$error]", "")
            .replace("[$success]", "")
            .replace("[$warning]", "")
            .replace("[$accent]", "")
        )
        return plain_message, False

    return message, True


class StatusBar(Horizontal):
    """Bottom status bar with context text and message text."""

    def __init__(
        self, context: str = "No file | 0 rows x 0 cols", message: str = "Ready", severity: str = "information"
    ) -> None:
        """Initialize status bar state.

        Args:
            context: Initial left-side status context.
            message: Initial right-side status message.
            severity: Initial status severity.
        """
        super().__init__(id="status_bar")
        self.context = context
        self.message = message
        self.severity = severity
        self._context_widget: Static | None = None
        self._message_widget: Static | None = None

    def compose(self) -> ComposeResult:
        """Compose context and message widgets."""
        self._context_widget = Static(self.context, id="status_context")
        self._message_widget = Static(self.message, id="status_message")
        yield self._context_widget
        yield self._message_widget

    def set_context(self, context: str) -> None:
        """Update the left-side context text.

        Args:
            context: Context text to render.
        """
        self.context = context
        self._context_widget.update(context)

    def set_message(self, message: str, *, severity: str = "information", markup: bool = True) -> None:
        """Update the right-side message text and severity styling.

        Args:
            message: Message text to render.
            severity: Severity used for message styling.
            markup: Whether the message should be interpreted as Rich markup.
        """
        message, effective_markup = _normalize_message(message, markup)
        rendered_message = Content.from_markup(message) if effective_markup else Content(message)

        self.message = message
        self.severity = severity

        self._message_widget.update(rendered_message)
        self._message_widget.remove_class("is-success")
        self._message_widget.remove_class("is-warning")
        self._message_widget.remove_class("is-error")
        self._message_widget.tooltip = None

        if severity == "success":
            self._message_widget.add_class("is-success")
        elif severity == "warning":
            self._message_widget.add_class("is-warning")
            self._message_widget.tooltip = message
        elif severity == "error":
            self._message_widget.add_class("is-error")
            self._message_widget.tooltip = message
