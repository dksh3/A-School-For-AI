"""Tests for background worker."""
from core.routing.v26.background import BackgroundWorker
from core.routing.v26.orchestrator import Orchestrator
from core.routing.v26.tools.base import Tool, ToolRegistry, ToolResult


class MockTool(Tool):
    def __init__(self, tool_name: str):
        self._name = tool_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Mock {self._name}"

    @property
    def schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"executed": self._name}, errors=[], metadata={})


class TestBackgroundWorker:
    def test_on_memory_stored_below_threshold(self):
        registry = ToolRegistry()
        registry.register(MockTool("school_knowledge"))
        orch = Orchestrator(registry)
        worker = BackgroundWorker(orch, {"consolidation_threshold": 5})
        for _ in range(4):
            worker.on_memory_stored()
        assert len(orch._background_tasks) == 0

    def test_on_memory_stored_triggers_at_threshold(self):
        registry = ToolRegistry()
        registry.register(MockTool("school_knowledge"))
        orch = Orchestrator(registry)
        worker = BackgroundWorker(orch, {"consolidation_threshold": 3})
        for _ in range(3):
            worker.on_memory_stored()
        assert len(orch._background_tasks) == 1
        assert worker._memory_count == 0

    def test_run_cycle_processes_tasks(self):
        registry = ToolRegistry()
        registry.register(MockTool("school_knowledge"))
        orch = Orchestrator(registry)
        orch.trigger_background("school_knowledge")
        worker = BackgroundWorker(orch)
        results = worker.run_cycle()
        assert len(results) == 1
        assert results[0].success
