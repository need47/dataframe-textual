# DataFrame Textual

A powerful, interactive terminal-based viewer/editor for CSV/TSV/Excel/Parquet/JSON/NDJSON built with Python, [Polars](https://pola.rs/), and [Textual](https://textual.textualize.io/). Inspired by [VisiData](https://www.visidata.org/), this tool provides smooth keyboard navigation, data manipulation, and a clean interface for exploring tabular data directly in terminal with multi-tab support for multiple files!

![Screenshot](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshot.png)

## Features

### Data Viewing
- 🚀 **Fast Loading** - Powered by Polars for efficient data handling
- 🎨 **Rich Terminal UI** - Beautiful, color-coded columns with various data types (e.g., integer, float, string)
- ⌨️ **Comprehensive Keyboard Navigation** - Intuitive controls

# Process compressed data from stdin
zcat compressed_data.csv.gz | dv -f csv editing, and manipulating data
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
- 📌 **Freeze Rows/Columns** - Keep important rows and columns visible while scrolling
- 🎯 **Cursor Type Cycling** - Switch between cell, row, and column selection modes
- 🔗 **Link Column Creation** - Generate clickable URLs using template expressions with placeholder support

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
dv <csv_file>
```

### Using [uv](https://docs.astral.sh/uv/)

```bash
# Quick run using uvx without installation
uvx https://github.com/need47/dataframe-textual.git <csvfile>

# Clone or download the project
cd dataframe-textual
uv sync --extra excel  # with Excel support

# Run directly with uv
uv run dv <csv_file>
```

### Development installation

```bash
# Clone the repository
git clone https://github.com/need47/dataframe-textual.git
cd dataframe-textual

# Install from local source
pip install -e .

# Or with development dependencies
pip install -e ".[excel,dev]"
```

## Usage

### Basic Usage - Single File

```bash
# After pip install dataframe-textual
dv pokemon.csv

# Or if running from source
python main.py pokemon.csv

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
- Each file appears as a separate tab
- Switch between tabs using `>` (next) or `<` (previous), or use `b` for cycling tabs
- Open additional files with `Ctrl+O`
- Close the current tab with `Ctrl+W`
- Each file maintains its own state (edits, sort order, selections, history, etc.)

## Command Line Options

```
usage: dv [-h] [-f {csv,excel,tsv,parquet,json,ndjson}] [-H] [-I] [-E] [-c COMMENT_PREFIX] [-q QUOTE_CHAR] [-l SKIP_LINES] [-a SKIP_ROWS_AFTER_HEADER] [-n NULL [NULL ...]] [files ...]

Interactive terminal based viewer/editor for tabular data (e.g., CSV/Excel).

positional arguments:
  files                 Files to view (or read from stdin)

options:
  -h, --help            show this help message and exit
  -f, --format {csv,excel,tsv,parquet,json,ndjson}
                        Specify the format of the input files
  -H, --no-header       Specify that input files have no header row
  -I, --no-inferrence   Do not infer data types when reading CSV/TSV
  -E, --ignore-errors   Ignore errors when reading CSV/TSV
  -c, --comment-prefix COMMENT_PREFIX
                        Comment lines are skipped when reading CSV/TSV (default: skip none)
  -q, --quote-char QUOTE_CHAR
                        Quote character for reading CSV/TSV (default: "; use None to disable)
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

# CSV with comment lines
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
| `Ctrl+O` | Open file in a new tab |
| `Ctrl+W` | Close current tab |
| `Ctrl+A` | Save all open tabs to Excel file |
| `b` | Cycle through tabs |
| `>` | Move to next tab |
| `<` | Move to previous tab |
| `B` | Toggle tab bar visibility |
| `q` | Quit the application |

#### View & Settings

| Key | Action |
|-----|--------|
| `F1` | Toggle help panel |
| `k` | Cycle through themes |

---

### Table-Level Controls

#### Navigation

| Key | Action |
|-----|--------|
| `g` | Jump to first row |
| `G` | Jump to last row (loads all remaining rows) |
| `↑` / `↓` | Move up/down one row |
| `←` / `→` | Move left/right one column |
| `Home` / `End` | Jump to first/last column |
| `Ctrl + Home` / `Ctrl + End` | Jump to page top/bottom |
| `PageDown` / `PageUp` | Scroll down/up one page |
| `Ctrl+F` | Page down |
| `Ctrl+B` | Page up |

#### Undo/Redo/Reset
| `u` | Undo last action |
| `U` | Redo last undone action |
| `Ctrl+U` | Reset to initial state |

#### Viewing & Display

| Key | Action |
|-----|--------|
| `Enter` | Record view of current row |
| `F` | Show frequency distribution for current column |
| `s` | Show statistics for current column |
| `S` | Show statistics for entire dataframe |
| `K` | Cycle cursor types: cell → row → column → cell |
| `~` | Toggle row labels |
| `_` (underscore) | Expand column to full width |
| `z` | Freeze rows and columns |
| `,` | Toggle thousand separator for numeric display |

#### Data Editing

| Key | Action |
|-----|--------|
| `Double-click` | Edit cell or rename column header |
| `delete` | Clear current cell (set to NULL) |
| `e` | Edit current cell (respects data type) |
| `E` | Edit entire column with expression |
| `a` | Add empty column after current |
| `A` | Add column with name and value/expression |
| `@` | Add a link column from template |
| `-` (minus) | Delete current column |
| `x` | Delete current row |
| `X` | Delete current row and all those below |
| `Ctrl+X` | Delete current row and all those above |
| `d` | Duplicate current column (appends '_copy' suffix) |
| `D` | Duplicate current row |
| `h` | Hide current column |
| `H` | Show all hidden rows/columns |

#### Searching & Filtering

| Key | Action |
|-----|--------|
| `\` | Search in current column using cursor value and select rows |
| `\|` (pipe) | Search in current column with expression and select rows |
| `{` | Go to previous selected row |
| `}` | Go to next selected row |
| `/` | Find in current column with cursor value and highlight matches |
| `?` | Find in current column with expression and highlight matches |
| `n` | Go to next match |
| `N` | Go to previous match |
| `'` | Select/deselect current row |
| `t` | Toggle selected rows (invßert) |
| `T` | Clear all selected rows and/or matches |
| `"` (quote) | Filter to selected rows and remove others |
| `v` | View only rows (and hide others) by selected rows and/or matches or cursor value |
| `V` | View only rows (and hide others) by expression |

#### SQL Interface

| Key | Action |
|-----|--------|
| `l` | Simple SQL interface (select columns & where clause) |
| `L` | Advanced SQL interface (full SQL query with syntax highlight) |

#### Find & Replace

| Key | Action |
|-----|--------|
| `;` | Find across all columns with cursor value |
| `:` | Find across all columns with expression |
| `r` | Find and replace in current column (interactive or replace all) |
| `R` | Find and replace across all columns (interactive or replace all) |

#### Sorting

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
| `Ctrl+S` | Save current tab to file |

## Features in Detail

### 1. Color-Coded Data Types

Columns are automatically styled based on their data type:
- **integer**: Cyan text, right-aligned
- **float**: Magenta text, right-aligned
- **string**: Green text, left-aligned
- **boolean**: Blue text, centered
- **temporal**: Yellow text, centered

### 2. Row Detail View

Press `Enter` on any row to open a modal showing all column values for that row.
Useful for examining wide datasets where columns don't fit well on screen.

**In the Row Detail Modal**:
- Press `v` to **view** all rows containing the selected column value (and hide others)
- Press `"` to **filter** all rows containing the selected column value (and remove others)
- Press `q` or `Escape` to close the modal

### 3. Search & Filtering

The application provides multiple search modes for different use cases:

**Search Operations** - Search by value/expression in current column and select rows:
- **`\` - Column Cursor Search**: Search cursor value
- **`|` - Column Expression Search**: Opens dialog to search with custom expression

**Find Operations** - Find by value/expression and highlight matches:
- **`/` - Column Find**: Find cursor value within current column
- **`?` - Column Expression Find**: Open dialog to search current column with expression
- **`;` - Global Find**: Find cursor value across all columns
- **`:` - Global Expression Find**: Open dialog to search all columns with expression

**Selection & Filtering**:
- **`'` - Toggle Row Selection**: Select/deselect current row (marks it for filtering or viewing)
- **`t` - Invert Selections**: Flip selections of all rows
- **`T` - Clear Selections**: Remove all row selections and matches
- **`"` - Filter Selected**: View only the selected rows (others removed)
- **`v` - View by Value**: View rows by selected rows or cursor value (others hidden but preserved)
- **`V` - View by Expression**: View rows using custom expression (others hidden but preserved)

**Advanced Matching Options**:

When searching or finding, you can use checkboxes in the dialog to enable:
- **Match Nocase**: Ignore case differences (e.g., "john", "John", "JOHN" all match)
- **Match Whole**: Match complete value, not partial substrings or words (e.g., "cat" won't match in "catfish")

These options work with plain text searches. Use Polars regex patterns in expressions for more control:
- **Case-insensitive matching in expressions**: Use `(?i)` prefix in regex (e.g., `(?i)john`)
- **Word boundaries in expressions**: Use `\b` in regex (e.g., `\bjohn\b` matches whole word)

**Quick Tips:**
- Search results highlight matching rows/cells in **red**
- Multiple searches **accumulate** - each new search adds to the selections or matches
- Type-aware matching automatically converts values. Resort to string comparison if conversion fails
- Use `u` to undo any search or filter

### 3b. Find & Replace

The application provides powerful find and replace functionality for both single-column and global replacements.

**Replace Operations**:
- **`r` - Column Replace**: Replace values in the current column
- **`R` - Global Replace**: Replace values across all columns

**How It Works:**

When you press `r` or `R`, a dialog opens where you can enter:
1. **Find term**: The value or expression to search for
2. **Replace term**: What to replace matches with
3. **Matching options**:
   - **Match Nocase**: Ignore case differences when matching (unchecked by default)
   - **Match Whole**: Match complete words only, not partial words (unchecked by default)
4. **Replace option**:
   - Choose **"Replace All"** to replace all matches at once (with confirmation)
   - Otherwise, review and confirm each match individually

**Replace All** (`r` or `R` → Choose "Replace All"):
- Shows a confirmation dialog with the number of matches and replacements
- Replaces all matches with a single operation
- Full undo support with `u`
- Useful for bulk replacements when you're confident about the change

**Replace Interactive** (`r` or `R` → Choose "Replace Interactive"):
- Shows each match one at a time with a preview of the replacement
- For each match, press:
  - `Enter` or press the `Yes` button - **Replace this occurrence** and move to next
  - Press the `Skip` button - **Skip this occurrence** and move to next
  - `Escape` or press the `No` button - **Cancel** remaining replacements (but keep already-made replacements)
- Displays progress: `Occurrence X of Y` (Y = total occurrences, X = current)
- Useful for careful replacements where you want to review each change

**For Global Replace (`R`)**:
- Searches and replaces across all columns simultaneously
- Each column can have different matching behavior (string matching for text, numeric for numbers)
- Preview shows which columns contain matches before replacement
- Useful for standardizing values across multiple columns

**Features:**
- **Full history support**: Use `u` (undo) to revert any replacement
- **Visual feedback**: Matching cells are highlighted before you choose replacement mode
- **Safe operations**: Requires confirmation before replacing
- **Progress tracking**: Shows how many replacements have been made during interactive mode
- **Type-aware**: Respects column data types when matching and replacing
- **Flexible matching**: Support for case-insensitive and whole-word matching

**Tips:**
- **NULL**: Replace null/missing values (type `NULL`)
- Use interactive mode for one-time replacements to be absolutely sure
- Use "Replace All" for routine replacements (e.g., fixing typos, standardizing formats)
- Use **Match Nocase** for matching variations of names or titles
- Use **Match Whole** to avoid unintended partial replacements
- Use `u` immediately if you accidentally replace something wrong
- For complex replacements, use Polars expressions or regex patterns in the find term
- Test with a small dataset first before large replacements

### 4. [Polars Expressions](https://docs.pola.rs/api/python/stable/reference/expressions/index.html)

Complex values or filters can be specified via Polars expressions, with the following adaptions for convenience:

**Column References:**
- `$_` - Current column (based on cursor position)
- `$1`, `$2`, etc. - Column by 1-based index
- `$age`, `$salary` - Column by name (use actual column names)

**Row References:**
- `$#` - Current row index (1-based)

**Basic Comparisons:**
- `$_ > 50` - Current column greater than 50
- `$salary >= 100000` - Salary at least 100,000
- `$age < 30` - Age less than 30
- `$status == 'active'` - Status exactly matches 'active'
- `$name != 'Unknown'` - Name is not 'Unknown'

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

### 5. Sorting

- Press `[` to sort current column ascending
- Press `]` to sort current column descending
- Multi-column sorting supported (press multiple times on different columns)
- Press same key twice to remove the column from sorting

### 6. Frequency Distribution

Press `F` to see value distributions of the current column. The modal shows:
- Value, Count, Percentage, Histogram
- **Total row** at the bottom

**In the Frequency Table**:
- Press `[` and `]` to sort by any column (value, count, or percentage)
- Press `v` to **filter** all rows with the selected value (others hidden but preserved)
- Press `"` to **exclude** all rows containing the selected value (others removed)
- Press `q` or `Escape` to close the frequency table

This is useful for:
- Understanding value distributions
- Quickly filtering to specific values
- Identifying rare or common values
- Finding the most/least frequent entries

### 7. Column & Dataframe Statistics

Press `s` to see summary statistics for the current column, or press `S` for statistics across the entire dataframe.

**Column Statistics** (`s`):
- Shows calculated statistics using Polars' `describe()` method
- Displays: count, null count, mean, median, std, min, max, etc.

**Dataframe Statistics** (`S`):
- Shows statistics for all numeric and applicable columns simultaneously
- Displays: count, null count, mean, median, std, min, max, etc.

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

### 8. Data Editing

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

### 9. Hide & Show Columns

**Hide Column** (`h`):
- Temporarily hides the current column from display
- Column data is preserved in the dataframe
- Hidden columns are included in saves

**Show Hidden Rows/Columns** (`H`):
- Restores all previously hidden rows/columns to the display

### 10. Duplicate Column

Press `d` to duplicate the current column:
- Creates a new column immediately after the current column
- New column has '_copy' suffix (e.g., 'price' → 'price_copy')
- Duplicate preserves all data from original column
- New column is inserted into the dataframe

This is useful for:
- Creating backup copies of columns before transformation
- Working with alternative versions of column data
- Comparing original vs. processed column values side-by-side

### 11. Duplicate Row

Press `D` to duplicate the current row:
- Creates a new row immediately after the current row
- Duplicate preserves all data from original row
- New row is inserted into the dataframe

This is useful for:
- Creating variations of existing data records
- Batch adding similar rows with modifications

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

### 13.5. Thousand Separator Toggle

Press `,` to toggle thousand separator formatting for numeric data:
- Applies to **integer** and **float** columns
- Formats large numbers with commas for readability (e.g., `1000000` → `1,000,000`)
- Works across all numeric columns in the table
- Toggle on/off as needed for different viewing preferences
- Display-only: does not modify underlying data in the dataframe
- State persists during the session

### 14. Save File

Press `Ctrl+S` to save:
- Save filtered, edited, or sorted data back to file
- Choose filename in modal dialog
- Confirm if file already exists

### 15. Undo/Redo/Reset

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

### 16. Column Type Conversion

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

### 17. Cursor Type Cycling

Press `K` to cycle through selection modes:
1. **Cell mode**: Highlight individual cell (and its row/column headers)
2. **Row mode**: Highlight entire row
3. **Column mode**: Highlight entire column

### 18. SQL Interface

The SQL interface provides two modes for querying your dataframe:

#### Simple SQL Interface (`l`)
Select specific columns and apply WHERE conditions without writing full SQL:
- Choose which columns to include in results
- Specify WHERE clause for filtering
- Ideal for quick filtering and column selection

#### Advanced SQL Interface (`L`)
Execute complete SQL queries for advanced data manipulation:
- Write full SQL queries with standard [SQL syntax](https://docs.pola.rs/api/python/stable/reference/sql/index.html)
- Support for JOINs, GROUP BY, aggregations, and more
- Access to all SQL capabilities for complex transformations
- Always use `self` as the table name
- Syntax highlighted

**Examples:**
```sql
-- Filter and select specific rows and/or columns
SELECT name, age FROM self WHERE age > 30

-- Aggregate with GROUP BY
SELECT department, COUNT(*) as count, AVG(salary) as avg_salary
FROM self
GROUP BY department

-- Complex filtering with multiple conditions
SELECT *
FROM self
WHERE (age > 25 AND salary > 50000) OR department = 'Management'
```

### 19. Clipboard Operations

Copies value to system clipboard with `pbcopy` on macOS and `xclip` on Linux
**Note** May require a X server to work

- Press `c` to copy cursor value
- Press `Ctrl+C` to copy column values
- Press `Ctrl+R` to copy row values (delimited by tab)
- Hold `Shift` to select with mouse

### 20. Link Column Creation

Press `@` to create a new column containing dynamically generated URLs using template.

**Template Placeholders:**

The link template supports multiple placeholder types for maximum flexibility:

- **`$_`** - Current column (the column where cursor was when `@` was pressed)
  - Example: `https://example.com/search/$_` - Uses values from the current column

- **`$1`, `$2`, `$3`, etc.** - Column by 1-based position index
  - Example: `https://example.com/product/$1/details/$2` - Uses 1st and 2nd columns
  - Index corresponds to column display order (left-to-right)

- **`$name`** - Column by name (use actual column names)
  - Example: `https://pubchem.ncbi.nlm.nih.gov/search?q=$product_id` - Uses `product_id` column
  - Example: `https://example.com/$region/$city/data` - Uses `region` and `city` columns

**Features:**
- **Multiple Placeholders**: Mix and match placeholders in a single template
- **URL Prefix**: Automatically prepends `https://` if URL doesn't start with `http://` or `https://`

**Tips:**
- Use full undo (`u`) if template produces unexpected URLs
- For complex multi-column URLs, use column names (`$name`) for clarity over positions (`$1`)

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
