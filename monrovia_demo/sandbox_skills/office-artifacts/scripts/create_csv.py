from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = spec.get("rows", [])
    headers = spec.get("headers")

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        if rows and isinstance(rows[0], dict):
            inferred_headers = headers or list(rows[0].keys())
            writer = csv.DictWriter(handle, fieldnames=inferred_headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in inferred_headers})
            return

        writer = csv.writer(handle)
        if headers:
            writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    main()
