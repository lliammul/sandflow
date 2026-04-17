---
name: office-artifacts
description: Generate CSV, DOCX, XLSX, and PPTX workflow artifacts with the correct Python libraries and file paths inside the sandbox.
---

Use this skill whenever a workflow asks you to generate one of these artifact formats:

- `csv`
- `docx`
- `xlsx`
- `pptx`

## Purpose

This skill exists to tell you which libraries and file-writing patterns are available in the sandbox.

It does not define the content or structure of the document for you.

You should decide the document layout, wording, tables, slides, and overall presentation based on the workflow task itself.

## Runtime rules

When generating an artifact:

1. Read the workflow definition and the declared artifact output `format`.
2. Write the real artifact file under `outputs/artifacts/`.
3. Make sure the file is genuinely that format. Do not fake Office files with plain text.
4. Write `outputs/result.json` only after the artifact exists.
5. Reference artifact paths in `outputs/result.json` using relative workspace paths such as `outputs/artifacts/report.docx`.

Do not write placeholder or fallback text into an Office file path.

## Available libraries

### DOCX

Use `python-docx`.

Example:

```python
from docx import Document

doc = Document()
doc.add_heading("Quarterly Business Review", 0)
doc.add_paragraph("Executive summary goes here.")
doc.save("outputs/artifacts/report.docx")
```

Use this when you want the agent to author the document structure directly in code.

### PPTX

Use `python-pptx`.

Example:

```python
from pptx import Presentation

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[0])
slide.shapes.title.text = "Quarterly Business Review"
slide.placeholders[1].text = "Prepared by the workflow"
prs.save("outputs/artifacts/slides.pptx")
```

### XLSX

Use `openpyxl`.

Example:

```python
from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.title = "Findings"
ws.append(["Severity", "Title", "Recommendation"])
ws.append(["High", "Missing SLA", "Add service window commitments"])
wb.save("outputs/artifacts/findings.xlsx")
```

### CSV

Use the Python standard library `csv` module unless there is a strong reason not to.

Example:

```python
import csv

with open("outputs/artifacts/export.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["severity", "title", "recommendation"])
    writer.writerow(["high", "Missing SLA", "Add service window commitments"])
```

## Optional helper scripts

Helper scripts are available under `.agents/office-artifacts/scripts/`.

You may use them if they save time, but they are optional. They are not the default required workflow.

Available helpers:

- `create_csv.py`
- `create_docx.py`
- `create_xlsx.py`
- `create_pptx.py`

Use them when a small generated spec is the fastest route. Otherwise, write the Python code yourself with the libraries above.

## Recommended approach

- First decide what the artifact should contain.
- Then write Python that generates that artifact with the correct library.
- Keep the document structure appropriate to the task instead of forcing a generic template.
- Verify the file exists under `outputs/artifacts/`.
- Then write `outputs/result.json`.
