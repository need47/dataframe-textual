"""A screen to display Plotext plots."""

from collections.abc import Callable, Iterable
from types import ModuleType
from typing import TYPE_CHECKING, Any

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


def _has_non_pos(values: Iterable[Any]) -> bool:
    """Return True if any value in the iterable is non-positive."""
    return any(v <= 0 for v in values)


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

    COMMAND_SCOPE = Scope.PLOT_SCREEN
    DEFAULT_CSS = """
        PlotScreen {
            align: center middle;
        }

        PlotScreen PlotextPlot {
            width: 80%;
            height: 80%;
        }
    """

    def __init__(self) -> None:
        super().__init__()
        self.registry: KeyBindingRegistry = self.app.key_registry
        self.scale_x = False
        self.scale_y = False

    def compose(self) -> ComposeResult:
        self.plot = PlotextPlot(id="plot")
        yield self.plot

    def on_mount(self) -> None:
        """Configure the initial plot after the widget is mounted."""
        self.draw()

    def on_key(self, event: Key) -> None:
        """Dispatch screen-specific commands, then common plot-screen commands."""
        for scope in (self.COMMAND_SCOPE, Scope.PLOT_SCREEN):
            if self.registry.dispatch(event.key, "", scope, self):
                event.stop()
                event.prevent_default()
                return

        # Unhandled key event will bubble up to the viewer/app level
        event.stop()
        event.prevent_default()

    def cmd_close_plot(self) -> None:
        """Close the plot modal."""
        self.app.pop_screen()

    def cmd_toggle_scale_x(self) -> None:
        """Toggle the x-axis scale between linear and logarithmic."""
        self.scale_x = not self.scale_x
        self.draw()

    def cmd_toggle_scale_y(self) -> None:
        """Toggle the y-axis scale between linear and logarithmic."""
        self.scale_y = not self.scale_y
        self.draw()

    def _apply_axis_scales(self, axis: str = "xy") -> None:
        """Apply and validate each requested axis scale before refreshing the plot."""
        fig = self.plot.plt.figure

        if "x" in axis:
            fig.ruler("x", side="both").scale("log" if self.scale_x else "linear")
        if "y" in axis:
            fig.ruler("y", side="both").scale("log" if self.scale_y else "linear")

    def draw(self) -> None:
        """Update the plot with the current data."""
        raise NotImplementedError("Subclasses must implement the draw method.")


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

        if self.scale_x and _has_non_pos(x_values):
            self.app.notify(
                "X values contain zero or negative numbers, cannot use log scale",
                title="Scatter Plot",
                severity="warning",
            )
            return
        if self.scale_y and _has_non_pos(y_values):
            self.app.notify(
                "Y values contain zero or negative numbers, cannot use log scale",
                title="Scatter Plot",
                severity="warning",
            )
            return

        plt = self.plot.plt
        fig = plt.figure
        fig.clear()
        fig.draw(fig.signal(x_values, y_values))
        # fig.title("Scatter Plot")
        fig.label(self.col_x or self.col_y, axis="x")
        fig.label(self.col_y, axis="y")
        self._apply_axis_scales("xy")
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

        if self.scale_x and _has_non_pos(x_values):
            self.app.notify(
                "X values contain zero or negative numbers, cannot use log scale",
                title="Line Plot",
                severity="warning",
            )
            return
        if self.scale_y and _has_non_pos(y_values):
            self.app.notify(
                "Y values contain zero or negative numbers, cannot use log scale",
                title="Line Plot",
                severity="warning",
            )
            return

        plt = self.plot.plt
        fig = plt.figure
        fig.clear()
        chart = fig.signal(x_values, y_values).lines()
        fig.draw(chart)
        fig.draw(fig.signal(x_values, y_values, marker=plt.marker("circle")))
        fig.label(self.col_x or self.col_y, axis="x")
        fig.label(self.col_y, axis="y")
        self._apply_axis_scales("xy")
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
        labels = self.y_columns
        y_values = [self.df[col_name].drop_nulls() for col_name in self.y_columns]

        if self.scale_y and any(_has_non_pos(ys) for ys in y_values):
            self.app.notify(
                "Y values contain zero or negative numbers, cannot use log scale",
                title="Box Plot",
                severity="warning",
            )
            return

        plt = self.plot.plt
        fig = plt.figure
        fig.clear()
        fig.draw(fig.box(labels, y_values))
        # fig.title("Box Plot")
        self._apply_axis_scales("y")
        self.plot.refresh()


class BarPlotScreen(PlotScreen):
    """Display grouped bars for one or more numeric dataframe columns."""

    COMMAND_SCOPE = Scope.BAR_PLOT_SCREEN
    CSS = PlotScreen.DEFAULT_CSS.replace("PlotScreen", "BarPlotScreen")

    def __init__(self, df: pl.DataFrame, y_columns: list[str], x_column: str | None = None):
        super().__init__()
        self.df = df
        self.x_column = x_column
        self.y_columns = y_columns
        self.orientation = "vertical"
        self.stacked = False
        self.label_mode: bool | str = False

    def cmd_barplot_cycle_label(self) -> None:
        """Cycle bar labels through none, count, percentage, and both modes."""
        label_modes: tuple[bool | str, ...] = (False, True, "%", "both")
        self.label_mode = label_modes[(label_modes.index(self.label_mode) + 1) % len(label_modes)]
        self.draw()

    def cmd_barplot_toggle_orientation(self) -> None:
        """Toggle the bar plot between horizontal and vertical, then redraw."""
        self.orientation = "horizontal" if self.orientation == "vertical" else "vertical"
        self.draw()

    def cmd_barplot_toggle_stacked(self) -> None:
        """Toggle stacked bars and redraw the plot."""
        self.stacked = not self.stacked
        self.draw()

    def _series_markers_and_label(self, y_columns: list[str], plt: ModuleType) -> tuple[list[Any] | None, Any | None]:
        """Build series markers and a matching label, using Plotext defaults for one series."""
        if not y_columns:
            return None, None
        if len(y_columns) == 1:
            return None, y_columns[0]

        # Generate a unique marker for each series and remove it from the figure's cycler to avoid reuse.
        markers = []
        for _ in y_columns:
            marker = plt.figure._next_marker()
            markers.append(marker)
            plt.figure._cycler.remove_pixel(marker.pixel())

        labels = [
            plt.colorize(col_name).fill(marker.pixel()) for col_name, marker in zip(y_columns, markers, strict=True)
        ]
        label_matrix = labels[0].matrix()
        for label in labels[1:]:
            label_matrix = label_matrix.hstack(", ").hstack(label)

        return markers, label_matrix

    def _build_with_positive_baseline(
        self, builder: Callable[[], Any], minimum: float | None = None, omit_empty: bool = False
    ) -> Any:
        """Build native bars with positive lower bounds when the value axis is logarithmic.

        Args:
            builder: Callable constructing the bar or histogram signal.
            minimum: Smallest bar value across series, or None to use bin heights.
            omit_empty: Whether to omit zero-height histogram bins on log axes.

        Returns:
            The constructed Plotext signal.
        """
        value_axis = "y" if self.orientation == "vertical" else "x"
        if not getattr(self, f"scale_{value_axis}"):
            return builder()
        if minimum is not None and minimum / 10 <= 0:
            setattr(self, f"scale_{value_axis}", False)
            self.app.notify("Logarithmic bars require strictly positive values", title="Log Scale", severity="warning")
            return builder()

        fig = self.plot.plt.figure
        original_flat_bar = fig._flat_bar

        def positive_baseline_bar(*args: Any, **kwargs: Any) -> Any:
            """Adjust lower bounds before Plotext constructs bar geometry."""
            positions, upper = args[0], args[-1]
            if omit_empty:
                populated = [(position, value) for position, value in zip(positions, upper, strict=True) if value > 0]
                positions = [position for position, _ in populated]
                upper = [value for _, value in populated]
                if not upper:
                    return original_flat_bar(positions, upper, **kwargs)
            baseline = (minimum if minimum is not None else min(upper)) / 10
            lower = [baseline] * len(upper) if len(args) == 2 else [max(value, baseline) for value in args[1]]
            return original_flat_bar(positions, lower, upper, **kwargs)

        try:
            fig._flat_bar = positive_baseline_bar
            return builder()
        finally:
            fig._flat_bar = original_flat_bar

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
        series_markers, series_label = self._series_markers_and_label(self.y_columns, plt)

        labeled: bool | list[list[str]] = self.label_mode is True
        if self.label_mode in ("%", "both"):
            labeled = []
            for values in y_values:
                total = values.sum()
                value_labels = []
                for value in values:
                    percentage = value / total * 100 if total else 0
                    if self.label_mode == "%":
                        value_labels.append(f"{percentage:.1f}%")
                    else:
                        value_labels.append(f"{value} ({percentage:.1f}%)")
                labeled.append(value_labels)

        chart = self._build_with_positive_baseline(
            lambda: fig.bar(
                x_values,
                y_values,
                orientation=self.orientation,
                stacked=self.stacked,
                labeled=labeled,
                marker=series_markers,
            ),
            minimum=min(values.min() for values in y_values),
        )
        fig.draw(chart)
        # fig.title("Bar Plot")
        fig.label(self.x_column, axis="x")
        fig.label(series_label, axis="y")
        self._apply_axis_scales("y" if self.orientation == "vertical" else "x")
        self.plot.refresh()


class HistogramPlotScreen(BarPlotScreen):
    """Display overlaid histograms for one or more numeric dataframe columns."""

    COMMAND_SCOPE = Scope.HISTOGRAM_PLOT_SCREEN
    CSS = PlotScreen.DEFAULT_CSS.replace("PlotScreen", "HistogramPlotScreen")

    def __init__(self, df: pl.DataFrame, y_columns: list[str]):
        super().__init__(df, y_columns)
        self.bins = 10
        self.norm = False

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

    def cmd_histogram_toggle_norm(self) -> None:
        """Toggle histogram normalization and redraw."""
        self.norm = not self.norm
        self.draw()

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
            # Series doesn't work for normalization, so we convert to a list
            values = self.df[col_name].drop_nulls().to_list()
            if not values:
                continue

            fig.draw(
                self._build_with_positive_baseline(
                    lambda: fig.hist(
                        values,
                        bins=self.bins,
                        orientation=self.orientation,
                        norm=self.norm,
                    ),
                    omit_empty=True,
                ).label(col_name)
            )
            plotted_columns += 1

        if not plotted_columns:
            self.app.notify("No values available for a histogram", title="Histogram", severity="warning")
            return

        # fig.title("Histogram")
        self._apply_axis_scales("y" if self.orientation == "vertical" else "x")
        self.plot.refresh()


class ConfusionMatrixScreen(PlotScreen):
    """Display counts comparing actual and predicted string labels."""

    COMMAND_SCOPE = Scope.CONFUSION_MATRIX_SCREEN
    CSS = PlotScreen.DEFAULT_CSS.replace("PlotScreen", "ConfusionMatrixScreen")

    def __init__(self, df: pl.DataFrame, actual_column: str, predicted_column: str) -> None:
        super().__init__()
        self.df = df
        self.actual_column = actual_column
        self.predicted_column = predicted_column
        self.norm = False

    def cmd_cmatrix_toggle_norm(self) -> None:
        """Toggle normalization of the confusion matrix."""
        self.norm = not self.norm
        self.draw()

    def draw(self) -> None:
        """Draw a confusion matrix from the selected actual and predicted columns."""
        fig = self.plot.plt.figure
        fig.clear()

        if self.df.is_empty():
            self.app.notify("No rows available for a confusion matrix", title="Confusion Matrix", severity="warning")
            return

        actual = self.df[self.actual_column]
        predicted = self.df[self.predicted_column]
        labels = sorted(set(actual.to_list()) | set(predicted.to_list()))
        fig.draw(fig.cmatrix(actual, predicted, labels=labels, map="viridis", norm=self.norm))
        positions = list(range(len(labels)))
        fig.ruler("x", side="both").ticks(positions, labels=labels)
        fig.ruler("y", side="both").ticks(positions, labels=labels[::-1])
        fig.label(self.predicted_column, axis="x", side="both")
        fig.label(self.actual_column, axis="y", side="both")
        self.plot.refresh()
