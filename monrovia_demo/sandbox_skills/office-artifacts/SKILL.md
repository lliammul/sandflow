---
name: office-artifacts
description: Generate CSV, DOCX, XLSX, and PPTX workflow artifacts using the provided helper scripts instead of hand-building file formats.
---

Use this skill whenever a workflow asks you to generate one of these artifact formats:

- `csv`
- `docx`
- `xlsx`
- `pptx`

## How to use this skill

1. Read the workflow definition and the declared artifact output `format`.
2. Create a small JSON spec file in the workspace, usually under `outputs/tmp/`.
3. Run the matching helper script from `scripts/`.
4. Write the real artifact file under `outputs/artifacts/`.
5. Reference that file from `outputs/result.json`.

Do not try to hand-author Office file formats directly. Prefer these scripts.

## Script guide

### CSV

```bash
python3 .agents/office-artifacts/scripts/create_csv.py \
  --spec outputs/tmp/export.json \
  --output outputs/artifacts/export.csv
```

Expected spec:

```json
{
  "headers": ["severity", "title", "recommendation"],
  "rows": [
    ["high", "Missing SLA", "Add service window commitments"]
  ]
}
```

You may also pass rows as objects:

```json
{
  "rows": [
    {"severity": "high", "title": "Missing SLA", "recommendation": "Add service window commitments"}
  ]
}
```

### DOCX

```bash
python3 .agents/office-artifacts/scripts/create_docx.py \
  --spec outputs/tmp/report.json \
  --output outputs/artifacts/report.docx
```

Expected spec:

```json
{
  "title": "Review Report",
  "subtitle": "Vendor addendum review",
  "paragraphs": ["Short narrative summary."],
  "sections": [
    {
      "heading": "Findings",
      "bullets": ["High risk term", "Missing schedule"]
    }
  ],
  "tables": [
    {
      "title": "Findings Table",
      "headers": ["Severity", "Title", "Recommendation"],
      "rows": [
        ["High", "Termination clause", "Confirm notice period"]
      ]
    }
  ]
}
```

### XLSX

```bash
python3 .agents/office-artifacts/scripts/create_xlsx.py \
  --spec outputs/tmp/workbook.json \
  --output outputs/artifacts/findings.xlsx
```

Expected spec:

```json
{
  "sheets": [
    {
      "name": "Findings",
      "headers": ["Severity", "Title", "Recommendation"],
      "rows": [
        ["High", "Termination clause", "Confirm notice period"]
      ]
    }
  ]
}
```

### PPTX

```bash
python3 .agents/office-artifacts/scripts/create_pptx.py \
  --spec outputs/tmp/deck.json \
  --output outputs/artifacts/summary-deck.pptx
```

Expected spec:

```json
{
  "title": "Review Summary",
  "subtitle": "Contract workflow run",
  "slides": [
    {
      "title": "Top Findings",
      "bullets": ["High risk termination language", "Missing attached schedule"]
    }
  ]
}
```

## Recommended workflow

- Build the structured `fields` output first.
- Convert those results into a compact JSON spec for the artifact.
- Use the helper script.
- If the helper script fails, stop and surface the error. Do not write placeholder text into an Office file path.
- Verify the file exists under `outputs/artifacts/`.
- Then reference it in `outputs/result.json`.
