# Sandflow Desktop MVP

Sandflow is now structured as a desktop-first app:

- `python-sidecar/`
  - FastAPI sidecar for workflow storage, sandbox execution, SSE events, and artifact downloads
- `web/`
  - Next.js 16 frontend for runtime, builder, setup, and Customise flows
- `src-tauri/`
  - Tauri v2 shell for macOS runtime orchestration, git-backed customisation, and packaging
- `codex-runner/`
  - Node subprocess wrapping the Codex TS SDK; the Rust shell launches it to drive customise preview runs
- `sandflow/`
  - legacy Reflex implementation kept only as a migration reference

## Local Development

Install the web and sidecar dependencies:

```bash
pnpm install
uv sync --project python-sidecar
```

Run the sidecar and web app separately during development:

```bash
pnpm dev:sidecar
pnpm dev:web
```

The frontend expects the sidecar at `http://127.0.0.1:8000` unless `NEXT_PUBLIC_SIDECAR_BASE_URL` is set.

Desktop dev mode uses:

```bash
pnpm tauri:dev
```

That command now reseeds `~/Library/Application Support/com.sandflow.desktop/repo` from the current workspace before launching Tauri, so runtime-side changes always reflect the latest local source without manually deleting the app-data repo first.

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
pnpm test:sidecar
```

Build the Next.js frontend:

```bash
pnpm build:web
```

## Runtime Requirements

- Docker must be running locally for workflow execution.
- The sidecar requires `OPENAI_API_KEY` and `OPENAI_SANDBOX_MODEL` at runtime.
- The desktop shell bootstraps a writable runtime repo in app-data and currently stores the OpenAI API key in the local runtime config file for MVP convenience.

## Customise Flow

Sandflow ships an in-app customise pipeline: describe a change, a preview clone
of the runtime is spun up with its own sidecar and Next.js dev server, Codex
makes the change, and you approve or discard.

Build the Codex runner bundle once before running Tauri:

```bash
pnpm --dir codex-runner install
pnpm --dir codex-runner build
```

Then start the desktop app (`pnpm tauri:dev`), open the **Customise** tab, and
follow the prompt → review → approve flow. Locked paths are listed in
`AGENTS.md`; apply is blocked automatically if the preview touches any of them.

Preview workspaces live at
`~/Library/Application Support/com.sandflow.desktop/runtime/previews/<run_id>/`
and are torn down on approval or discard.

## Artifact Generation

The sandbox image ships with:

- `python-docx`
- `python-pptx`
- `openpyxl`
- `pypdf`

The mounted office artifact skill pack lives under `python-sidecar/src/sandflow_sidecar/sandbox_skills/office-artifacts/`.
