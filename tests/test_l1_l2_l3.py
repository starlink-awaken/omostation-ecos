"""Tests for L1/L2/L3 minimal core."""

import sys
from pathlib import Path

import pytest

ECOS_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(ECOS_SRC))


class TestL1Scheduler:
    def test_emit_event(self):
        from ecos.l1.runtime.scheduler import L1Scheduler
        s = L1Scheduler()
        event = s.emit_event("test", "topic", {"key": "value"})
        assert "plane" in event
        assert event["topic"] == "topic"

    def test_schedule_step(self):
        from ecos.l1.runtime.scheduler import L1Scheduler
        s = L1Scheduler()
        result = s.schedule_step({"name": "s1", "action": "echo"})
        assert result["status"] == "scheduled"
        assert result["step"] == "s1"

    def test_execute_workflow(self):
        from ecos.l1.runtime.scheduler import L1Scheduler
        s = L1Scheduler()
        steps = [{"name": "s1", "action": "a"}, {"name": "s2", "action": "b"}]
        result = s.execute_workflow(steps)
        assert result["total"] == 2
        assert result["executed"] == 2

    def test_execution_log(self):
        from ecos.l1.runtime.scheduler import L1Scheduler
        s = L1Scheduler()
        s.schedule_step({"name": "s1"})
        s.schedule_step({"name": "s2"})
        assert len(s.execution_log) == 2


class TestL2KnowledgeEngine:
    def test_query_m1_by_type(self):
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        results = engine.query_m1(node_type="OMOTask")
        assert len(results) > 0

    def test_query_m1_by_id(self):
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        results = engine.query_m1(node_id="OMOTASK-P35-W1-W2-COMBO")
        assert len(results) == 1

    def test_query_m2(self):
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        results = engine.query_m2()
        assert len(results) > 0

    def test_get_relations(self):
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        rel = engine.get_relations("ACTION-ACP-IMPLEMENT")
        assert "id" in rel
        assert "depends_on" in rel
        assert "provides" in rel

    def test_search(self):
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        results = engine.search("战役")
        assert len(results) > 0


class TestL3Entry:
    def test_health(self):
        from ecos.l3.entry.api import L3Entry
        entry = L3Entry()
        health = entry.health()
        assert health["status"] == "ok"

    def test_get_m1(self):
        from ecos.l3.entry.api import L3Entry
        entry = L3Entry()
        results = entry.get_m1(node_id="OMOTASK-P35-W1-W2-COMBO")
        assert len(results) == 1

    def test_get_m2(self):
        from ecos.l3.entry.api import L3Entry
        entry = L3Entry()
        results = entry.get_m2()
        assert len(results) > 0

    def test_search(self):
        from ecos.l3.entry.api import L3Entry
        entry = L3Entry()
        results = entry.search("战役")
        assert len(results) > 0

    def test_execute(self):
        from ecos.l3.entry.api import L3Entry
        entry = L3Entry()
        result = entry.execute([{"name": "s1"}])
        assert result["total"] == 1
