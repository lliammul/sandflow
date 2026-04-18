# Sandflow Desktop MVP

Sandflow is now structured as a desktop-first app:

- `python-sidecar/`
  - FastAPI sidecar for workflow storage, sandbox execution, SSE events, and artifact downloads
- `web/`
  - Next.js 16 frontend for runtime, builder, setup, and Customise flows
- `src-tauri/`
  - Tauri v2 shell for macOS runtime orchestration, git-backed customisation, and packaging
- `sandflow/`
  - legacy Reflex implementation kept only as a migration reference

## Local Development

Install the web and sidecar dependencies:

```bash
npm install
npm install --prefix web
uv sync --project python-sidecar
```

Run the sidecar and web app separately during development:

```bash
npm run dev:sidecar
npm run dev:web
```

The frontend expects the sidecar at `http://127.0.0.1:8000` unless `NEXT_PUBLIC_SIDECAR_BASE_URL` is set.

## Sidecar API

The Python sidecar exposes:

- `GET /health`
- `GET /workflow-entries`
- `GET /workflows`
- `GET /workflows/:id`
- `PUT /workflows/:id`
- `DELETE /workflows/:id`
- `GET /runs`
- `POST /workflows/:id/run`
- `GET /runs/:id/events`
- `GET /runs/:id`
- `GET /runs/:id/artifacts/:artifact_id`

Workflow runs stream progress and terminal events over SSE.

## Tests

Run the sidecar test suite:

```bash
npm run test:sidecar
```

Build the Next.js frontend:

```bash
npm run build:web
```

## Runtime Requirements

- Docker must be running locally for workflow execution.
- The sidecar requires `OPENAI_API_KEY` and `OPENAI_SANDBOX_MODEL` at runtime.
- The desktop shell bootstraps a writable runtime repo in app-data and stores the OpenAI API key in the macOS Keychain.

## Artifact Generation

The sandbox image ships with:

- `python-docx`
- `python-pptx`
- `openpyxl`
- `pypdf`

The mounted office artifact skill pack lives under `python-sidecar/src/sandflow_sidecar/sandbox_skills/office-artifacts/`.
