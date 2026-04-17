from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import reflex as rx
from reflex.app import UploadFile

from ..models import WorkflowProgressEvent, WorkflowRunTerminalEvent
from ..storage import load_run_records, safe_filename, staging_upload_dir
from ..workflow_registry import get_workflow, list_workflows
from ..workflow_runner import execution_enabled, stream_workflow


class UserState(rx.State):
    workflow_cards: list[dict[str, Any]] = []
    selected_workflow_id: str = ""
    selected_workflow_name: str = ""
    selected_workflow_description: str = ""
    active_file_field_id: str = ""
    input_fields: list[dict[str, Any]] = []
    output_fields: list[dict[str, Any]] = []
    artifact_outputs: list[dict[str, Any]] = []

    status: str = "idle"
    status_message: str = "Choose a workflow and provide the required inputs."
    error_message: str = ""
    can_execute_live: bool = False
    config_message: str = ""
    debug_mode: bool = False

    active_run_id: str = ""
    current_stage: str = "preparing"
    progress_events: list[dict[str, Any]] = []
    progress_timeline_labels: list[str] = [
        "preparing",
        "starting_sandbox",
        "running_workflow",
        "validating_outputs",
        "saving_outputs",
    ]

    result_summary: str = ""
    result_fields: list[dict[str, Any]] = []
    result_artifacts: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    expanded_run_id: str = ""

    @rx.var
    def has_workflows(self) -> bool:
        return bool(self.workflow_cards)

    @rx.var
    def has_error(self) -> bool:
        return bool(self.error_message)

    @rx.var
    def has_results(self) -> bool:
        return bool(self.result_summary or self.result_fields or self.result_artifacts)

    @rx.var
    def has_file_inputs(self) -> bool:
        return any(field["type"] == "file" for field in self.input_fields)

    @rx.var
    def show_config_warning(self) -> bool:
        return not self.can_execute_live

    @rx.var
    def is_running(self) -> bool:
        return self.status == "running"

    @rx.var
    def has_progress(self) -> bool:
        return bool(self.progress_events)

    @rx.var
    def can_run(self) -> bool:
        if not self.can_execute_live or self.is_running:
            return False
        for field in self.input_fields:
            if field["type"] == "file" and field["required"] and not field.get("staged_path"):
                return False
            if field["type"] != "file" and field["required"] and not str(field.get("value", "")).strip():
                return False
        return bool(self.selected_workflow_id)

    @rx.var
    def debug_mode_label(self) -> str:
        return "Debug On" if self.debug_mode else "Debug Off"

    @rx.var
    def progress_feed(self) -> list[dict[str, Any]]:
        return list(reversed(self.progress_events))[:5]

    @rx.var
    def stage_timeline(self) -> list[dict[str, Any]]:
        runtime_stage = self._latest_runtime_stage()
        current_index = (
            self.progress_timeline_labels.index(runtime_stage)
            if runtime_stage in self.progress_timeline_labels
            else -1
        )
        items: list[dict[str, str]] = []
        total = len(self.progress_timeline_labels)
        for index, stage in enumerate(self.progress_timeline_labels):
            if self.status == "failed" and index == current_index:
                tone = "error"
                state = "failed"
            elif current_index > index:
                tone = "active"
                state = "complete"
            elif current_index == index and self.status in {"running", "complete"}:
                tone = "accent"
                state = "active"
            else:
                tone = "neutral"
                state = "pending"
            items.append(
                {
                    "id": stage,
                    "label": self._format_stage_label(stage),
                    "tone": tone,
                    "state": state,
                    "index": str(index + 1),
                    "is_last": index == total - 1,
                }
            )
        return items

    @rx.var
    def status_badge_label(self) -> str:
        return {
            "idle": "Ready",
            "running": "Running",
            "complete": "Complete",
            "failed": "Failed",
        }.get(self.status, "Ready")

    @rx.var
    def status_badge_tone(self) -> str:
        return {
            "running": "accent",
            "complete": "active",
            "failed": "error",
        }.get(self.status, "neutral")

    @rx.var
    def current_stage_label(self) -> str:
        if self.status == "complete":
            return "Complete"
        if self.status == "failed":
            return "Failed"
        return self._format_stage_label(self._latest_runtime_stage())

    def load_page(self):
        self.can_execute_live = execution_enabled()
        self.config_message = "" if self.can_execute_live else "Set OPENAI_API_KEY and OPENAI_SANDBOX_MODEL to run workflows."
        self.workflow_cards = [workflow.model_dump() for workflow in list_workflows(include_inactive=False)]
        self.runs = [self._run_to_card(record) for record in load_run_records(limit=10)]
        if self.selected_workflow_id and any(card["id"] == self.selected_workflow_id for card in self.workflow_cards):
            self.select_workflow(self.selected_workflow_id)
            return
        if self.workflow_cards:
            self.select_workflow(self.workflow_cards[0]["id"])
        else:
            self.selected_workflow_id = ""
            self.selected_workflow_name = ""
            self.selected_workflow_description = ""
            self.active_file_field_id = ""
            self.input_fields = []
            self.output_fields = []
            self.artifact_outputs = []
            self.status_message = "No active workflows yet. Create one in Builder mode."
            self.progress_events = []

    def select_workflow(self, workflow_id: str):
        if self.is_running:
            return
        workflow = get_workflow(workflow_id)
        self.selected_workflow_id = workflow.id
        self.selected_workflow_name = workflow.name
        self.selected_workflow_description = workflow.description
        self.input_fields = [
            {
                "id": field.id,
                "label": field.label,
                "type": field.type,
                "required": field.required,
                "help_text": field.help_text,
                "value": "",
                "staged_name": "",
                "staged_path": "",
                "preview": "",
            }
            for field in workflow.input_fields
        ]
        self.active_file_field_id = next(
            (field["id"] for field in self.input_fields if field["type"] == "file"),
            "",
        )
        self.output_fields = [field.model_dump() for field in workflow.output_fields]
        self.artifact_outputs = [artifact.model_dump() for artifact in workflow.artifact_outputs]
        self.active_run_id = ""
        self.current_stage = "preparing"
        self.progress_events = []
        self.result_summary = ""
        self.result_fields = []
        self.result_artifacts = []
        self.error_message = ""
        self.status = "idle"
        self.status_message = "Workflow ready. Supply inputs and run."

    def update_text_input(self, field_id: str, value: str):
        if self.is_running:
            return
        self.input_fields = [
            {
                **field,
                "value": value,
            }
            if field["id"] == field_id
            else field
            for field in self.input_fields
        ]

    def set_active_file_field(self, field_id: str):
        if self.is_running:
            return
        self.active_file_field_id = field_id
        self.status_message = f"Uploader is targeting `{field_id}`."

    async def handle_active_file_upload(self, files: list[UploadFile]):
        if self.is_running:
            return
        if not files:
            return
        if not self.active_file_field_id:
            self.error_message = "Choose a file input target before uploading."
            return
        upload = files[0]
        filename = upload.filename or "upload.bin"
        destination = staging_upload_dir() / f"{self.active_file_field_id}_{uuid4().hex[:8]}_{safe_filename(filename)}"
        payload = await upload.read()
        destination.write_bytes(payload)
        preview = self._preview_for_file(destination)
        self.input_fields = [
            {
                **field,
                "staged_name": filename,
                "staged_path": str(destination),
                "preview": preview,
            }
            if field["id"] == self.active_file_field_id
            else field
            for field in self.input_fields
        ]
        self.status_message = f"Staged file for {self.active_file_field_id}."

    def toggle_debug_mode(self):
        if self.is_running:
            return
        self.debug_mode = not self.debug_mode
        self.status_message = (
            "Debug mode enabled. Full agent trace will be saved with the run."
            if self.debug_mode
            else "Debug mode disabled."
        )

    def clear_inputs(self):
        if self.is_running:
            return
        self.input_fields = [
            {
                **field,
                "value": "",
                "staged_name": "",
                "staged_path": "",
                "preview": "",
            }
            for field in self.input_fields
        ]
        self.active_run_id = ""
        self.current_stage = "preparing"
        self.progress_events = []
        self.result_summary = ""
        self.result_fields = []
        self.result_artifacts = []
        self.error_message = ""
        self.status = "idle"
        self.status_message = "Inputs cleared."

    async def run_selected_workflow(self):
        if not self.can_execute_live:
            self.error_message = self.config_message
            return

        self.status = "running"
        self.status_message = "Starting run..."
        self.error_message = ""
        self.active_run_id = ""
        self.current_stage = "preparing"
        self.progress_events = []
        self.result_summary = ""
        self.result_fields = []
        self.result_artifacts = []
        yield

        text_inputs = {
            field["id"]: str(field.get("value", "")).strip()
            for field in self.input_fields
            if field["type"] != "file" and str(field.get("value", "")).strip()
        }
        file_inputs = {
            field["id"]: Path(field["staged_path"])
            for field in self.input_fields
            if field["type"] == "file" and field.get("staged_path")
        }

        async for update in stream_workflow(
            self.selected_workflow_id,
            text_inputs,
            file_inputs,
            debug=self.debug_mode,
        ):
            if isinstance(update, WorkflowProgressEvent):
                self.current_stage = update.stage
                self.status_message = update.title
                self._append_progress_event(update)
                yield
                continue

            if update.record is not None:
                self.active_run_id = update.record.id

            if update.status == "complete" and update.record is not None:
                self.status = "complete"
                self.current_stage = "complete"
                self.status_message = "Run complete."
                self.result_summary = update.record.result.summary if update.record.result else ""
                self.result_fields = self._build_result_fields(update.record)
                self.result_artifacts = [
                    artifact.model_dump()
                    for artifact in (update.record.result.artifacts if update.record.result else [])
                ]
                self.runs = [self._run_to_card(run) for run in load_run_records(limit=10)]
                yield
                return

            self.status = "failed"
            self.current_stage = "failed"
            self.error_message = update.error or (update.record.error if update.record is not None else "Run failed.")
            self.status_message = "Run failed."
            self.runs = [self._run_to_card(run) for run in load_run_records(limit=10)]
            yield
            return

    def download_artifact(self, stored_path: str, filename: str, mime_type: str | None = None):
        path = Path(stored_path)
        if not path.exists():
            self.error_message = f"Artifact `{filename}` is missing on disk."
            return
        return rx.download(
            data=path.read_bytes(),
            filename=filename,
            mime_type=mime_type or "application/octet-stream",
        )

    def _append_progress_event(self, event: WorkflowProgressEvent) -> None:
        timestamp = event.timestamp
        event_card = {
            "timestamp": timestamp,
            "timestamp_label": self._time_label(timestamp),
            "stage": event.stage,
            "stage_label": self._format_stage_label(event.stage),
            "kind": event.kind,
            "kind_label": event.kind.replace("_", " "),
            "title": event.title,
            "detail": event.detail,
        }
        self.progress_events = [*self.progress_events, event_card][-50:]

    def _build_result_fields(self, record) -> list[dict[str, Any]]:
        if record.result is None:
            return []

        workflow = record.workflow_snapshot
        rendered: list[dict[str, Any]] = []
        for field in workflow.output_fields:
            value = record.result.fields.get(field.id)
            rendered.append(
                {
                    "id": field.id,
                    "label": field.label,
                    "type": field.type,
                    "value": value,
                    "display": json.dumps(value, indent=2) if field.type == "json" else str(value),
                }
            )
        return rendered

    def _run_to_card(self, record) -> dict[str, Any]:
        summary = record.result.summary if record.result else ""
        error = record.error or ""
        primary = summary or error
        artifact_n = len(record.result.artifacts) if record.result else 0
        stage_n = len(record.progress_timeline)
        debug_n = len(record.debug_trace)
        return {
            "id": record.id,
            "workflow_name": record.workflow_name,
            "status": record.status,
            "started_at": record.started_at,
            "started_label": self._time_label(record.started_at),
            "summary": summary,
            "error": error,
            "preview": (primary.splitlines()[0] if primary else "")[:120],
            "artifact_count": str(artifact_n),
            "stage_count": str(stage_n),
            "debug_enabled": record.debug_enabled,
            "debug_event_count": str(debug_n),
            "meta_label": f"{stage_n} {'stage' if stage_n == 1 else 'stages'} · "
            f"{artifact_n} {'artifact' if artifact_n == 1 else 'artifacts'} · "
            f"{debug_n} {'trace event' if debug_n == 1 else 'trace events'}",
            "raw_result_json": record.raw_result_json or "",
            "timeline_text": self._format_timeline_text(record),
            "debug_trace_text": self._format_debug_trace_text(record),
        }

    def toggle_run_expanded(self, run_id: str):
        self.expanded_run_id = "" if self.expanded_run_id == run_id else run_id

    def _preview_for_file(self, path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            return "PDF staged. Text extraction will happen inside the workflow."
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:320] or "Preview unavailable."
        except Exception:
            return "Preview unavailable."

    def _latest_runtime_stage(self) -> str:
        for event in reversed(self.progress_events):
            if event["stage"] in self.progress_timeline_labels:
                return str(event["stage"])
        if self.current_stage in self.progress_timeline_labels:
            return self.current_stage
        return "preparing"

    def _format_stage_label(self, stage: str) -> str:
        return {
            "preparing": "Preparing",
            "starting_sandbox": "Sandbox",
            "running_workflow": "Running",
            "validating_outputs": "Validating",
            "saving_outputs": "Saving",
            "complete": "Complete",
            "failed": "Failed",
        }.get(stage, stage.replace("_", " ").title())

    def _time_label(self, value: str) -> str:
        return value[11:19] if "T" in value and len(value) >= 19 else value

    def _format_timeline_text(self, record) -> str:
        if not record.progress_timeline:
            return "No persisted timeline."
        lines: list[str] = []
        for entry in record.progress_timeline:
            prefix = f"{self._time_label(entry.timestamp)}  {self._format_stage_label(entry.stage)}  {entry.title}"
            if entry.detail:
                lines.append(f"{prefix}\n{entry.detail}")
            else:
                lines.append(prefix)
        return "\n\n".join(lines)

    def _format_debug_trace_text(self, record) -> str:
        if not record.debug_trace:
            return "No debug trace captured."
        blocks: list[str] = []
        for entry in record.debug_trace:
            header = f"{self._time_label(entry.timestamp)}  {entry.event_type}  {entry.title}"
            payload = entry.payload.strip() or "(empty payload)"
            blocks.append(f"{header}\n{payload}")
        return "\n\n".join(blocks)
