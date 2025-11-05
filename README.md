# DataFrame Textual

A powerful, interactive terminal-based viewer/editor for CSV/TSV/Excel/Parquet/JSON/NDJSON built with Python, [Polars](https://pola.rs/), and [Textual](https://textual.textualize.io/). Inspired by [VisiData](https://www.visidata.org/), this tool provides smooth keyboard navigation, data manipulation, and a clean interface for exploring tabular data directly in your terminal. Now with **multi-file support for simultaneous data comparison**!

![Screenshot](https://raw.githubusercontent.com/need47/dataframe-textual/refs/heads/main/screenshot.png)

## Features

### Core Data Viewing
- 🚀 **Fast Loading** - Powered by Polars for efficient data handling
- 🎨 **Rich Terminal UI** - Beautiful, color-coded columns with automatic type detection
- ⌨️ **Comprehensive Keyboard Navigation** - Intuitive controls for browsing, editing, and manipulating data
- 📊 **Flexible Input** - Read from files or stdin (pipes/redirects)
- 🔄 **Smart Pagination** - Lazy load rows on demand for handling large datasets

### Data Manipulation
- 📝 **Data Editing** - Edit cells, delete rows, and remove columns
- 🔍 **Search & Filter** - Find values, highlight matches, and filter selected rows
- ↔️ **Column/Row Reordering** - Move columns and rows with simple keyboard shortcuts
- 📈 **Sorting & Statistics** - Multi-column sorting and frequency distribution analysis
- 💾 **Save & Undo** - Save filtered data back to file with full undo/redo support

### Advanced Features
- 📌 **Pin Rows/Columns** - Keep important rows and columns visible while scrolling
- 🎯 **Cursor Type Cycling** - Switch between cell, row, and column selection modes
- 📂 **Multi-File Support** - Open multiple files in tabs for side-by-side comparison
- 🔄 **Tab Management** - Seamlessly switch between open files with keyboard shortcuts

## Installation

### Using pip

```bash
# Install from PyPI
pip install dataframe-textual

# With Excel support (fastexcel, xlsxwriter)
pip install dataframe-textual[excel]
```

Then run:
```bash
dataframe-textual <csv_file>
```

### Using uv

```bash
# Quick run using uvx without installation
uvx https://github.com/need47/dataframe-textual.git <csvfile>

# Clone or download the project
cd dataframe-textual

# Run directly with uv
uv run python main.py <csv_file>

#
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
dataframe-textual pokemon.csv

# Or if running from source
python main.py pokemon.csv

# Or with uv
uv run python main.py pokemon.csv

# Read from stdin
cat data.csv | dataframe-textual
dataframe-textual < data.csv
```

### Multi-File Usage - Multiple Tabs

```bash
# Open multiple files in tabs
dataframe-textual file1.csv file2.csv file3.csv

# Open multiple sheets in tabs in an Excel file
dataframe-textual file.xlsx

# Mix files and stdin (file opens first, then read from stdin)
dataframe-textual data1.csv < data2.csv
```

When multiple files are opened:
- Each file appears as a separate tab at the top
- Switch between tabs using `>` (next) or `<` (previous)
- Open additional files with `Ctrl+O`
- Close the current tab with `Ctrl+W`
- Each file maintains its own state (sort order, selections, history, etc.)
- Edits and filters are independent per file

## Keyboard Shortcuts

### App-Level Controls

#### File & Tab Management

| Key | Action |
|-----|--------|
| `Ctrl+O` | Open new CSV file in a new tab |
| `Ctrl+W` | Close current tab |
| `Ctrl+Shift+S` | Save all open tabs to Excel file |
| `>` or `b` | Move to next tab |
| `<` | Move to previous tab |
| `B` | Toggle tab bar visibility |
| `q` | Quit the application |

#### View & Settings

| Key | Action |
|-----|--------|
| `Ctrl+H` | Toggle help panel |
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
| `PageDown` / `PageUp` | Scroll down/up |
| Arrow keys | Navigate the table |

#### Viewing & Display

| Key | Action |
|-----|--------|
| `Enter` | View full details of current row in modal |
| `F` | Show frequency distribution for column |
| `s` | Show statistics for current column |
| `S` | Show statistics for entire dataframe |
| `!` | Cycle cursor type: cell → row → column → cell |
| `@` | Toggle row labels visibility |

#### Data Editing

| Key | Action |
|-----|--------|
| `e` | Edit current cell (respects data type) |
| `E` | Edit entire column with expression |
| `m` | Rename current column |
| `a` | Add empty column after current |
| `A` | Add column with name and optional expression (separated by `;`) |
| `x` | Delete current row |
| `X` | Clear current cell (set to None) |
| `D` | Duplicate current row |
| `-` | Delete current column |
| `d` | Duplicate current column (appends '_copy' suffix) |
| `h` | Hide current column |
| `H` | Show all hidden columns |

#### Searching & Filtering

| Key | Action |
|-----|--------|
| `\|` (pipe) | Search in current column with expression |
| `Ctrl+\|` | Global search with expression |
| `\` | Search in current column using cursor value |
| `Ctrl+\` | Global search using cursor value |
| `/` | Find in current column with cursor value |
| `Ctrl+/` | Global find using cursor value |
| `?` | Find in current column with expression |
| `Ctrl+Shift+/` | Global find with expression |
| `'` | Select/deselect current row |
| `t` | Toggle highlighting of all selected rows (invert) |
| `T` | Clear all selected rows |
| `"` (quote) | Filter to show only selected rows |
| `v` | View/filter rows by selected rows or current cell value |
| `V` | View/filter rows by expression (Polars expression syntax) |

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

#### Type Conversion

| Key | Action |
|-----|--------|
| `#` | Cast current column to integer (Int64) |
| `%` | Cast current column to float (Float64) |
| `$` | Cast current column to boolean |
| `^` | Cast current column to string |

#### Data Management

| Key | Action |
|-----|--------|
| `p` | Pin rows and columns |
| `Ctrl+C` | Copy current cell to clipboard |
| `Ctrl+S` | Save current tab to file |
| `u` | Undo last action |
| `U` | Reset to original data |

#### Modal Interactions

**In Frequency Distribution Modal** (opened with `F`):
- `[` / `]` - Sort frequency table
- `v` - Filter main table to selected value
- `"` - Highlight rows with selected value
- `q` / `Escape` - Close modal

**In Row Detail Modal** (opened with `Enter`):
- `v` - Filter main table to selected column value
- `"` - Highlight rows with selected column value
- `q` / `Escape` - Close modal

**Tip**: Press `?` or `h` to open the context-sensitive help panel which displays all available shortcuts based on your current focus.

## Features in Detail

### 1. Color-Coded Data Types

Columns are automatically styled based on their data type:
- **Int64** (Integers): Cyan text, right-aligned
- **Float64** (Decimals): Magenta text, right-aligned
- **String**: Green text, left-aligned
- **Boolean**: Blue text, centered
- **Date/Datetime**: Blue text, centered

### 2. Row Detail View

Press `Enter` on any row to open a modal showing all column values for that row. Useful for examining wide datasets where columns don't fit on screen.

**In the Row Detail Modal**:
- Press `v` to **filter** the main table to show only rows with the selected column value
- Press `"` to **highlight** all rows containing the selected column value
- Press `q` or `Escape` to close the modal

### 3. Search & Filtering

The application provides multiple search modes for different use cases:

**Search Operations** - Direct value/expression matching in current column:
- **`|` - Column Expression Search**: Opens dialog to search current column with custom expression
- **`\` - Column Cursor Search**: Instantly search current column using the current cell's value
- **`Ctrl+\` - Global Cursor Search**: Instantly search all columns using the current cell's value

**Find Operations** - Quick cursor value matching:
- **`/` - Column Find**: Find current cell value within current column
- **`Ctrl+/` - Global Find**: Find current cell value across all columns
- **`?` - Column Expression Find**: Open dialog to search current column with expression
- **`Ctrl+Shift+/` - Global Expression Find**: Open dialog to search all columns with expression

**Selection & Filtering**:
- **`'` - Toggle Row Selection**: Select/deselect current row (marks it for filtering)
- **`t` - Invert All Selections**: Flip selection state of all rows at once
- **`T` - Clear Selections**: Remove all row selections and highlights
- **`"` - Filter Selected**: Display only the selected rows (others hidden but preserved)
- **`v` - View by Value**: Filter/view rows by selected rows or current cell value
- **`V` - View by Expression**: Filter/view rows using custom Polars expression

**How It Works:**
- Search results highlight matching rows/cells in **red**
- Multiple searches **accumulate selections** - each new search adds to the highlight
- Type-aware matching automatically converts values to strings for comparison
- Large datasets automatically load additional rows if matches extend beyond visible area
- Use `u` (undo) to restore original view

**Quick Tips:**
- Use `\` for instant searching without opening a dialog
- Use `Ctrl+\` to search all columns without typing
- Use `"` after selecting rows to hide everything except your selection
- Use `u` to undo any search or filter

### 4. Filter by Expression

Complex filters can be applied via Polars expressions using the `V` key. The following special syntax is supported:

**Column References:**
- `$_` - Current column (based on cursor position)
- `$1`, `$2`, etc. - Column by 1-based index
- `$age`, `$salary` - Column by name (use actual column names)

**Basic Comparisons:**
- `$_ > 50` - Current column greater than 50
- `$salary >= 100000` - Salary at least 100,000
- `$age < 30` - Age less than 30
- `$status == 'active'` - Status exactly matches 'active'
- `$name != 'Unknown'` - Name is not 'Unknown'

**Logical Operators:**
- `&` - AND (both conditions true)
- `|` - OR (either condition true)
- `~` - NOT (negate condition)

**Practical Examples:**
- `$age < 30 & $status == 'active'` - Age less than 30 AND status is active
- `$name == 'Alice' | $name == 'Bob'` - Name is Alice or Bob
- `$salary / 1000 >= 50` - Salary divided by 1,000 is at least 50
- `$department == 'Sales' & $bonus > 5000` - Sales department with bonus over 5,000
- `$score >= 80 & $score <= 90` - Score between 80 and 90
- `~($status == 'inactive')` - Status is not inactive
- `$revenue > $expenses` - Revenue exceeds expenses

**String Matching:**
- `$name.str.contains("John")` - Name contains "John" (case-sensitive)
- `$name.str.contains("(?i)john")` - Name contains "john" (case-insensitive)
- `$email.str.ends_with("@company.com")` - Email ends with domain
- `$code.str.starts_with("ABC")` - Code starts with "ABC"

**Number Operations:**
- `$age * 2 > 100` - Double age greater than 100
- `($salary + $bonus) > 150000` - Total compensation over 150,000
- `$percentage >= 50` - Percentage at least 50%

**Null Handling:**
- `$column.is_null()` - Find null/missing values
- `$column.is_not_null()` - Find non-null values

**Tips:**
- Use column names that match exactly (case-sensitive)
- String literals must be in single or double quotes
- Numbers don't need quotes
- Use parentheses to clarify complex expressions: `($a & $b) | ($c && $d)`
- Press `q` or `Escape` to cancel the filter dialog without filtering

### 5. Sorting

- Press `[` to sort current column ascending
- Press `]` to sort current column descending
- Multi-column sorting supported (press multiple times on different columns)
- Press same key twice to toggle direction
- Frequency view (`F`) shows value distribution with optional sorting

### 6. Frequency Distribution

Press `F` to see how many times each value appears in the current column. The modal shows:
- Value
- Count
- Percentage of total
- **Total row** at the bottom

**In the Frequency Table**:
- Press `[` and `]` to sort by any column (value, count, or percentage)
- Press `v` to **filter** the main table to show only rows with the selected value
- Press `"` to **highlight** all rows containing the selected value
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
- Values are color-coded according to their data type
- Statistics label column has no styling for clarity

**Dataframe Statistics** (`S`):
- Shows statistics for all numeric and applicable columns simultaneously
- Data columns are color-coded by their type (Int64, Float64, String, etc.)

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

**Edit Cell** (`e`):
- Opens modal for editing current cell
- Validates input based on column data type
- Shows column name and type
- Integer, number, and text inputs available

**Delete Row** (`d`):
- Delete single row at cursor
- Or delete all selected rows at once
- Deleted rows are marked internally but kept for undo

**Delete Column** (`-`):
- Removes the entire column from view and dataframe
- Cannot be undone directly (use undo feature)

### 9. Hide & Show Columns

**Hide Column** (`h`):
- Temporarily hides the current column from display
- Column data is preserved in the dataframe
- Hidden columns don't appear in saves until shown again

**Show Hidden Columns** (`H`):
- Restores all previously hidden columns to the display
- Returns table to full column view
- Useful for temporarily removing columns from view without deleting them

This is useful for:
- Focusing on specific columns without deleting data
- Temporarily removing cluttered or unnecessary columns
- Comparing different column sets via hide/show
- Preserving all data while simplifying the view

### 10. Duplicate Column

Press `d` to duplicate the current column:
- Creates a new column immediately after the current column
- New column has '_copy' suffix (e.g., 'price' → 'price_copy')
- Duplicate preserves all data from original column
- New column is inserted into the dataframe using Polars operations

This is useful for:
- Creating backup copies of columns before transformation
- Working with alternative versions of column data
- Comparing original vs. processed column values side-by-side
- Data preparation and validation workflows

### 11. Duplicate Row

Press `D` to duplicate the current row:
- Creates a new row immediately after the current row
- Duplicate preserves all data from original row
- New row is inserted into the dataframe
- Cursor moves to the duplicated row

This is useful for:
- Creating variations of existing data records
- Batch adding similar rows with modifications
- Testing with duplicate data
- Data validation and comparison workflows

### 12. Column & Row Reordering

**Move Columns**: `Shift+←` and `Shift+→`
- Swaps adjacent columns
- Reorder is preserved when saving

**Move Rows**: `Shift+↑` and `Shift+↓`
- Swaps adjacent rows
- Visual reordering without affecting data

### 13. Pin Rows and Columns

Press `p` to open the pin dialog:
- Enter number of fixed rows: keeps top rows visible while scrolling
- Enter two numbers: `<rows> <columns>` (space-separated)
- Example: `2 3` pins top 2 rows and left 3 columns

### 14. Save File

Press `Ctrl+S` to save:
- Save filtered, edited, or sorted data back to file
- Choose filename in modal dialog
- Confirm if file already exists

### 15. Undo/Redo

Press `u` to undo:
- Reverts last action with full state restoration
- Works for edits, deletions, sorts, searches, etc.
- Shows description of reverted action

### 16. Column Type Conversion

Press the type conversion keys to instantly cast the current column to a different data type:

**Type Conversion Shortcuts**:
- `#` - Cast to **Integer (Int64)**
- `%` - Cast to **Float (Float64)**
- `$` - Cast to **Boolean**
- `*` - Cast to **String**

**Examples**:
- Convert string numbers to integers: Move to column, press `#`
- Convert integers to decimals: Move to column, press `%`
- Convert text to string: Move to column, press `*`
- Convert numeric values to true/false: Move to column, press `$`

**Features**:
- Instant conversion with visual feedback
- Full undo support - press `u` to revert
- Automatic error handling with helpful messages
- Works with Polars' robust type casting

**Note**: Type conversion attempts to preserve data where possible. Conversions that would lose data (e.g., float to int rounding, invalid boolean strings) will notify you with the reason.

### 17. Cursor Type Cycling

Press `!` to cycle through selection modes:
1. **Cell mode**: Highlight individual cell (and its row/column headers)
2. **Row mode**: Highlight entire row
3. **Column mode**: Highlight entire column

Visual feedback shows which mode is active.

### 18. Clipboard Operations

Press `Ctrl+C` to copy:
- Copies current cell value to system clipboard
- Works on macOS (`pbcopy`) and Linux (`xclip`)
- Shows confirmation notification

## Data Type Support

- **Int64, Int32, UInt32**: Integer values
- **Float64, Float32**: Decimal numbers (shown with 4 significant figures)
- **String**: Text data
- **Boolean**: True/False values
- **Date**: ISO date format (YYYY-MM-DD)
- **Datetime**: ISO datetime format
- **Null values**: Displayed as `-`

## Examples

### Single File Examples

```bash
# View Pokemon dataset
dataframe-textual pokemon.csv

# View Titanic dataset with analysis
dataframe-textual titanic.csv

# Filter and view specific columns
cut -d',' -f1,2,3 pokemon.csv | dataframe-textual

# View with grep filter (then use | search in viewer)
grep "Fire" pokemon.csv | dataframe-textual

# Chain with other commands
cat data.csv | sort -t',' -k2 | dataframe-textual
```

### Multi-File/Tab Examples

```bash
# Open multiple sheets as tabs in a single Excel
dataframe-textual sales.csv

# Open multiple files
dataframe-textual pokemon.csv titanic.csv

# Start with one file, open others using Ctrl+O
dataframe-textual initial_data.csv
# Then press Ctrl+O to open more files interactively
```


## Performance

- **Lazy loading**: Only loads visible rows + 10 rows ahead
- **Efficient sorting**: Uses Polars' optimized sort algorithms
- **Smooth scrolling**: No lag when paging through large files
- **Memory efficient**: Handles datasets larger than RAM


## Dependencies

- **polars**: Fast DataFrame library for data processing
- **textual**: Terminal UI framework
- **fastexcel**: Read Excel files
- **xlsxwriter**: Write Excel files

## Architecture Overview

### Single-Table Design

The core of the application is built around the `DataFrameTable` widget:

- **Self-contained**: Each table instance maintains its own complete state (13 independent variables)
- **Fully autonomous**: All operations (editing, sorting, filtering, searching) are handled within the table
- **Event-driven**: Each table owns and handles its keyboard events
- **Backward compatible**: Works identically in single-file mode

### Multi-Table Design

The `DataFrameApp` coordinates multiple independent `DataFrameTable` instances:

- **Tab-based interface**: Uses Textual's `TabbedContent` for tab management
- **Independent state**: Each tab has completely separate state (sort order, selections, history)
- **Seamless switching**: Switch between files without losing context or state
- **File management**: Open/close files dynamically without restarting the application

### State Isolation

Each `DataFrameTable` instance owns:
- DataFrame (`self.df`)
- Sorted columns (`self.sorted_columns`)
- Selected rows (`self.selected_rows`)
- Edit history (`self.histories`)
- Cursor state (position, type)
- Search/filter state
- And 8 more internal state variables

This ensures perfect isolation between tabs with zero cross-contamination.

## Requirements

- Python 3.11+
- POSIX-compatible terminal (macOS, Linux, WSL)
- Terminal supporting ANSI escape sequences and mouse events

## Acknowledgments

- Inspired by [VisiData](https://visidata.org/)
- Built with [Textual](https://textual.textualize.io/), [Polars](https://www.pola.rs/), and [Rich](https://rich.readthedocs.io/)
- All code created through iterative development
