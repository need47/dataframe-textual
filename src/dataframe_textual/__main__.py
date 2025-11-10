"""Entry point for running DataFrameViewer as a module."""

import argparse
import sys
from pathlib import Path

from .data_frame_viewer import DataFrameViewer

SUPPORTED_FORMATS = ["csv", "excel", "tsv", "parquet", "json", "ndjson"]


def main() -> None:
    """Run the DataFrame Viewer application.

    Parses command-line arguments to determine input files or stdin, validates
    file existence, and launches the interactive DataFrame Viewer application.

    Returns:
        None

    Raises:
        SystemExit: If invalid arguments are provided or required files are missing.
    """
    parser = argparse.ArgumentParser(
        description="Interactive terminal based viewer/editor for tabular data (e.g., CSV/Excel).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  dataframe-textual data.csv\n"
        "  dataframe-textual file1.csv file2.csv file3.csv\n"
        "  dataframe-textual data.xlsx  (opens all sheets in tabs)\n"
        "  cat data.csv | dataframe-textual --format csv\n",
    )
    parser.add_argument("files", nargs="*", help="Files to view (or read from stdin)")
    parser.add_argument(
        "-f",
        "--format",
        choices=SUPPORTED_FORMATS,
        help="Specify the format of the input files (csv, excel, tsv etc.)",
    )
    parser.add_argument("-H", "--no-header", action="store_true", help="Specify that input files have no header row")

    args = parser.parse_args()
    filenames = []

    # Check if reading from stdin (pipe or redirect)
    if not sys.stdin.isatty():
        filenames.append("-")
    if args.files:
        # Validate all files exist
        for filename in args.files:
            if not Path(filename).exists():
                print(f"File not found: {filename}")
                sys.exit(1)
        filenames.extend(args.files)

    if not filenames:
        parser.print_help()
        sys.exit(1)

    app = DataFrameViewer(*filenames, file_format=args.format, has_header=not args.no_header)
    app.run()


if __name__ == "__main__":
    main()
