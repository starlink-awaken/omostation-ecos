"""Unit tests for PolicyComplianceInspector, TruthCanvasServer, and PitfallInspector (ADR-0193 / ADR-0194)."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest
import yaml

from ecos.cli.constraint import main as constraint_cli
from ecos.ssot.compiler.pitfall_inspector import PitfallInspector
from ecos.ssot.compiler.policy_inspector import PolicyComplianceInspector
from ecos.ssot.compiler.truth_canvas_server import create_truth_canvas_server


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ── 1. PolicyComplianceInspector Tests (ADR-0193) ────────────────────────────


def test_policy_inspector_weijian_budget_violation(tmp_path: Path):
    doc = tmp_path / "high_budget_proposal.md"
    doc.write_text(
        "# 某市全民健康信息平台二期升级\n\n项目总投资预算 850 万元。拟采购通用服务器与数据库套件。\n",
        encoding="utf-8",
    )
    inspector = PolicyComplianceInspector()
    report = inspector.audit_file(doc, domain="work-weijian")
    assert report.passed is False
    assert any(v.rule_id == "E-POL-WJ-001" for v in report.violations)


def test_policy_inspector_weijian_compliant_proposal(tmp_path: Path):
    doc = tmp_path / "compliant_proposal.md"
    doc.write_text(
        "# 基层医疗卫生服务平台升级工程\n\n"
        "项目总投资 680 万元。经组织业内专家论证，全面采用信创自主可控软硬件架构。\n"
        "系统严格落实网络安全等保三级与互联互通四级乙等标准，具备端到端国密加密防护。\n",
        encoding="utf-8",
    )
    inspector = PolicyComplianceInspector()
    report = inspector.audit_file(doc)
    assert report.passed is True
    assert len(report.violations) == 0


def test_policy_inspector_transfer_reward_violation(tmp_path: Path):
    text = (
        "关于某超声 AI 科技成果赋权与作价入股方案："
        "科技成果完成团队所得收益分配比例拟定为 55%，其余归资产管理公司所有。"
    )
    inspector = PolicyComplianceInspector()
    report = inspector.audit_text(text, domain="work-transfer")
    assert report.passed is False
    assert any(v.rule_id == "E-POL-TF-001" for v in report.violations)


def test_policy_inspector_explain_and_list():
    inspector = PolicyComplianceInspector()
    rule = inspector.explain_policy("E-POL-WJ-001")
    assert rule is not None
    assert "专家论证" in rule.title

    all_policies = inspector.list_policies()
    assert len(all_policies) >= 4

    weijian_policies = inspector.list_policies(domain="work-weijian")
    assert len(weijian_policies) >= 2


# ── 2. TruthCanvasServer Tests (ADR-0194) ────────────────────────────────────


def test_truth_canvas_server_lifecycle_and_api(tmp_path: Path):
    facts_root = tmp_path / "Documents" / "@工作文档"
    weijian_facts = facts_root / "卫健委" / "_entities" / "facts"
    weijian_facts.mkdir(parents=True, exist_ok=True)

    fact_data = {
        "schema_version": "v1.0",
        "entity_id": "FACT-WJ-2026-TEST",
        "domain": "work-weijian",
        "name": "测试基层卫生信息工程",
        "owner": "规划信息处",
        "updated_at": "2026-08-17",
        "lifecycle_stage": "PILOT",
        "facts": {"budget_million": 4.5, "nodes": 12},
    }
    (weijian_facts / "fact-wj-2026-test.yaml").write_text(
        yaml.safe_dump(fact_data, allow_unicode=True), encoding="utf-8"
    )

    port = 8799
    server = create_truth_canvas_server(host="127.0.0.1", port=port, facts_dir=facts_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # 1. Health check
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "healthy"

        # 2. Get facts
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/facts", timeout=3) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["total_count"] >= 1
            assert data["facts"][0]["entity_id"] == "FACT-WJ-2026-TEST"

        # 3. Post new fact
        new_fact = {
            "schema_version": "v1.0",
            "entity_id": "FACT-TF-2026-POST",
            "domain": "work-transfer",
            "name": "多模态超声转化项目",
            "owner": "科技转化部",
            "updated_at": "2026-08-17",
            "lifecycle_stage": "IMPLEMENTATION",
            "facts": {"trl_level": 7},
        }
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/facts",
            data=json.dumps(new_fact).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            post_res = json.loads(resp.read().decode("utf-8"))
            assert post_res["success"] is True

        # Verify file persisted
        tf_file = facts_root / "国转中心" / "_entities" / "facts" / "fact-tf-2026-post.yaml"
        assert tf_file.exists()
    finally:
        server.shutdown()
        server.server_close()


# ── 3. PitfallInspector Tests (ADR-0194) ──────────────────────────────────────


def test_pitfall_inspector_detects_anti_patterns():
    inspector = PitfallInspector()

    # Code containing Gatekeeper mutation trap
    bad_code = "def save_data(p_out):\n    p_out.write_text('payload')\n"
    res = inspector.scan_text(bad_code)
    assert res.passed is False
    assert any(m.pitfall_id == "PITFALL-001" for m in res.matches)

    # Clean code
    clean_code = "def save_data(p_out):\n    with open(str(p_out), 'w', encoding='utf-8') as f:\n        f.write('payload')\n"
    res_clean = inspector.scan_text(clean_code)
    assert res_clean.passed is True


def test_pitfall_inspector_list_and_explain():
    inspector = PitfallInspector()
    all_p = inspector.list_pitfalls()
    assert len(all_p) >= 3
    p1 = inspector.explain_pitfall("PITFALL-001")
    assert p1 is not None
    assert "Gatekeeper" in p1.title


# ── 4. CLI Subcommand Tests ──────────────────────────────────────────────────


def test_cli_policy_and_pitfall_commands(capsys: pytest.CaptureFixture[str]):
    # 1. Policy list
    rc_list = constraint_cli(["policy", "list", "--json"])
    assert rc_list == 0
    out_list = capsys.readouterr().out
    assert "E-POL-WJ-001" in out_list

    # 2. Policy explain
    rc_exp = constraint_cli(["policy", "explain", "E-POL-WJ-001", "--json"])
    assert rc_exp == 0
    out_exp = capsys.readouterr().out
    assert "专家论证" in out_exp

    # 3. Pitfall list
    rc_p_list = constraint_cli(["pitfall", "list", "--json"])
    assert rc_p_list == 0
    out_p_list = capsys.readouterr().out
    assert "PITFALL-001" in out_p_list
