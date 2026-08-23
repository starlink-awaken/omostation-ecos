"""Smoke tests for P0/P1 MOF tools."""
import subprocess, sys
from pathlib import Path
import pytest

TOOLS = Path(__file__).resolve().parent.parent / "src" / "ecos" / "ssot" / "tools"

P0_TOOLS = [
    ("ecos-constraint-compiler", ["--enforce"]),
    ("mof-scan", ["--check-status"]),
    ("mof-predictive-loop", ["--enforce"]),
    ("mof-reason", ["impact", "ACTION-ACP-IMPLEMENT"]),
]

P1_TOOLS = [
    ("mof-derive", []),
    ("mof-gate", []),
    ("mof-enforce", []),
    ("mof-relation-builder", []),
    ("mof-bridge-match", ["--threshold", "0.08"]),
    ("mof-state-bridge", []),
    ("mof-sla", ["--snapshot-only"]),
    ("mof-extract", ["--help"]),
    ("mof-events", []),
    ("mof-model", []),
    ("mof-capability", []),
    ("mof-register-tasks", []),
    ("mof-schema-validate", []),
    ("mof-verify", []),
    ("mof-view", []),
    ("mof-workflow", []),
]

def _run(tool, args):
    cmd = [sys.executable, str(TOOLS / f"{tool}.py")] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return -1, str(e)

class TestP0Core:
    @pytest.mark.parametrize("tool,args", P0_TOOLS)
    def test_p0_runs(self, tool, args):
        rc, out = _run(tool, args)
        assert rc == 0, f"{tool} failed: {out[:100]}"

class TestP1Active:
    @pytest.mark.parametrize("tool,args", P1_TOOLS)
    def test_p1_runs(self, tool, args):
        rc, out = _run(tool, args)
        assert rc == 0, f"{tool} failed: {out[:100]}"
