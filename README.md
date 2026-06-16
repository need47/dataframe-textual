# DataFrame Textual

A powerful, interactive terminal-based viewer/editor for CSV/TSV/Excel/[Parquet](https://parquet.apache.org/)/[Vortex](https://vortex.dev/)/JSON/[NDJSON](https://jsonlines.org/) built with Python, [Polars](https://pola.rs/), and [Textual](https://textual.textualize.io/). Inspired by [VisiData](https://www.visidata.org/), this tool provides smooth keyboard navigation, data manipulation, and a clean interface for exploring and analyzing tabular data directly in terminal with multi-tab support for multiple files!

![Screenshot](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/main-table.png)

## Features

### Data Viewing

- 🚀 **Fast Loading** - Powered by Polars for efficient batch data handling
- 🎨 **Rich Terminal UI** - Beautiful, color-coded columns with auto-detected data types (e.g., integer, float, string)
- ⌨️ **Comprehensive Keyboard Navigation** - Intuitive controls with fully customizable key bindings (mostly VisiData compatible)
- 📊 **Flexible Input** - Read from files and/or stdin (pipes/redirects) in various formats
- 🔄 **Smart Pagination** - Lazy load rows on demand for handling large datasets

### Data Manipulation

- 📝 **Data Editing** - Edit cells, delete rows, reorder columns, and beyond
- 🧹 **Duplicate Removal** - Remove duplicate rows
- 🔍 **Search & Filter** - Find values, highlight matches, and filter selected rows
- ↔️ **Column/Row Reordering** - Move columns and rows with simple keyboard shortcuts
- 📈 **Sorting & Statistics** - Multi-column sorting, frequency distribution, and histogram analysis
- 💾 **Save & Undo** - Save edits back to file with full undo/redo support

### Advanced Features

- 📂 **Multi-File Support** - Open multiple files in separate tabs
- 🔄 **Tab Management** - Seamlessly switch between open files with keyboard shortcuts
- 🔗 **Table Joins** - Join two tables into a new tab
- 📑 **Duplicate Tab** - Create a copy of the current tab with the same data
- 🐍 **Embedded Python Console** - Inspect and transform the active table directly in app
- 📌 **Freeze Rows/Columns** - Keep important rows and columns visible while scrolling
- 📸 **Take Screenshot** - Capture terminal view as a SVG image

## Installation

### Using pip

```bash
# Install from PyPI
pip install dataframe-textual
```

This installs an executable `dv`.

### Using [uv](https://docs.astral.sh/uv/)

```bash
# Install from PyPI
uv tool install dataframe-textual

# Install from GitHub
uv tool install https://github.com/need47/dataframe-textual.git

# Run once with uvx without installing locally
uvx dataframe-textual <csvfile>
```

### Development installation

```bash
# Clone the repository
git clone https://github.com/need47/dataframe-textual.git
cd dataframe-textual

# Install from local source with development dependencies
pip install -e ".[dev]"
```

## Usage

### Basic Usage - Single File

```bash
# Open one file
dv pokemon.csv
```

### Multi-File Usage - Multiple Tabs

```bash
# Open multiple files in tabs
dv file1.csv file2.csv file3.csv

# Open multiple sheets in an Excel file as separate tabs
dv file.xlsx

# Mix files and stdin
dv data1.tsv < data2.tsv
```

### Multi-File Usage - Single Tab

```bash

# Read all parquet files (must be of same format and same structure) into one single table
dv *.parquet --all-in-one
```

## Command Line Options

```
usage: dv [-h] [-V] [-d DELIMITER] [-f FORMAT] [-F [FIELDS ...]] [-H [HEADER ...]] [-L [N]] [-I] [-T] [-E] [-C [C]] [-Q [C]] [-K N] [-A N] [-M [N]] [-N NULL [NULL ...]] [--theme [THEME]] [--all-in-one]
          [--expr EXPR] [--sql SQL] [-o OUTPUT]
          [files ...]

TUI viewer/editor for tabular data (e.g., CSV/Excel).

positional arguments:
  files                 Files to view (or read from stdin)

options:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
  -d, --delimiter DELIMITER
                        Specify the delimiter of the input files (must be a single character, e.g., `|` or `;`). By default, the delimiter is inferred from the file extension. If reading from stdin, the
                        delimiter must be specified unless it is tab delimited.
  -f, --format FORMAT   Specify the format of the input files (e.g., `csv` or `excel`). By default, the format is inferred from the file extension. If reading from stdin, the format must be specified
                        unless it is tab delimited.
  -F, --fields [FIELDS ...]
                        When used without values, list available fields. Otherwise, read only specified fields.
  -H, --header [HEADER ...]
                        Specify header info. When reading CSV/TSV. If used without values, assumes no header. Otherwise, use provided values as column header (e.g., `-H col1 col2 col3`).
  -L, --infer_schema_length [N]
                        Number of rows to use for inferring schema when reading CSV/TSV. Defaults to 100. When used without value, uses all rows for schema inference (can be slow for large files).
  -I, --no-inference    Do not infer data types when reading CSV/TSV. All values will be of string type.
  -T, --truncate-ragged-lines
                        Truncate ragged lines when reading CSV/TSV
  -E, --ignore-errors   Ignore errors when reading CSV/TSV
  -C, --comment-prefix [C]
                        Skip comment lines starting with `C` when reading CSV/TSV
  -Q, --quote-char [C]  Use `C` as quote character for reading CSV/TSV. When used without value, disables special handling of quote characters.
  -K, --skip-lines N    Skip first N lines when reading CSV/TSV
  -A, --skip-rows-after-header N
                        Skip N rows after header when reading CSV/TSV
  -M, --n-rows [N]      Read maximum rows
  -N, --null NULL [NULL ...]
                        Values to interpret as null values when reading CSV/TSV
  --theme [THEME]       Set the theme for the application. If used without value, show available themes.
  --all-in-one, --aio, --one
                        Read all files (must be of same format and same structure) into one single table.
  --expr EXPR           Specify a Polars expression to filter data (e.g., $age > 30)
  --sql SQL             Specify a SQL query to execute on the input file (e.g., to select and filter data)
  -o, --output OUTPUT   Output file (optionally modified) with specified format, which is inferred from file extension (e.g., .csv, .xlsx).
```

### CLI Examples

```bash
# Open a file
dv data.csv

# Gzipped files are supported
dv data.csv.gz

# Read from stdin (defaults to TSV)
cat data.tsv | dv
dv < data.tsv

# Specify delimiter
dv data.txt -d '|'

# Specify format
dv data.json -f ndjson

# View headless CSV file
dv data_no_header.csv -H

# View headless CSV file with provided header
dv data_no_header.csv -H country ip requests

# Skip first 3 rows (e.g., metadata)
dv data_with_meta.csv -K 3

# Skip 1 row after header (e.g., units row)
dv data_with_units.csv -A 1

# Skip 3 rows before header and 1 row after
dv messy_scientific_data.csv -K 3 -A 1

# Skip comment lines (or just -C)
dv commented_data.csv -C '#'

# Disable type inference for faster loading
dv large_data.csv -I

# Ignore parsing errors in malformed CSV
dv data_with_errors.csv -E

# Treat specific values as null (e.g., 'NA', 'N/A')
dv data.csv -N NA N/A

# Use different quote character (e.g., single quote for CSV)
dv data.csv -Q "'"

# Disable quote character processing for TSV with embedded quotes
dv data.tsv -Q

# Choose the `monokai` theme
dv data.csv --theme monokai

# Show column headers
dv data.csv -F

# Read only specific columns: 'name', 'age', first column, and last column
dv data.csv -F name age 1 -1

# Read all files (must be of same format and same structure) into one single table
dv data-1.csv data-2.csv --all-in-one

# Filter rows before opening the TUI using a Polars expression
dv data.csv --expr '$age > 30'

# Filter data using SQL query (use 'self' as the table name)
dv data.csv --sql 'SELECT * FROM self WHERE age > 30'

# Convert to other format
dv data.csv -o data.parquet
```

## Keyboard Shortcuts

Shortcuts are a single key, a modifier combo (e.g., `Shift+G`), or a **leader sequence** starting with `g` or `z` (e.g., `g/`, `g_`, `zQ`).

**How Leader Mode Works:**

- Press the leader key `g` or `z` to activate the mode — a 3-second timeout begins
- Press the next key within the timeout to execute the combined command
- If no second key is pressed within 3 seconds or `Esc` is pressed, leader mode is cancelled.

**Important:** press `z` then `Ctrl+H` to open a **Commands** tab, where all commands and keybindings can be viewed and modified.

![Commands](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/commands.png)

### Memorize `g` vs `z` Quickly

Use this as a practical memory aid (not a strict rule):

- `g` often means broader scope, global-style behavior, or toward left/up.
- `z` is often the opposite: narrower/specific variants, toward right/down, or transform-style/less common actions.

Why this helps:

- In alphabet order, `g` comes before `z`, so it is easier to remember `g` as global/earlier/wider and `z` as later/narrower.
- This pattern appears repeatedly in the command registry and default keybinding registry.

Useful examples from current bindings:

- Scope widening:
  - `,` selects matching rows in current column, while `g,` selects in all columns.
  - `/` searches current column, while `g/` searches all columns.
  - `?` searches backward in current column, while `g?` searches backward in all columns.
- Left/up vs right/down:
  - `g*` delete current column and those before (left), while `z*` deletes current column and those after (right).
  - `gd` delete current row and those above, while `zd` deletes current row and those below.
  - `gb` move tab left, while `zb` moves tab right.
- Specific/transform-style variants under `z`:
  - `z/` and `z?` search with cursor value (specialized variant).
  - `z:` joins selected columns.
  - `zT` transposes rows/columns.
  - `za` adds a link column from a URL template.

**Tip**: Learn the base key first, then its `g` and `z` variants as a small family.

### App-Level Controls

#### File & Tab Management

| Key            | Action                                                     |
| -------------- | ---------------------------------------------------------- |
| `q`            | Quit current tab (prompts to save unsaved changes) or view |
| `gq`           | Quit all tabs then app (prompts to save unsaved changes)   |
| `Ctrl+Q`       | Force quit app (discards unsaved changes)                  |
| `S`            | Show all open sheets/tabs                                  |
| `gB`           | Toggle tab bar visibility                                  |
| `B`            | Previous tab                                               |
| `b`            | Next tab                                                   |
| `gb`           | Move current tab left (wrap to last)                       |
| `zb`           | Move current tab right (wrap to first)                     |
| `Ctrl+T`       | Save current tab (or current view) to file                 |
| `Ctrl+S`       | Save all tabs to file                                      |
| `w`            | Save current tab to file (overwrite without prompt)        |
| `gw`           | Save all tabs to file (overwrite without prompt)           |
| `Ctrl+D`       | Duplicate current tab                                      |
| `Ctrl+O`       | Open file in a new tab                                     |
| `Ctrl+N`       | Create new tab from Polars expression                      |
| `Double-click` | Rename tab                                                 |

**Tips:**

- Tabs with unsaved changes are indicated with a bright background
- Closing a tab with unsaved changes triggers a save prompt

#### View & Settings

| Key                         | Action                               |
| --------------------------- | ------------------------------------ |
| `F1`                        | Toggle help panel                    |
| `` ` `` (backtick)          | Toggle Python console                |
| `gT`                        | Select theme                         |
| `z Ctrl+H` or `z Backspace` | Show all commands and key bindings   |
| `Ctrl+P` -> `Screenshot`    | Capture terminal view as a SVG image |

---

### Table-Level Controls

#### Undo/Redo/Reset

| Key  | Action                  |
| ---- | ----------------------- |
| `U`  | Undo last action        |
| `R`  | Redo last undone action |
| `gU` | Reset to initial state  |

#### Navigation

| Key                      | Action                              |
| ------------------------ | ----------------------------------- |
| `gg`                     | Go to first row                     |
| `G`                      | Go to last row                      |
| `Ctrl+G`                 | Go to specific row                  |
| `←` / `↓` / `↑` / `→`    | Move left/down/up/right             |
| `h` / `j` / `k` / `l`    | Move left/down/up/right (Vim-style) |
| `gh`                     | Scroll to leftmost column           |
| `gj`                     | Scroll to last row                  |
| `gk`                     | Scroll to first row                 |
| `gl`                     | Scroll to rightmost column          |
| `Home` / `End`           | Go to first/last column             |
| `Ctrl+Home` / `Ctrl+End` | Go to page top/bottom               |
| `PageDown` / `PageUp`    | Scroll down/up one page             |
| `Ctrl+F`                 | Page forward                        |
| `Ctrl+B`                 | Page backward                       |

#### Display

| Key               | Action                                                                        |
| ----------------- | ----------------------------------------------------------------------------- |
| `Enter`           | Show details for the current row as two-column key–value pairs                |
| `Tab`             | Show current cell details                                                     |
| `C`               | Show metadata for all columns (name and data type)                            |
| `F`               | Show frequency distribution for current or selected columns                   |
| `I`               | Show statistics for current column                                            |
| `gI`              | Show statistics for all columns                                               |
| `=`               | Show histogram for current column                                             |
| `g=`              | Show histogram for current column with custom bins                            |
| `z=`              | Toggle inline bar chart display for current numeric column                    |
| `-` (minus)       | Hide selected columns or current column                                       |
| `g-` (minus)      | Hide current column and all columns before it                                 |
| `z-` (minus)      | Hide current column and all columns after it                                  |
| `gv`              | Show all hidden columns                                                       |
| `$`               | Toggle 1-based column index prefixes                                          |
| `z#`              | Toggle freeze rows and/or columns                                             |
| `_` (underscore)  | Toggle column full width for current column                                   |
| `g_` (underscore) | Toggle column full width for all string/list columns                          |
| `z,`              | Toggle thousand separator for current column                                  |
| `(`               | Expand current list column into indexed columns (e.g. ``col[1]``, ``col[2]``) |
| `)`               | Contract indexed sibling columns (``col[N]``) back into a list column         |
| `<`               | Decrease float precision for current column                                   |
| `>`               | Increase float precision for current column                                   |
| `g^`              | Set current row as the new header row                                         |
| `g#`              | Cycle cursor type (cell -> row -> column)                                     |

#### Editing

| Key            | Action                                                          |
| -------------- | --------------------------------------------------------------- |
| `Double-click` | Edit cell or rename column header                               |
| `Delete`       | Clear current cell (set to NULL)                                |
| `Shift+Delete` | Clear current column (set matching cells to NULL)               |
| `e`            | Edit current cell (respects data type)                          |
| `E`            | Edit entire column with value/expression                        |
| `a`            | Add empty column after current                                  |
| `A`            | Add column with name and value/expression                       |
| `i`            | Add index column after current                                  |
| `za`           | Add a link column from URL template                             |
| `^`            | Rename current column                                           |
| `*`            | Delete selected columns or current column                       |
| `g*`           | Delete current column and all columns before it                 |
| `z*`           | Delete current column and all columns after it                  |
| `d`            | Delete current row                                              |
| `gd`           | Delete current row and all those above                          |
| `zd`           | Delete current row and all those below                          |
| `D`            | Duplicate current row                                           |
| `zD`           | Duplicate current column                                        |
| `zU`           | Remove duplicate rows (keep first occurrence)                   |
| `:`            | Split current string column into a new column by delimiter      |
| `z:`           | Join all selected columns into a new string column by delimiter |
| `g:`           | Glue items of a list column into a string column by delimiter   |
| `Ctrl+U`       | Convert current or selected string column(s) to uppercase       |
| `Ctrl+L`       | Convert current or selected string column(s) to lowercase       |
| `zB`           | Strip leading and trailing whitespaces in current string column |
| `o`            | Explode current list column into multiple rows                  |
| `O`            | Explode current string column by delimiter into multiple rows   |
| `zT`           | Transpose table (swap rows and columns)                         |

#### Row/Column Selection

| Key              | Action                                                                         |
| ---------------- | ------------------------------------------------------------------------------ |
| `,`              | Select rows with cell matches or those matching cursor value in current column |
| `g,`             | Select rows with cell matches or those matching cursor value in all columns    |
| `\|` (pipe)      | Select rows where expression matches in current column                         |
| `g\|`            | Select rows where expression matches in all columns                            |
| `\`              | Unselect selected rows where expression matches in current column              |
| `g\`             | Unselect selected rows where expression matches in all columns                 |
| `{`              | Go to previous selected row                                                    |
| `}`              | Go to next selected row                                                        |
| `s`              | Select/deselect current row                                                    |
| `gs`             | Select current row and all rows above                                          |
| `zs`             | Select current row and all rows below                                          |
| `u`              | Unselect the current row                                                       |
| `gu`             | Unselect all rows                                                              |
| `'` (apostrophe) | Select/deselect current column                                                 |
| `t`              | Toggle row selections (invert)                                                 |
| `T`              | Clear all row/column selections and cell matches                               |

#### Find & Replace

| Key  | Action                                                          |
| ---- | --------------------------------------------------------------- |
| `/`  | Search forward in current column with expression                |
| `g/` | Search forward in all columns with expression                   |
| `z/` | Search forward in current column with cursor value              |
| `?`  | Search backward in current column with expression               |
| `g?` | Search backward in all columns with expression                  |
| `z?` | Search backward in current column with cursor value             |
| `n`  | Go to next matching cell                                        |
| `N`  | Go to previous matching cell                                    |
| `r`  | Find and replace in current column (interactive or replace all) |
| `gr` | Find and replace in all columns (interactive or replace all)    |

#### Filter & Collect

| Key                | Action                                                 |
| ------------------ | ------------------------------------------------------ |
| `v`                | Filter rows with cursor value in the current column    |
| `V`                | Filter rows with specified value or expression         |
| `f`                | Filter rows using values in the current column         |
| `.`                | Filter rows with non-null values in the current column |
| `z.`               | Filter rows with null values in the current column     |
| `"` (double quote) | Collect rows/columns to a new tab                      |

#### Sorting (supporting multiple columns)

| Key | Action                         |
| --- | ------------------------------ |
| `[` | Sort current column ascending  |
| `]` | Sort current column descending |

#### Reordering

| Key               | Action                         |
| ----------------- | ------------------------------ |
| `H` / `Shift+←`   | Move current column left       |
| `J` / `Shift+↓`   | Move current row down          |
| `K` / `Shift+↑`   | Move current row up            |
| `L` / `Shift+→`   | Move current column right      |
| `gH` / `gShift+←` | Move column to start           |
| `gJ` / `gShift+↓` | Move row to bottom             |
| `gK` / `gShift+↑` | Move row to top                |
| `gL` / `gShift+→` | Move column to end             |
| `!`               | Pin column to start and freeze |

#### Type Casting

| Key | Action                         |
| --- | ------------------------------ |
| `~` | Cast current column to string  |
| `@` | Cast current column to date    |
| `#` | Cast current column to integer |
| `%` | Cast current column to float   |

#### Copy

| Key      | Action                                |
| -------- | ------------------------------------- |
| `c`      | Copy current cell to clipboard        |
| `Ctrl+C` | Copy column to clipboard              |
| `Ctrl+R` | Copy row to clipboard (tab-separated) |

#### Join Tables

| Key | Action                         |
| --- | ------------------------------ |
| `&` | Join two tables into a new tab |

#### SQL Interface

| Key     | Action                                                     |
| ------- | ---------------------------------------------------------- |
| `Q`     | SQL query interface (full SQL query with syntax highlight) |
| `zQ`    | SQL query interface (select columns & where clause)        |
| `Space` | Run a command by name with optional arguments              |

## Features in Detail

### 1. Undo/Redo/Reset

These actions are the fastest way to get out of trouble after a mistaken edit, delete, sort, filter, or other table change.

- `U`: Undo the last action and restore the previous state.
- `R`: Redo the last undone action.
- `gU`: Reset the table to its original loaded state if you want to start over.

### 2. Display & UI

Columns are automatically styled based on their data types (auto-inferred):

| Data Type | Text Color | Alignment |
| --------- | ---------- | --------- |
| integer   | Cyan       | right     |
| float     | Yellow     | right     |
| string    | Green      | left      |
| boolean   | Blue       | centered  |
| temporal  | Magenta    | centered  |

These controls change how the table is shown without changing the underlying data.

- `-`: Hide selected columns, or the current column if nothing is selected.
- `g-`: Hide the current column and all columns before it.
- `z-`: Hide the current column and all columns after it.
- `gv`: Show all hidden columns.
- `z#`: Freeze rows and/or columns to keep important areas visible while scrolling.
- `$`: Toggle a 1-based index prefix in visible column headers such as `1_colname`.
- `z,`: Toggle the thousand separator for the current numeric column.
- `(`: Expand the current list column into indexed columns named like `colname[1]`, `colname[2]`, etc.
- `)`: Contract those indexed sibling columns back into a single list column. Position the cursor on any sibling (e.g. `colname[2]`) and press `)` to merge all `colname[N]` columns back into `colname`.
- `<` / `>`: Decrease or increase float precision for the current float column. Each column keeps its own precision setting, and `0` means the default full display.
- `z=`: Toggle inline bar chart display for the current numeric column. When active, each cell is rendered as a Rich `Bar`, normalized to that column's min/max range. Press `z=` again to restore normal value display.

### 3. Modal Screen

Several features open a **modal screen** (an overlay table) for inspection or interaction. The following modals share a common set of keyboard shortcuts:

| Modal Screen    | Opened With | Purpose                                    |
| --------------- | ----------- | ------------------------------------------ |
| Sheets Overview | `S`         | Summary of all open tabs                   |
| Column Metadata | `C`         | Column names and data types                |
| Row Detail      | `Enter`     | All column values for one row              |
| Cell Detail     | `Tab`       | Drill into a single cell value             |
| Frequency       | `F`         | Value distribution for a column            |
| Statistics      | `I` / `gI`  | Summary statistics for column or dataframe |
| Histogram       | `=` / `g=`  | Numeric distribution as histogram          |

**Common keys available in all modal screens:**

| Key            | Action                                       |
| -------------- | -------------------------------------------- |
| `q` / `Escape` | Close the modal                              |
| `g`            | Scroll to top                                |
| `G`            | Scroll to bottom                             |
| `[`            | Sort by current column ascending             |
| `]`            | Sort by current column descending            |
| `,`            | Toggle thousand separator for numeric values |
| `C`            | Cycle cursor type (cell → row → column)      |
| `T`            | Open modal data as a new tab                 |
| `Ctrl+S`       | Save the modal table to file                 |

Individual modals may add extra keys on top of these (documented in each subsection below).

### 4. Sheets Overview

Press `S` to open a modal providing a summary view of all currently opened tabs.

![Sheets](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/sheets.png)

The modal displays a table with the following columns:

| Column       | Description             |
| ------------ | ----------------------- |
| **Tab**      | Display name of the tab |
| **#Rows**    | Total number of rows    |
| **#Cols**    | Number of columns       |
| **Filename** | Source file path        |

**Keys inside the modal:**

| Key     | Action                                                      |
| ------- | ----------------------------------------------------------- |
| `Enter` | Close the modal and switch to the tab under the cursor      |
| `e`     | Rename the tab under the cursor                             |
| `d`     | Close the tab under the cursor (prompts if unsaved changes) |
| `s`     | Select or deselect the tab under the cursor                 |
| `&`     | Join exactly two selected tabs into a new tab               |

This is useful for quickly navigating between tabs, reviewing file sizes at a glance, closing tabs you no longer need without switching to them first, or selecting two tabs and pressing `&` to open the join-table modal.

### 5. Column Overview

Press `C` to open a modal displaying details for all columns:
  - **Column** - Column name
  - **Type** - Data type (e.g., Int64, String, Float64, Boolean)

**Keys inside the modal**

- Press `Enter` to jump to the selected column in the main table and close the modal
- Press `F` to show the frequency table for the selected column
- Press `I` to show the statistics table for the selected column
- Press `J` or `Shift+↓` to move the selected column right (and move the metadata row down)
- Press `K` or `Shift+↑` to move the selected column left (and move the metadata row up)
- Press `e` to rename the selected column
- Press `d` to delete the selected column from the main table

### 6. Column Statistics

Show summary statistics such as count, unique count, null count, mean, median, standard deviation, min, max, sum, and etc.

- `I` shows statistics for the current column
- `gI` shows statistics for all columns in the dataframe

![Column statistics](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/column-statistics.png)

This is useful for:

- Understanding data distributions and overall column behavior
- Identifying outliers and anomalies
- Checking data quality quickly
- Reviewing summary statistics
- Comparing columns at a glance

### 7. Row Detail View

Press `Enter` on any row to open a modal showing all column values for that row.
Useful for examining wide table where columns don't fit well on screen.

![Row detail](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/row-detail.png)

**Keys inside the modal**:

- Press `v` to **filter** all rows containing the selected column value
- Press `"` to **collect** all rows containing the selected column value to a new tab
- Press `{` to show the previous row
- Press `}` to show the next row
- Press `F` to show the frequency table for the selected column
- Press `I` to show the statistics table for the selected column
- Press `Tab` to open a cell-detail modal for the selected field

### 8. Cell Detail View

Press `Tab` in the main table to inspect the current cell in its own modal for complex data or long text

You can also press `Tab` from the Row Detail modal to drill into the selected field.

Inside the cell-detail modal, press `Tab` again on the selected row/column to keep drilling into nested values.

- Scalar values are displayed inline. For long text, press `Tab` again to view the full content in a multi-line modal.
- String values are split into multiple rows using `|` by default
- List-like values are expanded into a one-column table
- Dict-like values are shown as key/value columns

### 9. Frequency Distribution

Press `F` to see value distributions for the current column. If multiple columns are selected, it shows frequency of value combinations across those selected columns.

![Frequency distribution](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/frequency-distribution.png)

**Keys inside the modal**:

- Press `v` to **filter** rows matching the selected value (or selected value combinations)
- Press `"` to **collect** rows matching the selected value (or selected value combinations) to a new tab

This is useful for:

- Understanding value distributions
- Quickly filtering to specific values
- Identifying rare or common values
- Finding the most/least frequent entries

### 10. Row/Column Selection

The application provides multiple ways to select rows (for filtering or collecting) and columns (for hiding or deleting):

- `,` - Select rows with cell matches or those matching cursor value in current column (respects data type)
- `g,` - Select rows with cell matches or those matching cursor value in all columns
- `|` - Select rows where expression matches in the current column
- `g|` - Select rows where expression matches in all columns
- `\` - Unselect currently selected rows where expression matches in the current column
- `g\` - Unselect currently selected rows where expression matches in all columns
- `s` - Select/deselect current row
- `gs` - Select current row and all rows above
- `zs` - Select current row and all rows below
- `u` - Unselect the current row
- `gu` - Unselect all rows
- `'` (apostrophe) - Select/deselect current column
- `t` - Flip selections of all rows
- `T` - Clear all row selections, column selections, and cell matches
- `{` - Go to previous selected row
- `}` - Go to next selected row

**Advanced Options**:

When searching, you can use checkboxes in the dialog to enable:

- Match option `Nocase` for case-insensitive matching
- Match option `Whole` to match full text
- Match option `Literal` to ignore special regex characters
- Match option `Reverse` to perform reverse match

These options work with plain text searches. Use Polars regex patterns in expressions for more control. For example, use `(?i)` prefix in regex (e.g., `(?i)john`) for case-insensitive matching.

**Quick Tips:**

- Search results highlight matching rows in **red**
- Use expression for advanced selection (e.g., $attack > $defense)
- Type-aware matching automatically converts values. Resort to string comparison if conversion fails

### 11. Find & Replace

Find by value/expression and highlight matching cells:

- `/` - Search forward in current column with expression
- `g/` - Search forward in all columns with expression
- `z/` - Search forward in current column with cursor value
- `?` - Search backward in current column with expression
- `g?` - Search backward in all columns with expression
- `z?` - Search backward in current column with cursor value
- `n` - Go to next matching cell
- `N` - Go to previous matching cell

Replace values in current column (`r`) or in all columns (`gr`).

**How It Works:**

When you press `r` or `gr`, enter:

1. **Find term**: Value or expression to search for (done by string value)
2. **Replace term**: Replacement value
3. **Matching options**:
   - `Nocase` for case-insensitive matching
   - `Whole` to match full text
   - `Literal` to ignore special regex characters
   - `Reverse` to perform reverse match
4. **Replace mode**: All at once or interactive review

**Replace All**:

- Replaces all matches with one operation
- Shows confirmation with match count

**Replace Interactive**:

- Review each match one at a time (confirm, skip, or cancel)
- Shows progress

**Tips:**

- Search are done by string value (i.e., ignoring data type)
- Type `NULL` to find or replace null values

### 12. Filter & Collect

Both actions work on a subset of the original dataframe, but they serve different workflows.

**Filtering options**:

**Basic Filter** (`v`):

- Opens the chose subset as a derived view inside the current workflow
- Edits made in the filtered view still apply to the original dataframe
- Press `Ctrl+T` to save the current view to a file
- Press `q` to leave the filtered view and return to the main table

**Advanced Filter** (`V`):

- Opens a dialog for value-based or expression-based filtering
- Useful when you want to define the subset directly

![Advanced Filter](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/advanced-filter.png)

**Column Filter** (`f`):

- Opens a type-aware filter dialog for the current column
- Numeric columns support `=`, `!=`, `<`, `<=`, `>=`, and `>`
- String columns support exact match, prefix, suffix, contains, and regex matching
- Boolean columns support true, false, and null filtering
- Temporal columns support the same comparison operators as numeric columns
- List columns support exact-list matching and item membership checks such as "contains"

![Column Filter](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/column-filter.png)

**Collect** (`"`):

- Creates a separate tab containing only the chosen rows/columns
- The collected tab is independent from the source dataframe
- Edits in the collected tab do not modify the original table

For **Basic Filter** (`v`) and **Collect** (`"`), rows are chosen in this order:

- Use selected rows if any are present
- Otherwise, use rows with active matches from search or find
- Otherwise, use rows whose current-column value matches the current cell

### 13. Sorting

- Press `[` to sort current column ascending
- Press `]` to sort current column descending
- Multi-column sorting supported (press multiple times on different columns)
- Press same key twice to remove the current column from sorting

![Sorting](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/sort-column.png)

### 14. Editing

Editing covers cell updates, structural table changes, and quick cleanup.

- `e` or **Double-click**: Edit the current cell with type-aware validation.
- `^` or **Double-click** column header: Rename the current column.
- `d`: Delete the selected rows, or the current row if nothing is selected.
- `gd`: Delete the current row and all rows above it.
- `zd`: Delete the current row and all rows below it.
- `*`: Delete selected columns, or the current column if nothing is selected.
- `g*`: Delete the current column and all columns to its left.
- `z*`: Delete the current column and all columns to its right.
- `a`: Add an empty column after the current column.
- `A`: Add a column after the current column using a value or expression such as `$age * 2`.
- `i`: Insert an index column after the current column.
- `D`: Duplicate the current row.
- `zD`: Duplicate the current column using a `_copy` suffix.
- `zU`: Remove duplicate rows while keeping the first occurrence, based on visible-column values.
- `:`: Split the current string column into a new list column using a delimiter.
- `Ctrl+U`: Convert the current column, or all selected columns that are string type, to uppercase.
- `Ctrl+L`: Convert the current column, or all selected columns that are string type, to lowercase.
- `zB`: Strip leading and trailing whitespaces in the current string column.

### 15. Column & Row Reordering

**Move Columns**: `Shift+←` and `Shift+→`

- Swaps adjacent columns
- `H` and `L` provide the same left/right movement
- `gH` / `gShift+←` moves column to start
- `gL` / `gShift+→` moves column to end
- Reorder is preserved when saving

**Move Rows**: `Shift+↑` and `Shift+↓`

- Swaps adjacent rows
- `J` and `K` provide the same down/up movement
- `gK` / `gShift+↑` moves row to top
- `gJ` / `gShift+↓` moves row to bottom
- Reorder is preserved when saving

**Pin Column**: `!`

- Moves the current column to the leftmost unfrozen position and freezes it
- If columns are already frozen, appends to the frozen set (increments `fixed_columns`)

### 16. Save File

The application provides save actions for the current tab (or active view) and all tabs.

**Save Current Tab** (`Ctrl+T`):

- Saves the active tab to file
- If currently in a derived/filtered view, saves the current view instead
- Useful when you want to export only the dataframe you are currently working on

**Save All Tabs** (`Ctrl+S`):

- Saves every open tab to file
- Useful after editing multiple datasets in the same session

The output format is determined by the file extension, making it easy to convert between formats such as CSV, TSV, Parquet, or Excel.

![Save File](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/save-file.png)

### 17. Clipboard Operations

Copies value to system clipboard with `pbcopy` on macOS and `xclip` on Linux.

**Note**: may require a X server to work.

- Press `c` to copy cursor value
- Press `Ctrl+C` to copy column values
- Press `Ctrl+R` to copy row values (delimited by tab)
- Hold `Shift` to select with mouse

### 18. [Polars Expressions](https://docs.pola.rs/api/python/stable/reference/expressions/index.html)

Complex values, filters, and advanced operations can be specified via Polars expressions, with the following adaptions for convenience:

**Column References:**

- `$_` - Current column (based on cursor position)
- `$1`, `$2`, etc. - Column by 1-based index
- `$age`, `$salary` - Column by name (use actual column names)
- `` $`col name` `` - Column by name with spaces (backtick quoted)

**Row References:**

- `$#` - Current row index (1-based)

**DataFrame References:**

- `self` - Current dataframe

**Basic Comparisons:**

- `$_ > 50` - Current column greater than 50
- `$salary >= 100000` - Salary at least 100,000
- `$age < 30` - Age less than 30
- `$status == 'active'` - Status exactly matches 'active'
- `$name != 'Unknown'` - Name is not 'Unknown'
- `$# <= 10` - Top 10 rows

**Logical Operators:**

- `&` - AND
- `|` - OR
- `~` - NOT

**Practical Examples:**

- `($age < 30) & ($status == 'active')` - Age less than 30 AND status is active
- `($name == 'Alice') | ($name == 'Bob')` - Name is Alice or Bob
- `$salary / 1000 >= 50` - Salary divided by 1,000 is at least 50
- `($department == 'Sales') & ($bonus > 5000)` - Sales department with bonus over 5,000
- `($score >= 80) & ($score <= 90)` - Score between 80 and 90
- `~($status == 'inactive')` - Status is not inactive
- `$revenue > $expenses` - Revenue exceeds expenses
- ``$`product id` > 100`` - Product ID with spaces in column name greater than 100
- `self.drop(RID).is_duplicated()` - Duplicate rows (note: the internal RID column must be excluded)

**String Operations:** ([Polars string API reference](https://docs.pola.rs/api/python/stable/reference/series/string.html))

- `$name.str.contains("John")` - Name contains "John" (case-sensitive)
- `$name.str.contains("(?i)john")` - Name contains "john" (case-insensitive)
- `$email.str.ends_with("@company.com")` - Email ends with domain
- `$code.str.starts_with("ABC")` - Code starts with "ABC"
- `$name.str.len_chars() < 7` - Length of name shorter than 7

**Number Operations:**

- `$age * 2 > 100` - Double age greater than 100
- `($salary + $bonus) > 150000` - Total compensation over 150,000
- `$percentage >= 50` - Percentage at least 50%

**Null Handling:**

- `$column.is_null()` - Find null values
- `$column.is_not_null()` - Find non-null values
- `NULL` - a value to represent null for convenience

**Tips:**

- Use column indices (e.g., `$1`, `$2`) for faster column access.
- Use column names that match exactly (case-sensitive)
- Use parentheses to clarify complex expressions: `($a & $b) | ($c & $d)`

### 19. Link Column Creation

Press `za` to create a new column containing dynamically generated URLs using template. Links are typically clickable in a terminal emulator using Ctrl+Click.

**Template Placeholders:**

The link template supports multiple placeholder types for maximum flexibility:

- **`$_`** - Current column, e.g., `https://example.com/search/$_` - Uses values from the current column
- **`$1`, `$2`, `$3`, etc.** - Column by 1-based position index, e.g., `https://example.com/product/$1/details/$2` - Uses 1st and 2nd columns
- **`$name`** - Column by name (use actual column names), e.g., `https://example.com/$region/$city/data` - Uses `region` and `city` columns

**Features:**

- **Multiple Placeholders**: Mix and match placeholders in a single template
- **URL Prefix**: Automatically prepends `https://` if URL doesn't start with `http://` or `https://`

### 20. Join Tables

Press `&` from the main table to open the join-table modal. The modal lets you choose the left and right tables, select matching key columns from each side, choose the join type, and create the joined result as a new tab.

You can also start from the Sheets Overview: press `S`, select exactly two tabs with `s`, then press `&` to open the same join-table modal with those two tables pre-selected.

Supported join types include inner, left, right, full, semi, and anti joins. Select the same number of key columns on both sides before pressing **Join**.

### 21. SQL Interface

The SQL interface provides two modes for querying your dataframe:

#### Advanced SQL Interface (`Q`)

Execute complete SQL queries for advanced data manipulation:

- Write full SQL queries with standard [SQL syntax](https://docs.pola.rs/api/python/stable/reference/sql/index.html)
- Access to all SQL capabilities for complex transformations
- Always use `self` as the table name
- Syntax highlighted

![SQL Interface](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/sql-query.png)

#### Simple SQL Interface (`zQ`)

SELECT specific columns and apply WHERE conditions without writing full SQL:

- Choose which columns to include in results
- Specify WHERE clause for filtering
- Ideal for quick filtering and column selection

![SQL Interface](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/sql-simple.png)

**Examples:**

```sql
-- Filter and select specific rows and/or columns
SELECT name, age
FROM self
WHERE age > 30

-- Use backticks (`) for column names with spaces
SELECT *
FROM self
WHERE `product id` = 7
```

### 22. Python Console

Use the built-in Python console for quick interactive transformations without leaving the TUI.

- Open/close console: `` ` ``
- Run shell commands: prefix with `!` (example: `!ls`)
- In console: `clear` or `cls` clears console output
- In console: `Esc` closes the console panel
- Available names: `df` (active DataFrame), `self` (active table), `app` (viewer app), `pl` (Polars)
- Assign a DataFrame or Series back to `df` to refresh the current table immediately

![Python Console](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshots/python-console.png)

## Handling Loading Errors

Most loading failures come from malformed CSV/TSV input, quoting issues, or mixed column types. When this happens, the application prints a hint with a suggested retry option.

**Common fixes:**

- Use `-Q` if quote characters are mismatched, improperly escaped, or should be ignored entirely
- Use `-T` when rows contain more fields than expected and you want to truncate ragged lines
- Use `-L` to increase the number of rows used for schema inference when early rows do not represent the full column types
- Use `-I` to disable type inference and read CSV/TSV values as strings
- Check the delimiter and format options if the input appears empty or unreadable
- Use `-E` as a last resort to ignore recoverable parsing errors

**Typical cases:**

**Malformed CSV or broken quoting**:

- Symptom: errors mentioning malformed CSV, mismatched quotes, or improperly escaped fields
- Try: `-Q` to disable quoting or choose a different quote character

**Ragged lines or inconsistent field counts**:

- Symptom: errors saying the input has more fields than defined in the schema
- Try: `-T` to truncate ragged lines

**Mixed data types in one column**:

- Symptom: errors saying a value could not be parsed as an integer, float, or other inferred type at a specific column
- Try: `-L` first, then `-I` if the column is genuinely mixed

**No data could be loaded**:

- Symptom: errors indicating that no data was available to load
- Check: whether the file is empty, the format is correct, and the delimiter matches the input

**Fallback option**:

- If none of the above helps and the file is mostly usable, retry with `-E` to ignore parsing errors

**Examples:**

```bash
# Disable quote handling when CSV quoting is broken
dv bad.csv -Q

# Truncate ragged lines
dv messy.tsv -T

# Increase schema inference depth
dv mixed_types.csv -L 1000

# Disable type inference entirely
dv mixed_types.csv -I

# Ignore recoverable parsing errors
dv partially_broken.csv -E
```

## Dependencies

- **polars**: Fast DataFrame library for data loading/processing
- **textual**: Terminal UI framework
- **fastexcel**: Read Excel files
- **xlsxwriter**: Write Excel files
- **vortex-data**: Read/Write Vortex files

## Requirements

- Python 3.11+
- POSIX-compatible terminal (macOS, Linux, WSL)
- Terminal supporting ANSI escape sequences and mouse events

## Acknowledgments

- Inspired by [VisiData](https://visidata.org/)
- Built with [Textual](https://textual.textualize.io/) and [Polars](https://www.pola.rs/)
