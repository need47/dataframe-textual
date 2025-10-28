from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer

ROWS = [
    ("lane", "swimmer", "country", "time"),
    (4, "Joseph Schooling", "Singapore", 50.39),
    (2, "Michael Phelps", "United States", 51.14),
    (5, "Chad le Clos", "South Africa", 51.14),
    (6, "László Cseh", "Hungary", 51.14),
    (3, "Li Zhuhao", "China", 51.26),
    (8, "Mehdy Metella", "France", 51.58),
    (7, "Tom Shields", "United States", 51.73),
    (1, "Aleksandr Sadovnikov", "Russia", 51.84),
    (10, "Darren Burns", "Scotland", 51.84),
]


class DataFrameViewer(App):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "toggle_row_labels", "Toggle Row Labels"),
        ("r", "setup_table", "Reset Table"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable()
        yield Footer()

    def on_mount(self) -> None:
        self.action_setup_table()

    def action_toggle_row_labels(self) -> None:
        table = self.query_one(DataTable)
        table.show_row_labels = not table.show_row_labels

    def action_setup_table(self) -> None:
        table = self.query_one(DataTable)

        table.clear(columns=True)

        # Always set show row labels during setup
        table.show_row_labels = True

        for col in ROWS[0]:
            table.add_column(str(col))

        for row_idx, row in enumerate(ROWS[1:]):
            rid = str(row_idx + 1)
            table.add_row(*row, label=rid)

        # Hide labels by default after initial load
        table.show_row_labels = False


if __name__ == "__main__":
    app = DataFrameViewer()
    app.run()
