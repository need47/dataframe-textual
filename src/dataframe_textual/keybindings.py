"""Key binding registry for mapping keys to commands.

Keybindings map physical key presses (with optional leader-key prefixes) to command IDs.
Bindings must be unique within a given scope (same leader + key + scope = conflict).
Bindings may share the same key across different scopes.

The default bindings defined here mirror the existing hard-coded bindings.
Users can override them via a config file or change them at runtime.

Dispatch flow:
1. ``on_key()`` receives a key event
2. It calls ``registry.dispatch(key, leader, scope, target)``
3. The registry looks up the binding → finds the command → calls ``target.cmd_*()``
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .commands import COMMANDS, Category, Command, Scope

log = logging.getLogger(__name__)


APP_NAME = "dataframe_textual"


def get_config_dir() -> Path:
    """Return the platform-appropriate config directory for the app.

    Returns:
        Path to the config directory (e.g. ~/.config/dataframe_textual on Linux).
    """
    if sys.platform == "win32":
        config_base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        config_base = Path.home() / "Library" / "Application Support"
    else:
        config_base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_base / APP_NAME


class KeyBindingConflict(Exception):
    """Raised when a new binding conflicts with an existing one.

    Attributes:
        existing: The existing binding that conflicts.
        attempted: The binding that was attempted.
    """

    def __init__(self, existing: "KeyBinding", attempted: "KeyBinding") -> None:
        super().__init__(
            f"Key '{attempted.display_key}' (scope={attempted.scope.value}) is already bound to '{existing.command_id}'"
        )


@dataclass(frozen=True, eq=False)
class KeyBinding:
    """A key binding that maps a key (with optional leader prefix) to a command.

    Attributes:
        leader: Optional leader key prefix ("g" or "z"). Empty string means no leader.
        key: The Textual key name (e.g. "q", "ctrl+g", "slash").
        scope: The scope where this binding is active.
        command_id: The ID of the command this binding triggers.
    """

    leader: str
    key: str
    scope: Scope
    command_id: str

    def __eq__(self, other: object) -> bool:
        """Compare bindings by leader, key, and scope.

        Args:
            other: The object to compare against.

        Returns:
            True when both bindings represent the same key slot.
        """
        if not isinstance(other, KeyBinding):
            return NotImplemented
        return (self.leader, self.key, self.scope) == (other.leader, other.key, other.scope)

    def __hash__(self) -> int:
        """Hash bindings by leader, key, and scope.

        Returns:
            A stable hash for dict/set usage keyed by binding slot.
        """
        return hash((self.leader, self.key, self.scope))

    @property
    def display_key(self) -> str:
        """Human-readable representation of the key combination."""
        key_display = format_key_display(self.key)
        if self.leader:
            return f"{self.leader}{key_display}"
        return key_display

    @property
    def command(self) -> Command | None:
        """Look up the associated Command from the registry."""
        return COMMANDS.get(self.command_id)


# Textual key name -> human-friendly display string
_KEY_DISPLAY_MAP: dict[str, str] = {
    "f1": "F1",
    "tilde": "~",
    "grave_accent": "`",
    "exclamation_mark": "!",
    "at": "@",
    "number_sign": "#",
    "dollar_sign": "$",
    "percent_sign": "%",
    "circumflex_accent": "^",
    "ampersand": "&",
    "asterisk": "*",
    "left_parenthesis": "(",
    "right_parenthesis": ")",
    "underscore": "_",
    "minus": "-",
    "plus": "+",
    "equals_sign": "=",
    "backspace": "Backspace",
    "left_curly_bracket": "{",
    "left_square_bracket": "[",
    "right_curly_bracket": "}",
    "right_square_bracket": "]",
    "vertical_line": "|",
    "backslash": "\\",
    "colon": ":",
    "semicolon": ";",
    "quotation_mark": '"',
    "apostrophe": "'",
    "enter": "Enter",
    "less_than_sign": "<",
    "comma": ",",
    "greater_than_sign": ">",
    "full_stop": ".",
    "question_mark": "?",
    "slash": "/",
    "escape": "Escape",
    "tab": "Tab",
    "delete": "Delete",
    "home": "Home",
    "end": "End",
    "pageup": "PgUp",
    "pagedown": "PgDn",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "shift+up": "Shift+Up",
    "shift+down": "Shift+Down",
    "shift+left": "Shift+Left",
    "shift+right": "Shift+Right",
    "shift+delete": "Shift+Delete",
    "space": "Space",
}


def format_key_display(key: str) -> str:
    """Convert a Textual key name to a human-friendly display string."""
    if key in _KEY_DISPLAY_MAP:
        return _KEY_DISPLAY_MAP[key]

    if key.startswith("ctrl+"):
        return f"Ctrl+{key[5:].upper()}"

    return key


# Reverse mapping: display string -> Textual key name
_DISPLAY_TO_KEY: dict[str, str] = {v: k for k, v in _KEY_DISPLAY_MAP.items()}


def parse_key_display(display: str) -> str:
    """Convert a human-friendly display string back to a Textual key name.

    Args:
        display: The display string (e.g. "^", "Ctrl+T", "Enter").

    Returns:
        The Textual key name (e.g. "circumflex_accent", "ctrl+t", "enter").
    """
    if display in _DISPLAY_TO_KEY:
        return _DISPLAY_TO_KEY[display]

    if display.startswith("Ctrl+") and len(display) > 5:
        return f"ctrl+{display[5:].lower()}"

    return display


# ─── Default key bindings ─────────────────────────────────────────────────────

DEFAULT_BINDINGS: dict[KeyBinding, Command] = {}


def _bind(key: str, command_id: str, leader: str = "", scope: Scope = Scope.MAIN_TABLE) -> None:
    """Create and register a default key binding."""
    binding = KeyBinding(leader=leader, key=key, scope=scope, command_id=command_id)
    DEFAULT_BINDINGS[binding] = COMMANDS[command_id]


# ═══════════════════════════════════════════════════════════════════════════════
# App-scope bindings
# ═══════════════════════════════════════════════════════════════════════════════

_bind("q", "close", scope=Scope.APP)
_bind("q", "close-all", leader="g", scope=Scope.APP)
_bind("ctrl+q", "force-quit", scope=Scope.APP)
_bind("B", "toggle-tab-bar", leader="g", scope=Scope.APP)
_bind("B", "prev-tab", scope=Scope.APP)
_bind("b", "next-tab", scope=Scope.APP)
_bind("b", "move-tab-left", leader="g", scope=Scope.APP)
_bind("b", "move-tab-right", leader="z", scope=Scope.APP)
_bind("ctrl+t", "save-current-tab", scope=Scope.APP)
_bind("ctrl+s", "save-all-tabs", scope=Scope.APP)
_bind("w", "save-tab-overwrite", scope=Scope.APP)
_bind("w", "save-all-overwrite", leader="g", scope=Scope.APP)
_bind("ctrl+d", "duplicate-tab", scope=Scope.APP)
_bind("ctrl+o", "open-file", scope=Scope.APP)
_bind("ctrl+n", "new-tab", scope=Scope.APP)
_bind("f1", "toggle-help-panel", scope=Scope.APP)
_bind("grave_accent", "toggle-python-console", scope=Scope.APP)
_bind("S", "show-sheets", scope=Scope.APP)
_bind("backspace", "show-commands", leader="z", scope=Scope.APP)
_bind("ctrl+h", "show-commands", leader="z", scope=Scope.APP)

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Navigation
# ═══════════════════════════════════════════════════════════════════════════════

_bind("h", "cursor-left")
_bind("j", "cursor-down")
_bind("k", "cursor-up")
_bind("l", "cursor-right")
_bind("g", "go-top", leader="g")  # 'gg' sequence (g is leader, then g as second key)
_bind("G", "go-bottom")
_bind("ctrl+g", "go-to-row")
_bind("ctrl+b", "page-backward")
_bind("ctrl+f", "page-forward")
_bind("h", "scroll-home", leader="g")
_bind("j", "scroll-bottom", leader="g")
_bind("k", "scroll-top", leader="g")
_bind("l", "scroll-end", leader="g")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Undo/Redo/Reset
# ═══════════════════════════════════════════════════════════════════════════════

_bind("u", "undo")
_bind("U", "undo")
_bind("R", "redo")
_bind("u", "reset", leader="g")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Display
# ═══════════════════════════════════════════════════════════════════════════════

_bind("enter", "view-row-detail")
_bind("tab", "view-cell-detail")
_bind("F", "show-frequency")
_bind("m", "show-histogram")
_bind("m", "show-histogram-custom", leader="g")
_bind("I", "show-statistics")
_bind("I", "show-statistics-all", leader="g")
_bind("C", "cycle-cursor-type", leader="z")
_bind("equals_sign", "show-bar")
_bind("C", "metadata-column")
_bind("minus", "hide-column")
_bind("minus", "hide-column-before", leader="g")
_bind("minus", "hide-column-after", leader="z")
_bind("v", "show-hidden-columns", leader="g")
_bind("underscore", "expand-column")
_bind("underscore", "expand-all-columns", leader="g")
_bind("plus", "toggle-freeze")
_bind("tilde", "toggle-column-index", leader="z")
_bind("circumflex_accent", "set-row-as-header", leader="g")
_bind("T", "select-theme", leader="g", scope=Scope.APP)
_bind("circumflex_accent", "toggle-rid", leader="z")
_bind("comma", "toggle-thousand-separator", leader="z")
_bind("less_than_sign", "decrease-float-precision")
_bind("greater_than_sign", "increase-float-precision")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Editing
# ═══════════════════════════════════════════════════════════════════════════════

_bind("e", "edit-cell")
_bind("E", "edit-column")
_bind("a", "add-column")
_bind("A", "add-column-expr")
_bind("i", "add-index-column")
_bind("a", "add-link-column", leader="z")
_bind("circumflex_accent", "rename-column")
_bind("d", "delete-row")
_bind("d", "delete-row-above", leader="g")
_bind("d", "delete-row-below", leader="z")
_bind("delete", "clear-cell")
_bind("shift+delete", "clear-column")
_bind("asterisk", "delete-column")
_bind("asterisk", "delete-column-before", leader="g")
_bind("asterisk", "delete-column-after", leader="z")
_bind("D", "duplicate-row")
_bind("D", "duplicate-column", leader="z")
_bind("U", "remove-duplicates", leader="g")
_bind("T", "transpose", leader="z")
_bind("left_parenthesis", "expand-list-column")
_bind("right_parenthesis", "contract-list-column")
_bind("o", "explode-column")
_bind("O", "explode-column-delim")
_bind("colon", "split-column")
_bind("colon", "join-columns", leader="z")
_bind("colon", "glue-list-column", leader="g")
_bind("ctrl+u", "upper-case-column")
_bind("ctrl+l", "lower-case-column")
_bind("B", "strip-whitespace", leader="z")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Row/Column Selection
# ═══════════════════════════════════════════════════════════════════════════════

_bind("comma", "select-rows")
_bind("comma", "select-rows-all", leader="g")
_bind("vertical_line", "select-rows-expr")
_bind("vertical_line", "select-rows-expr-all", leader="g")
_bind("backslash", "unselect-rows-expr")
_bind("backslash", "unselect-rows-expr-all", leader="g")
_bind("s", "toggle-selection-row")
_bind("apostrophe", "toggle-selection-col")
_bind("t", "toggle-selections")
_bind("T", "clear-selections")
_bind("left_curly_bracket", "prev-selected-row")
_bind("right_curly_bracket", "next-selected-row")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Find & Replace
# ═══════════════════════════════════════════════════════════════════════════════

_bind("slash", "find-forward")
_bind("slash", "find-forward-all", leader="g")
_bind("slash", "find-forward-cursor", leader="z")
_bind("question_mark", "find-backward")
_bind("question_mark", "find-backward-all", leader="g")
_bind("question_mark", "find-backward-cursor", leader="z")
_bind("n", "next-match")
_bind("N", "prev-match")
_bind("r", "replace-column")
_bind("r", "replace-all-columns", leader="g")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Filter & Collect
# ═══════════════════════════════════════════════════════════════════════════════

_bind("v", "filter-rows")
_bind("V", "filter-rows-expr")
_bind("full_stop", "filter-rows-nonnull")
_bind("full_stop", "filter-rows-null", leader="z")
_bind("f", "filter-rows-value")
_bind("quotation_mark", "collect-rows")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Sorting
# ═══════════════════════════════════════════════════════════════════════════════

_bind("left_square_bracket", "sort-ascending")
_bind("right_square_bracket", "sort-descending")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Reorder
# ═══════════════════════════════════════════════════════════════════════════════

_bind("shift+left", "move-column-left")
_bind("H", "move-column-left")
_bind("shift+right", "move-column-right")
_bind("L", "move-column-right")
_bind("shift+up", "move-row-up")
_bind("K", "move-row-up")
_bind("shift+down", "move-row-down")
_bind("J", "move-row-down")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Type Casting
# ═══════════════════════════════════════════════════════════════════════════════

_bind("number_sign", "cast-integer")
_bind("percent_sign", "cast-float")
_bind("dollar_sign", "cast-boolean")
_bind("tilde", "cast-string")
_bind("at", "cast-date")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Copy
# ═══════════════════════════════════════════════════════════════════════════════

_bind("c", "copy-cell")
_bind("ctrl+c", "copy-column")
_bind("ctrl+r", "copy-row")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: SQL
# ═══════════════════════════════════════════════════════════════════════════════

_bind("Q", "sql-advanced")
_bind("Q", "sql-simple", leader="z")

# ═══════════════════════════════════════════════════════════════════════════════
# MainTable-scope bindings: Command Palette
# ═══════════════════════════════════════════════════════════════════════════════

_bind("space", "run-command")


# ─── Registry class ──────────────────────────────────────────────────────────


class KeyBindingRegistry:
    """Manages key bindings with lookup, dispatch, and customization support.

    Provides efficient lookup of bindings by key+leader+scope, dispatch to the
    appropriate cmd_* method, and supports runtime modification of bindings.
    """

    def __init__(self) -> None:
        """Initialize the registry with a set of bindings.

        Args:
            bindings: Initial mapping from binding slot to command.
                Uses DEFAULT_BINDINGS if None.
        """
        self._bindings: dict[KeyBinding, Command] = {}

    def lookup(self, key: str, leader: str = "", scope: Scope = Scope.MAIN_TABLE) -> KeyBinding | None:
        """Look up a binding by key, leader, and scope.

        Args:
            key: The Textual key name.
            leader: The leader key prefix (empty string for none).
            scope: The scope to search in.

        Returns:
            The matching KeyBinding, or None if not found.
        """
        probe = KeyBinding(leader=leader, key=key, scope=scope, command_id="")
        command = self._bindings.get(probe)
        if command is None:
            return None
        return KeyBinding(leader=leader, key=key, scope=scope, command_id=command.cmd)

    def dispatch(self, key: str, leader: str, scope: Scope, target: Any) -> bool:
        """Look up a binding and invoke the cmd_* method on target.

        This is the primary dispatch mechanism. It:
        1. Looks up the binding for (key, leader, scope)
        2. Resolves the command's ``cmd`` method name
        3. Calls ``getattr(target, cmd_method_name)()``

        Args:
            key: The Textual key name pressed.
            leader: The leader key prefix (empty string for none).
            scope: The scope to look up in.
            target: The object to call the cmd_* method on.

        Returns:
            True if a binding was found and dispatched, False otherwise.
        """
        probe = KeyBinding(leader=leader, key=key, scope=scope, command_id="")
        cmd = self._bindings.get(probe)
        if cmd is None:
            return False

        method = getattr(target, cmd.method_name, None)
        if method is None:
            log.warning(
                "Command %r wants method %r but target %r has no such method",
                cmd.cmd,
                cmd.method_name,
                type(target).__name__,
            )
            return False

        method()
        return True

    def get_bindings_for_command(self, command_id: str) -> list[KeyBinding]:
        """Get all bindings that trigger a given command."""
        return [binding for binding, command in self._bindings.items() if command.cmd == command_id]

    def get_bindings_for_scope(self, scope: Scope) -> list[KeyBinding]:
        """Get all bindings active in a given scope."""
        return [binding for binding in self._bindings if binding.scope == scope]

    def set_binding(self, binding: KeyBinding) -> None:
        """Add or replace a binding (no conflict check).

        If a binding already exists for the same key+leader+scope, it is replaced.
        For conflict-aware binding, use ``bind()`` instead.
        """
        self._bindings[binding] = COMMANDS[binding.command_id]

    def bind(
        self, key: str, command_id: str, leader: str = "", scope: Scope = Scope.MAIN_TABLE, force: bool = False
    ) -> KeyBinding | None:
        """Bind a key to a command, with conflict detection.

        Args:
            key: The Textual key name (e.g. "q", "ctrl+g", "slash").
            command_id: The command ID to bind to (must exist in COMMANDS).
            leader: Optional leader key prefix ("g" or "z"). Empty for no leader.
            scope: The scope where this binding is active.
            force: If True, silently replace any existing binding. If False,
                raise KeyBindingConflict when the slot is already occupied.

        Returns:
            The replaced KeyBinding if force=True and a conflict existed, else None.

        Raises:
            KeyBindingConflict: If force=False and the key+leader+scope is already bound.
            ValueError: If command_id does not exist in the command registry.
        """
        if command_id not in COMMANDS:
            raise ValueError(f"Unknown command ID: {command_id!r}")

        new_binding = KeyBinding(leader=leader, key=key, scope=scope, command_id=command_id)
        existing_cmd = self._bindings.get(new_binding)
        existing = (
            None
            if existing_cmd is None
            else KeyBinding(leader=leader, key=key, scope=scope, command_id=existing_cmd.cmd)
        )

        if existing_cmd is not None:
            if not force:
                raise KeyBindingConflict(existing, new_binding)

        self._bindings[new_binding] = COMMANDS[command_id]
        return existing

    def reset_to_defaults(self) -> None:
        """Reset all bindings to the defaults."""
        self._bindings = dict(DEFAULT_BINDINGS)

    def remove_binding(self, binding: KeyBinding) -> bool:
        """Remove a binding by slot. Returns True if found."""
        if binding in self._bindings:
            del self._bindings[binding]
            return True
        return False

    @property
    def bindings(self) -> list[KeyBinding]:
        """Get all registered bindings."""
        return list(self._bindings.keys())

    def get_all_with_commands(self) -> list[tuple[KeyBinding, Command]]:
        """Get all bindings paired with their associated commands."""
        return list(self._bindings.items())

    def generate_help_text(self, scope: Scope) -> str:
        """Generate Markdown help text for all bindings in a given scope.

        Args:
            scope: The scope to generate help for.

        Returns:
            Markdown-formatted help text grouped by category.
        """
        bindings = self.get_bindings_for_scope(scope)

        by_category: dict[Category, list[tuple[KeyBinding, Command]]] = {}
        for binding in bindings:
            cmd = binding.command
            if cmd is None:
                continue
            by_category.setdefault(cmd.category, []).append((binding, cmd))

        lines = []
        for category in Category:
            items = by_category.get(category)
            if not items:
                continue
            lines.append(f"\n## {category.value}")
            for binding, cmd in items:
                emoji = f"{cmd.emoji} " if cmd.emoji else ""
                lines.append(f"- **{binding.display_key}** - {emoji}{cmd.description}")

        return "\n".join(lines)

    def load_keybindings(self) -> None:
        """Load keybindings from the config directory and/or defaults.

        This method first attempts to load keybindings from the user's config
        directory. If the file doesn't exist or is invalid, it falls back to
        the default keybindings.

        After loading, the registry will contain a complete set of bindings, with
        user-defined bindings taking precedence over defaults, and any missing bindings
        filled in from the defaults.
        """

        # Read bindings from config file first
        filepath = get_config_dir() / "keybindings.json"

        # If the file doesn't exist, keep defaults and return early
        if not filepath.exists():
            self._bindings = dict(DEFAULT_BINDINGS)
            return

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Failed to load keybindings from %s: %s", filepath, e)
            return

        if not isinstance(data, list):
            log.warning("keybindings.json: expected a JSON array, got %s", type(data).__name__)
            return

        for entry in data:
            if not isinstance(entry, dict):
                continue
            key_display = entry.get("key", "")
            leader = entry.get("leader", "")
            command = entry.get("command", "")
            scope_str = entry.get("scope", "MainTable")

            if not (cmd := COMMANDS.get(command)):
                log.warning("keybindings.json: unknown command %r, skipping", command)
                continue

            try:
                scope = Scope(scope_str)
            except ValueError:
                log.warning("keybindings.json: unknown scope %r, skipping", scope_str)
                continue

            raw_key = parse_key_display(key_display)
            binding = KeyBinding(leader=leader, key=raw_key, scope=scope, command_id=command)
            self._bindings[binding] = COMMANDS[command]

        # Add any default bindings that weren't overridden by the user config
        for binding, cmd in DEFAULT_BINDINGS.items():
            if binding not in self._bindings:
                self._bindings[binding] = cmd


# ─── Module-level registry instance ──────────────────────────────────────────
key_registry = KeyBindingRegistry()
key_registry.load_keybindings()
