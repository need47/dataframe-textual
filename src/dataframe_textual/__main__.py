"""Entry point for running DataFrameViewer as a module."""

import argparse
import sys
from pathlib import Path

from .data_frame_viewer import DataFrameViewer


def main():
    """Run the DataFrame Viewer application."""
    parser = argparse.ArgumentParser(
        description="Interactive CSV/Excel viewer for the terminal (Textual version)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  dataframe-viewer data.csv\n"
        "  dataframe-viewer file1.csv file2.csv file3.csv\n"
        "  dataframe-viewer data.xlsx  (opens all sheets in tabs)\n"
        "  cat data.csv | dataframe-viewer\n",
    )
    parser.add_argument("files", nargs="*", help="CSV or Excel files to view (or read from stdin)")

    args = parser.parse_args()
    filenames = []

    # Check if reading from stdin (pipe or redirect)
    if not sys.stdin.isatty():
        filenames = ["-"]
    elif args.files:
        # Validate all files exist
        for filename in args.files:
            if not Path(filename).exists():
                print(f"File not found: {filename}")
                sys.exit(1)
        filenames = args.files

    if not filenames:
        parser.print_help()
        sys.exit(1)

    app = DataFrameViewer(*filenames)
    app.run()


if __name__ == "__main__":
    main()
