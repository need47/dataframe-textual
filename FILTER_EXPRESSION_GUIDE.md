# Filter Expression Guide

The DataFrame Viewer supports a powerful filter expression syntax that allows you to filter rows based on complex conditions. When you press `f` to open the filter screen, you can enter expressions following this syntax.

## Column References

### Current Column
- `$_` - The currently selected column (based on cursor position)

Example: `$_ > 50` filters for rows where the current column is greater than 50.

### By Index (1-based)
- `$1` - First column
- `$2` - Second column
- `$3` - Third column
- etc.

Example: `$1 > 50` filters for rows where the first column is greater than 50.

### By Name
- `$age` - Column named "age"
- `$name` - Column named "name"
- `$salary` - Column named "salary"

Example: `$name == 'Alex'` filters for rows where the name column equals "Alex".

## Comparison Operators

- `==` - Equal to
- `!=` - Not equal to
- `<` - Less than
- `>` - Greater than
- `<=` - Less than or equal to
- `>=` - Greater than or equal to

Example: `$age < 30` filters for rows where age is less than 30.

## Logical Operators

- `&&` - AND operator (both conditions must be true)
- `||` - OR operator (at least one condition must be true)

Example: `$1 > 30 && $name == 'Alex'` filters for rows where first column > 30 AND name is 'Alex'.

## Arithmetic Operators

You can use arithmetic in your expressions:

- `+` - Addition
- `-` - Subtraction
- `*` - Multiplication
- `/` - Division
- `%` - Modulo (remainder)

Example: `$salary / 1000 >= 50` filters for rows where salary divided by 1000 is at least 50.

## String Literals

Enclose strings in single or double quotes:

- `'text'` - Single-quoted string
- `"text"` - Double-quoted string

Example: `$status == 'active'` filters for rows where status equals "active".

## Numeric Literals

Integers and floating-point numbers are supported:

- `42` - Integer
- `3.14` - Float

Example: `$price > 99.99` filters for rows where price is greater than 99.99.

## Examples

### Simple Filters
| Expression | Meaning |
|-----------|---------|
| `$_ > 50` | Current column greater than 50 |
| `$1 > 50` | First column greater than 50 |
| `$name == 'Alice'` | Name equals Alice |
| `$salary >= 100000` | Salary at least 100,000 |
| `$status != 'inactive'` | Status is not inactive |

### Complex Filters with AND
| Expression | Meaning |
|-----------|---------|
| `$_ > 50 && $name == 'Alex'` | Current column > 50 AND name is Alex |
| `$1 > 30 && $name == 'Alex'` | First column > 30 AND name is Alex |
| `$age < 30 && $salary > 50000` | Age < 30 AND salary > 50,000 |
| `$1 > 3 && $2 != 'text' && $3 < $4` | Multiple AND conditions |

### Complex Filters with OR
| Expression | Meaning |
|-----------|---------|
| `$_ >= 1000 \|\| $age < 30` | Current column >= 1,000 OR age < 30 |
| `$salary >= 70000 \|\| $age < 30` | Salary >= 70,000 OR age < 30 |
| `$status == 'active' \|\| $status == 'pending'` | Status is active OR pending |

### Mixed Operators
| Expression | Meaning |
|-----------|---------|
| `$age < $salary / 1000` | Age less than salary divided by 1,000 |
| `$1 > 100 && ($name == 'Bob' \|\| $name == 'Alice')` | Complex nested expression |

## Parsing Rules

The parser handles:
1. **Column references** with `$` prefix (`$_` for current column, 1-based index, or name)
2. **Whitespace flexibility** - spaces around operators are optional (`$1>50` or `$1 > 50` both work)
3. **No spaces** - even complex expressions work: `$cola<$colb` parses correctly
4. **String literals** - with or without spaces: `$name=='text'` or `$name == 'text'`
5. **Automatic parenthesization** - the parser adds parentheses around logical operators to ensure correct precedence

## Error Handling

The parser provides helpful error messages:

- `Current column reference ($\_) used without a selected column` - You used `$_` but no column is selected
- `Column index out of range: $5` - You referenced column 5 but the dataframe has fewer columns
- `Column not found: $unknown_col` - The column name doesn't exist in the dataframe
- `Expression is empty` - You entered nothing
- Syntax errors - If the expression can't be parsed

## Tips

1. **Use `$_` for the current column** - quick filtering: `$_ > 100`
2. **Use 1-based indices** for specific columns: `$1 > 100`
3. **Use column names** for clarity: `$salary > 50000`
4. **Mix all methods** in the same expression: `$_ > 30 && $salary == $2`
5. **String matching** is case-sensitive: `'Alex'` ≠ `'alex'`
5. **Column names** are case-sensitive: `$age` ≠ `$Age`
