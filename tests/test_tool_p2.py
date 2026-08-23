"""Tests for P2 Essential tools."""
import subprocess, sys
from pathlib import Path
import pytest

TOOLS = Path(__file__).resolve().parent.parent / "src" / "ecos" / "ssot" / "tools"

P2_TOOLS = [
    ("mof-relation-builder", []),
    ("mof-bridge-match", ["--threshold", "0.08"]),
    ("mof-bridge-sync", []),
    ("mof-state-bridge", []),
    ("mof-sla", ["--snapshot-only"]),
    ("mof-audit", []),
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

class TestP2:
    @pytest.mark.parametrize("tool,args", P2_TOOLS)
    def test_p2_runs(self, tool, args):
        rc, out = _run(tool, args)
        assert rc == 0, f"{tool} failed: {out[:100]}"
