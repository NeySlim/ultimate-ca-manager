"""Cells of a CSV file a spreadsheet opens: a text it would run as a formula is neutralised."""

# OWASP CSV Injection: a cell starting with one of these is read as a formula
FORMULA_STARTS = ('=', '+', '-', '@', '\t', '\r', '\n', '\uff1d', '\uff0b', '\uff0d', '\uff20')


def csv_cell(value):
    """*value*, a text that starts like a formula prefixed with a quote; any other value as it is."""
    if isinstance(value, str) and value.startswith(FORMULA_STARTS):
        return "'" + value
    return value


def csv_row(values):
    return [csv_cell(v) for v in values]


def csv_dict(row):
    return {k: csv_cell(v) for k, v in row.items()}
