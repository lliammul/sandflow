# Sandflow Desktop Repo Guide

## Layout

- `web/`: Next.js 16 desktop UI. Editable by Codex.
- `python-sidecar/`: FastAPI backend, workflow runner, Docker sandbox integration, storage, and tests. Editable by Codex **except** `python-sidecar/src/sandflow_sidecar/contract.py`, which defines the frozen web↔sidecar API and must never be edited by Codex.
- `src-tauri/`: Rust shell, desktop runtime orchestration, git/customise commands, and packaging. Locked from Codex edits — the Tauri binary is signed and bundled; edits require an app reinstall.
- `codex-runner/`: Node subprocess that embeds `@openai/codex-sdk` to drive preview runs. Locked from Codex edits.
- `sandflow/`: legacy Reflex reference implementation. Read-only.

## Locked Paths

Codex must never write to these files or directories. The customise apply pipeline will reject the run if any are touched:

- `src-tauri/**`
- `codex-runner/**`
- `python-sidecar/src/sandflow_sidecar/contract.py`
- `.git/**`
- `.env`, `.env.*`
- any file matching `*secret*`
- any file matching `*.key`
- any file matching `*.pem`
- `previews/**`, `.context/**`, `.conductor/**`

## Dependency Rules

- If `python-sidecar/pyproject.toml` changes, the host installs with `uv sync --project python-sidecar` during apply.
- If `web/package.json` changes, the host installs with `pnpm install --dir web` during apply.
- Do not run dependency installers from inside a customise run. The host orchestrates this after apply.

## Runtime Rules

- The Python sidecar binds to `127.0.0.1` only.
- `web/**` changes are picked up by Next.js HMR after apply; no restart needed.
- `python-sidecar/**` changes trigger a hot sidecar swap (new process on a new port, old drained for up to 5 minutes).
- `python-sidecar/src/sandflow_sidecar/docker_sandbox/Dockerfile` or `requirements.txt` changes cause the next workflow run to rebuild the sandbox image (hash-based cache key).

## Customise Rules

- Customise runs execute in a **full clone** under `previews/<run_id>/`, never directly in the live runtime repo.
- Only files outside the Locked Paths list are editable.
- Only one preview is active at a time.
- The preview workspace runs its own sidecar and its own `next dev` on separate ports; changes are proven runnable in a second window before apply.
- Apply is atomic: failed readiness check after hot-swap rolls the live repo back to the pre-apply commit.
