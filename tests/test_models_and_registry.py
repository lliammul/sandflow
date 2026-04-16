from __future__ import annotations

import json
from pathlib import Path

import pytest

from monrovia_demo.models import (
    ArtifactOutputDefinition,
    WorkflowDebugTraceEntry,
    InputFieldDefinition,
    OutputFieldDefinition,
    WorkflowDefinition,
    WorkflowRunInputSummary,
    WorkflowRunRecord,
    WorkflowRunTimelineEntry,
    validate_execution_result,
)
from monrovia_demo.storage import ensure_storage, load_run_records, run_file_path, workflow_file_path
from monrovia_demo.workflow_registry import delete_workflow, get_workflow, save_workflow


def test_workflow_definition_rejects_duplicate_input_ids():
    with pytest.raises(ValueError):
        WorkflowDefinition(
            id="bad-workflow",
            name="Bad Workflow",
            prompt="Prompt",
            input_fields=[
                InputFieldDefinition(id="document", label="Document", type="file"),
                InputFieldDefinition(id="document", label="Again", type="file"),
            ],
            output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
        )


def test_validate_execution_result_rejects_undeclared_output():
    workflow = WorkflowDefinition(
        id="review-document",
        name="Review Document",
        prompt="Prompt",
        input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
        output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="markdown")],
        artifact_outputs=[ArtifactOutputDefinition(id="report_file", label="Report File")],
    )
    with pytest.raises(ValueError):
        validate_execution_result(
            workflow,
            {
                "summary": "done",
                "fields": {"summary": "ok", "unexpected": "nope"},
                "artifacts": [],
            },
        )


def test_validate_execution_result_rejects_wrong_artifact_extension():
    workflow = WorkflowDefinition(
        id="deck-workflow",
        name="Deck Workflow",
        prompt="Prompt",
        input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
        output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="markdown")],
        artifact_outputs=[ArtifactOutputDefinition(id="deck", label="Deck", format="pptx")],
    )
    with pytest.raises(ValueError):
        validate_execution_result(
            workflow,
            {
                "summary": "done",
                "fields": {"summary": "ok"},
                "artifacts": [
                    {
                        "artifact_id": "deck",
                        "label": "Deck",
                        "path": "outputs/artifacts/deck.docx",
                    }
                ],
            },
        )


def test_save_and_load_workflow_roundtrip():
    ensure_storage()
    workflow = WorkflowDefinition(
        id="test-registry-workflow",
        name="Test Registry Workflow",
        prompt="Prompt",
        input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
        output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
    )
    save_workflow(workflow)
    loaded = get_workflow(workflow.id)
    assert loaded.id == workflow.id
    assert workflow_file_path(workflow.id).exists()
    delete_workflow(workflow.id)
    assert not workflow_file_path(workflow.id).exists()


def test_workflow_run_record_defaults_progress_timeline_for_legacy_json():
    payload = {
        "id": "run_legacy",
        "workflow_id": "review-document",
        "workflow_name": "Review Document",
        "workflow_snapshot": WorkflowDefinition(
            id="review-document",
            name="Review Document",
            prompt="Prompt",
            input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
            output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
        ).model_dump(),
        "status": "failed",
        "started_at": "2026-04-16T12:00:00Z",
        "completed_at": "2026-04-16T12:01:00Z",
        "input_summary": WorkflowRunInputSummary().model_dump(),
        "error": "boom",
        "raw_result_json": None,
    }
    record = WorkflowRunRecord.model_validate(payload)
    assert record.progress_timeline == []
    assert record.debug_enabled is False
    assert record.debug_trace == []


def test_load_run_records_accepts_legacy_run_json_without_progress_timeline():
    ensure_storage()
    legacy_path = run_file_path("run_legacy_load")
    legacy_payload = {
        "id": "run_legacy_load",
        "workflow_id": "review-document",
        "workflow_name": "Review Document",
        "workflow_snapshot": WorkflowDefinition(
            id="review-document",
            name="Review Document",
            prompt="Prompt",
            input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
            output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
        ).model_dump(),
        "status": "failed",
        "started_at": "2026-04-16T12:00:00Z",
        "completed_at": "2026-04-16T12:01:00Z",
        "input_summary": WorkflowRunInputSummary().model_dump(),
        "result": None,
        "error": "boom",
        "raw_result_json": None,
    }
    legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
    records = load_run_records(limit=50)
    record = next(record for record in records if record.id == "run_legacy_load")
    assert record.progress_timeline == []
    assert record.debug_enabled is False
    assert record.debug_trace == []
    legacy_path.unlink(missing_ok=True)


def test_workflow_run_record_serializes_progress_timeline():
    record = WorkflowRunRecord(
        id="run_progress",
        workflow_id="review-document",
        workflow_name="Review Document",
        workflow_snapshot=WorkflowDefinition(
            id="review-document",
            name="Review Document",
            prompt="Prompt",
            input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
            output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
        ),
        status="complete",
        started_at="2026-04-16T12:00:00Z",
        completed_at="2026-04-16T12:01:00Z",
        input_summary=WorkflowRunInputSummary(),
        progress_timeline=[
            WorkflowRunTimelineEntry(
                timestamp="2026-04-16T12:00:01Z",
                stage="preparing",
                title="Validating workflow inputs",
                detail="",
            )
        ],
        debug_enabled=True,
        debug_trace=[
            WorkflowDebugTraceEntry(
                timestamp="2026-04-16T12:00:02Z",
                event_type="tool_called",
                title="RunItemStreamEvent: tool_called",
                payload="{\"name\": \"shell\"}",
            )
        ],
    )
    payload = record.model_dump()
    assert payload["progress_timeline"][0]["title"] == "Validating workflow inputs"
    assert payload["debug_enabled"] is True
    assert payload["debug_trace"][0]["event_type"] == "tool_called"


def test_ensure_storage_migrates_workflows_and_cleans_legacy_app_dirs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    legacy_workflow_dir = tmp_path / ".context" / "workflows"
    legacy_workflow_dir.mkdir(parents=True)
    (legacy_workflow_dir / "evaluate.json").write_text(
        WorkflowDefinition(
            id="evaluate",
            name="evaluate",
            prompt="Prompt",
            input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
            output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    for dirname in ("runs", "uploads", "artifacts"):
        path = tmp_path / ".context" / dirname
        path.mkdir(parents=True)
        (path / "stale.txt").write_text("stale", encoding="utf-8")

    ensure_storage()

    assert (tmp_path / ".application" / "workflows" / "evaluate.json").exists()
    assert not (tmp_path / ".context" / "workflows").exists()
    assert not (tmp_path / ".context" / "runs").exists()
    assert not (tmp_path / ".context" / "uploads").exists()
    assert not (tmp_path / ".context" / "artifacts").exists()
