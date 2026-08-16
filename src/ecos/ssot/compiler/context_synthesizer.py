"""MOF Context Synthesizer for proactive Agent prompt injection and shift-left governance."""

from __future__ import annotations

from typing import Any

from ecos.ssot.compiler.mof_policy_compiler import MOFPolicyCompiler


class MOFContextSynthesizer:
    """Synthesizes domain-scoped MOF architecture guardrails for Agent System Prompts."""

    def __init__(self, compiler: MOFPolicyCompiler | None = None) -> None:
        self.compiler = compiler or MOFPolicyCompiler()
        self.policy_set = self.compiler.compile()

    def synthesize_guardrails(
        self,
        domain: str = "default",
        layer: str = "L3",
        max_rules: int = 5,
    ) -> str:
        """Generate structured markdown guardrail block to inject into Agent System Prompt."""
        rules = self.compiler.get_domain_rules(domain, layer)
        selected_rules = rules[:max_rules] if max_rules > 0 else rules

        lines = [
            f'<mof_architecture_guardrails domain="{domain}" layer="{layer}">',
            "# 架构红线与合规契约 (MOF L0 Architecture Constraints):",
        ]

        if not selected_rules:
            # Fallback essential defaults
            lines.extend([
                "- [E-L0-002: REQUIRED] 禁止跨层直接 import 私有或底层未暴露模块，跨域必须通过 agora.client 统一路由。",
                "- [E-CMD-001: REQUIRED] 禁止在主环境执行全局安装命令 (如 pip install --user/-g)，依赖需使用 uv 管理。",
                "- [E-PATH-001: REQUIRED] 文件写入操作仅限在当前 domain 目录或公开临时产物路径内。",
            ])
        else:
            for rule in selected_rules:
                sev = rule.severity.value.upper()
                desc = rule.description or rule.remediation_hint or rule.rule_expr
                lines.append(f"- [{rule.violation_code}: {sev}] {rule.dimension.upper()}: {desc}")

        lines.append("</mof_architecture_guardrails>")
        return "\n".join(lines)

    def get_domain_summary(self, domain: str = "default", layer: str = "L3") -> dict[str, Any]:
        """Return raw dictionary digest of active policies for the domain."""
        rules = self.compiler.get_domain_rules(domain, layer)
        return {
            "domain": domain,
            "layer": layer,
            "active_rules_count": len(rules),
            "rules": [
                {
                    "id": r.id,
                    "violation_code": r.violation_code,
                    "severity": r.severity.value,
                    "dimension": r.dimension,
                    "description": r.description,
                    "remediation_hint": r.remediation_hint,
                }
                for r in rules
            ],
        }

    def explain_rule(self, identifier: str) -> dict[str, Any] | None:
        """Find and explain a rule by its rule_id (e.g. 'X1-C02') or violation_code ('E-L0-002')."""
        target = None
        for rule in self.policy_set.rules.values():
            if rule.id.lower() == identifier.lower() or rule.violation_code.lower() == identifier.lower():
                target = rule
                break

        if target is None:
            # Check built-in fallback explanations
            if identifier.upper() in {"E-L0-002", "X1-C02"}:
                return {
                    "rule_id": "X1-C02",
                    "violation_code": "E-L0-002",
                    "severity": "required",
                    "dimension": "dependency",
                    "summary": "跨层直连私有模块违规",
                    "motivation": "防止上层组件强耦合底层或同层私有实现，保证松耦合与统一可观测性",
                    "remediation": "使用 agora.client 统一路由访问 BOS 服务",
                    "code_recipe": {
                        "invalid": "import runtime.private.credentials as creds",
                        "valid": "from agora.client import get_service_client\nclient = get_service_client('bos://governance/mof/auth')",
                    },
                }
            elif identifier.upper() in {"E-CMD-001", "X1-C01"}:
                return {
                    "rule_id": "X1-C01",
                    "violation_code": "E-CMD-001",
                    "severity": "required",
                    "dimension": "command_safety",
                    "summary": "禁止全局安装 Python 包",
                    "motivation": "避免全局环境污染、依赖冲突以及多项目运行时的交叉破坏",
                    "remediation": "使用 uv 管理项目虚拟环境依赖",
                    "code_recipe": {
                        "invalid": "pip install --user flask",
                        "valid": "uv add flask",
                    },
                }
            return None

        recipe = {
            "invalid": "# 直接调用未受保护或越界的私有对象",
            "valid": "# 经由 agora.client 或标准对外接口访问",
        }
        if "agora" in target.remediation_hint.lower() or "import" in target.rule_expr.lower():
            recipe = {
                "invalid": "import runtime.private.credentials",
                "valid": "from agora.client import get_service_client\nclient = get_service_client('bos://governance/mof/auth')",
            }

        return {
            "rule_id": target.id,
            "violation_code": target.violation_code,
            "severity": target.severity.value,
            "dimension": target.dimension,
            "summary": target.description or target.remediation_hint,
            "motivation": "MOF L0 元模型定义的核心架构不变性约束",
            "remediation": target.remediation_hint,
            "applies_to": target.applies_to,
            "code_recipe": recipe,
        }
