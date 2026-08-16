"""Data models for MOF Policy Compiler and Runtime Governance."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class RuleSeverity(str, Enum):
    REQUIRED = "required"       # 强拦截 (必须满足，违规直接阻断)
    PREFERRED = "preferred"     # 软告警 (建议满足，违规产生 warning)
    IMMUTABLE = "immutable"     # 不可变更 (系统核心基线)


@dataclass(frozen=True)
class ViolationReport:
    rule_id: str
    violation_code: str
    severity: RuleSeverity
    summary: str
    detail: str
    remediation: str
    line_number: int | None = None
    offending_symbol: str | None = None
    suggested_patch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "rule_id": self.rule_id,
            "violation_code": self.violation_code,
            "severity": self.severity.value,
            "summary": self.summary,
            "detail": self.detail,
            "remediation": self.remediation,
            "line_number": self.line_number,
            "offending_symbol": self.offending_symbol,
        }
        if self.suggested_patch is not None:
            d["suggested_patch"] = self.suggested_patch
        return d


@dataclass
class EvaluationResult:
    passed: bool
    violations: list[ViolationReport] = field(default_factory=list)

    @property
    def has_required_violations(self) -> bool:
        return any(v.severity in (RuleSeverity.REQUIRED, RuleSeverity.IMMUTABLE) for v in self.violations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
        }


@dataclass(frozen=True)
class PolicyRule:
    id: str
    dimension: str
    severity: RuleSeverity
    description: str
    rule_expr: str
    applies_to: list[str]
    violation_code: str
    remediation_hint: str
    evaluator: Callable[[dict[str, Any]], tuple[bool, str | None]] | None = None
    suggested_patch_template: str | None = None
    examples: list[dict[str, str]] = field(default_factory=list)


@dataclass
class CompiledPolicySet:
    version: str
    generated: str
    rules: dict[str, PolicyRule] = field(default_factory=dict)
    _by_dimension: dict[str, list[PolicyRule]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._index_rules()

    def _index_rules(self) -> None:
        self._by_dimension.clear()
        for rule in self.rules.values():
            self._by_dimension.setdefault(rule.dimension, []).append(rule)

    def add_rule(self, rule: PolicyRule) -> None:
        self.rules[rule.id] = rule
        self._by_dimension.setdefault(rule.dimension, []).append(rule)

    def get_rule(self, rule_id: str) -> PolicyRule | None:
        return self.rules.get(rule_id)

    def get_rules_by_dimension(self, dimension: str) -> list[PolicyRule]:
        return self._by_dimension.get(dimension, [])

    def __len__(self) -> int:
        return len(self.rules)
