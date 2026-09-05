"""Tests for ecos diff_broker (BET-Y1Q3-T10-115): 100% interception semantics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecos.governance.diff_broker import check_draft, enforce, load_rules


def _seed_rules(tmp_path: Path) -> Path:
    rules = [
        {"rule_id": "HN-001", "rule_type": "banned_phrase",
         "pattern": "为进一步推进", "description": "署名中 4 次删除该表述", "count": 4},
        {"rule_id": "HN-002", "rule_type": "terminology_replace",
         "pattern": "高度重视", "description": "署名偏好删除该表述", "count": 3},
    ]
    p = tmp_path / "rules.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rules), encoding="utf-8")
    return p


def test_check_draft_rejects_rule_hit(tmp_path: Path):
    rules = load_rules(_seed_rules(tmp_path))
    verdict = check_draft("为进一步推进健康平台建设，特此通知。", rules)
    assert verdict.allowed is False
    assert verdict.violations and verdict.violations[0].rule_id == "HN-001"


def test_check_draft_allows_clean_draft(tmp_path: Path):
    rules = load_rules(_seed_rules(tmp_path))
    verdict = check_draft("健康平台由各单位落实数据互通。", rules)
    assert verdict.allowed is True and verdict.violations == []
    assert verdict.rules_checked == 2


def test_enforce_raises_on_violation(tmp_path: Path):
    rules = load_rules(_seed_rules(tmp_path))
    with pytest.raises(ValueError, match="DIFF_BROKER_REJECTED"):
        enforce("方案要求各级单位高度重视数据安全。", rules)
    assert enforce("数据安全由各单位落实。", rules) == "数据安全由各单位落实。"


def test_missing_rules_library_is_empty_and_permissive(tmp_path: Path):
    rules = load_rules(tmp_path / "nonexistent.jsonl")
    assert rules == []
    assert check_draft("任意草稿。", rules).allowed is True


def test_intercepts_original_draft_of_mined_sample(tmp_path: Path):
    """done_when[1]: 被萃取出规则的原始初稿 100% 被拦截。"""
    rules = load_rules(_seed_rules(tmp_path))
    original_draft = "为进一步推进该项工作，请各单位高度重视。"
    verdict = check_draft(original_draft, rules)
    assert verdict.allowed is False
    assert len(verdict.violations) >= 1
