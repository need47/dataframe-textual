"""Common utilities and constants for dataframe_viewer."""

import re
from dataclasses import dataclass
from typing import Any

import polars as pl
from rich.text import Text

# Boolean string mappings
BOOLS = {
    "true": True,
    "t": True,
    "yes": True,
    "y": True,
    "1": True,
    "false": False,
    "f": False,
    "no": False,
    "n": False,
    "0": False,
}

# itype is used by Input widget for input validation
# fmt: off
STYLES = {
    "Int64": {"style": "cyan", "justify": "right", "itype": "integer", "convert": int},
    "Float64": {"style": "magenta", "justify": "right", "itype": "number", "convert": float},
    "String": {"style": "green", "justify": "left", "itype": "text", "convert": str},
    "Boolean": {"style": "blue", "justify": "center", "itype": "text", "convert": lambda x: BOOLS[x.lower()]},
    "Date": {"style": "blue", "justify": "center", "itype": "text", "convert": str},
    "Datetime": {"style": "blue", "justify": "center", "itype": "text", "convert": str},
}
# fmt: on


@dataclass
class DtypeConfig:
    style: str
    justify: str
    itype: str
    convert: Any

    def __init__(self, dtype: pl.DataType):
        dc = STYLES.get(str(dtype), {"style": "", "justify": "", "itype": "text", "convert": str})
        self.style = dc["style"]
        self.justify = dc["justify"]
        self.itype = dc["itype"]
        self.convert = dc["convert"]


# Subscript digits mapping for sort indicators
SUBSCRIPT_DIGITS = {
    0: "₀",
    1: "₁",
    2: "₂",
    3: "₃",
    4: "₄",
    5: "₅",
    6: "₆",
    7: "₇",
    8: "₈",
    9: "₉",
}

# Cursor types ("none" removed)
CURSOR_TYPES = ["row", "column", "cell"]

# Pagination settings
INITIAL_BATCH_SIZE = 100  # Load this many rows initially
BATCH_SIZE = 50  # Load this many rows when scrolling


def _format_row(vals, dtypes, apply_justify=True) -> list[Text]:
    """Format a single row with proper styling and justification.

    Args:
        vals: The list of values in the row.
        dtypes: The list of data types corresponding to each value.
        apply_justify: Whether to apply justification styling. Defaults to True.
    """
    formatted_row = []

    for val, dtype in zip(vals, dtypes, strict=True):
        dc = DtypeConfig(dtype)

        # Format the value
        if val is None:
            text_val = "-"
        elif str(dtype).startswith("Float"):
            text_val = f"{val:.4g}"
        else:
            text_val = str(val)

        formatted_row.append(
            Text(
                text_val,
                style=dc.style,
                justify=dc.justify if apply_justify else "",
            )
        )

    return formatted_row


def _rindex(lst: list, value) -> int:
    """Return the last index of value in a list. Return -1 if not found."""
    for i, item in enumerate(reversed(lst)):
        if item == value:
            return len(lst) - 1 - i
    return -1


def _next(lst: list[Any], current, offset=1) -> Any:
    """Return the next item in the list after the current item, cycling if needed."""
    if current not in lst:
        raise ValueError("Current item not in list")
    current_index = lst.index(current)
    next_index = (current_index + offset) % len(lst)
    return lst[next_index]


def parse_polars_expression(expression: str, df: pl.DataFrame, current_col_idx: int) -> str:
    """Parse and convert a filter expression to Polars syntax.

    Replaces column references with Polars col() expressions:
    - $_ - Current selected column
    - $1, $2, etc. - Column by 1-based index
    - $col_name - Column by name (valid identifier starting with _ or letter)

    Examples:
    - "$_ > 50" -> "pl.col('current_col') > 50"
    - "$1 > 50" -> "pl.col('col0') > 50"
    - "$name == 'Alex'" -> "pl.col('name') == 'Alex'"
    - "$age < $salary" -> "pl.col('age') < pl.col('salary')"

    Args:
        expression: The filter expression as a string.
        df: The DataFrame to validate column references.
        current_col_idx: The index of the currently selected column (0-based). Used for $_ reference.

    Returns:
        A Python expression string with $references replaced by pl.col() calls.

    Raises:
        ValueError: If a column reference is invalid.
    """
    # Early return if no $ present
    # This may be valid Polars expression already
    if "$" not in expression:
        return expression

    # Pattern to match $ followed by either:
    # - _ (single underscore)
    # - digits (integer)
    # - identifier (starts with letter or _, followed by letter/digit/_)
    pattern = r"\$(_|\d+|[a-zA-Z_]\w*)"

    def replace_column_ref(match):
        col_ref = match.group(1)

        if col_ref == "_":
            # Current selected column
            col_name = df.columns[current_col_idx]
        elif col_ref.isdigit():
            # Column by 1-based index
            col_idx = int(col_ref) - 1
            if col_idx < 0 or col_idx >= len(df.columns):
                raise ValueError(f"Column index out of range: ${col_ref}")
            col_name = df.columns[col_idx]
        else:
            # Column by name
            if col_ref not in df.columns:
                raise ValueError(f"Column not found: ${col_ref}")
            col_name = col_ref

        return f"pl.col('{col_name}')"

    result = re.sub(pattern, replace_column_ref, expression)
    return result
