from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from .models import WorkflowRunTerminalEvent
from .workflow_runner import stream_workflow


@dataclass
class ManagedRun:
    run_id: str
    events: list[dict[str, object]] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    done: bool = False
    error: str | None = None
    task: asyncio.Task[None] | None = None


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, ManagedRun] = {}
        self._lock = asyncio.Lock()
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    async def start_run(
        self,
        workflow_id: str,
        text_inputs: dict[str, str],
        file_inputs: dict[str, Path],
        *,
        debug: bool = False,
    ) -> str:
        if self._paused:
            raise RuntimeError(
                "Sidecar is paused for a customise apply. Try again in a moment."
            )
        run_id = f"run_{uuid4().hex[:12]}"
        managed = ManagedRun(run_id=run_id)
        async with self._lock:
            self._runs[run_id] = managed
        managed.task = asyncio.create_task(
            self._run(managed, workflow_id, text_inputs, file_inputs, debug=debug)
        )
        return run_id

    def list_active(self) -> list[str]:
        return [run_id for run_id, managed in self._runs.items() if not managed.done]

    async def stream_events(self, run_id: str) -> AsyncIterator[dict[str, object]]:
        managed = self._runs.get(run_id)
        if managed is None:
            raise KeyError(run_id)

        index = 0
        while True:
            async with managed.condition:
                while index >= len(managed.events) and not managed.done:
                    await managed.condition.wait()
                if index < len(managed.events):
                    event = managed.events[index]
                    index += 1
                elif managed.done:
                    break
                else:
                    continue
            yield event

    async def _run(
        self,
        managed: ManagedRun,
        workflow_id: str,
        text_inputs: dict[str, str],
        file_inputs: dict[str, Path],
        *,
        debug: bool,
    ) -> None:
        try:
            async for event in stream_workflow(
                workflow_id,
                text_inputs,
                file_inputs,
                debug=debug,
                run_id=managed.run_id,
            ):
                await self._publish(managed, _serialize_runner_event(event))
        except Exception as exc:
            managed.error = str(exc)
            await self._publish(
                managed,
                {
                    "type": "terminal",
                    "payload": WorkflowRunTerminalEvent(
                        status="failed",
                        record=None,
                        error=str(exc),
                    ).model_dump(mode="json"),
                },
            )
        finally:
            async with managed.condition:
                managed.done = True
                managed.condition.notify_all()

    async def _publish(self, managed: ManagedRun, event: dict[str, object]) -> None:
        async with managed.condition:
            managed.events.append(event)
            managed.condition.notify_all()

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = [managed.task for managed in self._runs.values() if managed.task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(Exception):
                await task


def _serialize_runner_event(event: object) -> dict[str, object]:
    if isinstance(event, WorkflowRunTerminalEvent):
        return {"type": "terminal", "payload": event.model_dump(mode="json")}
    return {"type": "progress", "payload": event.model_dump(mode="json")}
