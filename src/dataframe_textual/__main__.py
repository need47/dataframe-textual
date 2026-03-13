"""Entry point for running DataFrameViewer as a module."""

import argparse
import sys
from pathlib import Path

from textual.theme import BUILTIN_THEMES

from . import __version__
from .common import handle_compute_error, load_dataframe
from .data_frame_viewer import DataFrameViewer


class ConstWithMultiArgs(argparse.Action):
    """
    An `argparse` action class that allows handling arguments with multiple values in different scenarios.

    This class extends the base `argparse.Action` to properly handle three cases:
      1. When values are explicitly provided with the argument (e.g., `--arg value1 value2`)
      2. When the flag is used without values (e.g., `--arg`), returning the const value
      3. When the argument is not used at all, returning the default value

    Args:
        parser (argparse.ArgumentParser): The parser object that uses this action.
        namespace (argparse.Namespace): The namespace to store the argument values.
        values (any): The argument values provided by the user.
        option_string (str, optional): The option string used to invoke this action.

    Example:
        parser.add_argument('--arg', nargs='*', action=ConstWithMultiArgs, const=DEFAULT_VALUE)
    """

    def __call__(self, parser, namespace, values, option_string=None):
        obj = (
            values
            if values  # if values are provided (e.g., `--arg value1 value2`)
            else self.const
            if option_string  # if `--arg` is used without values
            else self.default  # if `--arg` is not used at all
        )
        setattr(namespace, self.dest, obj)


def cli() -> argparse.Namespace:
    """Parse command-line arguments.

    Determines input files or stdin and validates file existence
    """
    parser = argparse.ArgumentParser(
        prog="dv",
        description="Interactive terminal based viewer/editor for tabular data (e.g., CSV/Excel).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  %(prog)s data.csv\n"
        "  %(prog)s file1.csv file2.csv file3.csv\n"
        "  %(prog)s data.xlsx (opens each sheet in separate tab)\n"
        "  cat data.txt | %(prog)s -d ';'\n",
    )
    parser.add_argument("files", nargs="*", help="Files to view (or read from stdin)")
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-d",
        "--delimiter",
        help="Specify the delimiter of the input files (must be a single character, e.g., `,` or `|`)",
    )
    parser.add_argument(
        "-f",
        "--fields",
        nargs="*",
        action=ConstWithMultiArgs,
        const="list",
        help="When used without values, list available fields. Otherwise, read only specified fields.",
    )
    parser.add_argument(
        "-H",
        "--header",
        nargs="*",
        action=ConstWithMultiArgs,
        const=False,
        help="Specify header info. when reading CSV/TSV. If used without values, assumes no header. Otherwise, use provided values as column names (e.g., `-H col1 col2 col3`).",
    )
    parser.add_argument(
        "-I", "--no-inference", action="store_true", help="Do not infer data types when reading CSV/TSV"
    )
    parser.add_argument(
        "-T", "--truncate-ragged-lines", action="store_true", help="Truncate ragged lines when reading CSV/TSV"
    )
    parser.add_argument("-E", "--ignore-errors", action="store_true", help="Ignore errors when reading CSV/TSV")
    parser.add_argument(
        "-C",
        "--comment-prefix",
        metavar="PREFIX",
        nargs="?",
        const="#",
        help="Skip comment lines starting with `PREFIX` when reading CSV/TSV",
    )
    parser.add_argument(
        "-Q",
        "--quote-char",
        metavar="C",
        nargs="?",
        const=None,
        default='"',
        help="Use `C` as quote character for reading CSV/TSV. When used without value, disables special handling of quote characters.",
    )
    parser.add_argument(
        "-K", "--skip-lines", metavar="N", type=int, default=0, help="Skip first N lines when reading CSV/TSV"
    )
    parser.add_argument(
        "-A",
        "--skip-rows-after-header",
        metavar="N",
        type=int,
        default=0,
        help="Skip N rows after header when reading CSV/TSV",
    )
    parser.add_argument("-M", "--n-rows", metavar="N", type=int, help="Read maximum rows")
    parser.add_argument(
        "-N",
        "--null",
        nargs="+",
        default=["IsNULL", "NULL"],
        help="Values to interpret as null values when reading CSV/TSV",
    )

    parser.add_argument(
        "--theme",
        nargs="?",
        default="textual-dark",
        const="list",
        help="Set the theme for the application. If used without value, show available themes.",
    )

    parser.add_argument(
        "--all-in-one",
        "--aio",
        action="store_true",
        help="Read all files (must be of the same structure) into a single table.",
    )

    args = parser.parse_args()

    if args.delimiter and len(args.delimiter) != 1:
        print("Delimiter must be a single character.", file=sys.stderr)
        sys.exit(1)

    # List available themes and exit
    if args.theme == "list":
        print("Available themes:")
        for theme in BUILTIN_THEMES:
            print(f"  - {theme}")
        sys.exit(0)
    elif args.theme and args.theme not in BUILTIN_THEMES:
        print(f"Theme '{args.theme}' not found. Use '--theme list' to show available themes.", file=sys.stderr)
        sys.exit(1)

    # Handle files
    if args.files is None:
        args.files = []

    # Check if reading from stdin (pipe or redirect)
    if not sys.stdin.isatty() and "-" not in args.files:
        args.files.append("-")

    # Validate all files
    for filename in args.files:
        if filename == "-":
            continue  # stdin will be handled separately

        filepath = Path(filename)
        if not filepath.exists():
            print(f"File not found: `{filename}`", file=sys.stderr)
            sys.exit(1)
        elif not filepath.is_file():
            print(f"Not a file: `{filename}`", file=sys.stderr)
            sys.exit(1)
        elif filepath.stat().st_size == 0:
            print(f"File is empty: `{filename}`", file=sys.stderr)
            sys.exit(1)

    if not args.files:
        parser.print_help()
        sys.exit(1)

    return args


def main() -> None:
    args = cli()

    sources = load_dataframe(
        args.files,
        delimiter=args.delimiter,
        header=args.header,
        infer_schema=not args.no_inference,
        comment_prefix=args.comment_prefix,
        quote_char=args.quote_char,
        skip_lines=args.skip_lines,
        skip_rows_after_header=args.skip_rows_after_header,
        null_values=args.null,
        ignore_errors=args.ignore_errors,
        truncate_ragged_lines=args.truncate_ragged_lines,
        n_rows=20 if args.fields == "list" else args.n_rows,
        use_columns=args.fields if args.fields and args.fields != "list" else None,
        all_in_one=args.all_in_one,
    )

    # List available fields and exit
    if args.fields == "list":
        for source in sources:
            for idx, field in enumerate(source.lf.collect_schema().names()):
                print(idx + 1, field, sep="\t")
            break  # Only list fields for the first source

        return

    # Run the DataFrame Viewer application
    app = DataFrameViewer(*sources, theme=args.theme)
    handle_compute_error(app.run())


if __name__ == "__main__":
    main()
