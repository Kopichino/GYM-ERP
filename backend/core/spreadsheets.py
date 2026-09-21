"""Writing untrusted text into spreadsheets.

Member names are member-controlled and enquiry names arrive from the public
website form, so any of them can be written to look like a formula. openpyxl
stores a string beginning with "=" as a live formula, and an owner opening the
export runs it -- a hyperlink to a phishing page, or worse.

Text that would be read as a formula is written with a leading apostrophe,
which spreadsheet programs treat as "this is text". Numbers such as phone
numbers ("+91...") and negative amounts are left as they are.
"""


def _looks_like_formula(value):
    if not value:
        return False
    first = value[0]
    if first in ("=", "@", "\t", "\r"):
        return True
    if first in ("+", "-") and len(value) > 1:
        second = value[1]
        return not (second.isdigit() or second in " .")
    return False


def neutralise_formulas(sheet):
    """Make every formula-shaped text cell in `sheet` plain text."""
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and _looks_like_formula(cell.value):
                cell.value = "'" + cell.value
