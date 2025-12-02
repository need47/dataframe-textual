"""DataFrame Viewer - Interactive CSV/Excel viewer for the terminal."""

from importlib.metadata import version

__version__ = version("dataframe-textual")

from .data_frame_help_panel import DataFrameHelpPanel
from .data_frame_table import DataFrameTable, History
from .data_frame_viewer import DataFrameViewer
from .table_screen import (
    FrequencyScreen,
    MetaColumnScreen,
    MetaShape,
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
    FilterScreen,
    FindReplaceScreen,
    FreezeScreen,
    OpenFileScreen,
    RenameColumnScreen,
    RenameTabScreen,
    SaveFileScreen,
    SearchScreen,
    YesNoScreen,
)

__all__ = [
    "DataFrameViewer",
    "DataFrameHelpPanel",
    "DataFrameTable",
    "History",
    "TableScreen",
    "RowDetailScreen",
    "FrequencyScreen",
    "StatisticsScreen",
    "MetaShape",
    "MetaColumnScreen",
    "YesNoScreen",
    "SaveFileScreen",
    "ConfirmScreen",
    "EditCellScreen",
    "SearchScreen",
    "FilterScreen",
    "FreezeScreen",
    "OpenFileScreen",
    "RenameColumnScreen",
    "EditColumnScreen",
    "AddColumnScreen",
    "AddLinkScreen",
    "FindReplaceScreen",
    "RenameTabScreen",
]
