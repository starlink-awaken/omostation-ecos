"""Tests for P2 Essential tools."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "src" / "ecos" / "ssot" / "tools"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _workspace_model_driven_m3(repo_root: Path = REPO_ROOT) -> Path | None:
    """Return the cross-repo M3 source only for a real workspace checkout."""
    projects_dir = repo_root.parent
    if projects_dir.name != "projects":
        return None
    candidate = projects_dir / "model-driven" / "src" / "model_driven" / "mof" / "m3_extended.py"
    return candidate if candidate.is_file() else None

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


def test_workspace_model_driven_m3_rejects_standalone_checkout(tmp_path: Path) -> None:
    assert _workspace_model_driven_m3(tmp_path / "ecos") is None


def test_workspace_model_driven_m3_accepts_initialized_workspace(tmp_path: Path) -> None:
    repo_root = tmp_path / "projects" / "ecos"
    source = tmp_path / "projects" / "model-driven" / "src" / "model_driven" / "mof" / "m3_extended.py"
    source.parent.mkdir(parents=True)
    source.write_text("# test source\n", encoding="utf-8")
    assert _workspace_model_driven_m3(repo_root) == source


def test_mof_enforce_uses_script_relative_boundary(tmp_path: Path) -> None:
    env = {**os.environ, "HOME": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(TOOLS / "mof-enforce.py"), "--no-cards"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr


class TestP2:
    @pytest.mark.parametrize("tool,args", P2_TOOLS)
    def test_p2_runs(self, tool, args):
        if tool == "mof-bridge-sync" and _workspace_model_driven_m3() is None:
            pytest.skip("mof-bridge-sync requires an initialized workspace model-driven sibling")
        rc, out = _run(tool, args)
        assert rc == 0, f"{tool} failed: {out[:100]}"
