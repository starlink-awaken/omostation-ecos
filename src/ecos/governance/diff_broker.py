"""Diff broker — 负样本硬规则 100% 拦截闸 (BET-Y1Q3-T10-115).

初稿生成侧的 MOF 动态约束接入点: 消费 hard_negative_miner 提炼的规则库
(``.omo/state/hard-negative-rules.jsonl``), 对命中负样本硬规则的草稿
返回 rejected + 违规明细。100% 拦截语义 = 规则命中即拒绝, 无豁免通道。

形态参照同目录 dlp_broker.py (规则引擎热路径, 零模型依赖)。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "ecos.governance.diff_broker.v1"
DEFAULT_RULES_REL = ".omo/state/hard-negative-rules.jsonl"


@dataclass(slots=True)
class CompiledRule:
    rule_id: str
    rule_type: str
    pattern: re.Pattern[str]
    description: str
    count: int


@dataclass(slots=True)
class Violation:
    rule_id: str
    rule_type: str
    description: str
    matched_text: str
    position: int


@dataclass(slots=True)
class DraftVerdict:
    allowed: bool
    violations: list[Violation] = field(default_factory=list)
    rules_checked: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "allowed": self.allowed,
            "rules_checked": self.rules_checked,
            "violation_count": len(self.violations),
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "rule_type": v.rule_type,
                    "description": v.description,
                    "matched_text": v.matched_text[:60],
                    "position": v.position,
                }
                for v in self.violations
            ],
        }


def load_rules(rules_path: str | Path | None = None) -> list[CompiledRule]:
    """Load and compile the hard-negative rule library (JSONL)."""
    p = Path(rules_path) if rules_path else None
    if p is None:
        cwd = Path.cwd()
        for parent in [cwd, *cwd.parents]:
            if (parent / "docs" / "project-registry.yaml").is_file():
                p = parent / DEFAULT_RULES_REL
                break
    if p is None or not Path(p).exists():
        return []
    rules: list[CompiledRule] = []
    with Path(p).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                compiled = re.compile(raw.get("pattern", ""))
            except re.error:
                continue
            rules.append(
                CompiledRule(
                    rule_id=str(raw.get("rule_id", "")),
                    rule_type=str(raw.get("rule_type", "")),
                    pattern=compiled,
                    description=str(raw.get("description", "")),
                    count=int(raw.get("count", 0)),
                )
            )
    return rules


def check_draft(text: str, rules: list[CompiledRule] | None = None) -> DraftVerdict:
    """Hard gate: any rule hit => allowed=False (no exemption channel)."""
    if rules is None:
        rules = load_rules()
    violations: list[Violation] = []
    for rule in rules:
        m = rule.pattern.search(text)
        if m:
            violations.append(
                Violation(
                    rule_id=rule.rule_id,
                    rule_type=rule.rule_type,
                    description=rule.description,
                    matched_text=m.group(0),
                    position=m.start(),
                )
            )
    return DraftVerdict(allowed=not violations, violations=violations, rules_checked=len(rules))


def enforce(text: str, rules: list[CompiledRule] | None = None) -> str:
    """Hard gate that raises when the draft violates rules (MOF constraint hook)."""
    verdict = check_draft(text, rules)
    if not verdict.allowed:
        details = "; ".join(f"{v.rule_id}:{v.description}" for v in verdict.violations[:5])
        raise ValueError(f"DIFF_BROKER_REJECTED: 草稿命中负样本硬规则 — {details}")
    return text
