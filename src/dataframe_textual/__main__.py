"""Entry point for running DataFrameViewer as a module."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .common import SUPPORTED_FORMATS, load_dataframe
from .data_frame_viewer import DataFrameViewer


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
        "  %(prog)s data.xlsx  (opens each sheet in separate tab)\n"
        "  cat data.csv | %(prog)s --format csv\n",
    )
    parser.add_argument("files", nargs="*", help="Files to view (or read from stdin)")
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=SUPPORTED_FORMATS,
        help="Specify the format of the input files (csv, excel, tsv etc.)",
    )
    parser.add_argument(
        "-H",
        "--no-header",
        action="store_true",
        help="Specify that input files have no header row when reading CSV/TSV",
    )
    parser.add_argument(
        "-I", "--no-inference", action="store_true", help="Do not infer data types when reading CSV/TSV"
    )
    parser.add_argument(
        "-t", "--truncate-ragged-lines", action="store_true", help="Truncate ragged lines when reading CSV/TSV"
    )
    parser.add_argument("-E", "--ignore-errors", action="store_true", help="Ignore errors when reading CSV/TSV")
    parser.add_argument(
        "-c", "--comment-prefix", nargs="?", const="#", help="Comment lines are skipped when reading CSV/TSV"
    )
    parser.add_argument(
        "-q", "--quote-char", nargs="?", const=None, default='"', help="Quote character for reading CSV/TSV"
    )
    parser.add_argument("-l", "--skip-lines", type=int, default=0, help="Skip lines when reading CSV/TSV")
    parser.add_argument(
        "-a", "--skip-rows-after-header", type=int, default=0, help="Skip rows after header when reading CSV/TSV"
    )
    parser.add_argument("-n", "--null", nargs="+", help="Values to interpret as null values when reading CSV/TSV")

    args = parser.parse_args()
    if args.files is None:
        args.files = []

    # Check if reading from stdin (pipe or redirect)
    if not sys.stdin.isatty():
        args.files.append("-")
    else:
        # Validate all files exist
        for filename in args.files:
            if not Path(filename).exists():
                print(f"File not found: {filename}")
                sys.exit(1)

    if not args.files:
        parser.print_help()
        sys.exit(1)

    return args


def main() -> None:
    """Run the DataFrame Viewer application."""
    args = cli()
    sources = load_dataframe(
        args.files,
        file_format=args.format,
        has_header=not args.no_header,
        infer_schema=not args.no_inference,
        comment_prefix=args.comment_prefix,
        quote_char=args.quote_char,
        skip_lines=args.skip_lines,
        skip_rows_after_header=args.skip_rows_after_header,
        null_values=args.null,
        ignore_errors=args.ignore_errors,
        truncate_ragged_lines=args.truncate_ragged_lines,
    )
    app = DataFrameViewer(*sources)
    app.run()


if __name__ == "__main__":
    main()
