# DataFrame Textual

A powerful, interactive terminal-based viewer/editor for CSV/TSV/Excel/Parquet/JSON/NDJSON built with Python, [Polars](https://pola.rs/), and [Textual](https://textual.textualize.io/). Inspired by [VisiData](https://www.visidata.org/), this tool provides smooth keyboard navigation, data manipulation, and a clean interface for exploring tabular data directly in terminal with multi-tab support for multiple files!

![Screenshot](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshot.png)

## Features

### Data Viewing
- 🚀 **Fast Loading** - Powered by Polars for efficient data handling
- 🎨 **Rich Terminal UI** - Beautiful, color-coded columns with various data types (e.g., integer, float, string)
- ⌨️ **Comprehensive Keyboard Navigation** - Intuitive controls
- 📊 **Flexible Input** - Read from files and/or stdin (pipes/redirects)
- 🔄 **Smart Pagination** - Lazy load rows on demand for handling large datasets

### Data Manipulation
- 📝 **Data Editing** - Edit cells, delete rows, and remove columns
- 🔍 **Search & Filter** - Find values, highlight matches, and filter selected rows
- ↔️ **Column/Row Reordering** - Move columns and rows with simple keyboard shortcuts
- 📈 **Sorting & Statistics** - Multi-column sorting and frequency distribution analysis
- 💾 **Save & Undo** - Save edits back to file with full undo/redo support

### Advanced Features
- 📂 **Multi-File Support** - Open multiple files in separate tabs
- 🔄 **Tab Management** - Seamlessly switch between open files with keyboard shortcuts
- 📑 **Duplicate Tab** - Create a copy of the current tab with the same data
- 📌 **Freeze Rows/Columns** - Keep important rows and columns visible while scrolling
- 🎯 **Cursor Type Cycling** - Switch between cell, row, and column selection modes
- 📸 **Take Screenshot** - Capture terminal view as a SVG image

## Installation

### Using pip

```bash
# Install from PyPI
pip install dataframe-textual

# With Excel support (fastexcel, xlsxwriter)
pip install dataframe-textual[excel]
```

This installs an executable `dv`.

Then run:
```bash
dv <file>
```

### Using [uv](https://docs.astral.sh/uv/)

```bash
# Quick run using uvx without installation
uvx https://github.com/need47/dataframe-textual.git <csvfile>

# Clone or download the project
cd dataframe-textual
uv sync --extra excel  # with Excel support

# Run directly with uv
uv run dv <file>
```

### Development installation

```bash
# Clone the repository
git clone https://github.com/need47/dataframe-textual.git
cd dataframe-textual

# Install from local source
pip install -e .

# With Excel support
pip install -e ".[excel]"

# With development dependencies
pip install -e ".[excel,dev]"
```

## Usage

### Basic Usage - Single File

```bash
# After pip install dataframe-textual
dv pokemon.csv

# Or run from module
python -m dataframe-textual pokemon.csv

# Or with uv
uv run python main.py pokemon.csv

# Read from stdin (defaults to TSV)
cat data.tsv | dv
dv < data.tsv

# Specify format for gzipped stdin
zcat data.csv.gz | dv -f csv

# Gzipped files are supported
dv data.csv.gz
```

### Multi-File Usage - Multiple Tabs

```bash
# Open multiple files in tabs
dv file1.csv file2.csv file3.csv

# Open multiple sheets in tabs in an Excel file
dv file.xlsx

# Mix files and stdin
dv data1.tsv < data2.tsv
```

When multiple files are opened:
- Each file appears as a separate tab. An Excel file may contain multiple tabs.
- Switch between tabs using `>` (next) or `<` (previous), or use `b` for cycling through tabs
- Save current tab to file with `Ctrl+T`
- Save all tabs to file with `Ctrl+A`
- Duplicate the current tab with `Ctrl+D`
- Open additional files with `Ctrl+O`
- Each file maintains its own state (edits, sort order, selections, history, etc.) and allow undo/redo.

## Command Line Options

```
usage: dv [-h] [-f {csv,excel,tsv,parquet,json,ndjson}] [-H] [-I] [-E] [-c COMMENT_PREFIX] [-q QUOTE_CHAR] [-l SKIP_LINES] [-a SKIP_ROWS_AFTER_HEADER] [-n NULL [NULL ...]] [files ...]

Interactive terminal based viewer/editor for tabular data (e.g., CSV/TSV/Excel).

positional arguments:
  files                 Input files (or read from stdin)

options:
  -h, --help            show this help message and exit
  -f, --format {csv,excel,tsv,parquet,json,ndjson}
                        Specify the format of the input files
  -H, --no-header       Specify that input files have no header row
  -I, --no-inference   Do not infer data types when reading CSV/TSV
  -E, --ignore-errors   Ignore errors when reading CSV/TSV
  -c, --comment-prefix COMMENT_PREFIX
                        Comment lines are skipped when reading CSV/TSV (default: skip none)
  -q, --quote-char QUOTE_CHAR
                        Quote character for reading CSV/TSV (default: "; use -q without argument value to disable)
  -l, --skip-lines SKIP_LINES
                        Skip lines when reading CSV/TSV (default: 0)
  -a, --skip-rows-after-header SKIP_ROWS_AFTER_HEADER
                        Skip rows after header when reading CSV/TSV (default: 0)
  -n, --null NULL [NULL ...]
                        Values to interpret as null values when reading CSV/TSV
```

### CLI Examples

```bash
# View headless CSV file
dv -H data_no_header.csv

# Disable type inference for faster loading
dv -I large_data.csv

# Ignore parsing errors in malformed CSV
dv -E data_with_errors.csv

# Skip first 3 lines of file (e.g., metadata)
dv -l 3 data_with_meta.csv

# Skip 1 row after header (e.g., units row)
dv -a 1 data_with_units.csv

# Skip comment lines (or just -c)
dv -c "#" commented_data.csv

# Treat specific values as null/missing (e.g., 'NA', 'N/A', '-')
dv -n NA N/A - data.csv

# Use different quote character (e.g., single quote for CSV)
dv -q "'" data.csv

# Disable quote character processing for TSV with embedded quotes
dv -q data.tsv

# Complex CSV with comments and units row
dv -l 3 -a 1 -I messy_scientific_data.csv

# Process compressed data
dv data.csv.gz
zcat compressed_data.csv.gz | dv -f csv
```

## Keyboard Shortcuts

### App-Level Controls

#### File & Tab Management

| Key | Action |
|-----|--------|
| `>` | Move to next tab |
| `<` | Move to previous tab |
| `b` | Cycle through tabs |
| `B` | Toggle tab bar visibility |
| `q` | Close current tab (prompts to save unsaved changes) |
| `Q` | Close all tabs and app (prompts to save unsaved changes) |
| `Ctrl+Q` | Force to quit app (regardless of unsaved changes) |
| `Ctrl+T` | Save current tab to file |
| `Ctrl+A` | Save all tabs to a Excel file |
| `w` | Save current tab to file (overwrite without prompt) |
| `W` | Save all tabs to file (overwrite without prompt) |
| `Ctrl+D` | Duplicate current tab |
| `Ctrl+O` | Open file in a new tab |
| `Double-click` | Rename tab |

#### View & Settings

| Key | Action |
|-----|--------|
| `F1` | Toggle help panel |
| `k` | Cycle through dark, light and other themes |
| `Ctrl+P` -> `Screenshot` | Capture terminal view as a SVG image |

---

### Table-Level Controls

#### Navigation

| Key | Action |
|-----|--------|
| `g` | Jump to first row |
| `G` | Jump to last row |
| `↑` / `↓` | Move up/down one row |
| `←` / `→` | Move left/right one column |
| `Home` / `End` | Jump to first/last column |
| `Ctrl + Home` / `Ctrl + End` | Jump to page top/bottom |
| `PageDown` / `PageUp` | Scroll down/up one page |
| `Ctrl+F` | Page forward |
| `Ctrl+B` | Page backforward |

#### Undo/Redo/Reset
| Key | Action |
|-----|--------|
| `u` | Undo last action |
| `U` | Redo last undone action |
| `Ctrl+U` | Reset to initial state |

#### Display

| Key | Action |
|-----|--------|
| `Enter` | Record view of current row transposed |
| `F` | Show frequency distribution for current column |
| `s` | Show statistics for current column |
| `S` | Show statistics for entire dataframe |
| `m` | Show metadata for row count and column count |
| `M` | Show metadata for current column |
| `K` | Cycle cursor types: cell → row → column → cell |
| `~` | Toggle row labels |
| `_` (underscore) | Toggle column full width |
| `z` | Freeze rows and columns |
| `,` | Toggle thousand separator for numeric display |
| `h` | Hide current column |
| `H` | Show all hidden rows/columns |

#### Data Editing

| Key | Action |
|-----|--------|
| `Double-click` | Edit cell or rename column header |
| `delete` | Clear current cell (set to NULL) |
| `e` | Edit current cell (respects data type) |
| `E` | Edit entire column with value/expression |
| `a` | Add empty column after current |
| `A` | Add column with name and value/expression |
| `@` | Add a link column from URL template |
| `-` (minus) | Delete current column |
| `x` | Delete current row |
| `X` | Delete current row and all those below |
| `Ctrl+X` | Delete current row and all those above |
| `d` | Duplicate current column |
| `D` | Duplicate current row |

#### Row Selection

| Key | Action |
|-----|--------|
| `\` | Select rows wth cell matches or those matching cursor value in current column |
| `\|` (pipe) | Select rows by expression |
| `{` | Go to previous selected row |
| `}` | Go to next selected row |
| `'` | Select/deselect current row |
| `t` | Toggle row selections (invert) |
| `T` | Clear all row selections and/or cell matches |

#### Find & Replace

| Key | Action |
|-----|--------|
| `/` | Find in current column with cursor value and highlight matching cells |
| `?` | Find in current column with expression and highlight matching cells |
| `n` | Go to next matching cell |
| `N` | Go to previous matching cell |
| `;` | Find across all columns with cursor value |
| `:` | Find across all columns with expression |
| `r` | Find and replace in current column (interactive or replace all) |
| `R` | Find and replace across all columns (interactive or replace all) |

#### View & Filter
| Key | Action |
|-----|--------|
| `"` (quote) | Filter selected rows (others removed) |
| `v` | View selected rows (others hidden) |
| `V` | View selected by expression (others hidden) |

#### SQL Interface

| Key | Action |
|-----|--------|
| `l` | Simple SQL interface (select columns & where clause) |
| `L` | Advanced SQL interface (full SQL query with syntax highlight) |

#### Sorting (supporting multiple columns)

| Key | Action |
|-----|--------|
| `[` | Sort current column ascending |
| `]` | Sort current column descending |

#### Reordering

| Key | Action |
|-----|--------|
| `Shift+↑` | Move current row up |
| `Shift+↓` | Move current row down |
| `Shift+←` | Move current column left |
| `Shift+→` | Move current column right |

#### Type Casting

| Key | Action |
|-----|--------|
| `#` | Cast current column to integer (Int64) |
| `%` | Cast current column to float (Float64) |
| `!` | Cast current column to boolean |
| `$` | Cast current column to string |

#### Copy & Save

| Key | Action |
|-----|--------|
| `c` | Copy current cell to clipboard |
| `Ctrl+C` | Copy column to clipboard |
| `Ctrl+R` | Copy row to clipboard (tab-separated) |
| `Ctrl+S` | Save to file |

## Features in Detail

### 1. Color-Coded Data Types

Columns are automatically styled based on their data type:
- **integer**: Cyan text, right-aligned
- **float**: Yellow text, right-aligned
- **string**: Green text, left-aligned
- **boolean**: Blue text, centered
- **temporal**: Magenta text, centered

### 2. Row Detail View

Press `Enter` on any row to open a modal showing all column values for that row.
Useful for examining wide datasets where columns don't fit well on screen.

**In the Row Detail Modal**:
- Press `v` to **view** all rows containing the selected column value (others hidden but preserved)
- Press `"` to **filter** all rows containing the selected column value (others removed)
- Press `{` to move to the previous row
- Press `}` to move to the next row
- Press `q` or `Escape` to close the modal

### 3. Row Selection

The application provides multiple modes for selecting rows (marks it for filtering or viewing):

- `\` - Select rows with cell matches or those matching cursor value in current column (respects data type)
- `|` - Opens dialog to select rows with custom expression
- `'` - Select/deselect current row
- `t` - Flip selections of all rows
- `T` - Clear all row selections and cell matches
- `{` - Go to previous selected row
- `}` - Go to next selected row

**Advanced Options**:

When searching or finding, you can use checkboxes in the dialog to enable:
- **Match Nocase**: Ignore case differences
- **Match Whole**: Match complete value, not partial substrings or words

These options work with plain text searches. Use Polars regex patterns in expressions for more control. For example, use `(?i)` prefix in regex (e.g., `(?i)john`) for case-insensitive matching.

**Quick Tips:**
- Search results highlight matching rows in **red**
- Use expression for advanced selection (e.g., $attack > $defense)
- Multiple searches **accumulate** - each new search adds to the selections or matches
- Type-aware matching automatically converts values. Resort to string comparison if conversion fails
- Use `u` to undo any search or filter

### 4. Find & Replace
Find by value/expression and highlight matching cells:
- `/` - Find cursor value within current column (respects data type)
- `?` - Open dialog to search current column with expression
- `;` - Find cursor value across all columns
- `:` - Open dialog to search all columns with expression
- `n` - Go to next matching cell
- `N` - Go to previous matching cell

Replace values in current column (`r`) or across all columns (`R`).

**How It Works:**

When you press `r` or `R`, enter:
1. **Find term**: Value or expression to search for (done by string value)
2. **Replace term**: Replacement value
3. **Matching options**: Match Nocase (ignore case), Match Whole (complete match only)
4. **Replace mode**: All at once or interactive review

**Replace All**:
- Replaces all matches with one operation
- Shows confirmation with match count

**Replace Interactive**:
- Review each match one at a time (confirm, skip, or cancel)
- Shows progress

**Tips:**
- Search are done by string value (i.e., ignoring data type)
- Type `NULL` to replace null/missing values
- Use `Match Nocase` for case-insensitive matching
- Use `Match Whole` to avoid partial replacements
- Support undo (`u`)

### 5. Filter vs. View

Both operations show selected rows but with fundamentally different effects:

| Operation | Keyboard | Effect | Data Preserved |
|-----------|----------|--------|-----------------|
| **View** | `v`, `V` | Hides non-matching rows | Yes (hidden, can be restored by `H`) |
| **Filter** | `"` | Removes non-matching rows | No (permanently deleted) |

**When to use View** (`v` or `V`):
- Exploring or analyzing data safely
- Switching between different perspectives
- Press `H` to restore hidden rows (and hidden columns)

**When to use Filter** (`"`):
- Cleaning data (removing unwanted rows)
- Creating a trimmed dataset for export
- Permanent row removal from your dataframe

**Note**:
- If currently there are no selected rows and no matching cells, the `"` (Filter) and `v` (View) will use cursor value for search.
- Both support full undo with `u`.

### 6. [Polars Expressions](https://docs.pola.rs/api/python/stable/reference/expressions/index.html)

Complex values or filters can be specified via Polars expressions, with the following adaptions for convenience:

**Column References:**
- `$_` - Current column (based on cursor position)
- `$1`, `$2`, etc. - Column by 1-based index
- `$age`, `$salary` - Column by name (use actual column names)
- `` $`col name` `` - Column by name with spaces (backtick quoted)

**Row References:**
- `$#` - Current row index (1-based)

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

**String Matching:** ([Polars string API reference](https://docs.pola.rs/api/python/stable/reference/series/string.html))
- `$name.str.contains("John")` - Name contains "John" (case-sensitive)
- `$name.str.contains("(?i)john")` - Name contains "john" (case-insensitive)
- `$email.str.ends_with("@company.com")` - Email ends with domain
- `$code.str.starts_with("ABC")` - Code starts with "ABC"
- `$age.cast(pl.String).str.starts_with("7")` - Age (cast to string first) starts with "7"

**Number Operations:**
- `$age * 2 > 100` - Double age greater than 100
- `($salary + $bonus) > 150000` - Total compensation over 150,000
- `$percentage >= 50` - Percentage at least 50%

**Null Handling:**
- `$column.is_null()` - Find null/missing values
- `$column.is_not_null()` - Find non-null values
- `NULL` - a value to represent null for convenience

**Tips:**
- Use column names that match exactly (case-sensitive)
- Use parentheses to clarify complex expressions: `($a & $b) | ($c & $d)`

### 7. Sorting

- Press `[` to sort current column ascending
- Press `]` to sort current column descending
- Multi-column sorting supported (press multiple times on different columns)
- Press same key twice to remove the column from sorting

### 8. Dataframe & Column Metadata

View quick metadata about your dataframe and columns to understand their structure and content.

**Dataframe Metadata** (`m`):
- Press `m` to open a modal displaying:
  - **Row** - Total number of rows in the dataframe
  - **Column** - Total number of columns in the dataframe

**Column Metadata** (`M`):
- Press `M` to open a modal displaying details for all columns:
  - **ID** - 1-based column index
  - **Name** - Column name
  - **Type** - Data type (e.g., Int64, String, Float64, Boolean)

**In Metadata Modals**:
- Press `q` or `Escape` to close

### 9. Frequency Distribution

Press `F` to see value distributions of the current column. The modal shows:
- Value, Count, Percentage, Histogram
- **Total row** at the bottom

**In the Frequency Table**:
- Press `[` and `]` to sort by any column (value, count, or percentage)
- Press `v` to **view** all rows containing the selected value (others hidden but preserved)
- Press `"` to **filter** all rows containing the selected value (others removed)
- Press `q` or `Escape` to close the frequency table

This is useful for:
- Understanding value distributions
- Quickly filtering to specific values
- Identifying rare or common values
- Finding the most/least frequent entries

### 10. Column & Dataframe Statistics

Show summary statistics (count, null count, mean, median, std, min, max, etc.) using Polars' `describe()` method.
- `s` for the current column
- `S` for all columns across the entire dataframe

**In the Statistics Modal**:
- Press `q` or `Escape` to close the statistics table
- Use arrow keys to navigate
- Useful for quick data validation and summary reviews

This is useful for:
- Understanding data distributions and characteristics
- Identifying outliers and anomalies
- Data quality assessment
- Quick statistical summaries without external tools
- Comparing statistics across columns

### 11. Data Editing

**Edit Cell** (`e` or **Double-click**):
- Opens modal for editing current cell
- Validates input based on column data type

**Rename Column Header** (**Double-click** column header):
- Quick rename by double-clicking the column header

**Delete Row** (`x`):
- Delete all selected rows (if any) at once
- Or delete single row at cursor

**Delete Row and Below** (`X`):
- Deletes the current row and all rows below it
- Useful for removing trailing data or the end of a dataset

**Delete Row and Above** (`Ctrl+X`):
- Deletes the current row and all rows above it
- Useful for removing leading rows or the beginning of a dataset

**Delete Column** (`-`):
- Removes the entire column from display and dataframe

**Add Empty Column** (`a`):
- Adds a new empty column after the current column
- Column is initialized with NULL values for all rows

**Add Column with Value/Expression** (`A`):
- Opens dialog to specify column name and initial value/expression
- Value can be a constant (e.g., `0`, `"text"`) or a Polars expression (e.g., `$age * 2`)
- Expression can reference other columns and perform calculations
- Useful for creating derived columns or adding data with formulas

**Duplicate Column** (`d`):
- Creates a new column immediately after the current column
- New column has '_copy' suffix (e.g., 'price' → 'price_copy')
- Useful for creating backups before transformation

**Duplicate Row** (`D`):
- Creates a new row immediately after the current row
- Duplicate preserves all data from original row
- Useful for batch adding similar records

**Hide/Show Columns** (`h` / `H`):
- `h` - Temporarily hide current column (data preserved)
- `H` - Restore all hidden columns and rows

### 12. Column & Row Reordering

**Move Columns**: `Shift+←` and `Shift+→`
- Swaps adjacent columns
- Reorder is preserved when saving

**Move Rows**: `Shift+↑` and `Shift+↓`
- Swaps adjacent rows
- Reorder is preserved when saving

### 13. Freeze Rows and Columns

Press `z` to open the dialog:
- Enter number of fixed rows and/or columns to keep top rows/columns visible while scrolling

### 14. Thousand Separator Toggle

Press `,` to toggle thousand separator formatting for numeric data:
- Applies to **integer** and **float** columns
- Formats large numbers with commas for readability (e.g., `1000000` → `1,000,000`)
- Works across all numeric columns in the table
- Toggle on/off as needed for different viewing preferences
- Display-only: does not modify underlying data in the dataframe
- State persists during the session

### 15. Save File

Press `Ctrl+S` to save filtered, edited, or sorted data back to file

### 16. Undo/Redo/Reset

**Undo** (`u`):
- Reverts last action with full state restoration
- Works for edits, deletions, sorts, searches, etc.
- Shows description of reverted action

**Redo** (`U`):
- Reapplies the last undone action
- Restores the state before the undo was performed
- Useful for redoing actions you've undone by mistake
- Useful for alternating between two different states

**Reset** (`Ctrl+U`):
- Reverts all changes and returns to original data state when file was first loaded
- Clears all edits, deletions, selections, filters, and sorts
- Useful for starting fresh without reloading the file

### 17. Column Type Conversion

Press the type conversion keys to instantly cast the current column to a different data type:

**Type Conversion Shortcuts**:
- `#` - Cast to **integer**
- `%` - Cast to **float**
- `!` - Cast to **boolean**
- `$` - Cast to **string**

**Features**:
- Instant conversion with visual feedback
- Full undo support - press `u` to revert
- Leverage Polars' robust type casting

**Note**: Type conversion attempts to preserve data where possible. Conversions may lose data (e.g., float to int rounding).

### 18. Cursor Type Cycling

Press `K` to cycle through selection modes:
1. **Cell mode**: Highlight individual cell (and its row/column headers)
2. **Row mode**: Highlight entire row
3. **Column mode**: Highlight entire column

### 19. SQL Interface

The SQL interface provides two modes for querying your dataframe:

#### Simple SQL Interface (`l`)
SELECT specific columns and apply WHERE conditions without writing full SQL:
- Choose which columns to include in results
- Specify WHERE clause for filtering
- Ideal for quick filtering and column selection

#### Advanced SQL Interface (`L`)
Execute complete SQL queries for advanced data manipulation:
- Write full SQL queries with standard [SQL syntax](https://docs.pola.rs/api/python/stable/reference/sql/index.html)
- Access to all SQL capabilities for complex transformations
- Always use `self` as the table name
- Syntax highlighted

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

### 20. Clipboard Operations

Copies value to system clipboard with `pbcopy` on macOS and `xclip` on Linux.

**Note**: may require a X server to work.

- Press `c` to copy cursor value
- Press `Ctrl+C` to copy column values
- Press `Ctrl+R` to copy row values (delimited by tab)
- Hold `Shift` to select with mouse

### 21. Link Column Creation

Press `@` to create a new column containing dynamically generated URLs using template.

**Template Placeholders:**

The link template supports multiple placeholder types for maximum flexibility:

- **`$_`** - Current column (the column where cursor was when `@` was pressed), e.g., `https://example.com/search/$_` - Uses values from the current column

- **`$1`, `$2`, `$3`, etc.** - Column by 1-based position index, e.g., `https://example.com/product/$1/details/$2` - Uses 1st and 2nd columns

- **`$name`** - Column by name (use actual column names), e.g., `https://example.com/$region/$city/data` - Uses `region` and `city` columns

**Features:**
- **Multiple Placeholders**: Mix and match placeholders in a single template
- **URL Prefix**: Automatically prepends `https://` if URL doesn't start with `http://` or `https://`

**Tips:**
- Use full undo (`u`) if template produces unexpected URLs
- For complex multi-column URLs, use column names (`$name`) for clarity over positions (`$1`)

### 22. Tab Management

Manage multiple files and dataframes simultaneously with tabs.

**Tab Operations:**
- **`Ctrl+O`** - Open file in a new tab
- **`>`** - Move to next tab
- **`<`** - Move to previous tab
- **`b`** - Cycle through tabs
- **`B`** - Toggle tab bar visibility
- **`Double-click`** - Rename the tab
- **`Ctrl+D`** - Duplicate current tab (creates a copy with same data and state)
- **`Ctrl+T`** - Save current tab to file
- **`Ctrl+A`** - Save all tabs in a single Excel file
- **`w`** - Save current tab to file (overwrite without prompt)
- **`W`** - Save all tabs to file (overwrite without prompt)
- **`q`** - Close current tab (closes tab, prompts to save if unsaved changes)
- **`Q`** - Close all tabs and exit app (prompts to save tabs with unsaved changes)
- **`Ctrl+Q`** - Force to quit app regardless of unsaved changes

**Tips:**
- Tabs with unsaved changes are indicated with a bright background
- Closing or quitting a tab with unsaved changes triggers a save prompt

## Dependencies

- **polars**: Fast DataFrame library for data loading/processing
- **textual**: Terminal UI framework
- **fastexcel**: Read Excel files
- **xlsxwriter**: Write Excel files

## Requirements

- Python 3.11+
- POSIX-compatible terminal (macOS, Linux, WSL)
- Terminal supporting ANSI escape sequences and mouse events

## Acknowledgments

- Inspired by [VisiData](https://visidata.org/)
- Built with [Textual](https://textual.textualize.io/) and [Polars](https://www.pola.rs/)
