"""Keep user-entered text literal when an exported CSV is opened in a spreadsheet."""

import csv
import io


def escape_formula(value):
    if isinstance(value, str) and (
        value.lstrip().startswith(("=", "+", "-", "@"))
        or value.startswith(("\t", "\r", "\n"))
    ):
        return "'" + value
    return value


def safe_csv(dataset):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    for row in [dataset.headers or [], *dataset]:
        writer.writerow([escape_formula(value) for value in row])
    return output.getvalue()


def safe_delimited_export(content, delimiter):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter)
    for row in csv.reader(io.StringIO(content), delimiter=delimiter):
        writer.writerow([escape_formula(value) for value in row])
    return output.getvalue()
