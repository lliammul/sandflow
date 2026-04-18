# Sandflow Desktop Repo Guide

## Layout

- `web/`: Next.js 16 desktop UI. Editable by Codex.
- `python-sidecar/`: FastAPI backend, workflow runner, Docker sandbox integration, storage, and tests. Editable by Codex except `python-sidecar/src/sandflow_sidecar/contract.py`.
- `src-tauri/`: Rust shell, desktop runtime orchestration, git/customise commands, and packaging. Locked from Codex edits.
- `sandflow/`: legacy Reflex-era reference implementation kept during migration. Read-only reference for behavior and visual parity.

## Locked Paths

Codex must never edit these files or directories:

- `src-tauri/**`
- `python-sidecar/src/sandflow_sidecar/contract.py`
- `.env`
- any file matching `*secret*`
- any file matching `*.key`
- any file matching `*.pem`
- `.git/**`

## Dependency Rules

- If `python-sidecar/pyproject.toml` changes, the host installs Python dependencies with `uv sync --project python-sidecar`.
- If `web/package.json` changes, the host installs web dependencies with `npm install --prefix web`.
- Do not run dependency installers from inside a Codex customise run. The host is responsible for that orchestration.

## Runtime Rules

- The Python sidecar binds to `127.0.0.1` only.
- Frontend HMR happens automatically when `web/**` changes.
- If `python-sidecar/**` changes, the host restarts the sidecar and waits for `/health`.
- If `python-sidecar/src/sandflow_sidecar/docker_sandbox/Dockerfile` or `requirements.txt` changes, the next workflow run rebuilds the sandbox image using the existing hash-based cache key behavior.

## Customise Rules

- Customise runs execute in a temporary git worktree, never directly in the live repo.
- Only files under `web/**`, `python-sidecar/**`, `AGENTS.md`, and dependency manifests are editable.
- Reject any run that changes a locked path or writes outside the allowlist.
- Commit only after dependency install, restart, and `/health` succeed.
