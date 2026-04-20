from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sandflow_sidecar.contract import create_app
from sandflow_sidecar.models import InputFieldDefinition, OutputFieldDefinition, WorkflowDefinition
from sandflow_sidecar.storage import run_file_path
from sandflow_sidecar.workflow_registry import save_workflow


def test_health_endpoint(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SANDFLOW_APP_STORAGE", str(tmp_path / ".application"))
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_workflow_crud_and_listing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SANDFLOW_APP_STORAGE", str(tmp_path / ".application"))
    client = TestClient(create_app())

    workflow = WorkflowDefinition(
        id="test-workflow",
        name="Test Workflow",
        prompt="Prompt",
        input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
        output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
    )

    put_response = client.put(f"/workflows/{workflow.id}", json=workflow.model_dump(mode="json"))
    assert put_response.status_code == 200
    assert put_response.json()["id"] == workflow.id

    list_response = client.get("/workflows")
    assert list_response.status_code == 200
    assert any(item["id"] == workflow.id for item in list_response.json())

    delete_response = client.delete(f"/workflows/{workflow.id}")
    assert delete_response.status_code == 204


def test_runs_endpoint_reads_persisted_record(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SANDFLOW_APP_STORAGE", str(tmp_path / ".application"))
    client = TestClient(create_app())

    workflow = WorkflowDefinition(
        id="persisted-workflow",
        name="Persisted Workflow",
        prompt="Prompt",
        input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
        output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
    )
    save_workflow(workflow)
    run_file_path("run_test").write_text(
        json.dumps(
            {
                "id": "run_test",
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "workflow_snapshot": workflow.model_dump(mode="json"),
                "status": "failed",
                "started_at": "2026-04-18T10:00:00Z",
                "completed_at": "2026-04-18T10:01:00Z",
                "input_summary": {"text_fields": {}, "files": []},
                "result": None,
                "error": "boom",
                "raw_result_json": None,
                "progress_timeline": [],
                "debug_enabled": False,
                "debug_trace": [],
            }
        ),
        encoding="utf-8",
    )

    response = client.get("/runs")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "run_test"


def test_events_endpoint_streams_manager_output(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SANDFLOW_APP_STORAGE", str(tmp_path / ".application"))
    app = create_app()

    async def fake_stream_events(run_id: str):
        assert run_id == "run_123"
        yield {"type": "progress", "payload": {"title": "Starting"}}
        yield {"type": "terminal", "payload": {"status": "complete"}}

    app.state.run_manager.stream_events = fake_stream_events
    client = TestClient(app)

    with client.stream("GET", "/runs/run_123/events") as response:
        body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert response.status_code == 200
    assert "event: progress" in body
    assert '"title":"Starting"' in body
    assert "event: terminal" in body


def test_run_endpoint_stages_uploaded_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SANDFLOW_APP_STORAGE", str(tmp_path / ".application"))
    app = create_app()

    workflow = WorkflowDefinition(
        id="upload-workflow",
        name="Upload Workflow",
        prompt="Prompt",
        input_fields=[InputFieldDefinition(id="document", label="Document", type="file", required=True)],
        output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
    )
    save_workflow(workflow)

    captured: dict[str, object] = {}

    async def fake_start_run(workflow_id: str, text_inputs: dict[str, str], file_inputs: dict[str, object], *, debug: bool = False):
        captured["workflow_id"] = workflow_id
        captured["text_inputs"] = text_inputs
        captured["file_inputs"] = file_inputs
        captured["debug"] = debug
        return "run_uploaded"

    app.state.run_manager.start_run = fake_start_run
    client = TestClient(app)

    response = client.post(
        "/workflows/upload-workflow/run",
        data={"debug": "true"},
        files={"file.document": ("test.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json() == {"run_id": "run_uploaded"}
    assert captured["workflow_id"] == "upload-workflow"
    assert captured["debug"] is True
    uploaded = captured["file_inputs"]["document"]
    assert uploaded.exists()
    assert uploaded.read_text(encoding="utf-8") == "hello world"
