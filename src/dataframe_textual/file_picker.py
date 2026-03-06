"""Modal screens for file picking dialogs."""

from pathlib import Path
from typing import Iterable

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Click
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Select
from textual.widgets.option_list import Option

from .common import SUPPORTED_FORMATS, guess_file_format


class FilePicker(ModalScreen):
    """Base modal screen for file picker dialogs."""

    BINDINGS = [("q,escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
        FilePicker {
            align: center middle;
        }

        #file-picker {
            width: 80;
            height: 90%;
            max-height: 90%;
            border: solid $primary;
            border-title-color: $primary;
            padding: 1;
            overflow: hidden;
        }

        #file-picker Horizontal {
            height: auto;
            align-vertical: middle;
        }

        #file-picker Button {
            height: 3;
        }

        #folder {
            margin-bottom: 1;
        }

        #folder Label {
            height: 3;
            padding: 1 0 1 1;
        }

        #dirname {
            width: 1fr;
        }

        #back, #up, #home {
            width: 6;
            min-width: 6;
            margin-left: 1;
            margin-right: 1;
        }

        #file-list {
            height: 1fr;
            min-height: 10;
            margin-bottom: 1;
            overflow: auto;
        }

        #file-name-type {
            margin-bottom: 1;
        }

        #filename {
            width: 1fr;
            margin-right: 1;
        }

        #file-type {
            width: 30;
        }

        #file-action {
            align: center middle;
        }

        #confirm, #cancel {
            margin-left: 2;
            margin-right: 2;
        }
    """

    def __init__(self, title: str = "", confirm_label: str = "Open", dirname: str = ".", filename: str = "") -> None:
        """Initialize the file picker.

        Args:
            title: Dialog title to display in the border.
            confirm: Label for the confirm button.
            dirname: Initial directory to display.
            filename: Initial filename to populate.
        """
        super().__init__()
        self.title = title
        self.dirname = Path(dirname).expanduser().resolve()
        self.confirm_label = confirm_label
        self.filename = Path(filename).name if filename else None
        self._option_paths: dict[str, Path] = {}
        self._option_is_dir: dict[str, bool] = {}
        self._highlighted_option_id: str | None = None
        self._history: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="file-picker") as container:
            if self.title:
                container.border_title = self.title

            with Horizontal(id="folder"):
                yield Label("In")
                yield Input(id="dirname", value=str(self.dirname))
                yield Button(label=Text.from_markup(":left_arrow:"), id="back", variant="warning", compact=True)
                yield Button(label=Text.from_markup(":up_arrow:"), id="up", variant="warning", compact=True)
                yield Button(label=Text.from_markup(":house:"), id="home", variant="warning", compact=True)

            yield OptionList(id="file-list")

            with Horizontal(id="file-name-type"):
                yield Input(value=self.filename, id="filename")
                yield Select(
                    [
                        ("All Files (*)", "*"),
                        ("CSV (*.csv)", "csv"),
                        ("TSV (*.tsv)", "tsv"),
                        ("Excel (*.xlsx, *.xls)", "excel"),
                        ("Parquet (*.parquet)", "parquet"),
                        ("NDJSON (*.ndjson)", "ndjson"),
                        ("JSON (*.json)", "json"),
                    ],
                    id="file-type",
                    allow_blank=False,
                )

            with Horizontal(id="file-action"):
                yield Button(self.confirm_label, id="confirm", variant="success", compact=True)
                yield Button("Cancel", id="cancel", variant="error", compact=True)

    def on_mount(self) -> None:
        self._refresh_file_list(self.dirname)

    def on_key(self, event) -> None:
        """Handle global key events for the dialog.

        Args:
            event: The key event instance.
        """
        if event.key == "escape":
            self.dismiss()
            event.stop()
        elif event.key == "enter":
            self.confirm()
            event.stop()

    def confirm(self) -> None:
        """Confirm the dialog selection.

        Raises:
            NotImplementedError: Always, subclasses must implement this.
        """
        raise NotImplementedError("confirm method should be implemented by subclasses")

    def _refresh_file_list(self, directory: Path) -> None:
        """Populate the file list with subfolders and files.

        Args:
            directory: Directory to list.
        """
        file_list = self.query_one("#file-list", OptionList)
        file_list.clear_options()
        self._option_paths.clear()
        self._option_is_dir.clear()

        if not directory.exists() or not directory.is_dir():
            self.notify(f"Directory not found: {directory}", severity="error", timeout=5)
            return

        if not self._is_root(directory):
            parent = directory.parent
            parent_label = self._folder_label("..")
            self._add_option(file_list, "dir:..", parent_label, parent, True)

        for option_id, label, path, is_dir in self._iter_directory_options(directory):
            self._add_option(file_list, option_id, label, path, is_dir)

    def _iter_directory_options(self, directory: Path) -> Iterable[tuple[str, Text | str, Path, bool]]:
        """Iterate over directory entries, returning option metadata.

        Args:
            directory: The directory to scan.

        Yields:
            Tuples of option id, label, path, and is_dir flag.
        """
        file_type = self._current_file_type()
        show_hidden = file_type == "*"
        folders: list[tuple[str, Text | str, Path, bool]] = []
        files: list[tuple[str, Text | str, Path, bool]] = []

        for entry in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
            if not show_hidden and entry.name.startswith("."):
                continue
            if entry.is_dir():
                option_id = f"dir:{entry}"
                folders.append((option_id, self._folder_label(entry.name), entry, True))
            elif file_type == "*" or self._matches_file_type(entry, file_type):
                option_id = f"file:{entry}"
                files.append((option_id, entry.name, entry, False))

        return [*folders, *files]

    def _add_option(self, file_list: OptionList, option_id: str, label: Text | str, path: Path, is_dir: bool) -> None:
        """Add a file list option and store metadata.

        Args:
            file_list: The OptionList widget to update.
            option_id: Unique option identifier.
            label: Display label for the option.
            path: Filesystem path for the option.
            is_dir: Whether the path is a directory.
        """
        file_list.add_option(Option(label, id=option_id))
        self._option_paths[option_id] = path
        self._option_is_dir[option_id] = is_dir

    def _current_file_type(self) -> str | None:
        """Return the currently selected file type filter.

        Returns:
            The selected file type value or None.
        """
        try:
            file_type_select_value = self.query_one("#file-type", Select).value
        except Exception as e:
            file_type_select_value = "*"
            self.log(f"Error retrieving file type selection: {str(e)}")

        return file_type_select_value

    def _matches_file_type(self, path: Path, file_type: str | None) -> bool:
        """Check if a file matches the selected file type filter.

        Args:
            path: File path to check.
            file_type: Selected file type value.

        Returns:
            True if the file matches or no filter is set.
        """
        if file_type == "*":
            return True

        fmt = guess_file_format(path)
        return fmt == file_type or (file_type == "excel" and fmt in {"xlsx", "xls"})

    def _folder_label(self, name: str) -> Text:
        """Build a label for a folder option.

        Args:
            name: Folder name to display.

        Returns:
            Rich Text label with folder icon.
        """
        label = Text.from_markup(":file_folder: ")
        label.append(name)
        return label

    def _is_root(self, directory: Path) -> bool:
        """Check whether a directory is a filesystem root.

        Args:
            directory: Directory to check.

        Returns:
            True if the directory is a root.
        """
        return directory == directory.parent

    def _option_id_from_event(self, event) -> str | None:
        """Extract the option id from an OptionList event.

        Args:
            event: OptionList event.

        Returns:
            Option id if present.
        """
        option_id = getattr(event, "option_id", None)
        if option_id:
            return option_id
        option = getattr(event, "option", None)
        if option is not None:
            return option.id
        return None

    def _activate_option(self, option_id: str | None) -> None:
        """Activate the currently highlighted option.

        Args:
            option_id: Option id to activate.
        """
        if not option_id:
            return

        path = self._option_paths.get(option_id)
        if path is None:
            return

        if self._option_is_dir.get(option_id, False):
            self._set_directory(path)
            return

        self.query_one("#filename", Input).value = path.name
        self.confirm()

    def _get_filename(self) -> Path | None:
        try:
            filename = self.query_one("#filename", Input).value.strip()
        except Exception as e:
            self.log(f"Error retrieving filename from input: {str(e)}")
            return None

        filepath = Path(filename)
        if not filepath.is_absolute():
            filepath = self.dirname / filepath

        return filepath

    @on(OptionList.OptionHighlighted, "#file-list")
    def _on_file_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Update filename when a file is highlighted.

        Args:
            event: The option highlighted event.
        """
        option_id = self._option_id_from_event(event)
        if not option_id:
            return
        self._highlighted_option_id = option_id
        if self._option_is_dir.get(option_id, False):
            return
        path = self._option_paths.get(option_id)
        if path is None:
            return
        self.query_one("#filename", Input).value = path.name

    @on(OptionList.OptionSelected, "#file-list")
    def _on_file_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection of files or folders.

        Args:
            event: The option selected event.
        """
        option_id = self._option_id_from_event(event)
        if not option_id:
            return

        self._highlighted_option_id = option_id
        if self._option_is_dir.get(option_id, False):
            return

        path = self._option_paths.get(option_id)
        if path is None:
            return

        self.query_one("#filename", Input).value = path.name

    @on(Click, "#file-list")
    def _on_file_list_click(self, event: Click) -> None:
        """Handle double-clicks on the file list.

        Args:
            event: The click event.
        """
        if event.chain > 1:
            self._activate_option(self._highlighted_option_id)
            event.stop()

    @on(Select.Changed, "#file-type")
    def _on_file_type_changed(self, event: Select.Changed) -> None:
        """Update file list when the file type filter changes.

        Args:
            event: The select changed event.
        """
        self._refresh_file_list(self.dirname)

    def _set_directory(self, directory: Path, record_history: bool = True) -> None:
        """Set the current directory and refresh the list.

        Args:
            directory: Directory to set.
            record_history: Whether to push the current directory to history.
        """
        new_dir = directory.expanduser().resolve()
        if record_history and new_dir != self.dirname:
            self._history.append(self.dirname)
        self.dirname = new_dir
        self.query_one("#dirname", Input).value = str(self.dirname)
        self._refresh_file_list(self.dirname)

    @on(Button.Pressed, "#back")
    def _back(self, event: Button.Pressed) -> None:
        """Navigate to the previous directory in history.

        Args:
            event: The button pressed event.
        """
        event.stop()
        if not self._history:
            return
        previous = self._history.pop()
        self._set_directory(previous, record_history=False)
        self.query_one("#file-list", OptionList).focus()

    @on(Button.Pressed, "#up")
    def _up(self, event: Button.Pressed) -> None:
        """Navigate to the parent directory.

        Args:
            event: The button pressed event.
        """
        event.stop()
        parent = self.dirname.parent
        if parent == self.dirname:
            return
        self._set_directory(parent)
        self.query_one("#file-list", OptionList).focus()

    @on(Button.Pressed, "#home")
    def _home(self, event: Button.Pressed) -> None:
        """Reset to the home directory.

        Args:
            event: The button pressed event.
        """
        event.stop()
        self._set_directory(Path.home())
        self.query_one("#file-list", OptionList).focus()

    @on(Button.Pressed, "#confirm")
    def _confirm(self, event: Button.Pressed) -> None:
        """Handle confirm button press.

        Args:
            event: The button pressed event.
        """
        event.stop()
        self.confirm()

    @on(Button.Pressed, "#cancel")
    def _cancel(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss()


class OpenFilePicker(FilePicker):
    """Modal screen for opening files."""

    def __init__(self, title: str = "Open File", confirm: str = "Open", dirname: str = ".", filename: str = "") -> None:
        """Initialize the open file picker.

        Args:
            title: Dialog title.
            confirm: Label for the confirm button.
            dirname: Initial directory.
            filename: Initial filename.
        """
        super().__init__(title=title, confirm_label=confirm, dirname=dirname, filename=filename)

    def on_mount(self):
        super().on_mount()
        self.query_one("#file-list", OptionList).focus()

    def confirm(self) -> None:
        """Confirm opening the selected file."""
        if not (filepath := self._get_filename()):
            self.notify("No file selected.", severity="warning")
            return

        if filepath.exists() and filepath.is_file():
            self.dismiss(filepath)
        else:
            self.notify(f"File not found: {filepath}", severity="error", timeout=5)


class SaveFilePicker(FilePicker):
    """Modal screen for saving files."""

    def __init__(self, title: str = "Save File", confirm: str = "Save", dirname: str = ".", filename: str = "") -> None:
        """Initialize the save file picker.

        Args:
            title: Dialog title.
            confirm: Label for the confirm button.
            dirname: Initial directory.
            filename: Initial filename.
        """
        super().__init__(title=title, confirm_label=confirm, dirname=dirname, filename=filename)

    def on_mount(self):
        super().on_mount()
        self.query_one("#filename", Input).focus()

    def confirm(self) -> None:
        """Confirm saving the selected file."""
        if not (filepath := self._get_filename()):
            self.notify("No filename provided.", severity="warning")
            return

        if not filepath.is_absolute():
            filepath = self.dirname / filepath

        if not (fmt := guess_file_format(filepath)):
            self.notify(
                f"Extension '[$error]{filepath.suffix}[/]' is invalid. Supported formats are: {', '.join(SUPPORTED_FORMATS)}",
                severity="error",
                timeout=5,
            )
            return

        if filepath.parent.exists() and filepath.parent.is_dir():
            self.dismiss(filepath)
        else:
            self.notify(f"Directory not found: {filepath.parent}", severity="error", timeout=5)
