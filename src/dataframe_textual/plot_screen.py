"""A screen to display Plotext plots."""

from types import ModuleType
from typing import TYPE_CHECKING

import polars as pl
from rich.text import Text
from textual.app import ComposeResult, RenderResult
from textual.events import Key
from textual.screen import ModalScreen
from textual.widget import Widget

from .commands import Scope
from .yes_no_screen import ConfirmScreen

if TYPE_CHECKING:
    from .keybindings import KeyBindingRegistry


class PlotextPlot(Widget):
    """Display a Plotext figure sized to the widget's available area."""

    DEFAULT_CSS = """
        PlotextPlot {
            width: 1fr;
            height: 1fr;
        }
    """

    @property
    def plt(self) -> ModuleType:
        """Return Plotext's plotting API for configuring this widget's figure."""
        try:
            import plotext
        except ModuleNotFoundError as e:
            if e.name != "plotext":
                raise
            raise ModuleNotFoundError(
                "Plot rendering requires the optional Plotext dependency. Install it with `pip install plotext`."
            ) from e

        return plotext

    def render(self) -> RenderResult:
        """Build and return the plot as a Rich renderable."""
        if self.size.width <= 0 or self.size.height <= 0:
            return Text("Plot area too small")

        figure = self.plt.figure
        figure.plot_size(self.size.width, self.size.height)
        return Text.from_ansi(figure.build().string())


class PlotScreen(ModalScreen):
    """Base class for screens displaying Plotext plots."""

    DEFAULT_CSS = """
        PlotScreen {
            align: center middle;
        }

        PlotScreen PlotextPlot {
            width: 80%;
            height: 60%;
        }
    """

    def __init__(self) -> None:
        super().__init__()
        self.registry: KeyBindingRegistry = self.app.key_registry

    def compose(self) -> ComposeResult:
        self.plot = PlotextPlot(id="plot")
        yield self.plot

    def on_mount(self) -> None:
        """Configure the initial plot after the widget is mounted."""
        self.draw()

    def on_key(self, event: Key) -> None:
        """Dispatch plot-screen commands and close on q or Escape."""
        if self.registry.dispatch(event.key, "", Scope.PLOT_SCREEN, self):
            event.stop()
            event.prevent_default()
            return

    def cmd_close_plot(self) -> None:
        """Close the plot modal."""
        self.app.pop_screen()

    def draw(self) -> None:
        """Update the plot with the current data."""
        raise NotImplementedError("Subclasses must implement the draw method.")


class BarPlotScreen(PlotScreen):
    """Display grouped bars for one or more numeric dataframe columns."""

    CSS = PlotScreen.DEFAULT_CSS.replace("PlotScreen", "BarPlotScreen")

    def __init__(self, df: pl.DataFrame, y_columns: list[str], x_column: str | None = None):
        super().__init__()
        self.df = df
        self.x_column = x_column
        self.y_columns = y_columns
        self.orientation = "vertical"  # Default orientation for the bar plot
        self.stacked = False
        self.labeled = False

    def on_key(self, event: Key) -> None:
        """Handle bar orientation commands before common plot-screen keys."""
        if self.registry.dispatch(event.key, "", Scope.BAR_PLOT_SCREEN, self):
            event.stop()
            event.prevent_default()
            return

        super().on_key(event)

    def cmd_barplot_horizontal(self) -> None:
        """Switch the bar plot to horizontal orientation and redraw it."""
        self.orientation = "horizontal"
        self.draw()

    def cmd_barplot_vertical(self) -> None:
        """Switch the bar plot to vertical orientation and redraw it."""
        self.orientation = "vertical"
        self.draw()

    def cmd_barplot_toggle_orientation(self) -> None:
        """Toggle the bar plot between horizontal and vertical, then redraw."""
        self.orientation = "horizontal" if self.orientation == "vertical" else "vertical"
        self.draw()

    def cmd_barplot_toggle_stacked(self) -> None:
        """Toggle stacked bars and redraw the plot."""
        self.stacked = not self.stacked
        self.draw()

    def draw(self) -> None:
        """Draw one bar series per selected y column."""
        plt = self.plot.plt
        fig = plt.figure
        fig.clear()

        columns = ([self.x_column] if self.x_column is not None else []) + self.y_columns
        plot_data = self.df.select(columns).drop_nulls()
        if plot_data.is_empty():
            self.app.notify("No values available for a bar plot", title="Bar Plot", severity="warning")
            return

        x_values = (
            plot_data[self.x_column] if self.x_column is not None else pl.Series("x", range(1, plot_data.height + 1))
        )
        y_values = [plot_data[col_name] for col_name in self.y_columns]
        fig.draw(fig.bar(x_values, y_values, orientation=self.orientation, stacked=self.stacked, labeled=self.labeled))
        # fig.title("Bar Plot")
        fig.label(self.x_column or "Row", axis="x")
        fig.label(", ".join(self.y_columns), axis="y")
        self.plot.refresh()


class HistogramPlotScreen(BarPlotScreen):
    """Display overlaid histograms for one or more numeric dataframe columns."""

    CSS = PlotScreen.DEFAULT_CSS.replace("PlotScreen", "HistogramPlotScreen")

    def __init__(self, df: pl.DataFrame, y_columns: list[str]):
        super().__init__(df, y_columns)
        self.bins = 10

    def on_key(self, event: Key) -> None:
        """Dispatch histogram orientation commands, then common plot keys."""
        if self.registry.dispatch(event.key, "", Scope.HISTOGRAM_PLOT_SCREEN, self):
            event.stop()
            event.prevent_default()
            return

        super().on_key(event)

    def cmd_histogram_toggle_orientation(self) -> None:
        """Toggle the histogram between horizontal and vertical, then redraw."""
        self.orientation = "horizontal" if self.orientation == "vertical" else "vertical"
        self.draw()

    def cmd_histogram_set_bins(self) -> None:
        """Prompt for a positive bin count and redraw the histogram."""
        self.app.push_screen(
            ConfirmScreen(
                title="Histogram Bins",
                label="Enter the number of bins",
                input={"value": str(self.bins), "type": "number"},
                yes="Apply",
                no="Cancel",
            ),
            callback=self._apply_bin_count,
        )

    def _apply_bin_count(self, result: str | None) -> None:
        """Apply a valid bin count returned by the confirmation dialog."""
        if result is None:
            return

        try:
            bins = int(result)
        except ValueError:
            self.notify("Enter a whole number of bins", title="Histogram Bins", severity="warning")
            return

        if bins < 1:
            self.notify("The number of bins must be at least 1", title="Histogram Bins", severity="warning")
            return

        self.bins = bins
        self.draw()

    def draw(self) -> None:
        """Draw one labeled histogram for each y column."""
        plt = self.plot.plt
        fig = plt.figure
        fig.clear()

        plotted_columns = 0
        for col_name in self.y_columns:
            values = self.df[col_name].drop_nulls()
            if values.is_empty():
                continue
            fig.draw(fig.hist(values, bins=self.bins, orientation=self.orientation).label(col_name))
            plotted_columns += 1

        if not plotted_columns:
            self.app.notify("No values available for a histogram", title="Histogram", severity="warning")
            return

        # fig.title("Histogram")
        self.plot.refresh()


class ScatterPlotScreen(PlotScreen):
    """Display a scatter plot of the selected y column against the x column or row positions."""

    CSS = PlotScreen.DEFAULT_CSS.replace("PlotScreen", "ScatterPlotScreen")

    def __init__(self, df: pl.DataFrame, col_y: str, col_x: str | None = None):
        super().__init__()
        self.df = df
        self.col_x = col_x
        self.col_y = col_y

    def draw(self) -> None:
        """Update the plot with the current DataFrame and columns."""
        plt = self.plot.plt
        fig = plt.figure
        fig.clear()

        y_values = self.df[self.col_y]
        if self.col_x is None:
            valid_rows = y_values.is_not_null()
            x_values = pl.Series("Row", range(1, self.df.height + 1)).filter(valid_rows)
            y_values = y_values.filter(valid_rows)
        else:
            x_values = self.df[self.col_x]
            valid_rows = x_values.is_not_null() & y_values.is_not_null()
            x_values = x_values.filter(valid_rows)
            y_values = y_values.filter(valid_rows)

        if y_values.is_empty():
            self.app.notify("No values available for a scatter plot", title="Scatter Plot", severity="warning")
            return

        fig.draw(fig.signal(x_values, y_values))
        # fig.title("Scatter Plot")
        fig.label(self.col_x or self.col_y, axis="x")
        fig.label(self.col_y, axis="y")
        self.plot.refresh()


class LinePlotScreen(PlotScreen):
    """Display a numeric y column against row positions or an x column."""

    CSS = PlotScreen.DEFAULT_CSS.replace("PlotScreen", "LinePlotScreen")

    def __init__(self, df: pl.DataFrame, col_y: str, col_x: str | None = None) -> None:
        super().__init__()
        self.df = df
        self.col_x = col_x
        self.col_y = col_y

    def draw(self) -> None:
        """Draw the selected y column against row positions or the selected x column."""
        plt = self.plot.plt
        fig = plt.figure
        fig.clear()

        y_values = self.df[self.col_y]
        if self.col_x is None:
            valid_rows = y_values.is_not_null()
            x_values = pl.Series("Row", range(1, self.df.height + 1)).filter(valid_rows)
            y_values = y_values.filter(valid_rows)
        else:
            x_values = self.df[self.col_x]
            valid_rows = x_values.is_not_null() & y_values.is_not_null()
            x_values = x_values.filter(valid_rows)
            y_values = y_values.filter(valid_rows)

        if y_values.is_empty():
            self.app.notify("No values available for a line plot", title="Line Plot", severity="warning")
            return

        chart = fig.signal(x_values, y_values).lines()
        fig.draw(chart)
        fig.label(self.col_x or self.col_y, axis="x")
        fig.label(self.col_y, axis="y")
        self.plot.refresh()


class BoxPlotScreen(PlotScreen):
    """Display box plots for one or more numeric dataframe columns."""

    CSS = PlotScreen.DEFAULT_CSS.replace("PlotScreen", "BoxPlotScreen")

    def __init__(self, df: pl.DataFrame, y_columns: list[str]):
        super().__init__()
        self.df = df
        self.y_columns = y_columns

    def draw(self) -> None:
        """Build one labeled box distribution for each y column."""
        plt = self.plot.plt
        fig = plt.figure
        fig.clear()

        labels = self.y_columns
        data = [self.df[col_name].drop_nulls().to_list() for col_name in self.y_columns]
        plot_data = [(label, values) for label, values in zip(labels, data, strict=True) if values]
        if not plot_data:
            self.app.notify("No numeric values available for a box plot", title="Box Plot", severity="warning")
            return

        labels, data = zip(*plot_data, strict=True)
        fig.draw(fig.box(labels, data))
        # fig.title("Box Plot")
        self.plot.refresh()
