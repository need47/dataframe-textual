"""Command registry for all available actions in the application.

Each command has:
- A unique ID (used as a stable reference for key bindings and dispatch).
- A human-readable description (shown in help and commands sheet).
- A ``cmd`` method name (the ``cmd_*`` method to call on the dispatch target).
- A scope where it is available.
- A category for grouping in help and commands sheets.

The ``cmd`` field is the method name (e.g. ``"cmd_close"``) that will be called
on the appropriate widget/app when dispatched via the key binding registry.
All dispatchable methods use the ``cmd_`` prefix so they are easily identifiable
and can be introspected for dynamic registration.
"""

from dataclasses import dataclass
from enum import Enum


class Scope(str, Enum):
    """Scopes where commands can be active."""

    APP = "App"
    MAIN_TABLE = "MainTable"
    FREQUENCY_SCREEN = "FrequencyScreen"
    ROW_DETAIL_SCREEN = "RowDetailScreen"
    META_COLUMN_SCREEN = "MetaColumnScreen"
    CELL_DETAIL_SCREEN = "CellDetailScreen"
    TABLE_SCREEN = "TableScreen"
    SHEET_SCREEN = "SheetScreen"


class Category(str, Enum):
    """Categories for grouping commands in help and commands sheet."""

    FILE_TAB = "File & Tab Management"
    NAVIGATION = "Navigation"
    UNDO_REDO = "Undo/Redo/Reset"
    DISPLAY = "Display"
    EDITING = "Editing"
    SELECTION = "Row/Column Selection"
    FIND_REPLACE = "Find & Replace"
    FILTER_COLLECT = "Filter & Collect"
    SORTING = "Sorting"
    REORDER = "Reorder"
    TYPE_CASTING = "Type Casting"
    COPY = "Copy"
    SQL = "SQL Interface"
    VIEW_SETTINGS = "View & Settings"


@dataclass(frozen=True, eq=False)
class Command:
    """A registered command in the application.

    Attributes:
        cmd: Unique command identifier using hyphens (e.g., ``"toggle-rid"``).
            The corresponding ``cmd_*`` method name is derived automatically.
        description: Human-readable description of what the command does.
        scope: Scope where this command is available.
        category: Category for grouping in help displays.
        emoji: Optional emoji icon for display in help text.
    """

    cmd: str
    description: str
    scope: Scope
    category: Category
    emoji: str = ""

    def __eq__(self, other: object) -> bool:
        """Compare commands by command identifier and scope."""
        if not isinstance(other, Command):
            return NotImplemented
        return (self.cmd, self.scope) == (other.cmd, other.scope)

    def __hash__(self) -> int:
        """Hash commands by command identifier and scope."""
        return hash((self.cmd, self.scope))

    @property
    def method_name(self) -> str:
        """Derive the ``cmd_*`` method name from the command identifier.

        Returns:
            The Python method name (e.g., ``"cmd_toggle_rid"`` for ``"toggle-rid"``).
        """
        return f"cmd_{self.cmd.replace('-', '_')}"


# fmt: off
# ─── All registered commands ──────────────────────────────────────────────────

COMMANDS: dict[str, Command] = {}


def _reg(cmd: str, description: str, scope: Scope, category: Category, emoji: str = "") -> None:
    """Register a command in the global registry."""
    COMMANDS[cmd] = Command(cmd=cmd, description=description, scope=scope, category=category, emoji=emoji)


# ═══════════════════════════════════════════════════════════════════════════════
# File & Tab Management (App scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("close",              "Quit tab (prompts to save unsaved changes) or view",  Scope.APP, Category.FILE_TAB, "🚪")
_reg("close-all",          "Quit all tabs (prompts to save unsaved changes)",     Scope.APP, Category.FILE_TAB, "🚪")
_reg("force-quit",         "Force quit app (discards unsaved changes)",           Scope.APP, Category.FILE_TAB, "⚠️")
_reg("toggle-tab-bar",     "Toggle tab bar visibility",                           Scope.APP, Category.FILE_TAB, "👁️")
_reg("prev-tab",           "Previous Tab",                                        Scope.APP, Category.FILE_TAB, "⏮️")
_reg("next-tab",           "Next Tab",                                            Scope.APP, Category.FILE_TAB, "⏭️")
_reg("move-tab-left",      "Move current tab left (wrap to last)",                Scope.APP, Category.FILE_TAB, "◀️")
_reg("move-tab-right",     "Move current tab right (wrap to first)",              Scope.APP, Category.FILE_TAB, "▶️")
_reg("save-current-tab",   "Save current tab (or current view) to file",          Scope.APP, Category.FILE_TAB, "💾")
_reg("save-all-tabs",      "Save all tabs to file",                               Scope.APP, Category.FILE_TAB, "💾")
_reg("save-tab-overwrite", "Save current tab to file (overwrite without prompt)", Scope.APP, Category.FILE_TAB, "💾")
_reg("save-all-overwrite", "Save all tabs to file (overwrite without prompt)",    Scope.APP, Category.FILE_TAB, "💾")
_reg("duplicate-tab",      "Duplicate current tab",                               Scope.APP, Category.FILE_TAB, "📋")
_reg("open-file",          "Open a file",                                         Scope.APP, Category.FILE_TAB, "📁")
_reg("new-tab",            "Create new tab from Polars expression",               Scope.APP, Category.FILE_TAB, "📋")

# ═══════════════════════════════════════════════════════════════════════════════
# View & Settings (App scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("show-sheets",           "Show all open sheets/tabs",          Scope.APP, Category.VIEW_SETTINGS, "📋")
_reg("toggle-help-panel",     "Toggle help panel",                  Scope.APP, Category.VIEW_SETTINGS, "❓")
_reg("toggle-python-console", "Toggle Python console",              Scope.APP, Category.VIEW_SETTINGS, "🐍")
_reg("select-theme",          "Select theme",                       Scope.APP, Category.VIEW_SETTINGS, "🎨")
_reg("show-commands",         "Show all commands and key bindings", Scope.APP, Category.VIEW_SETTINGS, "⌨️")

# ═══════════════════════════════════════════════════════════════════════════════
# Navigation (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("cursor-left",   "Move cursor left",           Scope.MAIN_TABLE, Category.NAVIGATION, "🎯")
_reg("cursor-down",   "Move cursor down",           Scope.MAIN_TABLE, Category.NAVIGATION, "🎯")
_reg("cursor-up",     "Move cursor up",             Scope.MAIN_TABLE, Category.NAVIGATION, "🎯")
_reg("cursor-right",  "Move cursor right",          Scope.MAIN_TABLE, Category.NAVIGATION, "🎯")
_reg("go-top",        "Go to first row",            Scope.MAIN_TABLE, Category.NAVIGATION, "⬆️")
_reg("go-bottom",     "Go to last row",             Scope.MAIN_TABLE, Category.NAVIGATION, "⬇️")
_reg("go-to-row",     "Go to row",                  Scope.MAIN_TABLE, Category.NAVIGATION, "🎯")
_reg("page-backward", "Page backward",              Scope.MAIN_TABLE, Category.NAVIGATION, "📜")
_reg("page-forward",  "Page forward",               Scope.MAIN_TABLE, Category.NAVIGATION, "📜")
_reg("scroll-home",   "Scroll to leftmost column",  Scope.MAIN_TABLE, Category.NAVIGATION, "⬅️")
_reg("scroll-end",    "Scroll to rightmost column", Scope.MAIN_TABLE, Category.NAVIGATION, "➡️")
_reg("scroll-top",    "Scroll to first row",        Scope.MAIN_TABLE, Category.NAVIGATION, "⬆️")
_reg("scroll-bottom", "Scroll to last row",         Scope.MAIN_TABLE, Category.NAVIGATION, "⬇️")

# ═══════════════════════════════════════════════════════════════════════════════
# Undo/Redo/Reset (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("undo",  "Undo last action",        Scope.MAIN_TABLE, Category.UNDO_REDO, "↩️")
_reg("redo",  "Redo last undone action", Scope.MAIN_TABLE, Category.UNDO_REDO, "🔄")
_reg("reset", "Reset to initial state",  Scope.MAIN_TABLE, Category.UNDO_REDO, "🔁")

# ═══════════════════════════════════════════════════════════════════════════════
# Display (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("view-row-detail",           "Show row details in modal",                                         Scope.MAIN_TABLE, Category.DISPLAY, "📋")
_reg("view-cell-detail",          "Show current cell details in modal",                                Scope.MAIN_TABLE, Category.DISPLAY, "🔍")
_reg("show-frequency",            "Show frequency distribution for current/selected columns",          Scope.MAIN_TABLE, Category.DISPLAY, "📊")
_reg("show-histogram",            "Show histogram for current column",                                 Scope.MAIN_TABLE, Category.DISPLAY, "📊")
_reg("show-histogram-custom",     "Show histogram for current column with custom bins",                Scope.MAIN_TABLE, Category.DISPLAY, "📊")
_reg("show-statistics",           "Show statistics for current column",                                Scope.MAIN_TABLE, Category.DISPLAY, "📈")
_reg("show-statistics-all",       "Show statistics for entire dataframe",                              Scope.MAIN_TABLE, Category.DISPLAY, "📊")
_reg("cycle-cursor-type",         "Cycle cursor type (cell → row → column)",                          Scope.MAIN_TABLE, Category.DISPLAY, "🎯")
_reg("show-bar",                  "Show bar chart (first selected col as label, cursor col as value)", Scope.MAIN_TABLE, Category.DISPLAY, "📊")
_reg("metadata-column",           "Show column metadata (ID, name, type)",                             Scope.MAIN_TABLE, Category.DISPLAY, "📋")
_reg("hide-column",               "Hide selected columns or current column",                           Scope.MAIN_TABLE, Category.DISPLAY, "👁️")
_reg("hide-column-before",        "Hide current column and those before",                              Scope.MAIN_TABLE, Category.DISPLAY, "👁️")
_reg("hide-column-after",         "Hide current column and those after",                               Scope.MAIN_TABLE, Category.DISPLAY, "👁️")
_reg("show-hidden-columns",       "Show all hidden columns",                                           Scope.MAIN_TABLE, Category.DISPLAY, "👀")
_reg("expand-column",             "Toggle column full width for current column",                       Scope.MAIN_TABLE, Category.DISPLAY, "📏")
_reg("expand-all-columns",        "Toggle column full width for all string/list columns",              Scope.MAIN_TABLE, Category.DISPLAY, "📏")
_reg("toggle-freeze",             "Freeze rows and/or columns",                                        Scope.MAIN_TABLE, Category.DISPLAY, "📌")
_reg("toggle-column-index",       "Toggle column index prefix",                                        Scope.MAIN_TABLE, Category.DISPLAY, "🏷️")
_reg("set-row-as-header",         "Mark current row as header",                                        Scope.MAIN_TABLE, Category.DISPLAY, "📌")
_reg("toggle-rid",                "Toggle internal row index (RID)",                                   Scope.MAIN_TABLE, Category.DISPLAY, "🆔")
_reg("toggle-thousand-separator", "Toggle thousand separator for current column",                      Scope.MAIN_TABLE, Category.DISPLAY, "🔢")
_reg("decrease-float-precision",  "Decrease float precision for current column",                       Scope.MAIN_TABLE, Category.DISPLAY, "🔢")
_reg("increase-float-precision",  "Increase float precision for current column",                       Scope.MAIN_TABLE, Category.DISPLAY, "🔢")

# ═══════════════════════════════════════════════════════════════════════════════
# Editing (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("edit-cell",            "Edit current cell",                                        Scope.MAIN_TABLE, Category.EDITING, "✏️")
_reg("edit-column",          "Edit entire column with expression",                       Scope.MAIN_TABLE, Category.EDITING, "✏️")
_reg("add-column",           "Add empty column after current",                           Scope.MAIN_TABLE, Category.EDITING, "➕")
_reg("add-column-expr",      "Add column with name and optional expression",             Scope.MAIN_TABLE, Category.EDITING, "➕")
_reg("add-index-column",     "Add an index column after current",                        Scope.MAIN_TABLE, Category.EDITING, "➕")
_reg("add-link-column",      "Add a link column after current",                          Scope.MAIN_TABLE, Category.EDITING, "➕")
_reg("rename-column",        "Rename current column",                                    Scope.MAIN_TABLE, Category.EDITING, "✏️")
_reg("delete-row",           "Delete current row",                                       Scope.MAIN_TABLE, Category.EDITING, "✖️")
_reg("delete-row-above",     "Delete row and those above",                               Scope.MAIN_TABLE, Category.EDITING, "✖️")
_reg("delete-row-below",     "Delete row and those below",                               Scope.MAIN_TABLE, Category.EDITING, "✖️")
_reg("clear-cell",           "Clear current cell (set to NULL)",                         Scope.MAIN_TABLE, Category.EDITING, "✖️")
_reg("clear-column",         "Clear current column (set matching cells to NULL)",        Scope.MAIN_TABLE, Category.EDITING, "✖️")
_reg("delete-column",        "Delete selected columns or current column",                Scope.MAIN_TABLE, Category.EDITING, "✖️")
_reg("delete-column-before", "Delete column and those before current column",            Scope.MAIN_TABLE, Category.EDITING, "✖️")
_reg("delete-column-after",  "Delete column and those after current column",             Scope.MAIN_TABLE, Category.EDITING, "✖️")
_reg("duplicate-row",        "Duplicate current row",                                    Scope.MAIN_TABLE, Category.EDITING, "📋")
_reg("duplicate-column",     "Duplicate current column",                                 Scope.MAIN_TABLE, Category.EDITING, "📋")
_reg("remove-duplicates",    "Remove duplicate rows (keep first occurrence)",            Scope.MAIN_TABLE, Category.EDITING, "🧹")
_reg("transpose",            "Transpose table (swap rows/columns)",                      Scope.MAIN_TABLE, Category.EDITING, "🔃")
_reg("expand-list-column",   "Expand current list column into indexed columns",          Scope.MAIN_TABLE, Category.EDITING, "🧩")
_reg("contract-list-column", "Contract indexed sibling columns back into a list column", Scope.MAIN_TABLE, Category.EDITING, "🧩")
_reg("explode-column",       "Explode current list column into rows",                    Scope.MAIN_TABLE, Category.EDITING, "💥")
_reg("explode-column-delim", "Explode current column by delimiter into rows",            Scope.MAIN_TABLE, Category.EDITING, "💥")
_reg("split-column",         "Split current column into a new column by delimiter",      Scope.MAIN_TABLE, Category.EDITING, "✂️")
_reg("join-columns",         "Join all selected columns into a new column",              Scope.MAIN_TABLE, Category.EDITING, "🔗")
_reg("glue-list-column",     "Glue list column values with separator",                   Scope.MAIN_TABLE, Category.EDITING, "🔗")
_reg("upper-case-column",    "Convert current or selected column(s) to uppercase",       Scope.MAIN_TABLE, Category.EDITING, "🔠")
_reg("lower-case-column",    "Convert current or selected column(s) to lowercase",       Scope.MAIN_TABLE, Category.EDITING, "🔡")
_reg("strip-whitespace",     "Strip leading and trailing whitespaces in current column", Scope.MAIN_TABLE, Category.EDITING, "🧼")

# ═══════════════════════════════════════════════════════════════════════════════
# Row/Column Selection (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("select-rows",            "Select rows matching cursor value in current column",      Scope.MAIN_TABLE, Category.SELECTION, "✅")
_reg("select-rows-all",        "Select rows matching cursor value in all columns",         Scope.MAIN_TABLE, Category.SELECTION, "✅")
_reg("select-rows-expr",       "Select rows where expression matches in current column",   Scope.MAIN_TABLE, Category.SELECTION, "✅")
_reg("select-rows-expr-all",   "Select rows where expression matches in all columns",      Scope.MAIN_TABLE, Category.SELECTION, "✅")
_reg("unselect-rows-expr",     "Unselect rows where expression matches in current column", Scope.MAIN_TABLE, Category.SELECTION, "➖")
_reg("unselect-rows-expr-all", "Unselect rows where expression matches in all columns",    Scope.MAIN_TABLE, Category.SELECTION, "➖")
_reg("toggle-selection-row",   "Select/deselect current row",                              Scope.MAIN_TABLE, Category.SELECTION, "✅")
_reg("toggle-selection-col",   "Select/deselect current column",                           Scope.MAIN_TABLE, Category.SELECTION, "✅")
_reg("toggle-selections",      "Toggle row selection (invert all)",                        Scope.MAIN_TABLE, Category.SELECTION, "💡")
_reg("clear-selections",       "Clear all row/column selections and cell matches",         Scope.MAIN_TABLE, Category.SELECTION, "🧹")
_reg("prev-selected-row",      "Go to previous selected row",                              Scope.MAIN_TABLE, Category.SELECTION, "⬆️")
_reg("next-selected-row",      "Go to next selected row",                                  Scope.MAIN_TABLE, Category.SELECTION, "⬇️")
_reg("unselect-current-row",   "Unselect the current row",                                 Scope.MAIN_TABLE, Category.SELECTION, "➖")
_reg("unselect-all-rows",      "Unselect all rows",                                        Scope.MAIN_TABLE, Category.SELECTION, "➖")

# ═══════════════════════════════════════════════════════════════════════════════
# Find & Replace (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("find-forward",         "Search forward in current column with expression",    Scope.MAIN_TABLE, Category.FIND_REPLACE, "🔎")
_reg("find-forward-all",     "Search forward in all columns with expression",       Scope.MAIN_TABLE, Category.FIND_REPLACE, "🌐")
_reg("find-forward-cursor",  "Search forward in current column with cursor value",  Scope.MAIN_TABLE, Category.FIND_REPLACE, "🔎")
_reg("find-backward",        "Search backward in current column with expression",   Scope.MAIN_TABLE, Category.FIND_REPLACE, "🔎")
_reg("find-backward-all",    "Search backward in all columns with expression",      Scope.MAIN_TABLE, Category.FIND_REPLACE, "🌐")
_reg("find-backward-cursor", "Search backward in current column with cursor value", Scope.MAIN_TABLE, Category.FIND_REPLACE, "🔎")
_reg("next-match",           "Go to next match",                                    Scope.MAIN_TABLE, Category.FIND_REPLACE, "⬇️")
_reg("prev-match",           "Go to previous match",                                Scope.MAIN_TABLE, Category.FIND_REPLACE, "⬆️")
_reg("replace-column",       "Replace in current column (interactive or all)",      Scope.MAIN_TABLE, Category.FIND_REPLACE, "🔄")
_reg("replace-all-columns",  "Replace across all columns (interactive or all)",     Scope.MAIN_TABLE, Category.FIND_REPLACE, "🔄")

# ═══════════════════════════════════════════════════════════════════════════════
# Filter & Collect (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("filter-rows",         "Filter rows with cursor value in current column",    Scope.MAIN_TABLE, Category.FILTER_COLLECT, "⏬")
_reg("filter-rows-expr",    "Filter rows with expression",                        Scope.MAIN_TABLE, Category.FILTER_COLLECT, "⏬")
_reg("filter-rows-nonnull", "Filter rows with non-null values in current column", Scope.MAIN_TABLE, Category.FILTER_COLLECT, "⏬")
_reg("filter-rows-null",    "Filter rows with null values in current column",     Scope.MAIN_TABLE, Category.FILTER_COLLECT, "⏬")
_reg("filter-rows-value",   "Filter rows by column value",                        Scope.MAIN_TABLE, Category.FILTER_COLLECT, "⏬")
_reg("collect-rows",        "Collect rows to a new tab",                          Scope.MAIN_TABLE, Category.FILTER_COLLECT, "📤")

# ═══════════════════════════════════════════════════════════════════════════════
# Sorting (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("sort-ascending",  "Sort column ascending",  Scope.MAIN_TABLE, Category.SORTING, "🔼")
_reg("sort-descending", "Sort column descending", Scope.MAIN_TABLE, Category.SORTING, "🔽")

# ═══════════════════════════════════════════════════════════════════════════════
# Reorder (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("move-row-up",       "Move row to up",       Scope.MAIN_TABLE, Category.REORDER, "⬆️")
_reg("move-row-down",     "Move row to down",     Scope.MAIN_TABLE, Category.REORDER, "⬇️")
_reg("move-row-top",      "Move row to top",      Scope.MAIN_TABLE, Category.REORDER, "⏫")
_reg("move-row-bottom",   "Move row to bottom",   Scope.MAIN_TABLE, Category.REORDER, "⏬")
_reg("move-column-left",  "Move column to left",  Scope.MAIN_TABLE, Category.REORDER, "⬅️")
_reg("move-column-right", "Move column to right", Scope.MAIN_TABLE, Category.REORDER, "➡️")
_reg("move-column-start", "Move column to start", Scope.MAIN_TABLE, Category.REORDER, "⏮️")
_reg("move-column-end",   "Move column to end",   Scope.MAIN_TABLE, Category.REORDER, "⏭️")

# ═══════════════════════════════════════════════════════════════════════════════
# Type Casting (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("cast-integer", "Cast column to integer", Scope.MAIN_TABLE, Category.TYPE_CASTING, "🔢")
_reg("cast-float",   "Cast column to float",   Scope.MAIN_TABLE, Category.TYPE_CASTING, "🔢")
_reg("cast-boolean", "Cast column to boolean", Scope.MAIN_TABLE, Category.TYPE_CASTING, "✅")
_reg("cast-string",  "Cast column to string",  Scope.MAIN_TABLE, Category.TYPE_CASTING, "📝")
_reg("cast-date",    "Cast column to date",    Scope.MAIN_TABLE, Category.TYPE_CASTING, "📅")

# ═══════════════════════════════════════════════════════════════════════════════
# Copy (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("copy-cell",   "Copy cell to clipboard",                Scope.MAIN_TABLE, Category.COPY, "📋")
_reg("copy-column", "Copy column to clipboard",              Scope.MAIN_TABLE, Category.COPY, "📊")
_reg("copy-row",    "Copy row to clipboard (tab-separated)", Scope.MAIN_TABLE, Category.COPY, "📝")

# ═══════════════════════════════════════════════════════════════════════════════
# SQL Interface (MainTable scope)
# ═══════════════════════════════════════════════════════════════════════════════

_reg("sql-advanced", "Open advanced SQL interface (full SQL queries)",            Scope.MAIN_TABLE, Category.SQL,           "🔎")
_reg("sql-simple",   "Open simple SQL interface (select columns & where clause)", Scope.MAIN_TABLE, Category.SQL,           "💬")
_reg("run-command",  "Run a command by name with optional arguments",             Scope.MAIN_TABLE, Category.VIEW_SETTINGS, "▶️")

# fmt: on


def get_commands_by_scope(scope: Scope) -> list[Command]:
    """Get all commands available in a given scope."""
    return [cmd for cmd in COMMANDS.values() if cmd.scope == scope]


def get_commands_by_category(category: Category) -> list[Command]:
    """Get all commands in a given category."""
    return [cmd for cmd in COMMANDS.values() if cmd.category == category]
