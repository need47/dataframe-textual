"""DataFrame Viewer - Interactive CSV/Excel viewer for the terminal."""

from importlib.metadata import version

__version__ = version("dataframe-textual")

from .data_frame_table import DataFrameTable, History
from .data_frame_viewer import DataFrameViewer
from .help_panel import DataFrameHelpPanel
from .table_screen import (
    FrequencyScreen,
    MetaColumnScreen,
    RowDetailScreen,
    StatisticsScreen,
    TableScreen,
)
from .yes_no_screen import (
    AddColumnScreen,
    AddLinkScreen,
    ConfirmScreen,
    EditCellScreen,
    EditColumnScreen,
    FindReplaceScreen,
    FreezeScreen,
    RenameColumnScreen,
    RenameTabScreen,
    SearchScreen,
    YesNoScreen,
)

__all__ = [
    "AddColumnScreen",
    "AddLinkScreen",
    "ConfirmScreen",
    "DataFrameHelpPanel",
    "DataFrameTable",
    "DataFrameViewer",
    "EditCellScreen",
    "EditColumnScreen",
    "FindReplaceScreen",
    "FreezeScreen",
    "FrequencyScreen",
    "History",
    "MetaColumnScreen",
    "OpenFileScreen",
    "RenameColumnScreen",
    "RenameTabScreen",
    "RowDetailScreen",
    "SaveFileScreen",
    "SearchScreen",
    "StatisticsScreen",
    "TableScreen",
    "SearchScreen",
    "YesNoScreen",
]
