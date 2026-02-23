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
    FindReplaceScreen,
    FreezeScreen,
    OpenFileScreen,
    RenameColumnScreen,
    RenameTabScreen,
    SaveFileScreen,
    SearchScreen,
    ViewScreen,
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
    "MetaShape",
    "OpenFileScreen",
    "RenameColumnScreen",
    "RenameTabScreen",
    "RowDetailScreen",
    "SaveFileScreen",
    "SearchScreen",
    "StatisticsScreen",
    "TableScreen",
    "ViewScreen",
    "YesNoScreen",
]
