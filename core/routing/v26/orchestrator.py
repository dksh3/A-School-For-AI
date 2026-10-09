"""Orchestrator — routes requests to tools and manages execution."""
from __future__ import annotations

import concurrent.futures
import contextlib
from typing import Any

from core.routing.v26.tools.base import (
    BackgroundTask,
    PipelineResult,
    ToolRegistry,
    ToolResult,
    format_error,
)


class Orchestrator:
    """Dispatches commands to a ToolRegistry.

    Fail-open: hostile tool names, hostile arguments, or hostile pipeline
    specs produce graceful failure results and never raise.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._background_tasks: list[BackgroundTask] = []

    def dispatch(self, command: str, **params) -> ToolResult:
        try:
            return self._registry.execute(command, **params)
        except Exception as exc:  # noqa: BLE001 - fail-open at the dispatch boundary
            return ToolResult(
                success=False,
                data={},
                errors=[f"dispatch failed safely: {format_error(exc)}"],
                metadata={},
            )

    def pipeline(self, steps: list[tuple[str, dict]]) -> PipelineResult:
        results: list[tuple[str, ToolResult]] = []
        context: dict[str, Any] = {}
        try:
            iterator = iter(steps)
        except Exception:  # noqa: BLE001 - hostile step specs are a failed pipeline
            return PipelineResult(steps=[], success=False)
        try:
            for step in iterator:
                try:
                    step_name, step_params = step
                    merged = {**step_params, **context}
                    result = self._registry.execute(step_name, **merged)
                except Exception as exc:  # noqa: BLE001 - one bad step fails the pipeline
                    name = _step_name(step)
                    result = ToolResult(
                        success=False,
                        data={},
                        errors=[f"pipeline step failed safely: {format_error(exc)}"],
                        metadata={},
                    )
                    results.append((name, result))
                    break
                results.append((step_name, result))
                if not result.success:
                    break
                if isinstance(result.data, dict):
                    context.update(result.data)
        except Exception:  # noqa: BLE001 - hostile iterators degrade to partial result
            pass
        return PipelineResult(steps=results, success=all(r.success for _, r in results))

    def parallel(self, calls: list[tuple[str, dict]]) -> PipelineResult:
        results: list[tuple[str, ToolResult]] = []
        futures: dict[Any, str] = {}
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                for call in calls:
                    try:
                        name, params = call
                        future = pool.submit(self._registry.execute, name, **params)
                        futures[future] = name
                    except Exception as exc:  # noqa: BLE001
                        results.append((
                            _step_name(call),
                            ToolResult(
                                success=False,
                                data={},
                                errors=[
                                    f"parallel call failed safely: {format_error(exc)}"
                                ],
                                metadata={},
                            ),
                        ))
                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result()
                    except Exception as exc:  # noqa: BLE001
                        result = ToolResult(
                            success=False,
                            data={},
                            errors=[f"parallel call failed safely: {format_error(exc)}"],
                            metadata={},
                        )
                    if not isinstance(result, ToolResult):
                        result = ToolResult(
                            success=False,
                            data={},
                            errors=["parallel call returned non-result"],
                            metadata={},
                        )
                    results.append((futures[future], result))
        except Exception:  # noqa: BLE001 - hostile call specs degrade to partial result
            pass
        return PipelineResult(steps=results, success=all(r.success for _, r in results))

    def remember_with_learning(self, content: str, outcome: str = "NEUTRAL",
                                project: str = "", session: str = "", **kwargs) -> PipelineResult:
        steps = [
            (
                "school_remember",
                {
                    "content": content,
                    "outcome": outcome,
                    "project": project,
                    "session": session,
                    **kwargs,
                },
            ),
            ("school_conflict", {"content": content, "project": project}),
            ("school_deduplicate", {"content": content, "project": project}),
        ]
        return self.pipeline(steps)

    def trigger_background(self, task_type: str, **params) -> None:
        with contextlib.suppress(Exception):  # fail-open: queueing must never raise
            self._background_tasks.append(BackgroundTask(task_type=task_type, params=params))

    def process_background(self) -> list[ToolResult]:
        results: list[ToolResult] = []
        while self._background_tasks:
            task = self._background_tasks.pop(0)
            try:
                result = self._registry.execute(task.task_type, **task.params)
            except Exception as exc:  # noqa: BLE001 - fail-open
                result = ToolResult(
                    success=False,
                    data={},
                    errors=[f"background task failed safely: {format_error(exc)}"],
                    metadata={},
                )
            results.append(result)
        return results


def _step_name(step: Any) -> str:
    """Best-effort name extraction from a pipeline step spec."""
    try:
        name = step[0]
        return name if isinstance(name, str) else repr(name)[:50]
    except Exception:  # noqa: BLE001
        return "<invalid step>"
