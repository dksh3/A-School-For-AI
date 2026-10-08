"""Integration tests for the full orchestrator + tools pipeline."""
from core.routing.v26.factory import create_orchestrator


class TestFullPipeline:
    def test_all_tools_registered(self):
        orch = create_orchestrator()
        tools = orch._registry.list_tools()
        assert len(tools) == 22  # 10 original + 7 skillgen + 5 github (Phase 2)

    def test_dispatch_status(self):
        orch = create_orchestrator()
        r = orch.dispatch("school_status")
        assert r.success is True

    def test_dispatch_confidence(self):
        orch = create_orchestrator()
        r = orch.dispatch("school_confidence", content="test", prediction="out")
        assert r.success is True
        assert "confidence" in r.data

    def test_dispatch_remember_and_recall(self):
        orch = create_orchestrator()
        r_store = orch.dispatch("school_remember", content="test memory", outcome="SUCCESS")
        assert r_store.success is True
        r_recall = orch.dispatch("school_recall", query="test")
        assert r_recall.success is True

    def test_dispatch_conflict(self):
        orch = create_orchestrator()
        r = orch.dispatch("school_conflict", content="test content")
        assert r.success is True
        assert "conflicts" in r.data

    def test_dispatch_deduplicate(self):
        orch = create_orchestrator()
        r = orch.dispatch("school_deduplicate", content="test content")
        assert r.success is True
        assert "duplicates" in r.data

    def test_dispatch_lifecycle(self):
        orch = create_orchestrator()
        # Store a memory first so we have a valid memory_id
        r_store = orch.dispatch("school_remember", content="lifecycle test", outcome="SUCCESS")
        assert r_store.success is True
        memory_id = r_store.data.get("experience_id") or r_store.data.get("id")
        r = orch.dispatch("school_lifecycle", action="score", memory_id=memory_id)
        assert r.success is True

    def test_dispatch_diagnose(self):
        orch = create_orchestrator()
        r = orch.dispatch("school_diagnose")
        assert r.success is True
        assert "health" in r.data

    def test_pipeline_sequential(self):
        orch = create_orchestrator()
        result = orch.pipeline([
            ("school_remember", {"content": "pipeline test", "outcome": "SUCCESS"}),
            ("school_conflict", {"content": "pipeline test"}),
        ])
        assert result.success is True
        assert len(result.steps) == 2
