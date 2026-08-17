"""Domain Policy-as-Code Compliance Inspector (ADR-0193).

Enforces vertical domain business rules & regulatory constraints:
- Weijian Health Informatics policies (E-POL-WJ-001 ~ E-POL-WJ-004)
- Work-Transfer tech commercialization policies (E-POL-TF-001 ~ E-POL-TF-004)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class PolicyRuleDefinition:
    rule_id: str
    domain: str
    title: str
    severity: str  # BLOCK | WARN | ADVISORY
    description: str
    remediation: str


DOMAIN_POLICIES: Final[dict[str, PolicyRuleDefinition]] = {
    "E-POL-WJ-001": PolicyRuleDefinition(
        rule_id="E-POL-WJ-001",
        domain="work-weijian",
        title="重大信息化项目预算与专家论证门禁",
        severity="BLOCK",
        description="单体预算超过 500 万元的信息化建设项目，必须明确专家论证结论与信创软硬件适配清单。",
        remediation="在规划或方案中补充专家评审意见，并注明信创软硬件自主可控替代方案。",
    ),
    "E-POL-WJ-002": PolicyRuleDefinition(
        rule_id="E-POL-WJ-002",
        domain="work-weijian",
        title="医疗卫生网络安全三级等保与互联互通标准合规",
        severity="BLOCK",
        description="涉及医疗机构临床数据或全员人口信息的系统，必须明确网络安全等级保护三级（等保三级）与互联互通四级乙等以上要求。",
        remediation="方案中须明确注明【等保三级】与【互联互通测评】达标规划及加密安全措施。",
    ),
    "E-POL-TF-001": PolicyRuleDefinition(
        rule_id="E-POL-TF-001",
        domain="work-transfer",
        title="科技成果转化科研团队收益分配红线",
        severity="BLOCK",
        description="科技成果转让、许可或作价投资收益，给予科技成果完成人及团队的奖励比例不得低于 70%。",
        remediation="收益分配方案中明确团队留存或奖励比例 ≥ 70%，并符合成果转化法规定。",
    ),
    "E-POL-TF-002": PolicyRuleDefinition(
        rule_id="E-POL-TF-002",
        domain="work-transfer",
        title="产业化项目技术成熟度 (TRL) 准入审查",
        severity="WARN",
        description="进入中试验证或产业孵化阶段的科技转化项目，技术成熟度等级 (TRL) 必须达到 6 级及以上。",
        remediation="请提供第三方检测报告或样机/中试平台运行数据，证明 TRL 等级 ≥ 6。",
    ),
}


@dataclass(slots=True)
class PolicyViolation:
    rule_id: str
    domain: str
    title: str
    severity: str
    detail: str
    remediation: str


@dataclass(slots=True)
class PolicyAuditReport:
    target: str
    passed: bool
    domain: str
    total_checks: int
    violations: list[PolicyViolation] = field(default_factory=list)
    warnings: list[PolicyViolation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "passed": self.passed,
            "domain": self.domain,
            "total_checks": self.total_checks,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "title": v.title,
                    "severity": v.severity,
                    "detail": v.detail,
                    "remediation": v.remediation,
                }
                for v in self.violations
            ],
            "warnings": [
                {
                    "rule_id": w.rule_id,
                    "title": w.title,
                    "severity": w.severity,
                    "detail": w.detail,
                    "remediation": w.remediation,
                }
                for w in self.warnings
            ],
        }


class PolicyComplianceInspector:
    """Evaluates business documents, plans, and requirements against Policy-as-Code rules."""

    def __init__(self, custom_policies: dict[str, PolicyRuleDefinition] | None = None) -> None:
        self._policies = dict(DOMAIN_POLICIES)
        if custom_policies:
            self._policies.update(custom_policies)

    def explain_policy(self, policy_id: str) -> PolicyRuleDefinition | None:
        return self._policies.get(policy_id)

    def list_policies(self, domain: str | None = None) -> list[PolicyRuleDefinition]:
        if not domain:
            return list(self._policies.values())
        return [p for p in self._policies.values() if p.domain == domain or domain == "all"]

    def audit_text(self, text: str, domain: str = "auto", target_name: str = "in-memory-text") -> PolicyAuditReport:
        """Analyze text content against domain policies."""
        violations: list[PolicyViolation] = []
        warnings: list[PolicyViolation] = []

        # Domain deduction if auto
        detected_domain = domain
        if detected_domain == "auto":
            if any(k in text for k in ["卫生", "医疗", "卫健", "医院", "互联互通", "等保", "DRG", "健康", "信息化", "疾控"]):
                detected_domain = "work-weijian"
            elif any(k in text for k in ["转化", "专利", "技术成熟度", "TRL", "赋权", "中试", "产业化"]):
                detected_domain = "work-transfer"
            else:
                detected_domain = "general"

        applicable_rules = [p for p in self._policies.values() if detected_domain == "all" or p.domain == detected_domain]

        # 1. 卫健委预算门禁 (E-POL-WJ-001)
        if any(r.rule_id == "E-POL-WJ-001" for r in applicable_rules):
            budget_match = re.search(r"(?:预算|投资|总投资|金额)[^\d]*(\d+(?:\.\d+)?)\s*(?:万|百万元)", text)
            if budget_match:
                budget_num = float(budget_match.group(1))
                if budget_num > 500.0:
                    if not any(k in text for k in ["专家论证", "专家评审", "信创", "自主可控"]):
                        rule = self._policies["E-POL-WJ-001"]
                        violations.append(
                            PolicyViolation(
                                rule_id=rule.rule_id,
                                domain=rule.domain,
                                title=rule.title,
                                severity=rule.severity,
                                detail=f"项目总预算为 {budget_num} 万元 (>500万)，但未包含专家论证结论或信创适配清单。",
                                remediation=rule.remediation,
                            )
                        )

        # 2. 卫健委等保与互联互通门禁 (E-POL-WJ-002)
        if any(r.rule_id == "E-POL-WJ-002" for r in applicable_rules):
            if any(k in text for k in ["临床", "诊疗", "电子病历", "健康档案", "全员人口", "区域平台", "HIS", "公有云"]):
                if not any(k in text for k in ["等保三级", "三级等保", "等保3级", "第三级"]):
                    rule = self._policies["E-POL-WJ-002"]
                    violations.append(
                        PolicyViolation(
                            rule_id=rule.rule_id,
                            domain=rule.domain,
                            title=rule.title,
                            severity=rule.severity,
                            detail="系统处理核心医疗/临床数据，但未明确提出网络安全【等保三级】达标要求。",
                            remediation=rule.remediation,
                        )
                    )

        # 3. 国转中心收益分配比例 (E-POL-TF-001)
        if any(r.rule_id == "E-POL-TF-001" for r in applicable_rules):
            reward_match = re.search(r"(?:奖励比例|分配比例|团队分配|所得收益)[^\d]*(\d+(?:\.\d+)?)\s*%", text)
            if reward_match:
                reward_ratio = float(reward_match.group(1))
                if reward_ratio < 70.0:
                    rule = self._policies["E-POL-TF-001"]
                    violations.append(
                        PolicyViolation(
                            rule_id=rule.rule_id,
                            domain=rule.domain,
                            title=rule.title,
                            severity=rule.severity,
                            detail=f"科研团队转化收益分配比例为 {reward_ratio}%，低于国家政策规定的 70% 红线标准。",
                            remediation=rule.remediation,
                        )
                    )

        # 4. 国转中心技术成熟度 TRL (E-POL-TF-002)
        if any(r.rule_id == "E-POL-TF-002" for r in applicable_rules):
            if any(k in text for k in ["产业化", "中试", "规模化生产", "投资入股"]):
                trl_match = re.search(r"(?:TRL|成熟度)[^\d]*([1-9])\s*级?", text, re.IGNORECASE)
                if trl_match:
                    trl_level = int(trl_match.group(1))
                    if trl_level < 6:
                        rule = self._policies["E-POL-TF-002"]
                        warnings.append(
                            PolicyViolation(
                                rule_id=rule.rule_id,
                                domain=rule.domain,
                                title=rule.title,
                                severity=rule.severity,
                                detail=f"产业化转化项目当前 TRL 成熟度为 {trl_level} 级，建议达到 6 级以上以降低产业化风险。",
                                remediation=rule.remediation,
                            )
                        )

        passed = len(violations) == 0
        return PolicyAuditReport(
            target=target_name,
            passed=passed,
            domain=detected_domain,
            total_checks=len(applicable_rules),
            violations=violations,
            warnings=warnings,
        )

    def audit_file(self, file_path: str | Path, domain: str = "auto") -> PolicyAuditReport:
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            return PolicyAuditReport(
                target=str(p),
                passed=False,
                domain=domain,
                total_checks=0,
                violations=[
                    PolicyViolation(
                        rule_id="E-SYS-001",
                        domain="system",
                        title="文件不存在",
                        severity="BLOCK",
                        detail=f"目标文件无法读取: {p}",
                        remediation="请提供有效的文件路径。",
                    )
                ],
            )
        try:
            content = p.read_text(encoding="utf-8")
            return self.audit_text(content, domain=domain, target_name=str(p))
        except Exception as e:
            return PolicyAuditReport(
                target=str(p),
                passed=False,
                domain=domain,
                total_checks=0,
                violations=[
                    PolicyViolation(
                        rule_id="E-SYS-002",
                        domain="system",
                        title="文件解析异常",
                        severity="BLOCK",
                        detail=f"读取文件内容失败: {e}",
                        remediation="请确保文件为 UTF-8 编码的纯文本或 Markdown 文件。",
                    )
                ],
            )
