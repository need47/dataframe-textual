"""Common utilities and constants for dataframe_viewer."""

import os
import re
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import polars as pl
from rich.text import Text

# Supported file formats
SUPPORTED_FORMATS = {"tsv", "tab", "csv", "excel", "xlsx", "xls", "parquet", "json", "ndjson"}


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


def format_float(value: float, thousand_separator: bool = False, precision: int = 2) -> str:
    """Format a float value, keeping integers without decimal point.

    Args:
        val: The float value to format.
        thousand_separator: Whether to include thousand separators. Defaults to False.

    Returns:
        The formatted float as a string.
    """

    if (val := int(value)) == value:
        if precision > 0:
            return f"{val:,}" if thousand_separator else str(val)
        else:
            return f"{val:,.{-precision}f}" if thousand_separator else f"{val:.{-precision}f}"
    else:
        if precision > 0:
            return f"{value:,.{precision}f}" if thousand_separator else f"{value:.{precision}f}"
        else:
            return f"{value:,f}" if thousand_separator else str(value)


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
        self, val: Any, style: str | None = None, justify: str | None = None, thousand_separator: bool = False
    ) -> str:
        """Format the value according to its data type.

        Args:
            val: The value to format.

        Returns:
            The formatted value as a Text.
        """
        # Format the value
        if val is None:
            text_val = NULL_DISPLAY
        elif self.gtype == "integer" and thousand_separator:
            text_val = f"{val:,}"
        elif self.gtype == "float":
            text_val = format_float(val, thousand_separator)
        else:
            text_val = str(val)

        return Text(
            text_val,
            style="" if style == "" else (style or self.style),
            justify="" if justify == "" else (justify or self.justify),
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


@dataclass
class Source:
    """Data source representation.

    Attributes:
        frame: The Polars DataFrame or LazyFrame.
        filename: The name of the source file.
        tabname: The name of the tab to display.
    """

    frame: pl.DataFrame | pl.LazyFrame
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


def format_row(vals, dtypes, styles: list[str | None] | None = None, thousand_separator=False) -> list[Text]:
    """Format a single row with proper styling and justification.

    Converts raw row values to formatted Rich Text objects with appropriate
    styling (colors), justification, and null value handling based on data types.

    Args:
        vals: The list of values in the row.
        dtypes: The list of data types corresponding to each value.
        styles: Optional list of style overrides for each value. Defaults to None.

    Returns:
        A list of Rich Text objects with proper formatting applied.
    """
    formatted_row = []

    for idx, (val, dtype) in enumerate(zip(vals, dtypes, strict=True)):
        dc = DtypeConfig(dtype)
        formatted_row.append(
            dc.format(
                val,
                style=styles[idx] if styles and styles[idx] else None,
                thousand_separator=thousand_separator,
            )
        )

    return formatted_row


def rindex(lst: list, value, pos: int | None = None) -> int:
    """Return the last index of value in a list. Return -1 if not found.

    Searches through the list in reverse order to find the last occurrence
    of the given value.

    Args:
        lst: The list to search through.
        value: The value to find.

    Returns:
        The index (0-based) of the last occurrence, or -1 if not found.
    """
    n = len(lst)
    for i, item in enumerate(reversed(lst)):
        if pos is not None and (n - 1 - i) > pos:
            continue
        if item == value:
            return n - 1 - i
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

    # Regex matches: $_ or $# or $\d+ or $`...` (backtick-quoted names with spaces) or $\w+ (column names)
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
        parts = [template]

    return parts


def parse_polars_expression(expression: str, columns: list[str], current_cidx: int) -> str:
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
        expression: The input expression as a string.
        columns: The list of column names in the DataFrame.
        current_cidx: The index of the currently selected column (0-based). Used for $_ reference.

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

    parts = parse_placeholders(expression, columns, current_cidx)

    result = []
    for part in parts:
        if isinstance(part, pl.Expr):
            col = part.meta.output_name()

            if col == RID:  # Convert to 1-based
                result.append(f"(pl.col('{col}') + 1)")
            else:
                result.append(f"pl.col('{col}')")
        else:
            result.append(part)

    return "".join(result)


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


def validate_expr(term: str, columns: list[str], current_col_idx: int) -> pl.Expr | None:
    """Validate and return the expression.

    Parses a user-provided expression string and validates it as a valid Polars expression.
    Converts special syntax like $_ references to proper Polars col() expressions.

    Args:
        term: The input expression as a string.
        columns: The list of column names in the DataFrame.
        current_col_idx: The index of the currently selected column (0-based). Used for $_ reference.

    Returns:
        A valid Polars expression object if validation succeeds.

    Raises:
        ValueError: If the expression is invalid, contains non-existent column references, or cannot be evaluated.
    """
    term = term.strip()

    try:
        # Parse the expression
        expr_str = parse_polars_expression(term, columns, current_col_idx)

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


def load_dataframe(
    filenames: list[str],
    file_format: str | None = None,
    has_header: bool = True,
    infer_schema: bool = True,
    comment_prefix: str | None = None,
    quote_char: str | None = '"',
    skip_lines: int = 0,
    skip_rows_after_header: int = 0,
    null_values: list[str] | None = None,
    ignore_errors: bool = False,
    truncate_ragged_lines: bool = False,
) -> list[Source]:
    """Load DataFrames from file specifications.

    Handles loading from multiple files, single files, or stdin. For Excel files,
    loads all sheets as separate entries. For other formats, loads as single file.

    Args:
        filenames: List of filenames to load. If single filename is "-", read from stdin.
        file_format: Optional format specifier for input files (e.g., 'csv', 'excel').
        has_header: Whether the input files have a header row. Defaults to True.
        infer_schema: Whether to infer data types for CSV/TSV files. Defaults to True.
        comment_prefix: Character(s) indicating comment lines in CSV/TSV files. Defaults to None.
        quote_char: Quote character for reading CSV/TSV files. Defaults to '"'.
        skip_lines: Number of lines to skip when reading CSV/TSV files. Defaults to 0.
        skip_rows_after_header: Number of rows to skip after header. Defaults to 0.
        null_values: List of values to interpret as null when reading CSV/TSV files. Defaults to None.
        ignore_errors: Whether to ignore errors when reading CSV/TSV files. Defaults to False.

    Returns:
        List of `Source` objects.
    """
    data: list[Source] = []
    prefix_sheet = len(filenames) > 1

    for filename in filenames:
        if filename == "-":
            source = StringIO(sys.stdin.read())
            file_format = file_format or "tsv"

            # Reopen stdin to /dev/tty for proper terminal interaction
            try:
                tty = open("/dev/tty")
                os.dup2(tty.fileno(), sys.stdin.fileno())
            except (OSError, FileNotFoundError):
                pass
        else:
            source = filename

        # If not specified, determine file format (may be different for each file)
        fmt = file_format
        if not fmt:
            ext = Path(filename).suffix.lower()
            if ext == ".gz":
                ext = Path(filename).with_suffix("").suffix.lower()
            fmt = ext.removeprefix(".")

            # Default to TSV
            if not fmt or fmt not in SUPPORTED_FORMATS:
                fmt = "tsv"

        # Load the file
        data.extend(
            load_file(
                source,
                prefix_sheet=prefix_sheet,
                file_format=fmt,
                has_header=has_header,
                infer_schema=infer_schema,
                comment_prefix=comment_prefix,
                quote_char=quote_char,
                skip_lines=skip_lines,
                skip_rows_after_header=skip_rows_after_header,
                null_values=null_values,
                ignore_errors=ignore_errors,
                truncate_ragged_lines=truncate_ragged_lines,
            )
        )

    return data


RE_COMPUTE_ERROR = re.compile(r"at column '(.*?)' \(column number \d+\)")


def handle_compute_error(
    err_msg: str,
    file_format: str | None,
    infer_schema: bool,
    schema_overrides: dict[str, pl.DataType] | None = None,
) -> tuple[bool, dict[str, pl.DataType] | None]:
    """Handle ComputeError during schema inference and determine retry strategy.

    Analyzes the error message and determines whether to retry with schema overrides,
    disable schema inference, or exit with an error.

    Args:
        err_msg: The error message from the ComputeError exception.
        file_format: The file format being loaded (tsv, csv, etc.).
        infer_schema: Whether schema inference is currently enabled.
        schema_overrides: Current schema overrides, if any.

    Returns:
        A tuple of (infer_schema, schema_overrides):

    Raises:
        SystemExit: If the error is unrecoverable.
    """
    # Already disabled schema inference, cannot recover
    if not infer_schema:
        print(f"Error loading even with schema inference disabled:\n{err_msg}", file=sys.stderr)

        if "CSV malformed" in err_msg:
            print(
                "\nSometimes quote characters might be mismatched. Try again with `-q` or `-E` to ignore errors",
                file=sys.stderr,
            )

        sys.exit(1)

    # Schema mismatch error
    if "found more fields than defined in 'Schema'" in err_msg:
        print(f"Input might be malformed:\n{err_msg}.\nTry again with `-E` to ignore errors", file=sys.stderr)
        sys.exit(1)

    # ComputeError: could not parse `n.a. as of 04.01.022` as `dtype` i64 at column 'PubChemCID' (column number 16)
    if file_format in ("tsv", "csv") and (m := RE_COMPUTE_ERROR.search(err_msg)):
        col_name = m.group(1)

        if schema_overrides is None:
            schema_overrides = {}
        schema_overrides.update({col_name: pl.String})
    else:
        infer_schema = False

    return infer_schema, schema_overrides


def load_file(
    source: str | StringIO,
    first_sheet: bool = False,
    prefix_sheet: bool = False,
    file_format: str | None = None,
    has_header: bool = True,
    infer_schema: bool = True,
    comment_prefix: str | None = None,
    quote_char: str | None = '"',
    skip_lines: int = 0,
    skip_rows_after_header: int = 0,
    schema_overrides: dict[str, pl.DataType] | None = None,
    null_values: list[str] | None = None,
    ignore_errors: bool = False,
    truncate_ragged_lines: bool = False,
) -> list[Source]:
    """Load a single file.

    For Excel files, when `first_sheet` is True, returns only the first sheet. Otherwise, returns one entry per sheet.
    For other files or multiple files, returns one entry per file.

    If a ComputeError occurs during schema inference for a column, attempts to recover
    by treating that column as a string and retrying the load. This process repeats until
    all columns are successfully loaded or no further recovery is possible.

    Args:
        filename: Path to file to load.
        first_sheet: If True, only load first sheet for Excel files. Defaults to False.
        prefix_sheet: If True, prefix filename to sheet name as the tab name for Excel files. Defaults to False.
        file_format: Optional format specifier (i.e., 'tsv', 'csv', 'excel', 'parquet', 'json', 'ndjson') for input files.
                     By default, infers from file extension.
        has_header: Whether the input files have a header row. Defaults to True.
        infer_schema: Whether to infer data types for CSV/TSV files. Defaults to True.
        comment_prefix: Character(s) indicating comment lines in CSV/TSV files. Defaults to None.
        quote_char: Quote character for reading CSV/TSV files. Defaults to '"'.
        skip_lines: Number of lines to skip when reading CSV/TSV files. The header will be parsed at this offset. Defaults to 0.
        skip_rows_after_header: Number of rows to skip after header when reading CSV/TSV files. Defaults to 0.
        schema_overrides: Optional dictionary of column name to Polars data type to override inferred schema.
        null_values: List of values to interpret as null when reading CSV/TSV files. Defaults to None.
        ignore_errors: Whether to ignore errors when reading CSV/TSV files.

    Returns:
        List of `Source` objects.
    """
    data: list[Source] = []

    filename = f"stdin.{file_format}" if isinstance(source, StringIO) else source
    filepath = Path(filename)

    if not file_format:
        ext = filepath.suffix.lower()
        if ext == ".gz":
            ext = Path(filename).with_suffix("").suffix.lower()
        file_format = ext.removeprefix(".")

    # Load based on file format
    if file_format in ("csv", "tsv"):
        lf = pl.scan_csv(
            source,
            separator="\t" if file_format == "tsv" else ",",
            has_header=has_header,
            infer_schema=infer_schema,
            comment_prefix=comment_prefix,
            quote_char=quote_char,
            skip_lines=skip_lines,
            skip_rows_after_header=skip_rows_after_header,
            schema_overrides=schema_overrides,
            null_values=null_values,
            ignore_errors=ignore_errors,
            truncate_ragged_lines=truncate_ragged_lines,
        )
        data.append(Source(lf, filename, filepath.stem))
    elif file_format in ("xlsx", "xls", "excel"):
        if first_sheet:
            # Read only the first sheet for multiple files
            lf = pl.read_excel(source).lazy()
            data.append(Source(lf, filename, filepath.stem))
        else:
            # For single file, expand all sheets
            sheets = pl.read_excel(source, sheet_id=0)
            for sheet_name, df in sheets.items():
                tabname = f"{filepath.stem}_{sheet_name}" if prefix_sheet else sheet_name
                data.append(Source(df.lazy(), filename, tabname))
    elif file_format == "parquet":
        lf = pl.scan_parquet(source)
        data.append(Source(lf, filename, filepath.stem))
    elif file_format == "json":
        lf = pl.read_json(source).lazy()
        data.append(Source(lf, filename, filepath.stem))
    elif file_format == "ndjson":
        lf = pl.scan_ndjson(source, schema_overrides=schema_overrides)
        data.append(Source(lf, filename, filepath.stem))
    else:
        raise ValueError(f"Unsupported file format: {file_format}. Supported formats are: {SUPPORTED_FORMATS}")

    # Attempt to collect, handling ComputeError for schema inference issues
    try:
        data = [Source(src.frame.collect(), src.filename, src.tabname) for src in data]
    except pl.exceptions.ComputeError as ce:
        # Handle the error and determine retry strategy
        infer_schema, schema_overrides = handle_compute_error(str(ce), file_format, infer_schema, schema_overrides)

        # Retry loading with updated schema overrides
        if isinstance(source, StringIO):
            source.seek(0)

        return load_file(
            source,
            file_format=file_format,
            has_header=has_header,
            infer_schema=infer_schema,
            comment_prefix=comment_prefix,
            quote_char=quote_char,
            skip_lines=skip_lines,
            skip_rows_after_header=skip_rows_after_header,
            schema_overrides=schema_overrides,
            null_values=null_values,
            ignore_errors=ignore_errors,
        )

    return data


def now() -> str:
    """Get the current local time as a formatted string."""
    import time

    return time.strftime("%m/%d/%Y %H:%M:%S", time.localtime())


async def sleep_async(seconds: float) -> None:
    """Async sleep to yield control back to the event loop.

    Args:
        seconds: The number of seconds to sleep.
    """
    import asyncio

    await asyncio.sleep(seconds)


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
