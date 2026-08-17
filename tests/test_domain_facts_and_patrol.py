"""Tests for Domain Fact Inspector, Client Sync Enhancements, and Hygiene Patrol (ADR-0192)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from ecos.cli.constraint import main as cli_main
from ecos.ssot.compiler.fact_inspector import (
    FactInspectionResult,
    FactInspector,
)


@pytest.fixture
def temp_facts_dir(tmp_path: Path) -> Path:
    facts_dir = tmp_path / "_entities" / "facts"
    facts_dir.mkdir(parents=True)
    return facts_dir


def test_fact_inspector_valid_weijian_fact(temp_facts_dir: Path):
    fact_file = temp_facts_dir / "weijian_his_upgrade.yaml"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = {
        "schema_version": "v1.0",
        "entity_id": "FACT-WJ-2026-001",
        "domain": "work-weijian",
        "name": "市直医院 HIS 统一集成改造项目",
        "owner": "信息化推进处",
        "updated_at": now_iso,
        "lifecycle_stage": "IMPLEMENTATION",
        "facts": {
            "budget_million_cny": 12.5,
            "target_completion": "2026-12-31",
            "involved_hospitals": ["第一人民医院", "中医医院", "妇幼保健院"],
            "core_systems": ["统一门诊HIS", "电子病历EMR", "DRG结算引擎"],
            "security_level": "DJBH-3",
        },
    }
    fact_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    inspector = FactInspector()
    result: FactInspectionResult = inspector.inspect_file(fact_file)
    assert result.passed is True
    assert len(result.errors) == 0
    assert result.is_fresh is True
    assert result.entity_id == "FACT-WJ-2026-001"


def test_fact_inspector_missing_required_fields(temp_facts_dir: Path):
    fact_file = temp_facts_dir / "invalid_fact.yaml"
    data = {
        "domain": "work-weijian",
        # missing schema_version, entity_id, owner, updated_at, lifecycle_stage
        "facts": {"foo": "bar"},
    }
    fact_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    inspector = FactInspector()
    result = inspector.inspect_file(fact_file)
    assert result.passed is False
    assert len(result.errors) >= 3
    error_fields = [e.field for e in result.errors]
    assert "schema_version" in error_fields
    assert "entity_id" in error_fields
    assert "updated_at" in error_fields


def test_fact_inspector_freshness_stale_warning(temp_facts_dir: Path):
    fact_file = temp_facts_dir / "stale_fact.yaml"
    old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    data = {
        "schema_version": "v1.0",
        "entity_id": "FACT-TF-2026-009",
        "domain": "work-transfer",
        "name": "多模态超声 AI 辅助诊断转化项目",
        "owner": "成果转化一部",
        "updated_at": old_date,
        "lifecycle_stage": "PILOT",
        "facts": {
            "trl_level": 7,
            "lead_inventor": "张教授团队",
            "patent_ids": ["ZL202510123456.7"],
        },
    }
    fact_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    inspector = FactInspector(max_age_days=14)
    result = inspector.inspect_file(fact_file)
    assert result.passed is True  # Format is valid
    assert result.is_fresh is False
    assert result.age_days >= 30
    assert "超过 14 天保鲜 SLA" in str(result.freshness_warning)


def test_fact_inspector_template_generation():
    inspector = FactInspector()
    wj_tpl = inspector.generate_template("work-weijian")
    assert "work-weijian" in wj_tpl
    assert "schema_version" in wj_tpl
    assert "facts" in wj_tpl

    tf_tpl = inspector.generate_template("work-transfer")
    assert "work-transfer" in tf_tpl
    assert "trl_level" in tf_tpl

    generic_tpl = inspector.generate_template("generic")
    assert "generic" in generic_tpl


def test_cli_facts_validate_command(temp_facts_dir: Path, capsys: pytest.CaptureFixture):
    fact_file = temp_facts_dir / "test_fact.yaml"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = {
        "schema_version": "v1.0",
        "entity_id": "FACT-GEN-001",
        "domain": "default",
        "name": "通用测试事实",
        "owner": "运维架构组",
        "updated_at": now_iso,
        "lifecycle_stage": "OPERATIONAL",
        "facts": {"status": "ACTIVE"},
    }
    fact_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    # JSON mode
    exit_code = cli_main(["facts", "validate", str(temp_facts_dir), "--json"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    res_json = json.loads(captured)
    assert res_json["files_scanned"] == 1
    assert res_json["valid_facts_count"] == 1
    assert res_json["violations_count"] == 0


def test_cli_facts_template_command(capsys: pytest.CaptureFixture):
    exit_code = cli_main(["facts", "template", "--domain", "work-weijian"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "schema_version: v1.0" in captured
    assert "domain: work-weijian" in captured


def test_cli_documents_sync_clients_options(capsys: pytest.CaptureFixture):
    # Dry run should pass without executing real writes
    exit_code = cli_main(["documents", "sync-clients", "--dry-run", "--json"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    res_json = json.loads(captured)
    assert "sync_results" in res_json
    assert len(res_json["sync_results"]) >= 4
    for item in res_json["sync_results"]:
        assert item["status"] in ("DRY_RUN_OK", "NOT_FOUND")


def test_cli_patrol_command(capsys: pytest.CaptureFixture, tmp_path: Path):
    report_file = tmp_path / "patrol_report.md"
    exit_code = cli_main(["patrol", "--output", str(report_file), "--json"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    res_json = json.loads(captured)
    assert "patrol_timestamp" in res_json
    assert "checks" in res_json
    assert "summary" in res_json
    assert report_file.exists()
    report_md = report_file.read_text(encoding="utf-8")
    assert "# 🛡️ 全域治理与双平面自动化巡检报告" in report_md
