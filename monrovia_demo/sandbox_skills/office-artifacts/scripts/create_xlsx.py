from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpyxl import Workbook


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheets = spec.get("sheets", [])
    if not sheets:
        sheets = [{"name": "Sheet1", "headers": [], "rows": []}]

    first = True
    for sheet_spec in sheets:
        if first:
            sheet = workbook.active
            first = False
        else:
            sheet = workbook.create_sheet()
        sheet.title = str(sheet_spec.get("name", "Sheet"))[:31]

        headers = sheet_spec.get("headers", [])
        rows = sheet_spec.get("rows", [])
        if headers:
            sheet.append(headers)

        if rows and isinstance(rows[0], dict):
            header_row = headers or list(rows[0].keys())
            if not headers:
                sheet.append(header_row)
            for row in rows:
                sheet.append([row.get(key, "") for key in header_row])
        else:
            for row in rows:
                sheet.append(row)

    workbook.save(str(output_path))


if __name__ == "__main__":
    main()
