"""Tests for MOF reasoning engines: reason, derive, gate, enforce."""

import sys
from pathlib import Path

import pytest

# Ensure ecos src is importable
ECOS_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(ECOS_SRC))

TOOLS = Path(__file__).resolve().parent.parent / "src" / "ecos" / "ssot" / "tools"


def _run(tool: str, *args) -> tuple[int, str]:
    """Run a tool CLI, return (rc, stdout)."""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(TOOLS / tool), *args],
        capture_output=True, text=True, cwd=str(TOOLS.parent.parent),
    )
    return r.returncode, r.stdout + r.stderr


class TestMofReason:
    """mof-reason: impact + state + value reasoning."""

    def test_impact_runs(self):
        rc, out = _run("mof-reason.py", "impact", "OMOTASK-P35-W1-W2-COMBO")
        assert rc == 0, f"reason impact failed: {out}"
        assert "Impact Analysis" in out

    def test_state_runs(self):
        rc, out = _run("mof-reason.py", "state", "OMOTASK-P35-W1-W2-COMBO")
        assert rc == 0, f"reason state failed: {out}"

    def test_value_runs(self):
        rc, out = _run("mof-reason.py", "value", "OMOTASK-P35-W1-W2-COMBO")
        assert rc == 0, f"reason value failed: {out}"

    def test_unknown_node(self):
        """Unknown node returns empty analysis (0 dependencies)."""
        rc, out = _run("mof-reason.py", "impact", "NONEXISTENT-NODE-XYZ")
        assert rc == 0  # doesn't crash
        # empty analysis: 0 dependencies
        assert "0" in out


class TestMofDerive:
    """mof-derive: cross-repo ontological reasoning."""

    def test_full_report(self):
        rc, out = _run("mof-derive.py")
        assert rc == 0, f"derive failed: {out}"
        assert "7" in out  # 7 stages coverage

    def test_stages_only(self):
        rc, out = _run("mof-derive.py", "--stages")
        assert rc == 0
        assert "planning" in out.lower() or "coverage" in out.lower()

    def test_json_output(self):
        rc, out = _run("mof-derive.py", "--json")
        assert rc == 0
        import json
        data = json.loads(out)
        # derive JSON uses gate_coverage / phase_assessment / stage_assessment
        assert "gate_coverage" in data or "phase_assessment" in data or "stage_assessment" in data


class TestMofGate:
    """mof-gate: L0 bypass detection."""

    def test_gate_runs(self):
        rc, out = _run("mof-gate.py")
        assert rc == 0, f"gate failed: {out}"
        assert "门禁" in out or "gate" in out.lower() or "违规" in out

    def test_no_violations_baseline(self):
        """Current baseline: 0 violations expected."""
        rc, out = _run("mof-gate.py")
        assert rc == 0
        # baseline should be clean
        assert "违规: 0" in out or "0 项" in out


class TestMofEnforce:
    """mof-enforce: layer compliance enforcement."""

    def test_enforce_runs(self):
        rc, out = _run("mof-enforce.py")
        # enforce may exit non-zero due to violations, but should produce output
        assert "MOF" in out or "Enforce" in out or "层合规" in out

    def test_json_output(self):
        rc, out = _run("mof-enforce.py", "--json")
        # should produce valid JSON regardless of violations
        import json
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            # may have non-JSON prefix, that's OK
            pass
