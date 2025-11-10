"""Common utilities and constants for dataframe_viewer."""

import re
from dataclasses import dataclass
from typing import Any

import polars as pl
from rich.text import Text

# Special string to represent null value
NULL = "NULL"
NULL_DISPLAY = "-"

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


@dataclass
class DtypeClass:
    gtype: str  # generic, high-level type
    style: str
    justify: str
    itype: str
    convert: Any


# itype is used by Input widget for input validation
# fmt: off
STYLES = {
    # str
    pl.String: DtypeClass(gtype="string", style="green", justify="left", itype="text", convert=str),
    # int
    pl.Int8: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    pl.Int16: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    pl.Int32: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    pl.Int64: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    pl.Int128: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    pl.UInt8: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    pl.UInt16: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    pl.UInt32: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    pl.UInt64: DtypeClass(gtype="integer", style="cyan", justify="right", itype="integer", convert=int),
    # float
    pl.Float32: DtypeClass(gtype="float", style="magenta", justify="right", itype="number", convert=float),
    pl.Float64: DtypeClass(gtype="float", style="magenta", justify="right", itype="number", convert=float),
    pl.Decimal: DtypeClass(gtype="float", style="magenta", justify="right", itype="number", convert=float),
    # bool
    pl.Boolean: DtypeClass(gtype="boolean", style="blue", justify="center", itype="text", convert=lambda x: BOOLS[x.lower()]),
    # temporal
    pl.Date: DtypeClass(gtype="temporal", style="yellow", justify="center", itype="text", convert=str),
    pl.Datetime: DtypeClass(gtype="temporal", style="yellow", justify="center", itype="text", convert=str),
    pl.Time: DtypeClass(gtype="temporal", style="yellow", justify="center", itype="text", convert=str),
    # unknown
    pl.Unknown: DtypeClass(gtype="unknown", style="", justify="", itype="text", convert=str),
}
# fmt: on


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

# For row index column
RIDX = "^_ridx_^"


def DtypeConfig(dtype: pl.DataType) -> DtypeClass:
    """Get the DtypeClass configuration for a given Polars data type.

    Retrieves styling and formatting configuration based on the Polars data type,
    including style (color), justification, and type conversion function.

    Args:
        dtype: A Polars data type to get configuration for.

    Returns:
        A DtypeClass containing style, justification, input type, and conversion function.
    """
    if dc := STYLES.get(dtype):
        return dc
    elif isinstance(dtype, pl.Datetime):
        return STYLES[pl.Datetime]
    elif isinstance(dtype, pl.Date):
        return STYLES[pl.Date]
    elif isinstance(dtype, pl.Time):
        return STYLES[pl.Time]
    else:
        return STYLES[pl.Unknown]


def format_float(value: float, thousand_separator: bool = False, precision: int = 2) -> str:
    """Format a float value, keeping integers without decimal point.

    Args:
        val: The float value to format.
        thousand_separator: Whether to include thousand separators. Defaults to False.

    Returns:
        The formatted float as a string.
    """

    if (val := int(value)) == value:
        return f"{val:,}" if thousand_separator else str(val)
    else:
        if precision > 0:
            return f"{value:,.{precision}f}" if thousand_separator else f"{value:.{precision}f}"
        else:
            return f"{value:,f}" if thousand_separator else str(value)


def format_row(vals, dtypes, apply_justify=True, thousand_separator=False) -> list[Text]:
    """Format a single row with proper styling and justification.

    Converts raw row values to formatted Rich Text objects with appropriate
    styling (colors), justification, and null value handling based on data types.

    Args:
        vals: The list of values in the row.
        dtypes: The list of data types corresponding to each value.
        apply_justify: Whether to apply justification styling. Defaults to True.

    Returns:
        A list of Rich Text objects with proper formatting applied.
    """
    formatted_row = []

    for val, dtype in zip(vals, dtypes, strict=True):
        dc = DtypeConfig(dtype)

        # Format the value
        if val is None:
            text_val = NULL_DISPLAY
        elif dc.gtype == "integer" and thousand_separator:
            text_val = f"{val:,}"
        elif dc.gtype == "float":
            text_val = format_float(val, thousand_separator)
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


def rindex(lst: list, value) -> int:
    """Return the last index of value in a list. Return -1 if not found.

    Searches through the list in reverse order to find the last occurrence
    of the given value.

    Args:
        lst: The list to search through.
        value: The value to find.

    Returns:
        The index (0-based) of the last occurrence, or -1 if not found.
    """
    for i, item in enumerate(reversed(lst)):
        if item == value:
            return len(lst) - 1 - i
    return -1


def get_next_item(lst: list[Any], current, offset=1) -> Any:
    """Return the next item in the list after the current item, cycling if needed.

    Finds the current item in the list and returns the item at position (current_index + offset),
    wrapping around to the beginning if necessary.

    Args:
        lst: The list to cycle through.
        current: The current item (must be in the list).
        offset: The number of positions to advance. Defaults to 1.

    Returns:
        The next item in the list after advancing by the offset.

    Raises:
        ValueError: If the current item is not found in the list.
    """
    if current not in lst:
        raise ValueError("Current item not in list")
    current_index = lst.index(current)
    next_index = (current_index + offset) % len(lst)
    return lst[next_index]


def parse_polars_expression(expression: str, df: pl.DataFrame, current_col_idx: int) -> str:
    """Parse and convert an expression to Polars syntax.

    Replaces column references with Polars col() expressions:
    - $_ - Current selected column
    - $# - Row index (1-based, requires '^__ridx__^' column to be present)
    - $1, $2, etc. - Column by 1-based index
    - $col_name - Column by name (valid identifier starting with _ or letter)

    Examples:
    - "$_ > 50" -> "pl.col('current_col') > 50"
    - "$# > 10" -> "pl.col('^__ridx__^') > 10"
    - "$1 > 50" -> "pl.col('col0') > 50"
    - "$name == 'Alex'" -> "pl.col('name') == 'Alex'"
    - "$age < $salary" -> "pl.col('age') < pl.col('salary')"

    Args:
        expression: The input expression as a string.
        df: The DataFrame to validate column references.
        current_col_idx: The index of the currently selected column (0-based). Used for $_ reference.

    Returns:
        A Python expression string with $references replaced by pl.col() calls.

    Raises:
        ValueError: If a column reference is invalid.
    """
    # Early return if no $ present
    if "$" not in expression:
        if "pl." in expression:
            # This may be valid Polars expression already
            return expression
        else:
            # Return as a literal string
            return f"pl.lit({expression})"

    # Pattern to match $ followed by either:
    # - _ (single underscore)
    # - # (hash for row index)
    # - digits (integer)
    # - identifier (starts with letter or _, followed by letter/digit/_)
    pattern = r"\$(_|#|\d+|[a-zA-Z_]\w*)"

    def replace_column_ref(match):
        col_ref = match.group(1)

        if col_ref == "_":
            # Current selected column
            col_name = df.columns[current_col_idx]
        elif col_ref == "#":
            # RIDX is used to store 0-based row index; add 1 for 1-based index
            return f"(pl.col('{RIDX}') + 1)"
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


def tentative_expr(term: str) -> bool:
    """Check if the given term could be a Polars expression.

    Heuristically determines whether a string might represent a Polars expression
    based on common patterns like column references ($) or direct Polars syntax (pl.).

    Args:
        term: The string to check.

    Returns:
        True if the term appears to be a Polars expression, False otherwise.
    """
    if "$" in term and not term.endswith("$"):
        return True
    if "pl." in term:
        return True
    return False


def validate_expr(term: str, df: pl.DataFrame, current_col_idx: int) -> pl.Expr | None:
    """Validate and return the expression.

    Parses a user-provided expression string and validates it as a valid Polars expression.
    Converts special syntax like $_ references to proper Polars col() expressions.

    Args:
        term: The input expression as a string.
        df: The DataFrame to validate column references against.
        current_col_idx: The index of the currently selected column (0-based). Used for $_ reference.

    Returns:
        A valid Polars expression object if validation succeeds.

    Raises:
        ValueError: If the expression is invalid, contains non-existent column references, or cannot be evaluated.
    """
    term = term.strip()

    try:
        # Parse the expression
        expr_str = parse_polars_expression(term, df, current_col_idx)

        # Validate by evaluating it
        try:
            expr = eval(expr_str, {"pl": pl})
            if not isinstance(expr, pl.Expr):
                raise ValueError(f"Expression evaluated to `{type(expr).__name__}` instead of a Polars expression")

            # Expression is valid
            return expr
        except Exception as e:
            raise ValueError(f"Failed to evaluate expression `{expr_str}`: {e}") from e
    except Exception as ve:
        raise ValueError(f"Failed to validate expression `{term}`: {ve}") from ve
