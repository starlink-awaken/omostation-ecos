"""Tests for L0 role + distributed coordination primitives."""

import sys
from pathlib import Path

import pytest

ECOS_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(ECOS_SRC))


class TestRoleRegistry:
    def test_default_roles(self):
        from ecos.l0.role.role_registry import RoleRegistry
        reg = RoleRegistry()
        roles = reg.list_roles()
        assert "orchestrator" in roles
        assert "executor" in roles
        assert "auditor" in roles

    def test_check_capability(self):
        from ecos.l0.role.role_registry import RoleRegistry
        reg = RoleRegistry()
        assert reg.check_capability("orchestrator", "schedule")
        assert reg.check_capability("executor", "execute")
        assert not reg.check_capability("executor", "schedule")

    def test_register_role(self):
        from ecos.l0.role.role_registry import RoleRegistry
        reg = RoleRegistry()
        reg.register_role("custom", {"capabilities": ["custom_op"], "description": "test"})
        assert "custom" in reg.list_roles()
        assert reg.check_capability("custom", "custom_op")

    def test_find_roles_with_capability(self):
        from ecos.l0.role.role_registry import RoleRegistry
        reg = RoleRegistry()
        roles = reg.find_roles_with_capability("execute")
        assert "executor" in roles


class TestCoordinationBus:
    def test_register_and_message(self):
        from ecos.l0.distributed.coordination import CoordinationBus
        bus = CoordinationBus()
        bus.register_agent("a1")
        bus.register_agent("a2")
        msg = bus.send_message("a1", "a2", {"task": "do_x"})
        assert msg["from"] == "a1"
        assert msg["to"] == "a2"

    def test_receive_messages(self):
        from ecos.l0.distributed.coordination import CoordinationBus
        bus = CoordinationBus()
        bus.register_agent("a1")
        bus.register_agent("a2")
        bus.send_message("a1", "a2", {"data": 1})
        bus.send_message("a1", "a2", {"data": 2})
        msgs = bus.receive_messages("a2")
        assert len(msgs) == 2

    def test_broadcast(self):
        from ecos.l0.distributed.coordination import CoordinationBus
        bus = CoordinationBus()
        for a in ["a1", "a2", "a3"]:
            bus.register_agent(a)
        msgs = bus.broadcast("a1", {"alert": "test"})
        assert len(msgs) == 2  # to a2 and a3

    def test_claim_task(self):
        from ecos.l0.distributed.coordination import CoordinationBus
        bus = CoordinationBus()
        assert bus.claim_task("task1", "a1")
        assert not bus.claim_task("task1", "a2")  # already claimed
        assert bus.release_task("task1", "a1")
        assert bus.claim_task("task1", "a2")  # now available

    def test_sync_state(self):
        from ecos.l0.distributed.coordination import CoordinationBus
        bus = CoordinationBus()
        bus.register_agent("a1")
        bus.sync_state("a1", {"status": "busy", "task": "t1"})
        state = bus.get_state("a1")
        assert state["status"] == "busy"
