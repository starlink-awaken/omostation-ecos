"""Tests for Workspace x Documents Dual-Plane Governance (ADR-0191)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ecos.cli.constraint import main as constraint_main
from ecos.ssot.compiler.context_synthesizer import MOFContextSynthesizer
from ecos.ssot.compiler.path_inspector import PathBoundaryInspector


def test_path_boundary_inspector_edoc001_script_prohibition(tmp_path: Path):
    inspector = PathBoundaryInspector()
    target_path = "@/Documents/@工作文档/卫健委/sync_job.py"
    res = inspector.inspect_write(target_path, caller_domain="work-weijian")

    assert not res.passed
    assert len(res.violations) == 1
    v = res.violations[0]
    assert v.violation_code == "E-DOC-001"
    assert v.rule_id == "X4-C15"
    assert "禁止在 Documents 内容域写入可执行代码脚本" in v.summary
    assert v.suggested_patch is not None
    assert "scripts/work-weijian/sync_job.py" in v.suggested_patch


def test_path_boundary_inspector_edoc002_dependency_dir_prohibition():
    inspector = PathBoundaryInspector()
    target_path = "~/Documents/@家庭生活/node_modules/pkg/index.json"
    res = inspector.inspect_write(target_path, caller_domain="family")

    assert not res.passed
    assert any(v.violation_code == "E-DOC-002" for v in res.violations)
    v = [v for v in res.violations if v.violation_code == "E-DOC-002"][0]
    assert v.rule_id == "X4-C16"
    assert "禁止在 Documents 内容域引入依赖/缓存环境" in v.summary


def test_path_boundary_inspector_allows_clean_markdown():
    inspector = PathBoundaryInspector()
    target_path = "@/Documents/@工作文档/卫健委/_entities/facts/01-progress.yaml"
    res = inspector.inspect_write(target_path, caller_domain="work-weijian")
    assert res.passed


def test_synthesize_documents_guardrails():
    synthesizer = MOFContextSynthesizer()
    prompt = synthesizer.synthesize_documents_guardrails(domain_id="work-weijian")
    assert '<documents_dual_plane_guardrails domain="work-weijian">' in prompt
    assert "E-DOC-001" in prompt
    assert "E-DOC-002" in prompt
    assert "ADR-0191" in prompt


def test_explain_edoc_rules():
    synthesizer = MOFContextSynthesizer()
    e1 = synthesizer.explain_rule("E-DOC-001")
    assert e1 is not None
    assert e1["violation_code"] == "E-DOC-001"
    assert "code_recipe" in e1
    assert "Workspace/scripts" in e1["code_recipe"]["valid"]

    e2 = synthesizer.explain_rule("E-DOC-002")
    assert e2 is not None
    assert e2["violation_code"] == "E-DOC-002"
    assert "node_modules" in e2["code_recipe"]["invalid"]


def test_cli_documents_guardrail(capsys: pytest.CaptureFixture):
    code = constraint_main(["documents", "guardrail", "--domain", "work-weijian"])
    assert code == 0
    captured = capsys.readouterr().out
    assert "<documents_dual_plane_guardrails" in captured
    assert "E-DOC-001" in captured


def test_cli_documents_audit(tmp_path: Path, capsys: pytest.CaptureFixture):
    doc_dir = tmp_path / "Documents" / "@工作文档"
    doc_dir.mkdir(parents=True)
    bad_script = doc_dir / "bad_script.py"
    bad_script.write_text("print('hello')", encoding="utf-8")
    good_doc = doc_dir / "report.md"
    good_doc.write_text("# Report", encoding="utf-8")

    code = constraint_main(["documents", "audit", str(doc_dir), "--json"])
    assert code == 0  # not strict
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["files_scanned"] >= 2
    assert data["violations_count"] >= 1
    assert any(v["violation_code"] == "E-DOC-001" for v in data["violations"])


def test_cli_documents_sync_clients(capsys: pytest.CaptureFixture):
    code = constraint_main(["documents", "sync-clients", "--dry-run", "--json"])
    assert code == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "sync_results" in data
