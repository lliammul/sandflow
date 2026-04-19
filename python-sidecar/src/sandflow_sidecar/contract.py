from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from .models import WorkflowDefinition, WorkflowRegistryEntry, WorkflowRunRecord
from .run_manager import RunManager
from .storage import (
    load_run_record,
    load_run_records,
    safe_filename,
    staging_upload_dir,
)
from .workflow_registry import (
    delete_workflow,
    get_workflow,
    list_workflow_entries,
    list_workflows,
    load_workflow_raw_error,
    save_workflow,
)

APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    run_manager = RunManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await run_manager.shutdown()

    app = FastAPI(title="Sandflow Sidecar", version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(https?://(127\.0\.0\.1|localhost)(:\d+)?|tauri://localhost)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.run_manager = run_manager

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": APP_VERSION}

    @app.get("/ready")
    async def ready() -> dict[str, Any]:
        checks: dict[str, bool] = {}
        try:
            list_workflow_entries(include_inactive=True)
            checks["registry"] = True
        except Exception:
            checks["registry"] = False
        try:
            staging_upload_dir()
            checks["storage"] = True
        except Exception:
            checks["storage"] = False
        checks["run_manager"] = app.state.run_manager is not None
        if not all(checks.values()):
            return JSONResponse({"status": "not_ready", "checks": checks}, status_code=503)
        return {"status": "ready", "version": APP_VERSION, "checks": checks}

    @app.get("/runs/active")
    async def active_runs() -> dict[str, list[str]]:
        return {"run_ids": run_manager.list_active()}

    @app.post("/runs/pause")
    async def pause_runs() -> dict[str, bool]:
        run_manager.pause()
        return {"paused": True}

    @app.post("/runs/resume")
    async def resume_runs() -> dict[str, bool]:
        run_manager.resume()
        return {"paused": False}

    @app.get("/workflow-entries", response_model=list[WorkflowRegistryEntry])
    async def workflow_entries(include_inactive: bool = True) -> list[WorkflowRegistryEntry]:
        return list_workflow_entries(include_inactive=include_inactive)

    @app.get("/workflows", response_model=list[WorkflowDefinition])
    async def workflows(include_inactive: bool = True) -> list[WorkflowDefinition]:
        return list_workflows(include_inactive=include_inactive)

    @app.get("/workflows/{workflow_id}", response_model=WorkflowDefinition)
    async def workflow(workflow_id: str) -> WorkflowDefinition:
        try:
            return get_workflow(workflow_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/workflows/{workflow_id}", response_model=WorkflowDefinition)
    async def put_workflow(workflow_id: str, workflow: WorkflowDefinition) -> WorkflowDefinition:
        previous_id = workflow_id if workflow_id == workflow.id or load_workflow_raw_error(workflow_id) is not None else workflow_id
        try:
            return save_workflow(workflow, previous_id=previous_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/workflows/{workflow_id}", status_code=204)
    async def remove_workflow(workflow_id: str) -> Response:
        delete_workflow(workflow_id)
        return Response(status_code=204)

    @app.get("/runs", response_model=list[WorkflowRunRecord])
    async def runs(limit: int = 10) -> list[WorkflowRunRecord]:
        return load_run_records(limit=limit)

    @app.post("/workflows/{workflow_id}/run")
    async def run_workflow_endpoint(workflow_id: str, request: Request) -> JSONResponse:
        try:
            get_workflow(workflow_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        text_inputs: dict[str, str] = {}
        file_inputs: dict[str, Path] = {}
        debug = False

        form = await request.form()
        for key, value in form.multi_items():
            if key == "debug":
                debug = str(value).lower() in {"1", "true", "yes", "on"}
                continue
            if key.startswith("text."):
                text_inputs[key.removeprefix("text.")] = str(value)
                continue
            if key.startswith("file.") and isinstance(value, StarletteUploadFile):
                staged = await _stage_upload(key.removeprefix("file."), value)
                file_inputs[key.removeprefix("file.")] = staged

        try:
            run_id = await run_manager.start_run(
                workflow_id,
                text_inputs,
                file_inputs,
                debug=debug,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return JSONResponse({"run_id": run_id})

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str) -> StreamingResponse:
        try:
            event_stream = run_manager.stream_events(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Run `{run_id}` does not exist.") from exc

        async def _body() -> Any:
            async for event in event_stream:
                event_name = str(event["type"])
                payload = JSONResponse(content=event).body.decode("utf-8")
                yield f"event: {event_name}\ndata: {payload}\n\n"

        return StreamingResponse(_body(), media_type="text/event-stream")

    @app.get("/runs/{run_id}", response_model=WorkflowRunRecord)
    async def run(run_id: str) -> WorkflowRunRecord:
        record = load_run_record(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run `{run_id}` does not exist.")
        return record

    @app.get("/runs/{run_id}/artifacts/{artifact_id}")
    async def run_artifact(run_id: str, artifact_id: str) -> FileResponse:
        record = load_run_record(run_id)
        if record is None or record.result is None:
            raise HTTPException(status_code=404, detail="Run artifact does not exist.")
        artifact = next((item for item in record.result.artifacts if item.artifact_id == artifact_id), None)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Run artifact does not exist.")
        return FileResponse(
            artifact.stored_path,
            filename=artifact.filename,
            media_type=artifact.mime_type or "application/octet-stream",
        )

    return app


async def _stage_upload(field_id: str, upload: UploadFile) -> Path:
    filename = upload.filename or "upload.bin"
    payload = await upload.read()
    destination = staging_upload_dir() / f"{field_id}_{safe_filename(filename)}"
    destination.write_bytes(payload)
    return destination
