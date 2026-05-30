"""Embedded Python console panel for the dataframe viewer."""

from __future__ import annotations

import code
import io
import subprocess
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.widgets import Input, RichLog, Static


class ConsolePanel(Vertical):
    """Bottom-docked interactive Python console for the active dataframe tab."""

    INPUT_PLACEHOLDER = "Enter Python code to execute"
    HISTORY_BEGINNING_PLACEHOLDER = "Already at beginning of history. Press Down to return."
    HISTORY_END_PLACEHOLDER = "Already at end of history. Press Up to return."

    BINDINGS = [
        ("escape", "close_console", "Close Console"),
    ]

    DEFAULT_CSS = """
        ConsolePanel {
            dock: bottom;
            height: 50%;
            min-height: 8;
            border-top: solid $primary;
            background: $surface;
            display: none;
        }

        #console_help {
            height: auto;
            background: $surface;
            color: $text-muted;
            padding-left: 1;
        }

        #console_output {
            height: 1fr;
            background: $surface-darken-1;
            color: $text;
            padding-left: 1;
        }

        #console_input_row {
            height: 4;
            align: left middle;
            background: $surface;
        }

        #console_prompt {
            width: auto;
            height: 3;
            color: $accent;
            content-align: right middle;
            padding-left: 1;
        }

        #console_input {
            height: 3;
            width: 1fr;
        }
    """

    def __init__(
        self,
        get_context: Callable[[], dict[str, Any]],
        apply_context: Callable[[dict[str, Any], Any], None],
        **kwargs,
    ) -> None:
        """Initialize the console panel.

        Args:
            get_context: Callback returning the current execution context.
            apply_context: Callback used to sync dataframe changes back to the UI.
            **kwargs: Additional widget keyword arguments.
        """
        super().__init__(**kwargs)
        self._get_context = get_context
        self._apply_context = apply_context
        self._locals: dict[str, Any] = {}
        self._interpreter = code.InteractiveConsole(self._locals)
        self._awaiting_more_input = False
        self._history: list[str] = []
        self._history_index: int | None = None
        self._history_pending_input = ""
        self._history_boundary: str | None = None
        self._suppress_history_reset = False
        self._ignore_input_changed = 0

    def compose(self) -> ComposeResult:
        """Compose the console output and input widgets."""
        sticky_help = "Python console ready. Available names: [$success]df[/] and [$success]pl[/]. Assign a DataFrame or Series back to [$success]df[/] to refresh the current table. Prefix with [$success]![/] to run shell commands."
        yield Static(sticky_help, id="console_help", markup=True)

        self.output = RichLog(id="console_output", markup=False, wrap=True, highlight=True)
        yield self.output

        with Horizontal(id="console_input_row"):
            self.prompt = Static(">>>", id="console_prompt")
            yield self.prompt
            self.input = Input(placeholder=self.INPUT_PLACEHOLDER, id="console_input")
            yield self.input

    def on_mount(self) -> None:
        """Set initial focus once the panel is mounted."""
        self.focus_input()

    def focus_input(self) -> None:
        """Focus the input widget for interactive use."""
        self.input.focus()

    def action_close_console(self) -> None:
        """Hide the console panel when escape is pressed."""
        self.display = False
        if table := self.app.active_table:
            table.focus()

    def write_line(self, text: str) -> None:
        """Append text to the output log.

        Args:
            text: Text to append.
        """
        lines = text.rstrip("\n").splitlines() or [""]
        for line in lines:
            self.output.write(line)

    def _update_prompt(self) -> None:
        """Update the prompt based on multi-line interpreter state."""
        prompt = "..." if self._awaiting_more_input else ">>>"
        self.prompt.update(prompt)

    def _record_history(self, source: str) -> None:
        """Record a submitted input line for later navigation.

        Args:
            source: Submitted source text.
        """
        if not source.strip():
            return

        if self._history and self._history[-1] == source:
            return

        self._history.append(source)

    def _reset_history_navigation(self) -> None:
        """Reset history cursor and pending in-progress input snapshot."""
        self._history_index = None
        self._history_pending_input = ""
        self._history_boundary = None
        self.input.placeholder = self.INPUT_PLACEHOLDER

    def _set_input_value(self, value: str, *, cursor_to_end: bool = True) -> None:
        """Set input value while ignoring the corresponding changed event.

        Args:
            value: Input value to set.
            cursor_to_end: Whether to place cursor at the end of value.
        """
        self._ignore_input_changed += 1
        self.input.value = value
        self.input.cursor_position = len(value) if cursor_to_end else 0

    def _enter_history_boundary(self, boundary: str) -> None:
        """Enter a boundary state and show a hint in the input placeholder.

        Args:
            boundary: Either "beginning" or "end".
        """
        self._history_index = None
        self._history_boundary = boundary
        self._suppress_history_reset = True
        try:
            self._set_input_value("", cursor_to_end=False)
            self.input.placeholder = (
                self.HISTORY_BEGINNING_PLACEHOLDER if boundary == "beginning" else self.HISTORY_END_PLACEHOLDER
            )
        finally:
            self._suppress_history_reset = False

    def _navigate_history(self, step: int) -> None:
        """Move backward or forward through input history.

        Args:
            step: -1 for older commands, +1 for newer commands.
        """
        if not self._history:
            return

        if self._history_boundary == "beginning":
            if step > 0:
                self._suppress_history_reset = True
                try:
                    self.input.placeholder = self.INPUT_PLACEHOLDER
                    self._set_input_value(self._history[0])
                    self._history_index = 0
                    self._history_boundary = None
                finally:
                    self._suppress_history_reset = False
            return

        if self._history_boundary == "end":
            if step < 0:
                self._suppress_history_reset = True
                try:
                    self.input.placeholder = self.INPUT_PLACEHOLDER
                    self._set_input_value(self._history[-1])
                    self._history_index = len(self._history) - 1
                    self._history_boundary = None
                finally:
                    self._suppress_history_reset = False
            return

        if self._history_index is None:
            self._history_pending_input = self.input.value
            self._history_index = len(self._history)
            self.input.placeholder = self.INPUT_PLACEHOLDER

        if step < 0 and self._history_index == 0:
            self._enter_history_boundary("beginning")
            return

        if step > 0 and self._history_index == len(self._history) - 1:
            self._enter_history_boundary("end")
            return

        if step > 0 and self._history_index == len(self._history):
            self._enter_history_boundary("end")
            return

        new_index = self._history_index + step
        new_index = max(0, min(new_index, len(self._history)))

        self._suppress_history_reset = True
        try:
            if new_index == len(self._history):
                self._set_input_value(self._history_pending_input)
                self._history_index = None
                self.input.placeholder = self.INPUT_PLACEHOLDER
            else:
                self._set_input_value(self._history[new_index])
                self._history_index = new_index
                self.input.placeholder = self.INPUT_PLACEHOLDER
        finally:
            self._suppress_history_reset = False

    def on_key(self, event: Key) -> None:
        """Handle Up/Down navigation for console input history.

        Args:
            event: Key event instance.
        """
        if not self.input.has_focus:
            return

        if event.key == "up":
            event.stop()
            self._navigate_history(-1)
        elif event.key == "down":
            event.stop()
            self._navigate_history(1)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Reset history cursor if the user edits text after navigating history.

        Args:
            event: Input changed event.
        """
        if event.input.id != "console_input":
            return

        if self._ignore_input_changed > 0:
            self._ignore_input_changed -= 1
            return

        if self._suppress_history_reset:
            return

        self.input.placeholder = self.INPUT_PLACEHOLDER
        self._history_boundary = None

        if self._history_index is not None:
            self._history_index = None
            self._history_pending_input = event.value

    def _run_shell_command(self, command: str) -> int:
        """Run a shell command and emit captured output in the console log.

        Args:
            command: Shell command string to execute.

        Returns:
            Process return code.
        """
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
        if result.stdout:
            self.write_line(result.stdout)
        if result.stderr:
            self.write_line(result.stderr)
        return result.returncode

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Execute submitted Python source.

        Args:
            event: Submitted input event.
        """
        if event.input.id != "console_input":
            return

        source = event.value
        self._record_history(source)
        self._reset_history_navigation()
        prompt = "..." if self._awaiting_more_input else ">>>"

        if not self._awaiting_more_input and source.strip().lower() in {"clear", "cls"}:
            self.output.clear()
            event.input.value = ""
            self.focus_input()
            return

        if not self._awaiting_more_input and source.lstrip().startswith("!"):
            self.write_line(f"{prompt} {source}")
            event.input.value = ""

            command = source.lstrip()[1:].strip()
            if not command:
                self.write_line("Shell command is empty.")
            else:
                self._run_shell_command(command)

            self._update_prompt()
            self.focus_input()
            return

        self.write_line(f"{prompt} {source}")
        event.input.value = ""

        context = self._get_context()
        self._locals.update(context)
        self._interpreter.locals = self._locals

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        try:
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                self._awaiting_more_input = self._interpreter.push(source)
        except SystemExit as error:
            stderr_buffer.write(f"SystemExit: {error}\n")
            self._awaiting_more_input = False
        except Exception:
            stderr_buffer.write(traceback.format_exc())
            self._awaiting_more_input = False

        try:
            previous_df = context.get("df")
            self._apply_context(self._locals, previous_df)
        except Exception:
            stderr_buffer.write(traceback.format_exc())
            self._awaiting_more_input = False

        output = stdout_buffer.getvalue()
        errors = stderr_buffer.getvalue()
        if output:
            self.write_line(output)
        if errors:
            self.write_line(errors)

        self._update_prompt()
        self.focus_input()
