from __future__ import annotations

from pathlib import Path

from .models import (
    WorkflowDefinition,
    WorkflowRegistryEntry,
    workflow_to_registry_entry,
    utc_now_iso,
)
from .storage import ensure_storage, workflow_file_path, WORKFLOWS_DIR


def list_workflow_entries(include_inactive: bool = True) -> list[WorkflowRegistryEntry]:
    ensure_storage()
    entries: list[WorkflowRegistryEntry] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.json")):
        try:
            workflow = WorkflowDefinition.model_validate_json(path.read_text(encoding="utf-8"))
            if include_inactive or workflow.is_active:
                entries.append(workflow_to_registry_entry(workflow))
        except Exception as exc:
            entries.append(
                WorkflowRegistryEntry(
                    id=path.stem,
                    name=path.stem,
                    has_error=True,
                    error_message=str(exc),
                )
            )
    entries.sort(key=lambda entry: (entry.has_error, entry.name.lower()))
    return entries


def list_workflows(include_inactive: bool = True) -> list[WorkflowDefinition]:
    ensure_storage()
    workflows: list[WorkflowDefinition] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.json")):
        try:
            workflow = WorkflowDefinition.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if include_inactive or workflow.is_active:
            workflows.append(workflow)
    workflows.sort(key=lambda workflow: workflow.name.lower())
    return workflows


def get_workflow(workflow_id: str) -> WorkflowDefinition:
    ensure_storage()
    path = workflow_file_path(workflow_id)
    if not path.exists():
        raise FileNotFoundError(f"Workflow `{workflow_id}` does not exist.")
    return WorkflowDefinition.model_validate_json(path.read_text(encoding="utf-8"))


def save_workflow(
    workflow: WorkflowDefinition,
    previous_id: str | None = None,
) -> WorkflowDefinition:
    ensure_storage()
    existing_created_at = workflow.created_at
    if previous_id:
        previous_path = workflow_file_path(previous_id)
        if previous_path.exists():
            try:
                existing_created_at = WorkflowDefinition.model_validate_json(
                    previous_path.read_text(encoding="utf-8")
                ).created_at
            except Exception:
                existing_created_at = workflow.created_at

    destination = workflow_file_path(workflow.id)
    if previous_id and previous_id != workflow.id and destination.exists():
        raise ValueError(f"A workflow with id `{workflow.id}` already exists.")

    updated_workflow = workflow.model_copy(
        update={
            "created_at": existing_created_at,
            "updated_at": utc_now_iso(),
        }
    )
    destination.write_text(updated_workflow.model_dump_json(indent=2), encoding="utf-8")

    if previous_id and previous_id != workflow.id:
        old_path = workflow_file_path(previous_id)
        if old_path.exists():
            old_path.unlink()

    return updated_workflow


def delete_workflow(workflow_id: str) -> None:
    path = workflow_file_path(workflow_id)
    if path.exists():
        path.unlink()


def duplicate_workflow(workflow_id: str) -> WorkflowDefinition:
    original = get_workflow(workflow_id)
    new_id = _next_available_id(original.id)
    duplicate = original.model_copy(
        update={
            "id": new_id,
            "name": f"{original.name} Copy",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        },
        deep=True,
    )
    return save_workflow(duplicate)


def load_workflow_raw_error(workflow_id: str) -> str | None:
    path = workflow_file_path(workflow_id)
    if not path.exists():
        return None
    try:
        WorkflowDefinition.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return str(exc)
    return None


def _next_available_id(base_id: str) -> str:
    candidate = f"{base_id}-copy"
    index = 2
    while workflow_file_path(candidate).exists():
        candidate = f"{base_id}-copy-{index}"
        index += 1
    return candidate
