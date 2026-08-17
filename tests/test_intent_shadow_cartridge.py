"""Tests for IntentSpecCompiler, ShadowChallenger, and DomainCartridgeManager (ADR-0195, ADR-0196, ADR-0198)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from ecos.cli.constraint import main
from ecos.ssot.compiler.domain_cartridge import DomainCartridgeManager
from ecos.ssot.compiler.intent_compiler import IntentSpecCompiler
from ecos.ssot.compiler.shadow_challenger import ShadowChallenger


def test_intent_spec_compiler_weijian() -> None:
    compiler = IntentSpecCompiler()
    spec = compiler.compile("请帮我起草关于卫健委全民健康信息平台跨区域互联互通立项方案")

    assert spec.detected_domain == "work-weijian"
    assert len(spec.policy_requirements) >= 2
    assert any(p.rule_id == "E-POL-WJ-001" for p in spec.policy_requirements)
    assert any(p.rule_id == "E-POL-WJ-002" for p in spec.policy_requirements)
    assert len(spec.fact_requirements) >= 1
    assert len(spec.agent_dag) == 4
    assert spec.compute_budget is not None
    assert spec.compute_budget.speculative_draft_enabled is True


def test_intent_spec_compiler_transfer() -> None:
    compiler = IntentSpecCompiler()
    spec = compiler.compile("请评估某生物医药专利作价入股与科技成果赋权转化方案")

    assert spec.detected_domain == "work-transfer"
    assert any(p.rule_id == "E-POL-TF-001" for p in spec.policy_requirements)
    assert any(p.rule_id == "E-POL-TF-002" for p in spec.policy_requirements)


def test_shadow_challenger_adversarial_critique_and_autopatch() -> None:
    challenger = ShadowChallenger()
    flawed_text = """
    # 卫健委全民健康信息化二期工程
    项目预算总额 1200 万元人民币。
    将核心诊疗数据库直接托管于外部公有云环境。
    """

    report = challenger.challenge_text(flawed_text, domain="work-weijian", auto_patch=True)
    assert report.passed is False
    assert report.robustness_score < 70
    assert len(report.challenges) >= 2
    assert any(c.perspective == "AUDIT_FINANCE" for c in report.challenges)
    assert any(c.perspective == "CYBER_SECURITY" for c in report.challenges)
    assert report.patched_text is not None
    assert "影子红蓝对抗合规补强与审查批注" in report.patched_text


def test_domain_cartridge_manager_lifecycle() -> None:
    manager = DomainCartridgeManager()
    cartridges = manager.list_cartridges()
    assert len(cartridges) >= 2

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "test-weijian.yaml"
        exported = manager.export_cartridge("cartridge-weijian-v1", output_path=out_file)
        assert exported.exists()

        valid, errors = manager.validate_cartridge_file(exported)
        assert valid is True
        assert len(errors) == 0


def test_cli_v2_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    # 1. intent compile
    code = main(["intent", "compile", "卫生健康区域平台建设", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert "detected_domain" in out

    # 2. challenge
    code = main(["challenge", "预算 800 万元", "--domain", "work-weijian", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert "challenges" in out

    # 3. cartridge list
    code = main(["cartridge", "list", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert "cartridge-weijian-v1" in out
