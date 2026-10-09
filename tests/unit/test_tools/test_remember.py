"""Tests for RememberTool."""
from core.routing.v26.memory_manager import MemoryManager
from core.routing.v26.tools.remember import RememberTool


def _make_tool():
    manager = MemoryManager()
    return RememberTool(manager)


def test_remember_tool_name():
    tool = _make_tool()
    assert tool.name == "school_remember"


def test_remember_tool_schema_has_content():
    tool = _make_tool()
    schema = tool.schema
    assert "content" in schema["properties"]
    assert "content" in schema["required"]


def test_remember_tool_validate_requires_content():
    tool = _make_tool()
    errors = tool.validate()
    assert len(errors) > 0
    assert "content" in errors[0]


def test_remember_tool_validate_with_content():
    tool = _make_tool()
    errors = tool.validate(content="test experience")
    assert errors == []


def test_remember_tool_execute_stores_experience():
    tool = _make_tool()
    result = tool.execute(content="learned that Python is useful")
    assert result.success is True
    assert "experience_id" in result.data
    assert result.data["stored"] is True


def test_remember_tool_execute_with_outcome():
    tool = _make_tool()
    result = tool.execute(content="debugged a bug", outcome="SUCCESS")
    assert result.success is True


def test_remember_tool_execute_invalid_outcome():
    tool = _make_tool()
    result = tool.execute(content="test", outcome="INVALID")
    assert result.success is False
    assert len(result.errors) > 0


def test_remember_tool_execute_with_tags():
    tool = _make_tool()
    result = tool.execute(content="tagged memory", tags=["python", "bugfix"])
    assert result.success is True


def test_remember_tool_execute_with_agent_id():
    _make_tool()
    result = _make_tool().execute(content="agent memory", agent_id="agent_42")
    assert result.success is True
