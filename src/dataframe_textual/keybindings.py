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
    "enter": "Enter",
    "backspace": "Backspace",
    "escape": "Escape",
    "tab": "Tab",
    "delete": "Delete",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "space": "Space",
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
    "less_than_sign": "<",
    "comma": ",",
    "greater_than_sign": ">",
    "full_stop": ".",
    "question_mark": "?",
    "slash": "/",
}


def format_key_display(key: str) -> str:
    """Convert a Textual key name to a human-friendly display string."""
    if key in _KEY_DISPLAY_MAP:
        return _KEY_DISPLAY_MAP[key]

    if "+" in key:
        parts = key.split("+")
        display_parts = []
        for part in parts:
            if part in _MODIFIER_DISPLAY_MAP:
                display_parts.append(_MODIFIER_DISPLAY_MAP[part])
            elif part in _KEY_DISPLAY_MAP:
                display_parts.append(_KEY_DISPLAY_MAP[part])
            elif len(part) == 1:
                display_parts.append(part.upper())
            else:
                display_parts.append(part)
        return "+".join(display_parts)

    return key


# Reverse mapping: display string -> Textual key name
_DISPLAY_TO_KEY: dict[str, str] = {v: k for k, v in _KEY_DISPLAY_MAP.items()}

_MODIFIER_DISPLAY_MAP: dict[str, str] = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "meta": "Meta",
}

_DISPLAY_TO_MODIFIER: dict[str, str] = {display: key for key, display in _MODIFIER_DISPLAY_MAP.items()}


def parse_key_display(display: str) -> str:
    """Convert a human-friendly display string back to a Textual key name.

    Args:
        display: The display string (e.g. "^", "Ctrl+T", "Enter").

    Returns:
        The Textual key name (e.g. "circumflex_accent", "ctrl+t", "enter").
    """
    if display in _DISPLAY_TO_KEY:
        return _DISPLAY_TO_KEY[display]

    if "+" in display:
        parts = display.split("+")
        key_parts = []
        for part in parts:
            if part in _DISPLAY_TO_MODIFIER:
                key_parts.append(_DISPLAY_TO_MODIFIER[part])
            elif part in _DISPLAY_TO_KEY:
                key_parts.append(_DISPLAY_TO_KEY[part])
            elif len(part) == 1:
                key_parts.append(part.lower())
            else:
                key_parts.append(part)
        return "+".join(key_parts)

    return display


# ─── Default key bindings ─────────────────────────────────────────────────────

DEFAULT_BINDINGS: dict[KeyBinding, Command] = {}


def _build_default_bindings() -> None:
    """Build DEFAULT_BINDINGS from COMMANDS.bindings (auto-generated from commands.py).

    This function is called after all commands are registered and their bindings are set.
    Each command specifies its key bindings, which are then converted to KeyBinding objects.
    """
    for cmd in COMMANDS.values():
        for key, leader in cmd.bindings:
            raw_key = parse_key_display(key)
            binding = KeyBinding(leader=leader or "", key=raw_key, scope=cmd.scope, command_id=cmd.cmd)
            if binding in DEFAULT_BINDINGS:
                existing_cmd = DEFAULT_BINDINGS[binding]
                log.warning(
                    f"Default binding conflict: {binding.display_key!r} already bound to "
                    f"'{existing_cmd.cmd}', cannot bind to '{cmd.cmd}'"
                )
                continue
            DEFAULT_BINDINGS[binding] = cmd


# ═══════════════════════════════════════════════════════════════════════════════
# Build default bindings from commands.py definitions
# ═══════════════════════════════════════════════════════════════════════════════
# All key bindings are now defined in commands.py via .bind() chains on command registration.
# This function populates DEFAULT_BINDINGS from those definitions.

_build_default_bindings()


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
                f"Command {cmd.cmd!r} wants method {cmd.method_name!r} but "
                f"target {type(target).__name__!r} has no such method"
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
        """

        # Read bindings from user config file first
        filepath = get_config_dir() / "keybindings.json"

        # If the file doesn't exist, use defaults
        if not filepath.exists():
            self._bindings = dict(DEFAULT_BINDINGS)
            return

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning(f"Failed to load keybindings from {filepath}: {e}")
            return

        if not isinstance(data, list):
            log.warning(f"keybindings.json: expected a JSON array, got {type(data).__name__}")
            return

        for entry in data:
            if not isinstance(entry, dict):
                continue
            key_display = entry.get("key", "")
            leader = entry.get("leader", "")
            command = entry.get("command", "")
            scope_str = entry.get("scope", "")

            if not (cmd := COMMANDS.get(command)):
                log.warning(f"keybindings.json: unknown command {command!r}, skipping")
                continue

            try:
                scope = Scope(scope_str)
            except ValueError:
                log.warning(f"keybindings.json: unknown scope {scope_str!r}, skipping")
                continue

            raw_key = parse_key_display(key_display)
            binding = KeyBinding(leader=leader, key=raw_key, scope=scope, command_id=command)
            self._bindings[binding] = cmd


# ─── Module-level registry instance ──────────────────────────────────────────
key_registry = KeyBindingRegistry()
key_registry.load_keybindings()
