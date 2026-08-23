"""Tests for modern MOF tools: scan, bridge-match, predictive-loop, constraint-compiler."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "src" / "ecos" / "ssot" / "tools"


def _run(tool: str, *args, cwd=None, env=None) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(TOOLS / tool), *args],
        capture_output=True, text=True,
        cwd=str(cwd or TOOLS.parent.parent),
        env=env,
    )
    return r.returncode, r.stdout + r.stderr


def _workspace_with_matching_omo_task(tmp_path: Path) -> dict[str, str]:
    task_dir = tmp_path / ".omo" / "tasks" / "active"
    task_dir.mkdir(parents=True)
    (task_dir / "P35-W1-W2-COMBO.yaml").write_text(
        """id: P35-W1-W2-COMBO
title: 战役 4 spawn 真替代 + CI 集成 omo audit (W1 + W2 合并)
description: P35-W1 战役 4 agora spawn 真替代
status: done
""",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["WORKSPACE_ROOT"] = str(tmp_path)
    return env


class TestMofScan:
    """mof-scan: M1 instance status compliance."""

    def test_check_status(self):
        rc, out = _run("mof-scan.py", "--check-status")
        assert rc == 0
        assert "不合规: 0" in out

    def test_summary(self):
        rc, out = _run("mof-scan.py", "--summary")
        assert rc == 0
        assert "总实例" in out or "total" in out.lower()

    def test_json_type_filter(self):
        rc, out = _run("mof-scan.py", "--json", "--type", "Protocol")
        assert rc == 0
        data = json.loads(out)
        assert data
        assert all(node["type"] == "Protocol" for node in data)

    def test_all_compliant(self):
        """All 1400 instances should be compliant."""
        rc, out = _run("mof-scan.py", "--check-status")
        assert rc == 0
        # should report 0 violations
        assert "0" in out.split("不合规:")[-1].split("\n")[0]


class TestMofBridgeMatch:
    """mof-bridge-match: content-based M1-tasks matching."""

    def test_matching_runs(self):
        rc, out = _run("mof-bridge-match.py", "--threshold", "0.08")
        assert rc == 0
        assert "配对成功" in out

    def test_finds_pairs(self, tmp_path):
        env = _workspace_with_matching_omo_task(tmp_path)
        rc, out = _run("mof-bridge-match.py", "--threshold", "0.2", env=env)
        assert rc == 0
        # should find at least some pairs
        lines = out.split("\n")
        pair_line = [l for l in lines if "配对成功" in l]
        assert len(pair_line) > 0
        count = int(pair_line[0].split(":")[-1].strip())
        assert count > 0
        assert "P35-W1-W2-COMBO" in out

    def test_json_output(self, tmp_path):
        env = _workspace_with_matching_omo_task(tmp_path)
        r = subprocess.run(
            [sys.executable, str(TOOLS / "mof-bridge-match.py"), "--json", "--threshold", "0.2"],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["m1_count"] > 0
        assert data["omo_count"] == 1
        assert any(
            pair["m1_id"] == "OMOTASK-P35-W1-W2-COMBO"
            and pair["omo_id"] == "P35-W1-W2-COMBO"
            for pair in data["pairs"]
        )


class TestMofPredictiveLoop:
    """mof-predictive-loop: unified governance report."""

    def test_healthy(self):
        rc, out = _run("mof-predictive-loop.py", cwd=TOOLS.parent.parent.parent.parent)
        assert rc == 0
        assert "healthy" in out.lower() or "PASS" in out

    def test_enforce_pass(self):
        rc, _ = _run("mof-predictive-loop.py", "--enforce", cwd=TOOLS.parent.parent.parent.parent)
        assert rc == 0  # healthy → exit 0

    def test_json(self):
        rc, out = _run("mof-predictive-loop.py", "--json", cwd=TOOLS.parent.parent.parent.parent)
        assert rc == 0
        data = json.loads(out)
        assert data["overall_status"] in ("healthy", "action_required")


class TestEcosConstraintCompiler:
    """ecos-constraint-compiler: YAML → executable module."""

    def test_compile(self):
        rc, out = _run("ecos-constraint-compiler.py")
        assert rc == 0
        assert "hash" in out.lower() or "PASS" in out

    def test_enforce_pass(self):
        rc, _ = _run("ecos-constraint-compiler.py", "--enforce")
        assert rc == 0  # all constraints pass in default state

    def test_json(self):
        rc, out = _run("ecos-constraint-compiler.py", "--json")
        assert rc == 0
        data = json.loads(out)
        failed = data.get("constraint_compiler", {}).get("failed_required", 0)
        assert failed == 0
