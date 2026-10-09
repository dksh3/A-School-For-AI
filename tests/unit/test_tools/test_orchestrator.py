"""Tests for orchestrator."""
from core.routing.v26.orchestrator import Orchestrator
from core.routing.v26.tools.base import Tool, ToolRegistry, ToolResult


class MockTool(Tool):
    def __init__(self, tool_name: str, success: bool = True):
        self._name = tool_name
        self._success = success

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Mock tool {self._name}"

    @property
    def schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=self._success, data={"tool": self._name, **kwargs}, errors=[], metadata={}
        )


class TestOrchestrator:
    def test_dispatch_success(self):
        registry = ToolRegistry()
        tool = MockTool("test_tool")
        registry.register(tool)
        orch = Orchestrator(registry)
        result = orch.dispatch("test_tool", key="value")
        assert result.success
        assert result.data["tool"] == "test_tool"
        assert result.data["key"] == "value"

    def test_dispatch_unknown_tool(self):
        registry = ToolRegistry()
        orch = Orchestrator(registry)
        result = orch.dispatch("nonexistent")
        assert not result.success
        assert "Unknown tool" in result.errors[0]

    def test_pipeline_success(self):
        registry = ToolRegistry()
        registry.register(MockTool("step1"))
        registry.register(MockTool("step2"))
        orch = Orchestrator(registry)
        result = orch.pipeline([("step1", {"a": 1}), ("step2", {"b": 2})])
        assert result.success
        assert len(result.steps) == 2

    def test_pipeline_stops_on_failure(self):
        registry = ToolRegistry()
        registry.register(MockTool("step1", success=False))
        registry.register(MockTool("step2"))
        orch = Orchestrator(registry)
        result = orch.pipeline([("step1", {}), ("step2", {})])
        assert not result.success
        assert len(result.steps) == 1

    def test_parallel_success(self):
        registry = ToolRegistry()
        registry.register(MockTool("tool1"))
        registry.register(MockTool("tool2"))
        orch = Orchestrator(registry)
        result = orch.parallel([("tool1", {}), ("tool2", {})])
        assert result.success
        assert len(result.steps) == 2

    def test_trigger_and_process_background(self):
        registry = ToolRegistry()
        registry.register(MockTool("bg_task"))
        orch = Orchestrator(registry)
        orch.trigger_background("bg_task", x=1)
        assert len(orch._background_tasks) == 1
        results = orch.process_background()
        assert len(results) == 1
        assert results[0].success
        assert len(orch._background_tasks) == 0

    def test_process_background_empty(self):
        registry = ToolRegistry()
        orch = Orchestrator(registry)
        results = orch.process_background()
        assert results == []
