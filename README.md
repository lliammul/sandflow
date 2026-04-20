# Sandflow Desktop

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

Install the workspace and sidecar dependencies:

```bash
pnpm install
uv sync --project python-sidecar
```

The repo is a pnpm workspace; the root install covers `web/` and
`codex-runner/`. The sidecar uses its own uv project under
`python-sidecar/`.

### Browser-only development

Run the sidecar and web app separately when developing the frontend in a
browser:

```bash
pnpm dev:sidecar
NEXT_PUBLIC_SIDECAR_BASE_URL=http://127.0.0.1:8000 pnpm dev:web
```

The sidecar binds to `127.0.0.1` and defaults to port `8000`. Outside the
Tauri runtime, the frontend needs `NEXT_PUBLIC_SIDECAR_BASE_URL` so it can find
the sidecar.

### Desktop development

Run the desktop shell with:

```bash
pnpm tauri:dev
```

Tauri starts the Next.js dev server on port `3100`, bootstraps a writable
runtime repo under app data, installs runtime dependencies there, and starts the
sidecar on an available local port after setup.

The app-data runtime repo is reused between launches. To reseed it from the
current workspace before launching Tauri, run:

```bash
pnpm tauri:dev -- --reset-state
```

## Sidecar API

The Python sidecar exposes:

- `GET /health`
- `GET /ready`
- `GET /runs/active`
- `POST /runs/pause`
- `POST /runs/resume`
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
- `uv`, `pnpm`, `git`, and `rsync` must be available for desktop bootstrap and
  customise previews.
- Workflow execution requires `OPENAI_API_KEY` and `OPENAI_SANDBOX_MODEL`.
- `OPENAI_API_BASE` is optional and can point the sidecar at a compatible API
  endpoint.
- The desktop shell bootstraps a writable runtime repo in app data and stores
  runtime configuration, including the OpenAI API key, in the local runtime
  config file for MVP convenience.

## Customise Flow

Sandflow ships an in-app customise pipeline: describe a change, a preview clone
of the runtime is spun up with its own sidecar and Next.js dev server, Codex
makes the change, and you approve or discard.

Build the Codex runner bundle before using the Customise tab:

```bash
pnpm --dir codex-runner build
```

Then start the desktop app (`pnpm tauri:dev`), open the **Customise** tab, and
follow the prompt, review, and approve flow. Locked paths are listed in
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
