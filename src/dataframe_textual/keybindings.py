"""Key binding registry for mapping keys to commands.

Keybindings map physical key presses (with optional leader-key prefixes) to command IDs.
Bindings must be unique within a given scope (same key + leader + scope = conflict).
Bindings may share the same key across different scopes.

The default bindings defined here mirror the existing hard-coded bindings.
Users can override them via a config file or change them at runtime.

Dispatch flow:
1. ``on_key()`` receives a key event
2. It calls ``registry.dispatch(key, leader, scope, target)``
3. The registry looks up the binding → finds the command → calls ``target.cmd_*()``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .commands import COMMANDS, Category, Command, Scope

log = logging.getLogger(__name__)


class KeyBindingConflict(Exception):
    """Raised when a new binding conflicts with an existing one.

    Attributes:
        existing: The existing binding that conflicts.
        attempted: The binding that was attempted.
    """

    def __init__(self, existing: "KeyBinding", attempted: "KeyBinding") -> None:
        self.existing = existing
        self.attempted = attempted
        super().__init__(
            f"Key '{attempted.display_key}' (scope={attempted.scope.value}) is already bound to '{existing.command_id}'"
        )


@dataclass(frozen=True)
class KeyBinding:
    """A key binding that maps a key (with optional leader prefix) to a command.

    Attributes:
        key: The Textual key name (e.g. "q", "ctrl+g", "slash").
        command_id: The ID of the command this binding triggers.
        leader: Optional leader key prefix ("g" or "z"). Empty string means no leader.
        scope: The scope where this binding is active.
    """

    key: str
    command_id: str
    leader: str = ""
    scope: Scope = Scope.MAIN_TABLE

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


def format_key_display(key: str) -> str:
    """Convert a Textual key name to a human-friendly display string."""
    key_map = {
        "circumflex_accent": "^",
        "grave_accent": "`",
        "underscore": "_",
        "minus": "-",
        "full_stop": ".",
        "comma": ",",
        "colon": ":",
        "slash": "/",
        "question_mark": "?",
        "left_square_bracket": "[",
        "right_square_bracket": "]",
        "left_curly_bracket": "{",
        "right_curly_bracket": "}",
        "left_parenthesis": "(",
        "right_parenthesis": ")",
        "less_than_sign": "<",
        "greater_than_sign": ">",
        "equals_sign": "=",
        "number_sign": "#",
        "percent_sign": "%",
        "dollar_sign": "$",
        "tilde": "~",
        "at": "@",
        "asterisk": "*",
        "vertical_line": "|",
        "backslash": "\\",
        "apostrophe": "'",
        "quotation_mark": '"',
        "enter": "Enter",
        "tab": "Tab",
        "escape": "Escape",
        "delete": "Delete",
        "home": "Home",
        "end": "End",
        "pageup": "PgUp",
        "pagedown": "PgDn",
        "up": "↑",
        "down": "↓",
        "left": "←",
        "right": "→",
        "shift+up": "Shift+↑",
        "shift+down": "Shift+↓",
        "shift+left": "Shift+←",
        "shift+right": "Shift+→",
        "shift+delete": "Shift+Delete",
        "f1": "F1",
    }

    if key in key_map:
        return key_map[key]

    if key.startswith("ctrl+"):
        return f"Ctrl+{key[5:].upper()}"

    return key


# ─── Default key bindings ─────────────────────────────────────────────────────

DEFAULT_BINDINGS: list[KeyBinding] = []


def _bind(key: str, command_id: str, leader: str = "", scope: Scope = Scope.MAIN_TABLE) -> None:
    """Create and register a default key binding."""
    DEFAULT_BINDINGS.append(KeyBinding(key=key, command_id=command_id, leader=leader, scope=scope))


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

    def __init__(self, bindings: list[KeyBinding] | None = None) -> None:
        """Initialize the registry with a set of bindings.

        Args:
            bindings: Initial list of bindings. Uses DEFAULT_BINDINGS if None.
        """
        self._bindings: list[KeyBinding] = list(bindings or DEFAULT_BINDINGS)
        self._index: dict[tuple[str, str, Scope], KeyBinding] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Rebuild the lookup index from the current binding list."""
        self._index.clear()
        for binding in self._bindings:
            index_key = (binding.key, binding.leader, binding.scope)
            self._index[index_key] = binding

    def lookup(self, key: str, leader: str = "", scope: Scope = Scope.MAIN_TABLE) -> KeyBinding | None:
        """Look up a binding by key, leader, and scope.

        Args:
            key: The Textual key name.
            leader: The leader key prefix (empty string for none).
            scope: The scope to search in.

        Returns:
            The matching KeyBinding, or None if not found.
        """
        return self._index.get((key, leader, scope))

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
        binding = self.lookup(key, leader, scope)
        if binding is None:
            return False

        cmd = binding.command
        if cmd is None:
            log.warning("Binding %s references unknown command %r", binding.display_key, binding.command_id)
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
        return [b for b in self._bindings if b.command_id == command_id]

    def get_bindings_for_scope(self, scope: Scope) -> list[KeyBinding]:
        """Get all bindings active in a given scope."""
        return [b for b in self._bindings if b.scope == scope]

    def set_binding(self, key: str, command_id: str, leader: str = "", scope: Scope = Scope.MAIN_TABLE) -> None:
        """Add or replace a binding (no conflict check).

        If a binding already exists for the same key+leader+scope, it is replaced.
        For conflict-aware binding, use ``bind()`` instead.
        """
        new_binding = KeyBinding(key=key, command_id=command_id, leader=leader, scope=scope)
        lookup_key = (key, leader, scope)
        self._bindings = [b for b in self._bindings if (b.key, b.leader, b.scope) != lookup_key]
        self._bindings.append(new_binding)
        self._index[lookup_key] = new_binding

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

        new_binding = KeyBinding(key=key, command_id=command_id, leader=leader, scope=scope)
        lookup_key = (key, leader, scope)
        existing = self._index.get(lookup_key)

        if existing is not None:
            if not force:
                raise KeyBindingConflict(existing, new_binding)
            # Force replace — remove old binding
            self._bindings = [b for b in self._bindings if (b.key, b.leader, b.scope) != lookup_key]

        self._bindings.append(new_binding)
        self._index[lookup_key] = new_binding
        return existing

    def remove_binding(self, key: str, leader: str = "", scope: Scope = Scope.MAIN_TABLE) -> bool:
        """Remove a binding by key+leader+scope. Returns True if found."""
        lookup_key = (key, leader, scope)
        if lookup_key in self._index:
            del self._index[lookup_key]
            self._bindings = [b for b in self._bindings if (b.key, b.leader, b.scope) != lookup_key]
            return True
        return False

    @property
    def bindings(self) -> list[KeyBinding]:
        """Get all registered bindings."""
        return list(self._bindings)

    def get_all_with_commands(self) -> list[tuple[KeyBinding, Command]]:
        """Get all bindings paired with their associated commands."""
        result = []
        for binding in self._bindings:
            cmd = binding.command
            if cmd is not None:
                result.append((binding, cmd))
        return result

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


# ─── Module-level registry instance ──────────────────────────────────────────
key_registry = KeyBindingRegistry()
