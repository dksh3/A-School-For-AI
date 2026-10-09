"""Tests for tool base classes."""
from core.routing.v26.tools.base import (
    BackgroundTask,
    PipelineResult,
    Tool,
    ToolRegistry,
    ToolResult,
)


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(success=True, data={"id": "123"}, errors=[], metadata={})
        assert r.success is True
        assert r.data == {"id": "123"}
        assert r.to_dict() == {"success": True, "data": {"id": "123"}, "errors": [], "metadata": {}}

    def test_error_result(self):
        r = ToolResult(success=False, data={}, errors=["bad input"], metadata={})
        assert r.success is False
        assert r.errors == ["bad input"]

    def test_to_dict_roundtrip(self):
        r = ToolResult(success=True, data={"a": 1}, errors=[], metadata={"t": 0.1})
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"] == {"a": 1}
        assert d["metadata"] == {"t": 0.1}


class ConcreteTool(Tool):
    @property
    def name(self) -> str:
        return "test_tool"

    @property
    def description(self) -> str:
        return "A test tool"

    @property
    def schema(self) -> dict:
        return {"input": {"type": "string"}}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=True, data={"input": kwargs.get("input", "")}, errors=[], metadata={}
        )


class TestTool:
    def test_tool_properties(self):
        t = ConcreteTool()
        assert t.name == "test_tool"
        assert t.description == "A test tool"
        assert "input" in t.schema

    def test_tool_execute(self):
        t = ConcreteTool()
        r = t.execute(input="hello")
        assert r.success is True
        assert r.data["input"] == "hello"

    def test_tool_validate_default(self):
        t = ConcreteTool()
        errors = t.validate(anything="value")
        assert errors == []


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = ConcreteTool()
        reg.register(tool)
        assert reg.get("test_tool") is tool

    def test_get_unknown(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(ConcreteTool())
        tools = reg.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"

    def test_execute_known_tool(self):
        reg = ToolRegistry()
        reg.register(ConcreteTool())
        r = reg.execute("test_tool", input="world")
        assert r.success is True
        assert r.data["input"] == "world"

    def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        r = reg.execute("nonexistent")
        assert r.success is False
        assert "Unknown tool" in r.errors[0]


class FailingTool(Tool):
    @property
    def name(self) -> str:
        return "failing"

    @property
    def description(self) -> str:
        return "Always fails"

    @property
    def schema(self) -> dict:
        return {}

    def validate(self, **kwargs) -> list[str]:
        if "required_field" not in kwargs:
            return ["required_field is missing"]
        return []

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=False, data={}, errors=["intentional failure"], metadata={})


class TestRegistryValidation:
    def test_validate_before_execute(self):
        reg = ToolRegistry()
        reg.register(FailingTool())
        r = reg.execute("failing")
        assert r.success is False
        assert "required_field is missing" in r.errors[0]

    def test_validate_pass(self):
        reg = ToolRegistry()
        reg.register(FailingTool())
        r = reg.execute("failing", required_field="value")
        assert r.success is False  # execute fails, but validation passed
        assert "required_field is missing" not in r.errors


class TestPipelineResult:
    def test_pipeline_result_success(self):
        r1 = ToolResult(success=True, data={"a": 1}, errors=[], metadata={})
        r2 = ToolResult(success=True, data={"b": 2}, errors=[], metadata={})
        pr = PipelineResult(steps=[("tool1", r1), ("tool2", r2)], success=True)
        assert pr.success is True
        d = pr.to_dict()
        assert len(d["steps"]) == 2
        assert d["steps"][0]["tool"] == "tool1"

    def test_pipeline_result_failure(self):
        r1 = ToolResult(success=False, data={}, errors=["fail"], metadata={})
        pr = PipelineResult(steps=[("tool1", r1)], success=False)
        assert pr.success is False


class TestBackgroundTask:
    def test_background_task_creation(self):
        import time
        bt = BackgroundTask(task_type="consolidate", params={"threshold": 10})
        assert bt.task_type == "consolidate"
        assert bt.params == {"threshold": 10}
        assert bt.created_at <= time.time()
