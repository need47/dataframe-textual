"""Common utilities and constants for dataframe_viewer."""

import gzip
import json
import os
import re
import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import polars as pl
import xlsxwriter
from rich.text import Text

# Supported file formats
SUPPORTED_FORMATS = {
    "tsv": "\t",
    "csv": ",",
    "psv": "|",
    "xlsx": None,
    "parquet": None,
    "ndjson": None,
    "jsonl": None,
    "json": None,
    "vortex": None,
}


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

# Special string to represent null value
NULL = "NULL"
NULL_DISPLAY = "-"

# Color for highlighting selections and matches
HIGHLIGHT_COLOR = "red"

# Maximum width for columns before truncation
COLUMN_WIDTH_CAP = 35

# Thousand separator for numeric values (must be ',' or '_' per Python's format mini-language)
THOUSAND_SEPARATOR = ","


def with_leader_key(func: Callable) -> Callable:
    """Decorator that resets leader mode after the action completes."""

    def wrapper(self, *args, **kwargs):
        val = func(self, *args, **kwargs)
        self.leader_key = ""
        return val

    return wrapper


def format_float(value: float, thousand_separator: bool = False, precision: int = 2) -> str:
    """Format a float value, keeping integers without decimal point.

    Args:
        value: The float value to format.
        thousand_separator: Whether to include thousand separators. Defaults to False.
        precision: The number of decimal places to display. Defaults to 2.

    Returns:
        The formatted float as a string.
    """

    if precision == 0 and (value_int := int(value)) == value:
        return f"{value_int:{THOUSAND_SEPARATOR}}" if thousand_separator else str(value_int)
    else:
        if precision > 0:
            return f"{value:{THOUSAND_SEPARATOR}.{precision}f}" if thousand_separator else f"{value:.{precision}f}"
        else:
            return f"{value:{THOUSAND_SEPARATOR}f}" if thousand_separator else str(value)


@dataclass
class DtypeClass:
    """Data type class configuration.

    Attributes:
        gtype: Generic, high-level type as a string.
        style: Style string for display purposes.
        justify: Text justification for display.
        itype: Input type for validation.
        convert: Conversion function for the data type.
    """

    gtype: str  # generic, high-level type
    style: str
    justify: str
    itype: str
    convert: Any

    def format(
        self,
        val: Any,
        style: str | None = None,
        justify: str | None = None,
        thousand_separator: bool = False,
        float_precision: int = 2,
    ) -> Text:
        """Format the value according to its data type.

        Args:
            val: The value to format.
            style: Optional style override for display. Defaults to None (uses the default style of the data type).
            justify: Optional justification (e.g., left, right, center) override for display. Defaults to None (uses the default justification of the data type).
            thousand_separator: Whether to include thousand separators for numeric values. Defaults to False.
            float_precision: Number of decimal places for float values. Defaults to 2.

        Returns:
            The formatted value as a Text.
        """
        # Format the value
        if val is None:
            text_val = NULL_DISPLAY
        elif self.gtype == "integer" and thousand_separator:
            text_val = f"{val:{THOUSAND_SEPARATOR}}"
        elif self.gtype == "float":
            text_val = format_float(val, thousand_separator, float_precision)
        else:
            text_val = str(val)

        return Text(
            text_val,
            style=self.style if style is None else style,
            justify=self.justify if justify is None else justify,
            overflow="ellipsis",
            no_wrap=True,
        )


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
    pl.Float32: DtypeClass(gtype="float", style="yellow", justify="right", itype="number", convert=float),
    pl.Float64: DtypeClass(gtype="float", style="yellow", justify="right", itype="number", convert=float),
    pl.Decimal: DtypeClass(gtype="float", style="yellow", justify="right", itype="number", convert=float),
    # bool
    pl.Boolean: DtypeClass(gtype="boolean", style="blue", justify="center", itype="text", convert=lambda x: BOOLS[x.lower()]),
    # temporal
    pl.Date: DtypeClass(gtype="temporal", style="magenta", justify="center", itype="text", convert=str),
    pl.Datetime: DtypeClass(gtype="temporal", style="magenta", justify="center", itype="text", convert=str),
    pl.Time: DtypeClass(gtype="temporal", style="magenta", justify="center", itype="text", convert=str),
    # object
    pl.Object: DtypeClass(gtype="object", style="", justify="", itype="text", convert=str),
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

# Row index mapping between filtered and original dataframe
RID = "^_RID_^"
RID_OLD = "^_RID_OLD_^"


@dataclass
class Source:
    """Data source representation.

    Attributes:
        lf: The LazyFrame.
        filename: The name of the source file.
        tabname: The name of the tab to display.
    """

    lf: pl.LazyFrame
    filename: str
    tabname: str


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


def format_row(
    vals,
    dtypes,
    style: str | list[str] | None = None,
    justify: str | list[str] | None = None,
    thousand_separator: bool | list[bool] = False,
    float_precision: int | list[int] = 2,
) -> list[Text]:
    """Format a single row with proper styling and justification.

    Converts raw row values to formatted Rich Text objects with appropriate
    styling (colors), justification, and null value handling based on data types.

    Args:
        vals: The list of values in the row.
        dtypes: The list of data types corresponding to each value.
        style: Optional list of style overrides for each value. Defaults to None (uses the default style of the data type).
        justify: Optional list of justification overrides for each value. Defaults to None (uses the default justification of the data type).
        thousand_separator: Whether to include thousand separators for numeric values.
            Can be a single bool (applied to all) or a list of bools per column. Defaults to False.
        float_precision: Number of decimal places for float values.
            Can be a single int (applied to all) or a list of ints per column. Defaults to 2.

    Returns:
        A list of Rich Text objects with proper formatting applied.
    """
    is_style_list = isinstance(style, list)
    is_justify_list = isinstance(justify, list)
    is_thousand_separator_list = isinstance(thousand_separator, list)
    is_float_precision_list = isinstance(float_precision, list)
    formatted_row = []

    for idx, (val, dtype) in enumerate(zip(vals, dtypes, strict=True)):
        dc = DtypeConfig(dtype)
        formatted_row.append(
            dc.format(
                val,
                style=style[idx] if is_style_list else style,
                justify=justify[idx] if is_justify_list else justify,
                thousand_separator=thousand_separator[idx] if is_thousand_separator_list else thousand_separator,
                float_precision=float_precision[idx] if is_float_precision_list else float_precision,
            )
        )

    return formatted_row


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


def tentative_expr(expr: str) -> bool:
    """Check if the given expr could be a Polars expression.

    Heuristically determines whether a string might represent a Polars expression
    based on common patterns like column references ($) or direct Polars syntax (pl.).

    Args:
        expr: The input expression as a string to be checked.

    Returns:
        True if the expr appears to be a Polars expression, False otherwise.
    """
    if "$" in expr and not expr.endswith("$"):
        return True
    if "pl." in expr:
        return True
    if "self" in expr:
        return True
    return False


def validate_expr(
    expr: str, columns: list[str], current_col_idx: int = 0, df: pl.DataFrame | None = None
) -> pl.Expr | pl.DataFrame | pl.Series | None:
    """Validate and return the expression.

    Parses a user-provided expression string and validates it as a valid Polars expression.
    Converts special syntax like $_ references to proper pl.col() expressions.

    Args:
        expr: The input expression as a string.
        columns: The list of column names in the DataFrame.
        current_col_idx: The index of the currently selected column (0-based). Used for $_ reference.
        df: The current DataFrame used for evaluating expressions involving `self`.

    Returns:
        A valid Polars expression object if validation succeeds.

    Raises:
        ValueError: If the expr is invalid, contains non-existent column references, or cannot be evaluated.
    """
    expr = expr.strip()

    try:
        # Parse the expression
        expr_str = parse_expr(expr, columns, current_col_idx)

        # Validate by evaluating it
        try:
            expr_pl = eval(expr_str, {"pl": pl, "self": df, "RID": RID})
            if not isinstance(expr_pl, (pl.Expr, pl.DataFrame, pl.Series)):
                raise ValueError(
                    f"Expression evaluated to `{type(expr_pl).__name__}` instead of a Polars expression, DataFrame, or Series"
                )

            # Expression is valid
            return expr_pl
        except Exception as e:
            raise ValueError(f"Failed to evaluate expression `{expr_str}`: {e}") from e
    except Exception as ve:
        raise ValueError(f"Failed to parse expression `{expr}`: {ve}") from ve


def parse_expr(expr: str, columns: list[str], current_cidx: int) -> str:
    """Parse and convert an expression to Polars syntax.

    Replaces column references with Polars col() expressions:
    - $_ - Current selected column
    - $# - Row index (1-based)
    - $1, $2, etc. - Column index (1-based)
    - $col_name - Column name (valid identifier starting with _ or letter)
    - $`col name` - Column name with spaces (backtick quoted)

    Examples:
    - "$_ > 50" -> "pl.col('current_col') > 50"
    - "$# > 10" -> "pl.col('^_RID_^') > 10"
    - "$1 > 50" -> "pl.col('col0') > 50"
    - "$name == 'Alex'" -> "pl.col('name') == 'Alex'"
    - "$age < $salary" -> "pl.col('age') < pl.col('salary')"
    - "$`product id` > 100" -> "pl.col('product id') > 100"

    Args:
        expr: The input expression as a string.
        columns: The list of column names in the DataFrame.
        current_cidx: The index of the currently selected column (0-based). Used for $_ reference.

    Returns:
        A Python expression string with $references replaced by pl.col() calls.

    Raises:
        ValueError: If a column reference is invalid.
    """
    # Early return if no $ present
    if "$" not in expr:
        if "pl." in expr:
            # This may be valid Polars expression already
            return expr
        elif "self" in expr:
            # self reference for current dataframe
            return expr
        else:
            # Return as a literal string
            return f"pl.lit({expr})"

    parts = parse_placeholders(expr, columns, current_cidx)

    result = []
    for part in parts:
        if isinstance(part, pl.Expr):
            col = part.meta.output_name()

            if col == RID:  # Convert to 1-based
                result.append(f"(pl.col('{col}') + 1)")
            else:
                result.append(f"pl.col('{col}')")
        else:  # Literal string part
            result.append(part)

    return "".join(result)


def parse_placeholders(template: str, columns: list[str], current_cidx: int) -> list[str | pl.Expr]:
    """Parse template string into a list of strings or Polars expressions

    Supports multiple placeholder types:
    - `$_` - Current column (based on current_cidx parameter)
    - `$#` - Row index (1-based)
    - `$1`, `$2`, etc. - Column index (1-based)
    - `$name` - Column name (e.g., `$product_id`)
    - `` $`col name` `` - Column name with spaces (e.g., `` $`product id` ``)

    Args:
        template: The template string containing placeholders and literal text
        columns: List of column names in the dataframe
        current_cidx: 0-based index of the current column for `$_` references in the columns list

    Returns:
        A list of strings (literal text) and Polars expressions (for column references)

    Raises:
        ValueError: If invalid column index or non-existent column name is referenced
    """
    if "$" not in template or template.endswith("$"):
        return [template]

    # Regex matches: $_ or $# or $\d+ or $`...` (backtick-Quoted names with spaces) or $\w+ (column names)
    # Pattern explanation:
    # \$(_|#|\d+|`[^`]+`|[a-zA-Z_]\w*)
    # - $_ : current column
    # - $# : row index
    # - $\d+ : column by index (1-based)
    # - $`[^`]+` : column by name with spaces (backtick quoted)
    # - $[a-zA-Z_]\w* : column by name without spaces
    placeholder_pattern = r"\$(_|#|\d+|`[^`]+`|[a-zA-Z_]\w*)"
    placeholders = re.finditer(placeholder_pattern, template)

    parts = []
    last_end = 0

    # Get current column name for $_ references
    try:
        col_name = columns[current_cidx]
    except IndexError:
        raise ValueError(f"Current column index {current_cidx} is out of range for columns list")

    for match in placeholders:
        # Add literal text before this placeholder
        if match.start() > last_end:
            parts.append(template[last_end : match.start()])

        placeholder = match.group(1)  # Extract content after '$'

        if placeholder == "_":
            # $_ refers to current column (where cursor was)
            parts.append(pl.col(col_name))
        elif placeholder == "#":
            # $# refers to row index (1-based)
            parts.append(pl.col(RID))
        elif placeholder.isdigit():
            # $1, $2, etc. refer to columns by 1-based position index
            col_idx = int(placeholder) - 1  # Convert to 0-based
            try:
                col_ref = columns[col_idx]
                parts.append(pl.col(col_ref))
            except IndexError:
                raise ValueError(f"Invalid column index: ${placeholder} (valid range: $1 to ${len(columns)})")
        elif placeholder.startswith("`") and placeholder.endswith("`"):
            # $`col name` refers to column by name with spaces
            col_ref = placeholder[1:-1]  # Remove backticks
            if col_ref in columns:
                parts.append(pl.col(col_ref))
            else:
                raise ValueError(f"Column not found: ${placeholder} (available columns: {', '.join(columns)})")
        else:
            # $name refers to column by name
            if placeholder in columns:
                parts.append(pl.col(placeholder))
            else:
                raise ValueError(f"Column not found: ${placeholder} (available columns: {', '.join(columns)})")

        last_end = match.end()

    # Add remaining literal text after last placeholder
    if last_end < len(template):
        parts.append(template[last_end:])

    # If no placeholders found, treat entire template as literal
    if not parts:
        parts: list[str | pl.Expr] = [template]

    return parts


RE_COMPUTE_ERROR = re.compile(r"at column '(.*?)' \(column number \d+\)")


def handle_compute_error(err_msg: str) -> None:
    """Handle ComputeError during schema inference and determine retry strategy.

    Analyzes the error message and determines whether to retry with schema overrides,
    disable schema inference, or exit with an error.

    Args:
        err_msg: The error message from the ComputeError exception.
        file_format: The file format being loaded (tsv, csv, etc.).
        infer_schema: Whether schema inference is currently enabled.

    Raises:
        SystemExit: If the error is unrecoverable.
    """
    if not err_msg:
        return

    from rich.console import Console

    console = Console(stderr=True)

    # CSV malformed error
    if "CSV malformed" in err_msg:
        console.rule("Error", style="red")
        console.print(err_msg)
        console.rule("Troubleshooting", style="green")
        console.print(
            "Sometimes quote characters might be mismatched and cause malformed CSV. Try again with `[yellow bold]-Q[/yellow bold]` to use a different quote character or disable quoting.\n"
        )

    # Schema mismatch error
    elif "found more fields than defined in 'Schema'" in err_msg:
        console.rule("Error", style="red")
        console.print(err_msg)
        console.rule("Troubleshooting", style="green")
        console.print(
            "Input might be malformed. Try again with `[yellow bold]-T[/yellow bold]` to truncate ragged lines.\n"
        )

    # Field ... is not properly escaped
    elif "is not properly escaped" in err_msg:
        console.rule("Error", style="red")
        console.print(err_msg)
        console.rule("Troubleshooting", style="green")
        console.print(
            "Quoting might be causing improper escaping. Try again with `[yellow bold]-Q[/yellow bold]` to use a different quote character or disable quoting.\n"
        )

    # ComputeError: could not parse `n.a. as of 04.01.022` as `dtype` i64 at column 'PubChemCID' (column number 16)
    elif m := RE_COMPUTE_ERROR.search(err_msg):
        col_name = m.group(1)
        console.rule("Error", style="red")
        console.print(err_msg)
        console.rule("Troubleshooting", style="green")
        console.print(
            f"Column `[green bold]{col_name}[/green bold]` has mixed types. Try again with `[yellow bold]-L[/yellow bold]` to increase the number of rows used for schema inference or `[yellow bold]-I[/yellow bold]` to disable type inference.\n"
        )

    # no data to load
    elif "The provided LazyFrame has no data to load" in err_msg:
        console.rule("Error", style="red")
        console.print(err_msg)
        console.rule("Troubleshooting", style="green")
        console.print(
            "No data could be read from the input. Check if the file is empty or if the format/delimiter is correct.\n"
        )

    # Other errors
    else:
        console.rule("Error", style="red")
        console.print(err_msg)
        console.rule("Troubleshooting", style="green")
        console.print("Unhandled error. Try again with `[yellow bold]-E[/yellow bold]` to ignore errors.\n")

    # Exit after handling the error
    sys.exit(1)


def get_columns(all_columns: list[str], use_columns: list[str] | None) -> list[str]:
    """Get the list of columns to read based on use_columns specification.

    Determines which columns to read from the input based on the use_columns parameter,
    which can specify columns by name, 1-based index, or negative index.

    Args:
        all_columns: The list of all column names in the input.
        use_columns: The list of columns to read, specified by name, 1-based index, or negative index. Defaults to None (read all columns).

    Returns:
        The list of column names to read.

    Raises:
        ValueError: If a specified column name does not exist or an index is out of range.
    """
    if use_columns is None:
        return all_columns

    ok_columns = []
    for col in use_columns:
        if col in all_columns:
            ok_columns.append(col)
        else:
            try:
                idx = int(col)
            except ValueError:
                raise ValueError(
                    f"Column name '{col}' not found in input (available columns: {', '.join(all_columns)})"
                )

            if 1 <= idx <= len(all_columns):
                ok_columns.append(all_columns[idx - 1])
            elif -len(all_columns) <= idx <= -1:
                ok_columns.append(all_columns[idx])
            else:
                raise ValueError(
                    f"Column index {col} is out of range (valid range: 1 to {len(all_columns)} or -{len(all_columns)} to -1)"
                )

    return ok_columns


def round_to_nearest_hundreds(num: int, N: int = 100) -> tuple[int, int]:
    """Round a number to the nearest hundred boundaries.

    Given a number, return a tuple of the two closest hundreds that bracket it.

    Args:
        num: The number to round.

    Returns:
        A tuple (lower_hundred, upper_hundred) where:
        - lower_hundred is the largest multiple of 100 <= num
        - upper_hundred is the smallest multiple of 100 > num

    Examples:
        >>> round_to_nearest_hundreds(0)
        (0, 100)
        >>> round_to_nearest_hundreds(150)
        (100, 200)
        >>> round_to_nearest_hundreds(200)
        (200, 300)
    """
    lower = (num // N) * N
    upper = lower + N
    return (lower, upper)


@contextmanager
def zopen(source: str | Path | StringIO):
    """Context manager to open files, including gzip compressed files.

    Args:
        source: The file path, Path object, or StringIO to open.

    Yields:
        A file-like object for the opened source.
    """
    # Handle StringIO from stdin directly
    if isinstance(source, StringIO):
        yield source

    # file-like object
    else:
        filepath = Path(source)
        is_gzipped = filepath.suffix.lower() == ".gz"

        if is_gzipped:
            with gzip.open(filepath, "rt") as f:
                yield f
        else:
            with open(filepath, "r") as f:
                yield f


def scan_ndjson(
    source: str | Path | StringIO,
    n_rows: int | None = None,
    infer_schema_length: int | None = 100,
    ignore_errors: bool = False,
) -> pl.LazyFrame:
    """Scan an NDJSON file into a Polars LazyFrame while preserving column order.

    Args:
        source: Path to the NDJSON file, a Path object, or a StringIO object.
        n_rows: Number of rows to read from the file. If None, read all rows. Defaults to None.
        infer_schema_length: Number of rows to use for schema inference. Defaults to 100.
        ignore_errors: Whether to ignore errors during scanning. Defaults to False.

    Returns:
        A Polars LazyFrame representing the scanned NDJSON data.
    """
    # https://github.com/pola-rs/polars/issues/23023
    # read_ndjson does not retain column order for 33 or more columns
    with zopen(source) as f:
        # Get column order from the first line
        line = f.readline()
        ordered_columns = json.loads(line).keys()

        # Reset file to the beginning
        f.seek(0)

        lf = pl.scan_ndjson(
            f,
            n_rows=n_rows,
            infer_schema_length=infer_schema_length,
            ignore_errors=ignore_errors,
        )

    # Reorder columns to match original order
    return lf.select(pl.col(ordered_columns))


def scan_vortex(source: str | list[str], n_rows: int | None = None) -> pl.LazyFrame:
    """Scan a Vortex file into a Polars LazyFrame.

    Args:
        source: Path to the Vortex file or list of files.
        n_rows: Number of rows to read from each file. If None, read all rows. Defaults to None.
    Returns:
        A Polars LazyFrame representing the scanned Vortex data.
    """
    import vortex as vx

    if isinstance(source, list):
        lf = pl.concat([vx.open(src).to_polars() for src in source])
    else:
        lf = vx.open(source).to_polars()

    if n_rows is not None:
        lf = lf.head(n_rows)

    return lf


def guess_file_format(filename: str | Path) -> str | None:
    """Guess the file format based on the filename extension.

    Args:
        filename: The name of the file to guess the format for.

    Returns:
        The guessed file format as a string (e.g., 'csv', 'excel', etc.) or None if the format cannot be determined or is not supported.
    """
    if not isinstance(filename, (str, Path)):
        return None

    ext = Path(filename).suffix.lower()
    if ext == ".gz":  # Handle .csv.gz, .tsv.gz, etc.
        ext = Path(filename).with_suffix("").suffix.lower()

    fmt = ext.removeprefix(".")
    return fmt if fmt in SUPPORTED_FORMATS else None


def load_dataframe(
    filenames: list[str],
    delimiter: str | None = None,
    format: str | None = None,
    header: bool | list[str] = True,
    infer_schema: bool = True,
    infer_schema_length: int | None = 100,
    comment_prefix: str | None = None,
    quote_char: str | None = '"',
    skip_lines: int = 0,
    skip_rows_after_header: int = 0,
    null_values: list[str] | None = None,
    ignore_errors: bool = False,
    truncate_ragged_lines: bool = False,
    n_rows: int | None = None,
    use_columns: list[str] | None = None,
    all_in_one: bool = False,
) -> list[Source]:
    """Load DataFrames from file specifications.

    Handles loading from multiple files, single files, or stdin. For Excel files,
    loads all sheets as separate entries. For other formats, loads as single file.

    Args:
        filenames: List of filenames to load. If single filename is "-", read from stdin.
        delimiter: Optional delimiter specifier for input files (e.g., ';' for SSV). Defaults to None (infer from file extension).
        format: Optional format specifier for input files (e.g., 'csv' or 'excel'). Defaults to None (infer from file extension).
        header: Specify header info. for CSV/TSV files. Can be True (header in first line), False (no header, auto-generate column names), or list of column names to use. Defaults to True.
        infer_schema: Whether to infer data types for CSV/TSV files. Defaults to True.
        infer_schema_length: Number of rows to use for schema inference when infer_schema is True. Defaults to 100.
        comment_prefix: Character(s) indicating comment lines in CSV/TSV files. Defaults to None.
        quote_char: Quote character for reading CSV/TSV files. Defaults to '"'.
        skip_lines: Number of lines to skip when reading CSV/TSV files. Defaults to 0.
        skip_rows_after_header: Number of rows to skip after header. Defaults to 0.
        null_values: List of values to interpret as null when reading CSV/TSV files. Defaults to None.
        ignore_errors: Whether to ignore errors when reading CSV/TSV files. Defaults to False.
        truncate_ragged_lines: Whether to truncate ragged lines when reading CSV/TSV files. Defaults to False.
        n_rows: Number of rows to read from CSV/TSV files. Defaults to None (read all rows).
        use_columns: List of columns to read from CSV/TSV files. Defaults to None (read all columns).
        all_in_one: Whether to read all files (must be of the same structure) into a single DataFrame. Defaults to False.
    Returns:
        List of `Source` objects.
    """
    data: list[Source] = []
    lfs_aio = []
    prefix_sheet = len(filenames) > 1
    # If all_in_one, only load first sheet for each file to ensure consistent structure
    first_sheet = all_in_one

    # Read files individually
    for filename in filenames:
        if filename == "-":
            content = sys.stdin.read()
            if not content:
                print("No data received from stdin", file=sys.stderr)
                sys.exit(1)
            source = StringIO(content)

            # Reopen stdin to /dev/tty for proper terminal interaction
            try:
                tty = open("/dev/tty")
                os.dup2(tty.fileno(), sys.stdin.fileno())
            except (OSError, FileNotFoundError):
                pass
        else:
            source = filename

        # Load the file
        ds = load_file(
            source,
            first_sheet=first_sheet,
            prefix_sheet=prefix_sheet,
            delimiter=delimiter,
            format=format,
            header=header,
            infer_schema=infer_schema,
            infer_schema_length=infer_schema_length,
            comment_prefix=comment_prefix,
            quote_char=quote_char,
            skip_lines=skip_lines,
            skip_rows_after_header=skip_rows_after_header,
            null_values=null_values,
            ignore_errors=ignore_errors,
            truncate_ragged_lines=truncate_ragged_lines,
            n_rows=n_rows,
            use_columns=use_columns,
        )

        if all_in_one:
            # For all-in-one, add a column to keep track of the source filename for each row
            lfs_aio.extend([src.lf.with_columns(pl.lit(src.filename).alias("^_FILE_^")) for src in ds])
        else:
            data.extend(ds)

    if lfs_aio:
        lf_aio = lfs_aio[0] if len(lfs_aio) == 1 else pl.concat(lfs_aio, rechunk=True)
        data.append(Source(lf_aio, "all-in-one.parquet", "all-in-one"))

    return data


def load_file(
    source: str | StringIO,
    first_sheet: bool = False,
    prefix_sheet: bool = False,
    delimiter: str | None = None,
    format: str | None = None,
    header: bool | list[str] = True,
    infer_schema_length: int | None = 100,
    infer_schema: bool = True,
    comment_prefix: str | None = None,
    quote_char: str | None = '"',
    skip_lines: int = 0,
    skip_rows_after_header: int = 0,
    null_values: list[str] | None = None,
    ignore_errors: bool = False,
    truncate_ragged_lines: bool = False,
    n_rows: int | None = None,
    use_columns: list[str] | None = None,
) -> list[Source]:
    """Load a single file.

    For Excel files, when `first_sheet` is True, returns only the first sheet. Otherwise, returns one entry per sheet.
    For other files or multiple files, returns one entry per file.

    If a ComputeError occurs during schema inference for a column, attempts to recover
    by treating that column as a string and retrying the load. This process repeats until
    all columns are successfully loaded or no further recovery is possible.

    Args:
        source: Path to file to load or a StringIO object.
        first_sheet: If True, only load first sheet for Excel files. Defaults to False.
        prefix_sheet: If True, prefix filename to sheet name as the tab name for Excel files. Defaults to False.
        delimiter: Optional delimiter specifier for input files (e.g., ';' for SSV). Defaults to None (infer from file extension).
        format: Optional format specifier for input files (e.g., 'csv' or 'excel'). Defaults to None (infer from file extension).
        header: Specify header info. for the input file. Can be True (header in first line), False (no header, auto-generate column names), or list of column names to use.
        infer_schema: Whether to infer data types for CSV/TSV files. Defaults to True.
        infer_schema_length: Number of rows to use for inferring schema when reading CSV/TSV. Defaults to 100.
        comment_prefix: Character(s) indicating comment lines in CSV/TSV files. Defaults to None.
        quote_char: Quote character for reading CSV/TSV files. Defaults to '"'.
        skip_lines: Number of lines to skip when reading CSV/TSV files. The header will be parsed at this offset. Defaults to 0.
        skip_rows_after_header: Number of rows to skip after header when reading CSV/TSV files. Defaults to 0.
        infer_schema_length: Number of rows to use for inferring schema when reading CSV/TSV. Defaults to 100.
        null_values: List of values to interpret as null when reading CSV/TSV files. Defaults to None.
        ignore_errors: Whether to ignore errors when reading CSV/TSV files.
        truncate_ragged_lines: Whether to truncate ragged lines when reading CSV/TSV files. Defaults to False.
        n_rows: Number of rows to read from CSV/TSV files. Defaults to None (read all rows).
        use_columns: List of columns to read from CSV/TSV files. Defaults to None (read all columns).

    Returns:
        List of `Source` objects.
    """
    data: list[Source] = []

    fmt = format or (None if delimiter else guess_file_format(source) or "tsv")
    if fmt:
        delimiter = SUPPORTED_FORMATS.get(fmt)

    filename = (f"stdin.{fmt}" if fmt else "stdin") if isinstance(source, StringIO) else source
    filepath = Path(filename)

    # check header
    if header is False:
        has_header = False
        new_columns = None
    elif isinstance(header, list):
        has_header = True
        new_columns = header
    else:
        has_header = True
        new_columns = None

    # Load based on file format
    if delimiter:
        lf = pl.scan_csv(
            source,
            separator=delimiter,
            has_header=has_header,
            infer_schema=infer_schema,
            infer_schema_length=infer_schema_length,
            comment_prefix=comment_prefix,
            quote_char=quote_char,
            skip_lines=skip_lines,
            skip_rows_after_header=skip_rows_after_header,
            null_values=null_values,
            ignore_errors=ignore_errors,
            truncate_ragged_lines=truncate_ragged_lines,
            n_rows=n_rows,
            new_columns=new_columns,
        )
        data.append(Source(lf, filename, filepath.stem))
    elif fmt == "xlsx":
        if first_sheet:
            # Read only the first sheet for multiple files
            try:
                df = pl.read_excel(source, has_header=has_header)
            except Exception as e:
                print(f"Error reading Excel file `{filename}`: {e}", file=sys.stderr)
                sys.exit(1)
            if n_rows is not None:
                df = df.head(n_rows)
            data.append(Source(df.lazy(), filename, filepath.stem))
        else:
            # For single file, expand all sheets
            try:
                sheets = pl.read_excel(source, sheet_id=0, has_header=has_header)
            except Exception as e:
                print(f"Error reading Excel file `{filename}`: {e}", file=sys.stderr)
                sys.exit(1)
            for sheet_name, df in sheets.items():
                if n_rows is not None:
                    df = df.head(n_rows)
                tabname = f"{filepath.stem}_{sheet_name}" if prefix_sheet else sheet_name
                data.append(Source(df.lazy(), filename, tabname))
    elif fmt == "parquet":
        lf = pl.scan_parquet(source, n_rows=n_rows)
        data.append(Source(lf, filename, filepath.stem))
    elif fmt in ("jsonl", "ndjson"):
        lf = scan_ndjson(source, n_rows=n_rows, infer_schema_length=infer_schema_length, ignore_errors=ignore_errors)
        data.append(Source(lf, filename, filepath.stem))
    elif fmt == "json":
        try:
            df = pl.read_json(source)
        except Exception as e:
            print(f"Error reading JSON file `{filename}`: {e}", file=sys.stderr)
            sys.exit(1)
        if n_rows is not None:
            df = df.head(n_rows)
        data.append(Source(df.lazy(), filename, filepath.stem))
    elif fmt == "vortex":
        lf = scan_vortex(source, n_rows=n_rows)
        data.append(Source(lf, filename, filepath.stem))
    else:
        raise ValueError(f"Unsupported file format: {fmt}. Supported formats are: {', '.join(SUPPORTED_FORMATS)}")

    # Attempt to collect, handling ComputeError for schema inference issues
    try:
        ds = []
        for src in data:
            all_columns = [c for c in src.lf.collect_schema().names()]

            if use_columns:
                try:
                    ok_columns = get_columns(all_columns, use_columns)
                except ValueError as ve:
                    print(ve, file=sys.stderr)
                    sys.exit(1)

                ds.append(Source(src.lf.select(ok_columns), src.filename, src.tabname))
            else:
                ds.append(Source(src.lf, src.filename, src.tabname))

        data = ds
    except Exception as e:
        print(f"Error loading file `{filename}`: {e}", file=sys.stderr)
        sys.exit(1)

    return data


def write_file(sources: list[Source], filename: str) -> None:
    if not (fmt := guess_file_format(filename)):
        print(
            f"Unsupported output file format `{fmt}` for `{filename}`. Supported formats: {', '.join(SUPPORTED_FORMATS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(sources) > 1 and fmt != "xlsx":
        print("Only Excel format (.xlsx) support multiple tabs", file=sys.stderr)
        sys.exit(1)

    # Get rid of the RID column
    for source in sources:
        source.lf = source.lf.select(pl.exclude(RID))

    compression = "gzip" if filename.endswith(".gz") else "uncompressed"

    try:
        if fmt == "csv":
            sources[0].lf.sink_csv(filename, compression=compression)
        elif fmt == "tsv":
            sources[0].lf.sink_csv(filename, separator="\t", compression=compression)
        elif fmt == "psv":
            sources[0].lf.sink_csv(filename, separator="|", compression=compression)
        elif fmt == "parquet":
            sources[0].lf.sink_parquet(filename)
        elif fmt in ("jsonl", "ndjson"):
            sources[0].lf.sink_ndjson(filename, compression=compression)
        elif fmt == "json":
            sources[0].lf.collect().write_json(filename)
        elif fmt == "vortex":
            import vortex as vx

            vx.io.write(sources[0].lf.collect().to_arrow(), filename)
        elif fmt == "xlsx":
            if len(sources) == 1:
                sources[0].lf.collect().write_excel(filename)
            else:
                with xlsxwriter.Workbook(filename) as wb:
                    for source in sources:
                        worksheet = wb.add_worksheet(source.tabname)
                        source.lf.collect().write_excel(workbook=wb, worksheet=worksheet)
        else:
            pass
    except Exception as e:
        print(f"Error writing to output file: {e}", file=sys.stderr)
        sys.exit(1)


def add_rid_column(frame: pl.DataFrame | pl.LazyFrame, offset: int = 0) -> pl.DataFrame | pl.LazyFrame:
    """Add internal row index as last column to the dataframe if not already present.

    Args:
        frame: The Polars DataFrame or LazyFrame to modify.
        offset: The starting index for the row IDs.
    Returns:
        The modified DataFrame or LazyFrame with the internal row index column added.
    """
    if isinstance(frame, pl.DataFrame) and RID not in frame.columns:
        frame = frame.lazy().with_row_index(RID, offset=offset).select(pl.exclude(RID), RID).collect()
    elif isinstance(frame, pl.LazyFrame) and RID not in frame.collect_schema():
        frame = frame.with_row_index(RID, offset=offset).select(pl.exclude(RID), RID)

    return frame
