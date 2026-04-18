from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from .models import (
    ArtifactOutputDefinition,
    InputFieldDefinition,
    OutputFieldDefinition,
    WorkflowDefinition,
    WorkflowRunRecord,
)

ROOT_DIR = Path(os.getenv("SANDFLOW_APP_STORAGE", ".application"))
WORKFLOWS_DIR = ROOT_DIR / "workflows"
RUNS_DIR = ROOT_DIR / "runs"
UPLOADS_DIR = ROOT_DIR / "uploads"
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
STAGING_UPLOADS_DIR = UPLOADS_DIR / "_staging"
LEGACY_ROOT_DIR = Path(".context")
LEGACY_WORKFLOWS_DIR = LEGACY_ROOT_DIR / "workflows"
LEGACY_RUNS_DIR = LEGACY_ROOT_DIR / "runs"
LEGACY_UPLOADS_DIR = LEGACY_ROOT_DIR / "uploads"
LEGACY_ARTIFACTS_DIR = LEGACY_ROOT_DIR / "artifacts"


def ensure_storage() -> None:
    for path in (ROOT_DIR, WORKFLOWS_DIR, RUNS_DIR, UPLOADS_DIR, ARTIFACTS_DIR, STAGING_UPLOADS_DIR):
        path.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_app_storage()
    _seed_starter_workflow_if_needed()


def workflow_file_path(workflow_id: str) -> Path:
    return WORKFLOWS_DIR / f"{workflow_id}.json"


def run_file_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def run_upload_dir(run_id: str) -> Path:
    path = UPLOADS_DIR / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_artifact_dir(run_id: str) -> Path:
    path = ARTIFACTS_DIR / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def staging_upload_dir() -> Path:
    STAGING_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return STAGING_UPLOADS_DIR


def safe_filename(filename: str) -> str:
    basename = Path(filename).name or "upload.bin"
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", basename).strip("-")
    return sanitized or "upload.bin"


def save_run_record(record: WorkflowRunRecord) -> None:
    ensure_storage()
    run_file_path(record.id).write_text(record.model_dump_json(indent=2), encoding="utf-8")


def load_run_records(limit: int | None = None) -> list[WorkflowRunRecord]:
    ensure_storage()
    records: list[WorkflowRunRecord] = []
    for path in sorted(RUNS_DIR.glob("*.json")):
        try:
            records.append(WorkflowRunRecord.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:
            continue

    records.sort(key=lambda record: record.started_at, reverse=True)
    if limit is not None:
        return records[:limit]
    return records


def load_run_record(run_id: str) -> WorkflowRunRecord | None:
    ensure_storage()
    path = run_file_path(run_id)
    if not path.exists():
        return None
    return WorkflowRunRecord.model_validate_json(path.read_text(encoding="utf-8"))


def delete_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _seed_starter_workflow_if_needed() -> None:
    if any(WORKFLOWS_DIR.glob("*.json")):
        return

    starter = WorkflowDefinition(
        id="review-document",
        name="Review Document",
        description="Review an uploaded document and produce structured findings plus an optional file artifact.",
        is_active=True,
        prompt=(
            "Review the provided document and produce a concise executive summary. Return a JSON "
            "array of findings where each item includes severity, title, evidence, and recommendation. "
            "If useful, you may also generate a supporting report file."
        ),
        input_fields=[
            InputFieldDefinition(
                id="document",
                label="Document",
                type="file",
                required=True,
                help_text="Upload a PDF, DOCX, TXT, or Markdown file.",
            ),
            InputFieldDefinition(
                id="review_focus",
                label="Review Focus",
                type="long_text",
                required=False,
                help_text="Optional instructions or concerns to emphasize.",
            ),
        ],
        output_fields=[
            OutputFieldDefinition(
                id="summary",
                label="Summary",
                type="markdown",
                required=True,
                help_text="A short executive summary.",
            ),
            OutputFieldDefinition(
                id="findings",
                label="Findings",
                type="json",
                required=True,
                help_text="Structured findings with severity, evidence, and recommendations.",
            ),
        ],
        artifact_outputs=[
            ArtifactOutputDefinition(
                id="report_file",
                label="Report File",
                format="docx",
                required=False,
                help_text="Optional generated report or export.",
            )
        ],
    )
    workflow_file_path(starter.id).write_text(
        starter.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _migrate_legacy_app_storage() -> None:
    if LEGACY_WORKFLOWS_DIR.exists():
        for path in sorted(LEGACY_WORKFLOWS_DIR.glob("*.json")):
            destination = workflow_file_path(path.stem)
            if destination.exists():
                path.unlink(missing_ok=True)
                continue
            shutil.move(str(path), str(destination))
        _remove_empty_dir(LEGACY_WORKFLOWS_DIR)

    for path in (LEGACY_RUNS_DIR, LEGACY_UPLOADS_DIR, LEGACY_ARTIFACTS_DIR):
        delete_tree(path)


def _remove_empty_dir(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        return
