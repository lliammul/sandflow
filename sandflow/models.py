from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FIELD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
WORKFLOW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

InputFieldType = Literal["short_text", "long_text", "file"]
OutputFieldType = Literal["text", "markdown", "json", "number", "boolean"]
ArtifactFormat = Literal["csv", "docx", "xlsx", "pptx", "txt", "md", "json", "html"]
RunStatus = Literal["running", "complete", "failed"]
WorkflowProgressStage = Literal[
    "preparing",
    "starting_sandbox",
    "running_workflow",
    "validating_outputs",
    "saving_outputs",
    "complete",
    "failed",
]
WorkflowProgressKind = Literal["stage", "tool_called", "tool_output", "message", "agent", "error"]

ARTIFACT_FORMAT_EXTENSIONS: dict[str, str] = {
    "csv": ".csv",
    "docx": ".docx",
    "xlsx": ".xlsx",
    "pptx": ".pptx",
    "txt": ".txt",
    "md": ".md",
    "json": ".json",
    "html": ".html",
}

ARTIFACT_FORMAT_MIME_TYPES: dict[str, str] = {
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "md": "text/markdown",
    "json": "application/json",
    "html": "text/html",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class InputFieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    type: InputFieldType
    required: bool = True
    help_text: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not FIELD_ID_RE.match(value):
            raise ValueError("Field ids must use lowercase letters, numbers, underscores, or hyphens.")
        return value

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field labels cannot be empty.")
        return value


class OutputFieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    type: OutputFieldType
    required: bool = True
    help_text: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not FIELD_ID_RE.match(value):
            raise ValueError("Field ids must use lowercase letters, numbers, underscores, or hyphens.")
        return value

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field labels cannot be empty.")
        return value


class ArtifactOutputDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    format: ArtifactFormat = "csv"
    required: bool = False
    help_text: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not FIELD_ID_RE.match(value):
            raise ValueError("Artifact ids must use lowercase letters, numbers, underscores, or hyphens.")
        return value

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Artifact labels cannot be empty.")
        return value


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str
    name: str
    description: str = ""
    is_active: bool = True
    prompt: str
    input_fields: list[InputFieldDefinition]
    output_fields: list[OutputFieldDefinition] = Field(default_factory=list)
    artifact_outputs: list[ArtifactOutputDefinition] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    @field_validator("id")
    @classmethod
    def validate_workflow_id(cls, value: str) -> str:
        value = value.strip()
        if not WORKFLOW_ID_RE.match(value):
            raise ValueError("Workflow ids must be lowercase slug strings with hyphens.")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Workflow names cannot be empty.")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt cannot be empty.")
        return value

    @model_validator(mode="after")
    def validate_structure(self) -> "WorkflowDefinition":
        if not self.input_fields:
            raise ValueError("Workflows must define at least one input field.")
        if not self.output_fields and not self.artifact_outputs:
            raise ValueError("Workflows must define at least one output field or artifact output.")

        input_ids = [field.id for field in self.input_fields]
        output_ids = [field.id for field in self.output_fields]
        artifact_ids = [artifact.id for artifact in self.artifact_outputs]

        if len(input_ids) != len(set(input_ids)):
            raise ValueError("Input field ids must be unique.")
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("Output field ids must be unique.")
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("Artifact output ids must be unique.")
        return self


class WorkflowExecutionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    label: str
    path: str
    format: ArtifactFormat | None = None
    mime_type: str | None = None


class WorkflowExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    fields: dict[str, Any]
    artifacts: list[WorkflowExecutionArtifact] = Field(default_factory=list)


class WorkflowArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    label: str
    format: ArtifactFormat
    stored_path: str
    filename: str
    mime_type: str | None = None


class FileInputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str
    original_name: str
    stored_path: str


class WorkflowRunInputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_fields: dict[str, str] = Field(default_factory=dict)
    files: list[FileInputSummary] = Field(default_factory=list)


class WorkflowPersistedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    fields: dict[str, Any]
    artifacts: list[WorkflowArtifactRef] = Field(default_factory=list)


class WorkflowRunTimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    stage: WorkflowProgressStage
    title: str
    detail: str = ""


class WorkflowDebugTraceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    event_type: str
    title: str
    payload: str = ""


class WorkflowProgressEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    stage: WorkflowProgressStage
    kind: WorkflowProgressKind
    title: str
    detail: str = ""
    persist: bool = False


class WorkflowRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    workflow_id: str
    workflow_name: str
    workflow_snapshot: WorkflowDefinition
    status: RunStatus
    started_at: str
    completed_at: str | None = None
    input_summary: WorkflowRunInputSummary
    result: WorkflowPersistedResult | None = None
    error: str | None = None
    raw_result_json: str | None = None
    progress_timeline: list[WorkflowRunTimelineEntry] = Field(default_factory=list)
    debug_enabled: bool = False
    debug_trace: list[WorkflowDebugTraceEntry] = Field(default_factory=list)


class WorkflowRunTerminalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["complete", "failed"]
    record: WorkflowRunRecord | None = None
    error: str | None = None


WorkflowRunnerEvent: TypeAlias = WorkflowProgressEvent | WorkflowRunTerminalEvent


class WorkflowRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    is_active: bool = False
    has_error: bool = False
    error_message: str | None = None


def workflow_to_registry_entry(workflow: WorkflowDefinition) -> WorkflowRegistryEntry:
    return WorkflowRegistryEntry(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        is_active=workflow.is_active,
        has_error=False,
        error_message=None,
    )


def ensure_jsonable(value: Any) -> None:
    json.dumps(value)


def validate_execution_result(
    workflow: WorkflowDefinition, payload: dict[str, Any]
) -> WorkflowExecutionResult:
    result = WorkflowExecutionResult.model_validate(payload)

    allowed_fields = {field.id: field for field in workflow.output_fields}
    allowed_artifacts = {artifact.id: artifact for artifact in workflow.artifact_outputs}

    unknown_fields = set(result.fields) - set(allowed_fields)
    if unknown_fields:
        raise ValueError(f"Undeclared output fields returned: {', '.join(sorted(unknown_fields))}.")

    for field in workflow.output_fields:
        if field.required and field.id not in result.fields:
            raise ValueError(f"Missing required output field: {field.id}.")
        if field.id in result.fields:
            _validate_output_value(field, result.fields[field.id])

    seen_artifact_ids: set[str] = set()
    for artifact in result.artifacts:
        if artifact.artifact_id not in allowed_artifacts:
            raise ValueError(f"Undeclared artifact returned: {artifact.artifact_id}.")
        if artifact.artifact_id in seen_artifact_ids:
            raise ValueError(f"Artifact returned more than once: {artifact.artifact_id}.")
        seen_artifact_ids.add(artifact.artifact_id)
        _validate_artifact_path(artifact.path)
        _validate_artifact_result(allowed_artifacts[artifact.artifact_id], artifact)

    for artifact in workflow.artifact_outputs:
        if artifact.required and artifact.id not in seen_artifact_ids:
            raise ValueError(f"Missing required artifact output: {artifact.id}.")

    return result


def _validate_output_value(field: OutputFieldDefinition, value: Any) -> None:
    if field.type in {"text", "markdown"}:
        if not isinstance(value, str):
            raise ValueError(f"Output field `{field.id}` must be a string.")
        return

    if field.type == "json":
        ensure_jsonable(value)
        return

    if field.type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Output field `{field.id}` must be numeric.")
        return

    if field.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"Output field `{field.id}` must be a boolean.")
        return


def _validate_artifact_path(path: str) -> None:
    candidate = PurePosixPath(path)
    if candidate.is_absolute():
        raise ValueError("Artifact paths must be workspace-relative.")
    if not candidate.parts or candidate == PurePosixPath("."):
        raise ValueError("Artifact paths cannot be empty.")
    if ".." in candidate.parts:
        raise ValueError("Artifact paths cannot escape the workspace.")


def _validate_artifact_result(
    definition: ArtifactOutputDefinition,
    artifact: WorkflowExecutionArtifact,
) -> None:
    expected_ext = ARTIFACT_FORMAT_EXTENSIONS[definition.format]
    candidate = PurePosixPath(artifact.path)
    if candidate.suffix.lower() != expected_ext:
        raise ValueError(
            f"Artifact `{artifact.artifact_id}` must use the `{definition.format}` extension `{expected_ext}`."
        )

    if artifact.format is not None and artifact.format != definition.format:
        raise ValueError(
            f"Artifact `{artifact.artifact_id}` declared format `{artifact.format}` but workflow expects `{definition.format}`."
        )

    expected_mime = ARTIFACT_FORMAT_MIME_TYPES[definition.format]
    if artifact.mime_type is not None and artifact.mime_type != expected_mime:
        raise ValueError(
            f"Artifact `{artifact.artifact_id}` must use MIME type `{expected_mime}`."
        )
