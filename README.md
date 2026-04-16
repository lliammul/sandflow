# Monrovia Workflow Console

Local Reflex app for building and running sandbox-backed workflows.

## Routes

- `/`
  - user mode
  - shows only active workflows
  - renders workflow-specific inputs and outputs
- `/builder`
  - builder mode
  - creates and edits workflow definitions stored locally in `.application/workflows`

## What it does

- Uses a local JSON registry for workflow definitions
- Supports builder-defined text inputs and file inputs
- Supports builder-defined structured outputs plus generated file artifacts
- Supports tier-2 artifact formats: `csv`, `docx`, `xlsx`, `pptx`, plus `txt`, `md`, `json`, and `html`
- Persists runs under `.application/runs`
- Copies uploaded files under `.application/uploads`
- Copies generated artifacts under `.application/artifacts`
- Optional debug mode persists the full streamed agent trace with each run
- Executes workflows through an OpenAI Unix-local sandbox agent
- Mounts a sandbox skill pack for Office-style artifact generation

## Run locally

```bash
uv sync
uv run reflex run
```

Then open `http://localhost:3000`.

## Required runtime config

Execution is live-only in this version. Builder mode works without credentials, but user runs are disabled until these values are set in `.env`:

```env
OPENAI_API_KEY=...
OPENAI_API_BASE=https://your-endpoint.example.com/v1/
OPENAI_SANDBOX_MODEL=your-model-name
```

If you are using OpenAI directly, `OPENAI_API_BASE` can be omitted.

## Artifact generation

Artifact outputs are declared by the builder in `/builder`. Each artifact has a `format`, and the sandbox runner enforces that the generated file matches that declared format.

Tier-2 formats are handled with helper scripts mounted into the sandbox as a local skill pack:

- `monrovia_demo/sandbox_skills/office-artifacts/SKILL.md`
- `monrovia_demo/sandbox_skills/office-artifacts/scripts/create_csv.py`
- `monrovia_demo/sandbox_skills/office-artifacts/scripts/create_docx.py`
- `monrovia_demo/sandbox_skills/office-artifacts/scripts/create_xlsx.py`
- `monrovia_demo/sandbox_skills/office-artifacts/scripts/create_pptx.py`

Inside the sandbox, the agent is instructed to consult `.agents/office-artifacts/` and use those scripts instead of trying to hand-author Office formats.

That means:

- `csv` artifacts are generated through a structured export helper
- `docx` artifacts are generated with `python-docx`
- `xlsx` artifacts are generated with `openpyxl`
- `pptx` artifacts are generated with `python-pptx`

These libraries are included in the local environment through `uv sync`, so the Unix-local sandbox can use them during workflow runs.

## Storage layout

- `.application/workflows`
  - persisted workflow definitions
- `.application/runs`
  - persisted run records
- `.application/uploads`
  - staged user uploads and per-run input copies
- `.application/artifacts`
  - persisted generated output files

## Notes

- The Reflex app entrypoint is `monrovia_demo/app.py`
- Route components live in `monrovia_demo/pages/`
- State lives in `monrovia_demo/state/`
- The generic sandbox runner lives in `monrovia_demo/workflow_runner.py`
- Workflow definitions live in `.application/workflows/` and are published instantly on save
