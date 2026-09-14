"""Intent-to-Spec Compiler (ADR-0195).

Deconstructs natural language intent into structured execution specs including:
- Domain categorization
- Policy-as-Code regulatory bindings
- Fact entity dependencies & freshness requirements
- Multi-Agent DAG collaboration topology
- Compute & Token budget estimations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PolicyRequirement:
    rule_id: str
    title: str
    severity: str
    binding_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "severity": self.severity,
            "binding_reason": self.binding_reason,
        }


@dataclass(frozen=True, slots=True)
class FactRequirement:
    entity_pattern: str
    target_domain: str
    max_age_days: int
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_pattern": self.entity_pattern,
            "target_domain": self.target_domain,
            "max_age_days": self.max_age_days,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class AgentRoleNode:
    role: str
    archetype: str
    responsibility: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "archetype": self.archetype,
            "responsibility": self.responsibility,
        }


@dataclass(frozen=True, slots=True)
class ComputeBudgetSpec:
    recommended_model_tier: str  # "local-8b" | "local-14b" | "cloud-pro"
    estimated_context_tokens: int
    safe_headroom_ratio: float
    speculative_draft_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_model_tier": self.recommended_model_tier,
            "estimated_context_tokens": self.estimated_context_tokens,
            "safe_headroom_ratio": self.safe_headroom_ratio,
            "speculative_draft_enabled": self.speculative_draft_enabled,
        }


@dataclass(slots=True)
class IntentExecutionSpec:
    raw_prompt: str
    detected_domain: str
    intent_summary: str
    policy_requirements: list[PolicyRequirement] = field(default_factory=list)
    fact_requirements: list[FactRequirement] = field(default_factory=list)
    agent_dag: list[AgentRoleNode] = field(default_factory=list)
    compute_budget: ComputeBudgetSpec | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_prompt": self.raw_prompt,
            "detected_domain": self.detected_domain,
            "intent_summary": self.intent_summary,
            "policy_requirements": [p.to_dict() for p in self.policy_requirements],
            "fact_requirements": [f.to_dict() for f in self.fact_requirements],
            "agent_dag": [a.to_dict() for a in self.agent_dag],
            "compute_budget": self.compute_budget.to_dict() if self.compute_budget else None,
        }


def _build_dynamic_dag(domain: str, text: str, policies: list) -> list[AgentRoleNode]:
    """基于领域和复杂度动态生成 Agent DAG 拓扑.

    根据任务领域和复杂度，生成不同规模的 Agent 协作图：
    - 简单任务: 2 角色 (Builder + Auditor)
    - 标准任务: 3 角色 (Planner + Builder + Auditor)
    - 复杂任务: 4 角色 (Planner + Builder + Auditor + Challenger)
    - 特定领域: 添加领域专家角色
    """
    is_complex = len(text) > 100 or any(k in text for k in ["立项", "方案", "规划", "评估", "深度", "全面"])
    has_block_policy = any(p.severity == "BLOCK" for p in policies)

    dag: list[AgentRoleNode] = []

    # 复杂任务或高合规风险：添加规划者
    if is_complex or has_block_policy:
        dag.append(AgentRoleNode(
            role="LeadPlanner",
            archetype="Sage",
            responsibility="系统性拆解任务目标、梳理政策依据与顶层规划",
        ))

    # 核心构建者（始终存在）
    dag.append(AgentRoleNode(
        role="DomainBuilder",
        archetype="Builder",
        responsibility="起草方案主体内容、设计具体业务流程与交付格式",
    ))

    # 特定领域：添加领域专家
    if domain == "work-weijian":
        dag.append(AgentRoleNode(
            role="DomainExpert",
            archetype="Sage",
            responsibility="提供医疗卫健领域专业知识与政策合规指导",
        ))
    elif domain == "work-transfer":
        dag.append(AgentRoleNode(
            role="DomainExpert",
            archetype="Sage",
            responsibility="提供科技成果转化法律与政策合规指导",
        ))
    elif domain == "engineering":
        dag.append(AgentRoleNode(
            role="TechLead",
            archetype="Builder",
            responsibility="技术方案评审、架构设计与代码质量把控",
        ))

    # 有政策要求时：添加合规审计
    if policies:
        dag.append(AgentRoleNode(
            role="ComplianceAuditor",
            archetype="Keeper",
            responsibility="对齐 Policy-as-Code 红线与事实真源 SLA",
        ))

    # 复杂任务或高合规风险：添加挑战者
    if is_complex and has_block_policy:
        dag.append(AgentRoleNode(
            role="ShadowChallenger",
            archetype="Devil",
            responsibility="进行 360 度红蓝对抗审议，寻找漏洞与合规缺陷并打补丁",
        ))

    # 确保至少有 2 个角色
    if len(dag) < 2:
        dag.append(AgentRoleNode(
            role="Reviewer",
            archetype="Keeper",
            responsibility="通用质量审查与交付验证",
        ))

    return dag


class IntentSpecCompiler:
    """Compiles unstructured natural language requests into structured execution specs."""

    def __init__(self) -> None:
        pass

    def compile(self, prompt: str, domain: str = "auto") -> IntentExecutionSpec:
        text = prompt.strip()
        detected_domain = domain

        # 1. Domain Detection
        if detected_domain == "auto":
            if any(
                k in text
                for k in [
                    "卫生",
                    "医疗",
                    "卫健",
                    "医院",
                    "互联互通",
                    "等保",
                    "DRG",
                    "健康",
                    "信息化",
                    "疾控",
                    "电子病历",
                ]
            ):
                detected_domain = "work-weijian"
            elif any(
                k in text for k in ["转化", "专利", "技术成熟度", "TRL", "赋权", "作价入股", "中试", "产业化", "国转"]
            ):
                detected_domain = "work-transfer"
            elif any(k in text for k in ["代码", "重构", "算法", "CLI", "TUI", "架构", "测试", "API"]):
                detected_domain = "engineering"
            else:
                detected_domain = "general"

        # 2. Extract Intent Summary
        summary = text[:80] + ("..." if len(text) > 80 else "")

        # 3. Derive Policy Requirements
        policies: list[PolicyRequirement] = []
        if detected_domain == "work-weijian":
            policies.append(
                PolicyRequirement(
                    rule_id="E-POL-WJ-001",
                    title="重大信息化项目专家论证与信创适配",
                    severity="BLOCK",
                    binding_reason="卫健委项目涉及立项预算与信创自主可控软硬件要求",
                )
            )
            policies.append(
                PolicyRequirement(
                    rule_id="E-POL-WJ-002",
                    title="核心医疗数据等保三级与互联互通标准",
                    severity="BLOCK",
                    binding_reason="医疗健康数据安全及网络安全等级保护强制要求",
                )
            )
        elif detected_domain == "work-transfer":
            policies.append(
                PolicyRequirement(
                    rule_id="E-POL-TF-001",
                    title="科研团队转化收益分配 ≥70% 红线",
                    severity="BLOCK",
                    binding_reason="科技成果赋权与作价入股收益分配法定要求",
                )
            )
            policies.append(
                PolicyRequirement(
                    rule_id="E-POL-TF-002",
                    title="产业化项目技术成熟度 (TRL ≥ 6) 准入建议",
                    severity="WARN",
                    binding_reason="中试及产业化转化落地成熟度要求",
                )
            )

        # 4. Derive Fact Dependencies
        facts: list[FactRequirement] = []
        if detected_domain == "work-weijian":
            facts.append(
                FactRequirement(
                    entity_pattern="00-budget.yaml | fact-wj-*.yaml",
                    target_domain="work-weijian",
                    max_age_days=14,
                    purpose="获取卫健委现有预算指标与归口项目基线数据",
                )
            )
        elif detected_domain == "work-transfer":
            facts.append(
                FactRequirement(
                    entity_pattern="fact-tf-*.yaml",
                    target_domain="work-transfer",
                    max_age_days=14,
                    purpose="获取科技成果完成团队成员名单与权利确权事实",
                )
            )

        # 5. Plan Multi-Agent DAG Topology (动态生成)
        dag = _build_dynamic_dag(detected_domain, text, policies)

        # 6. Estimate Compute & Token Budget
        is_complex = len(text) > 100 or any(k in text for k in ["立项", "方案", "规划", "评估", "深度", "全面"])
        model_tier = "cloud-pro" if is_complex else "local-14b"
        context_est = 8192 if is_complex else 3072

        budget = ComputeBudgetSpec(
            recommended_model_tier=model_tier,
            estimated_context_tokens=context_est,
            safe_headroom_ratio=0.85,
            speculative_draft_enabled=True,
        )

        return IntentExecutionSpec(
            raw_prompt=prompt,
            detected_domain=detected_domain,
            intent_summary=summary,
            policy_requirements=policies,
            fact_requirements=facts,
            agent_dag=dag,
            compute_budget=budget,
        )
