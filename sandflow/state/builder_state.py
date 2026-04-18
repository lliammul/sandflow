from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

import reflex as rx
from pydantic import ValidationError

from ..models import (
    ArtifactOutputDefinition,
    InputFieldDefinition,
    OutputFieldDefinition,
    WorkflowDefinition,
)
from ..workflow_registry import (
    delete_workflow,
    duplicate_workflow,
    get_workflow,
    list_workflow_entries,
    load_workflow_raw_error,
    save_workflow,
)


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "workflow"


def row_key(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


class BuilderState(rx.State):
    workflow_entries: list[dict[str, Any]] = []
    selected_registry_id: str = ""
    original_workflow_id: str = ""
    editor_error: str = ""
    editor_notice: str = ""
    validation_errors: list[str] = []
    invalid_entry_error: str = ""

    workflow_name: str = ""
    workflow_id: str = ""
    workflow_description: str = ""
    workflow_prompt: str = ""
    workflow_active: bool = True

    input_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    artifact_rows: list[dict[str, Any]] = []

    collapsed_row_keys: list[str] = []
    prompt_expanded: bool = True
    preview_expanded: bool = True

    snapshot: dict[str, Any] = {}

    @rx.var
    def has_selection(self) -> bool:
        return bool(self.selected_registry_id)

    @rx.var
    def has_invalid_entry(self) -> bool:
        return bool(self.invalid_entry_error)

    @rx.var
    def is_dirty(self) -> bool:
        return self._current_snapshot() != self.snapshot

    @rx.var
    def prompt_preview(self) -> str:
        text = self.workflow_prompt.strip()
        if not text:
            return "Empty prompt"
        first_line = text.splitlines()[0]
        return first_line[:120] + ("…" if len(first_line) > 120 else "")

    @rx.var
    def prompt_char_count(self) -> str:
        return f"{len(self.workflow_prompt)} chars"

    @rx.var
    def has_global_errors(self) -> bool:
        return bool(self.validation_errors)

    @rx.var
    def schema_preview(self) -> str:
        return json.dumps(
            {
                "input_fields": [
                    {
                        "id": row.get("field_id", ""),
                        "label": row.get("label", ""),
                        "type": row.get("type", ""),
                        "required": bool(row.get("required")),
                    }
                    for row in self.input_rows
                ],
                "output_fields": [
                    {
                        "id": row.get("field_id", ""),
                        "label": row.get("label", ""),
                        "type": row.get("type", ""),
                        "required": bool(row.get("required")),
                    }
                    for row in self.output_rows
                ],
                "artifact_outputs": [
                    {
                        "id": row.get("field_id", ""),
                        "label": row.get("label", ""),
                        "format": row.get("format", ""),
                        "required": bool(row.get("required")),
                    }
                    for row in self.artifact_rows
                ],
            },
            indent=2,
        )

    @rx.var
    def contract_preview(self) -> str:
        return json.dumps(
            {
                "summary": "Short run summary",
                "fields": {row.get("field_id", ""): row.get("type", "") for row in self.output_rows},
                "artifacts": {
                    row.get("field_id", ""): row.get("format", "")
                    for row in self.artifact_rows
                },
            },
            indent=2,
        )

    def load_page(self):
        self._refresh_entries()
        if self.selected_registry_id:
            self.select_workflow(self.selected_registry_id)
            return
        if self.workflow_entries:
            self.select_workflow(self.workflow_entries[0]["id"])
            return
        self.new_workflow()

    def select_workflow(self, workflow_id: str):
        self.editor_error = ""
        self.editor_notice = ""
        self.validation_errors = []
        self.selected_registry_id = workflow_id
        invalid_error = load_workflow_raw_error(workflow_id)
        if invalid_error:
            self.invalid_entry_error = invalid_error
            self.original_workflow_id = workflow_id
            self.workflow_name = workflow_id
            self.workflow_id = workflow_id
            self.workflow_description = ""
            self.workflow_prompt = ""
            self.workflow_active = False
            self.input_rows = []
            self.output_rows = []
            self.artifact_rows = []
            self.snapshot = self._current_snapshot()
            return

        workflow = get_workflow(workflow_id)
        self.invalid_entry_error = ""
        self.original_workflow_id = workflow.id
        self.workflow_name = workflow.name
        self.workflow_id = workflow.id
        self.workflow_description = workflow.description
        self.workflow_prompt = workflow.prompt
        self.workflow_active = workflow.is_active
        self.input_rows = [
            {
                "row_key": row_key("in"),
                "field_id": field.id,
                "label": field.label,
                "type": field.type,
                "required": field.required,
                "help_text": field.help_text,
                "errors": [],
            }
            for field in workflow.input_fields
        ]
        self.output_rows = [
            {
                "row_key": row_key("out"),
                "field_id": field.id,
                "label": field.label,
                "type": field.type,
                "required": field.required,
                "help_text": field.help_text,
                "errors": [],
            }
            for field in workflow.output_fields
        ]
        self.artifact_rows = [
            {
                "row_key": row_key("artifact"),
                "field_id": artifact.id,
                "label": artifact.label,
                "format": artifact.format,
                "required": artifact.required,
                "help_text": artifact.help_text,
                "errors": [],
            }
            for artifact in workflow.artifact_outputs
        ]
        self.snapshot = self._current_snapshot()

    def new_workflow(self):
        self.selected_registry_id = ""
        self.original_workflow_id = ""
        self.invalid_entry_error = ""
        self.editor_error = ""
        self.editor_notice = "New draft ready. Save to publish it instantly."
        self.validation_errors = []
        self.workflow_name = "New Workflow"
        self.workflow_id = "workflow"
        self.workflow_description = ""
        self.workflow_prompt = "Describe what this workflow should do."
        self.workflow_active = True
        self.input_rows = [
            {
                "row_key": row_key("in"),
                "field_id": "input_1",
                "label": "Input",
                "type": "short_text",
                "required": True,
                "help_text": "",
                "errors": [],
            }
        ]
        self.output_rows = [
            {
                "row_key": row_key("out"),
                "field_id": "output_1",
                "label": "Result",
                "type": "text",
                "required": True,
                "help_text": "",
                "errors": [],
            }
        ]
        self.artifact_rows = []
        self.snapshot = self._current_snapshot()

    def duplicate_selected_workflow(self):
        if self.invalid_entry_error or not self.original_workflow_id:
            self.editor_error = "Only valid workflows can be duplicated."
            return
        duplicated = duplicate_workflow(self.original_workflow_id)
        self._refresh_entries()
        self.select_workflow(duplicated.id)
        self.editor_notice = "Workflow duplicated."

    def delete_selected_workflow(self):
        if not self.selected_registry_id:
            return
        delete_workflow(self.selected_registry_id)
        self._refresh_entries()
        self.editor_notice = "Workflow deleted."
        if self.workflow_entries:
            self.select_workflow(self.workflow_entries[0]["id"])
        else:
            self.new_workflow()

    def save_current_workflow(self):
        self.editor_error = ""
        self.editor_notice = ""
        self.validation_errors = []
        if self._validate_rows():
            self.validation_errors = ["Fix per-field errors before saving."]
            return
        try:
            workflow = self._build_workflow()
            saved = save_workflow(workflow, previous_id=self.original_workflow_id or None)
        except ValidationError as exc:
            self.validation_errors = [error["msg"] for error in exc.errors()]
            return
        except ValueError as exc:
            self.validation_errors = [str(exc)]
            return

        self._refresh_entries()
        self.select_workflow(saved.id)
        self.editor_notice = "Workflow saved and published."

    def infer_slug_from_name(self, value: str):
        self.workflow_name = value
        if not self.original_workflow_id or self.workflow_id.startswith("workflow-") or self.workflow_id == slugify(self.workflow_name):
            self.workflow_id = slugify(value)

    def set_workflow_id(self, value: str):
        self.workflow_id = slugify(value)

    def set_workflow_description(self, value: str):
        self.workflow_description = value

    def set_workflow_prompt(self, value: str):
        self.workflow_prompt = value

    def toggle_active(self):
        self.workflow_active = not self.workflow_active

    def add_input_row(self):
        self.input_rows = [
            *self.input_rows,
            {
                "row_key": row_key("in"),
                "field_id": f"input_{len(self.input_rows) + 1}",
                "label": "New Input",
                "type": "short_text",
                "required": False,
                "help_text": "",
                "errors": [],
            },
        ]

    def add_output_row(self):
        self.output_rows = [
            *self.output_rows,
            {
                "row_key": row_key("out"),
                "field_id": f"output_{len(self.output_rows) + 1}",
                "label": "New Output",
                "type": "text",
                "required": False,
                "help_text": "",
                "errors": [],
            },
        ]

    def add_artifact_row(self):
        self.artifact_rows = [
            *self.artifact_rows,
            {
                "row_key": row_key("artifact"),
                "field_id": f"artifact_{len(self.artifact_rows) + 1}",
                "label": "New Artifact",
                "format": "csv",
                "required": False,
                "help_text": "",
                "errors": [],
            },
        ]

    def remove_input_row(self, row_id: str):
        self.input_rows = [row for row in self.input_rows if row["row_key"] != row_id]

    def remove_output_row(self, row_id: str):
        self.output_rows = [row for row in self.output_rows if row["row_key"] != row_id]

    def remove_artifact_row(self, row_id: str):
        self.artifact_rows = [row for row in self.artifact_rows if row["row_key"] != row_id]

    def toggle_input_required(self, row_id: str):
        target = next((row for row in self.input_rows if row["row_key"] == row_id), None)
        if target is None:
            return
        self.update_input_row(row_id, "required", not bool(target["required"]))

    def toggle_output_required(self, row_id: str):
        target = next((row for row in self.output_rows if row["row_key"] == row_id), None)
        if target is None:
            return
        self.update_output_row(row_id, "required", not bool(target["required"]))

    def toggle_artifact_required(self, row_id: str):
        target = next((row for row in self.artifact_rows if row["row_key"] == row_id), None)
        if target is None:
            return
        self.update_artifact_row(row_id, "required", not bool(target["required"]))

    def update_input_row(self, row_id: str, field: str, value: Any):
        self.input_rows = self._update_row_collection(self.input_rows, row_id, field, value)

    def update_output_row(self, row_id: str, field: str, value: Any):
        self.output_rows = self._update_row_collection(self.output_rows, row_id, field, value)

    def update_artifact_row(self, row_id: str, field: str, value: Any):
        self.artifact_rows = self._update_row_collection(self.artifact_rows, row_id, field, value)

    def toggle_row_expanded(self, row_id: str):
        if row_id in self.collapsed_row_keys:
            self.collapsed_row_keys = [key for key in self.collapsed_row_keys if key != row_id]
        else:
            self.collapsed_row_keys = [*self.collapsed_row_keys, row_id]

    def toggle_prompt_expanded(self):
        self.prompt_expanded = not self.prompt_expanded

    def toggle_preview_expanded(self):
        self.preview_expanded = not self.preview_expanded

    def _current_snapshot(self) -> dict[str, Any]:
        return {
            "name": self.workflow_name,
            "id": self.workflow_id,
            "description": self.workflow_description,
            "prompt": self.workflow_prompt,
            "active": self.workflow_active,
            "inputs": [
                {k: row.get(k) for k in ("field_id", "label", "type", "required", "help_text")}
                for row in self.input_rows
            ],
            "outputs": [
                {k: row.get(k) for k in ("field_id", "label", "type", "required", "help_text")}
                for row in self.output_rows
            ],
            "artifacts": [
                {k: row.get(k) for k in ("field_id", "label", "format", "required", "help_text")}
                for row in self.artifact_rows
            ],
        }

    def _validate_rows(self) -> bool:
        seen_ids: dict[str, str] = {}
        any_errors = False

        def annotate(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
            nonlocal any_errors
            updated: list[dict[str, Any]] = []
            for row in rows:
                field_id = str(row.get("field_id", "")).strip()
                row_errors: list[str] = []
                if not field_id:
                    row_errors.append("Id is required.")
                if not str(row.get("label", "")).strip():
                    row_errors.append("Label is required.")
                if field_id:
                    if field_id in seen_ids:
                        row_errors.append(f"Id `{field_id}` duplicates a {seen_ids[field_id]} field.")
                    else:
                        seen_ids[field_id] = kind
                if row_errors:
                    any_errors = True
                updated.append({**row, "errors": row_errors})
            return updated

        self.input_rows = annotate(self.input_rows, "input")
        self.output_rows = annotate(self.output_rows, "output")
        self.artifact_rows = annotate(self.artifact_rows, "artifact")
        return any_errors

    def _refresh_entries(self):
        self.workflow_entries = [entry.model_dump() for entry in list_workflow_entries(include_inactive=True)]

    def _build_workflow(self) -> WorkflowDefinition:
        return WorkflowDefinition(
            id=slugify(self.workflow_id),
            name=self.workflow_name.strip(),
            description=self.workflow_description.strip(),
            is_active=self.workflow_active,
            prompt=self.workflow_prompt.strip(),
            input_fields=[
                InputFieldDefinition(
                    id=str(row["field_id"]).strip(),
                    label=str(row["label"]).strip(),
                    type=str(row["type"]),
                    required=bool(row["required"]),
                    help_text=str(row["help_text"]).strip(),
                )
                for row in self.input_rows
            ],
            output_fields=[
                OutputFieldDefinition(
                    id=str(row["field_id"]).strip(),
                    label=str(row["label"]).strip(),
                    type=str(row["type"]),
                    required=bool(row["required"]),
                    help_text=str(row["help_text"]).strip(),
                )
                for row in self.output_rows
            ],
            artifact_outputs=[
                ArtifactOutputDefinition(
                    id=str(row["field_id"]).strip(),
                    label=str(row["label"]).strip(),
                    format=str(row["format"]),
                    required=bool(row["required"]),
                    help_text=str(row["help_text"]).strip(),
                )
                for row in self.artifact_rows
            ],
        )

    def _update_row_collection(
        self,
        rows: list[dict[str, Any]],
        row_id: str,
        field: str,
        value: Any,
    ) -> list[dict[str, Any]]:
        updated_rows: list[dict[str, Any]] = []
        for row in rows:
            if row["row_key"] == row_id:
                next_row = dict(row)
                if field == "field_id":
                    next_row[field] = str(value).strip().lower().replace(" ", "_")
                else:
                    next_row[field] = value
                updated_rows.append(next_row)
            else:
                updated_rows.append(row)
        return updated_rows
