from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from agents.items import MessageOutputItem, ToolCallItem, ToolCallOutputItem
from agents.sandbox.types import ExecResult
from agents.stream_events import AgentUpdatedStreamEvent, RawResponsesStreamEvent, RunItemStreamEvent

from monrovia_demo.models import (
    InputFieldDefinition,
    OutputFieldDefinition,
    WorkflowDefinition,
)
from monrovia_demo import workflow_runner


class FakeSession:
    def __init__(self):
        self.started = False

    async def start(self):
        self.started = True

    async def exec(self, *command, **kwargs):
        _ = (command, kwargs)
        return ExecResult(stdout=b"", stderr=b"", exit_code=0)

    async def stop(self):
        return None


class FakeClient:
    def __init__(self):
        self.created_manifest = None
        self.created_options = None
        self.deleted = False
        self.session = FakeSession()

    async def create(self, manifest, options):
        self.created_manifest = manifest
        self.created_options = options
        return self.session

    async def delete(self, session):
        self.deleted = True


class FakeStreamingResult:
    def __init__(self, events):
        self._events = events

    async def stream_events(self):
        for event in self._events:
            if isinstance(event, Exception):
                raise event
            yield event


class FakeAgent:
    def __init__(self, name: str):
        self.name = name


def build_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="review-document",
        name="Review Document",
        prompt="Review the document.",
        input_fields=[InputFieldDefinition(id="document", label="Document", type="file")],
        output_fields=[OutputFieldDefinition(id="summary", label="Summary", type="text")],
    )


def test_stream_workflow_emits_stages_and_persists_compact_timeline(monkeypatch, tmp_path):
    workflow = build_workflow()
    input_file = tmp_path / "doc.txt"
    input_file.write_text("hello", encoding="utf-8")
    saved_records = []
    fake_client = FakeClient()
    fake_agent = FakeAgent("Artifact Agent")

    async def fake_read_session_text(session, path):
        return json.dumps({"summary": "done", "fields": {"summary": "ok"}, "artifacts": []})

    async def fake_persist_artifacts(run_id, session, artifacts):
        return []

    events = [
        AgentUpdatedStreamEvent(new_agent=FakeAgent("Artifact Agent")),
        RunItemStreamEvent(
            name="tool_called",
            item=ToolCallItem(agent=fake_agent, raw_item={"type": "local_shell_call", "name": "shell"}, title="Shell tool"),
        ),
        RunItemStreamEvent(
            name="tool_output",
            item=ToolCallOutputItem(
                agent=fake_agent,
                raw_item={"type": "function_call_output"},
                output="created summary",
            ),
        ),
    ]

    monkeypatch.setattr(workflow_runner, "get_workflow", lambda workflow_id: workflow)
    monkeypatch.setattr(workflow_runner, "execution_enabled", lambda: True)
    monkeypatch.setattr(workflow_runner, "configure_openai_client", lambda: None)
    monkeypatch.setattr(workflow_runner, "_create_sandbox_backend", lambda: asyncio.sleep(0, result=(fake_client, object())))
    monkeypatch.setattr(workflow_runner.Runner, "run_streamed", lambda *args, **kwargs: FakeStreamingResult(events))
    monkeypatch.setattr(workflow_runner, "_read_session_text", fake_read_session_text)
    monkeypatch.setattr(workflow_runner, "_persist_artifacts", fake_persist_artifacts)
    monkeypatch.setattr(workflow_runner, "save_run_record", saved_records.append)

    async def collect_events():
        collected = []
        async for event in workflow_runner.stream_workflow(
            workflow.id,
            {},
            {"document": input_file},
        ):
            collected.append(event)
        return collected

    collected = asyncio.run(collect_events())

    progress_titles = [event.title for event in collected if hasattr(event, "title")]
    assert progress_titles[:4] == [
        "Validating workflow inputs",
        "Staging uploaded files",
        "Creating sandbox session",
        "Starting workflow agent",
    ]
    assert any(getattr(event, "kind", "") == "tool_called" for event in collected)
    terminal = collected[-1]
    assert terminal.status == "complete"
    assert fake_client.session.started is True
    assert saved_records[0].progress_timeline[0].title == "Validating workflow inputs"
    assert [entry.title for entry in saved_records[0].progress_timeline] == [
        "Validating workflow inputs",
        "Creating sandbox session",
        "Starting workflow agent",
        "Validating outputs/result.json",
        "Saving artifacts and run record",
    ]
    assert saved_records[0].debug_enabled is False
    assert saved_records[0].debug_trace == []


def test_stream_workflow_persists_debug_trace_when_enabled(monkeypatch, tmp_path):
    workflow = build_workflow()
    input_file = tmp_path / "doc.txt"
    input_file.write_text("hello", encoding="utf-8")
    saved_records = []
    fake_client = FakeClient()
    fake_agent = FakeAgent("Artifact Agent")

    async def fake_read_session_text(session, path):
        return json.dumps({"summary": "done", "fields": {"summary": "ok"}, "artifacts": []})

    async def fake_persist_artifacts(run_id, session, artifacts):
        return []

    events = [
        AgentUpdatedStreamEvent(new_agent=FakeAgent("Artifact Agent")),
        RunItemStreamEvent(
            name="tool_called",
            item=ToolCallItem(agent=fake_agent, raw_item={"type": "local_shell_call", "name": "shell"}, title="Shell tool"),
        ),
    ]

    monkeypatch.setattr(workflow_runner, "get_workflow", lambda workflow_id: workflow)
    monkeypatch.setattr(workflow_runner, "execution_enabled", lambda: True)
    monkeypatch.setattr(workflow_runner, "configure_openai_client", lambda: None)
    monkeypatch.setattr(workflow_runner, "_create_sandbox_backend", lambda: asyncio.sleep(0, result=(fake_client, object())))
    monkeypatch.setattr(workflow_runner.Runner, "run_streamed", lambda *args, **kwargs: FakeStreamingResult(events))
    monkeypatch.setattr(workflow_runner, "_read_session_text", fake_read_session_text)
    monkeypatch.setattr(workflow_runner, "_persist_artifacts", fake_persist_artifacts)
    monkeypatch.setattr(workflow_runner, "save_run_record", saved_records.append)

    async def collect_events():
        collected = []
        async for event in workflow_runner.stream_workflow(
            workflow.id,
            {},
            {"document": input_file},
            debug=True,
        ):
            collected.append(event)
        return collected

    asyncio.run(collect_events())

    assert saved_records[0].debug_enabled is True
    assert len(saved_records[0].debug_trace) == 2
    assert saved_records[0].debug_trace[0].event_type == "agent_updated"
    assert '"agent_name": "Artifact Agent"' in saved_records[0].debug_trace[0].payload
    assert '"tool_name": "Shell tool"' in saved_records[0].debug_trace[1].payload


def test_stream_workflow_skips_raw_response_events_in_debug_trace(monkeypatch, tmp_path):
    workflow = build_workflow()
    input_file = tmp_path / "doc.txt"
    input_file.write_text("hello", encoding="utf-8")
    saved_records = []
    fake_client = FakeClient()

    async def fake_read_session_text(session, path):
        return json.dumps({"summary": "done", "fields": {"summary": "ok"}, "artifacts": []})

    async def fake_persist_artifacts(run_id, session, artifacts):
        return []

    events = [
        RawResponsesStreamEvent(data={"type": "response.output_text.delta"}),
        AgentUpdatedStreamEvent(new_agent=FakeAgent("Artifact Agent")),
    ]

    monkeypatch.setattr(workflow_runner, "get_workflow", lambda workflow_id: workflow)
    monkeypatch.setattr(workflow_runner, "execution_enabled", lambda: True)
    monkeypatch.setattr(workflow_runner, "configure_openai_client", lambda: None)
    monkeypatch.setattr(workflow_runner, "_create_sandbox_backend", lambda: asyncio.sleep(0, result=(fake_client, object())))
    monkeypatch.setattr(workflow_runner.Runner, "run_streamed", lambda *args, **kwargs: FakeStreamingResult(events))
    monkeypatch.setattr(workflow_runner, "_read_session_text", fake_read_session_text)
    monkeypatch.setattr(workflow_runner, "_persist_artifacts", fake_persist_artifacts)
    monkeypatch.setattr(workflow_runner, "save_run_record", saved_records.append)

    async def collect_events():
        collected = []
        async for event in workflow_runner.stream_workflow(
            workflow.id,
            {},
            {"document": input_file},
            debug=True,
        ):
            collected.append(event)
        return collected

    asyncio.run(collect_events())

    assert len(saved_records[0].debug_trace) == 1
    assert saved_records[0].debug_trace[0].event_type == "agent_updated"


def test_stream_workflow_persists_failed_timeline(monkeypatch, tmp_path):
    workflow = build_workflow()
    input_file = tmp_path / "doc.txt"
    input_file.write_text("hello", encoding="utf-8")
    saved_records = []
    fake_client = FakeClient()

    monkeypatch.setattr(workflow_runner, "get_workflow", lambda workflow_id: workflow)
    monkeypatch.setattr(workflow_runner, "execution_enabled", lambda: True)
    monkeypatch.setattr(workflow_runner, "configure_openai_client", lambda: None)
    monkeypatch.setattr(workflow_runner, "_create_sandbox_backend", lambda: asyncio.sleep(0, result=(fake_client, object())))
    monkeypatch.setattr(
        workflow_runner.Runner,
        "run_streamed",
        lambda *args, **kwargs: FakeStreamingResult([RuntimeError("tool boom")]),
    )
    monkeypatch.setattr(workflow_runner, "save_run_record", saved_records.append)

    async def collect_events():
        collected = []
        async for event in workflow_runner.stream_workflow(
            workflow.id,
            {},
            {"document": input_file},
        ):
            collected.append(event)
        return collected

    collected = asyncio.run(collect_events())

    assert collected[-2].kind == "error"
    assert collected[-2].stage == "failed"
    assert collected[-1].status == "failed"
    assert saved_records[0].status == "failed"
    assert saved_records[0].progress_timeline[-1].title == "Workflow run failed"
    assert saved_records[0].debug_trace == []


def test_map_stream_event_ignores_raw_response_events():
    event = RawResponsesStreamEvent(data={"type": "response.output_text.delta"})
    assert workflow_runner._map_stream_event_to_progress(event) is None


def test_map_stream_event_truncates_tool_output():
    long_output = "x" * 300
    event = RunItemStreamEvent(
        name="tool_output",
        item=ToolCallOutputItem(
            agent=FakeAgent("Runner"),
            raw_item={"type": "function_call_output"},
            output=long_output,
        ),
    )
    mapped = workflow_runner._map_stream_event_to_progress(event)
    assert mapped is not None
    assert mapped.kind == "tool_output"
    assert len(mapped.detail) <= 160
    assert mapped.detail.endswith("…")


def test_map_stream_event_reads_message_output():
    event = RunItemStreamEvent(
        name="message_output_created",
        item=MessageOutputItem(
            agent=FakeAgent("Runner"),
            raw_item={
                "content": [
                    {
                        "text": {
                            "value": "Review finished with two findings.",
                        }
                    }
                ]
            },
        ),
    )
    mapped = workflow_runner._map_stream_event_to_progress(event)
    assert mapped is not None
    assert mapped.title == "Agent produced output"
    assert "two findings" in mapped.detail


def test_validate_persisted_artifact_rejects_fake_pptx(tmp_path):
    artifact = tmp_path / "report.pptx"
    artifact.write_text("PPTX generation unavailable in this sandbox.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="valid Office package|valid PowerPoint"):
        workflow_runner._validate_persisted_artifact(artifact, "pptx")


def test_agent_instructions_reference_python3_for_office_scripts():
    workflow = build_workflow()
    instructions = workflow_runner._build_agent_instructions(workflow)
    assert "Prefer writing Python directly with the appropriate library" in instructions
    assert "The helper scripts in `.agents/office-artifacts/scripts/` are optional fallbacks" in instructions
    assert "Do not write placeholder or fallback text into Office files" in instructions


def test_sandbox_image_reference_uses_hashed_local_image(monkeypatch):
    monkeypatch.delenv("MONROVIA_SANDBOX_IMAGE", raising=False)

    digest = hashlib.sha256()
    for path in (workflow_runner.DOCKER_SANDBOX_DOCKERFILE, workflow_runner.DOCKER_SANDBOX_REQUIREMENTS):
        digest.update(path.read_bytes())

    image_name, managed = workflow_runner._sandbox_image_reference()
    assert managed is True
    assert image_name == f"{workflow_runner.DOCKER_SANDBOX_IMAGE_PREFIX}:{digest.hexdigest()[:12]}"


def test_sandbox_image_reference_uses_configured_image(monkeypatch):
    monkeypatch.setenv("MONROVIA_SANDBOX_IMAGE", "custom/image:latest")
    assert workflow_runner._sandbox_image_reference() == ("custom/image:latest", False)


def test_sandbox_python_preflight_surfaces_missing_dependency_error():
    class MissingModuleSession:
        async def exec(self, *command, **kwargs):
            _ = (command, kwargs)
            return ExecResult(
                stdout=b"",
                stderr=b"missing modules: docx",
                exit_code=1,
            )

    with pytest.raises(RuntimeError, match="Sandbox Python preflight failed"):
        asyncio.run(workflow_runner._ensure_sandbox_python_runtime(MissingModuleSession()))
