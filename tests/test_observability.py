"""Tests for eCOS observability."""

import sys
from pathlib import Path

import pytest

ECOS_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(ECOS_SRC))


class TestObservability:
    def test_m1_status(self):
        from ecos.observability.health import m1_status
        status = m1_status()
        assert "ok" in status
        assert status["violations"] == 0

    def test_constraint_status(self):
        from ecos.observability.health import constraint_status
        status = constraint_status()
        assert status["ok"]

    def test_health_check(self):
        from ecos.observability.health import health_check
        health = health_check()
        assert "overall" in health
        assert health["overall"] in ("healthy", "degraded")
        assert "reasoning" in health
        assert "constraints" in health
        assert "m1" in health

    def test_metrics(self):
        from ecos.observability.health import metrics
        m = metrics()
        assert "health" in m
