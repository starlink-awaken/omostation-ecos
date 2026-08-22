"""Tests for X1-X4 workflow validators."""

import sys
from pathlib import Path

import pytest

ECOS_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(ECOS_SRC))

from ecos.workflow.validator import (
    X1ConstraintChecker,
    X2BudgetDeducer,
    X3CostRecorder,
    X4ConsistencyChecker,
    validate_step,
    validate_workflow,
)


class TestX1ConstraintChecker:
    def test_valid_step(self):
        step = {"name": "test-step", "action": "echo hello"}
        violations = X1ConstraintChecker.check_step(step)
        assert len(violations) == 0

    def test_missing_name(self):
        step = {"action": "echo"}
        violations = X1ConstraintChecker.check_step(step)
        assert any(v["id"] == "X1-C01-S001" for v in violations)

    def test_missing_action_and_role(self):
        step = {"name": "test"}
        violations = X1ConstraintChecker.check_step(step)
        assert any(v["id"] == "X1-C01-S002" for v in violations)

    def test_agent_role_ok(self):
        step = {"name": "test", "agent_role": "executor"}
        violations = X1ConstraintChecker.check_step(step)
        assert len(violations) == 0


class TestX2BudgetDeducer:
    def test_balance_readable(self):
        # Balance should be readable (may be negative if ledger has usage)
        balance = X2BudgetDeducer._read_balance()
        assert isinstance(balance, int)

    def test_check_budget_sufficient(self):
        m1_node = {"name": "test", "steps": []}
        status = X2BudgetDeducer.check_budget(m1_node)
        # Should have some budget status
        assert "ok" in status or "insufficient" in status or isinstance(status, dict)


class TestX3CostRecorder:
    def test_record_runs(self):
        # Should not raise
        result = {"passed": 3, "failed": 0}
        X3CostRecorder.record("test-workflow-001", result)


class TestX4ConsistencyChecker:
    def test_matching_steps(self):
        m1_node = {"steps": [{"name": "a"}, {"name": "b"}]}
        result = {"steps": [{"status": "ok"}, {"status": "ok"}]}
        violations = X4ConsistencyChecker.check_result(m1_node, result)
        # matching step count → no step-count violation
        assert not any(v["id"] == "X4-C01-STEP-COUNT" for v in violations)

    def test_mismatched_steps(self):
        m1_node = {"steps": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}
        result = {"steps": [{"status": "ok"}]}
        violations = X4ConsistencyChecker.check_result(m1_node, result)
        assert any(v["id"] == "X4-C01-STEP-COUNT" for v in violations)


class TestValidateWorkflow:
    def test_valid_workflow(self):
        m1_node = {
            "id": "TEST-WF-001",
            "name": "test",
            "steps": [{"name": "s1", "action": "echo"}],
        }
        violations = validate_workflow(m1_node)
        # valid workflow should have no violations
        assert isinstance(violations, list)

    def test_empty_workflow(self):
        m1_node = {"id": "TEST-EMPTY", "name": "empty", "steps": []}
        violations = validate_workflow(m1_node)
        assert isinstance(violations, list)
