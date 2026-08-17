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
            lines.extend(
                [
                    "- [E-L0-002: REQUIRED] 禁止跨层直接 import 私有或底层未暴露模块，跨域必须通过 agora.client 统一路由。",
                    "- [E-CMD-001: REQUIRED] 禁止在主环境执行全局安装命令 (如 pip install --user/-g)，依赖需使用 uv 管理。",
                    "- [E-PATH-001: REQUIRED] 文件写入操作仅限在当前 domain 目录或公开临时产物路径内。",
                ]
            )
        else:
            for rule in selected_rules:
                sev = rule.severity.value.upper()
                desc = rule.description or rule.remediation_hint or rule.rule_expr
                lines.append(f"- [{rule.violation_code}: {sev}] {rule.dimension.upper()}: {desc}")

        lines.append("</mof_architecture_guardrails>")
        return "\n".join(lines)

    def synthesize_documents_guardrails(
        self,
        domain_id: str = "default",
    ) -> str:
        """Generate dual-plane Documents guardrail block (ADR-0191) for Agent System Prompt."""
        lines = [
            f'<documents_dual_plane_guardrails domain="{domain_id}">',
            "# Workspace × Documents 双平面治理契约 (ADR-0191):",
            "1. [E-DOC-001: REQUIRED] 禁止在 Documents 业务域写入可执行脚本 (.py/.sh/.js/.ts)，脚本必须落地在 Workspace/scripts 或 projects/。",
            "2. [E-DOC-002: REQUIRED] 禁止在 Documents 内容域引入依赖/缓存环境 (node_modules/.venv/__pycache__)，保持内容面 100% 纯净。",
            "3. [E-DOC-003: REQUIRED] Documents 仅作为事实资产平面 (What & Truth)，物理事实以 _entities/facts/ 为 SSOT，执行状态以 Workspace/.omo/state 为准。",
            "4. [E-DOC-004: REQUIRED] 跨域调用必须经由 bos:// 统一寻址或 Cockpit Documents MCP 只读网关，严禁裸写其他域私有目录。",
            "</documents_dual_plane_guardrails>",
        ]
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
            id_up = identifier.upper()
            if id_up in {"E-L0-002", "X1-C02"}:
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
            elif id_up in {"E-CMD-001", "X1-C01"}:
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
            elif id_up in {"E-DOC-001", "X4-C15"}:
                return {
                    "rule_id": "X4-C15",
                    "violation_code": "E-DOC-001",
                    "severity": "required",
                    "dimension": "dual_plane_boundary",
                    "summary": "禁止在 Documents 内容域写入可执行脚本",
                    "motivation": "严格保持 Documents 作为纯文档与事实资产的纯净性，执行代码归入 Workspace (ADR-0191)",
                    "remediation": "将执行代码与脚本移至 Workspace/scripts/ 或 projects/ 对应工程子目录",
                    "code_recipe": {
                        "invalid": "# Write to ~/Documents/@工作文档/卫健委/fetch_data.py",
                        "valid": "# Write to ~/Workspace/scripts/weijian/fetch_data.py\n# Reference via SOP in ~/Documents/@工作文档/卫健委/_knowledge/SOP.md",
                    },
                }
            elif id_up in {"E-DOC-002", "X4-C16"}:
                return {
                    "rule_id": "X4-C16",
                    "violation_code": "E-DOC-002",
                    "severity": "required",
                    "dimension": "dual_plane_boundary",
                    "summary": "禁止在 Documents 引入运行时依赖/缓存环境",
                    "motivation": "防止 node_modules、.venv、__pycache__ 污染知识资产与多端云同步 (ADR-0191)",
                    "remediation": "使用 Workspace 统一环境与 uv/npm 管理，禁止在 Documents 内 init 虚拟环境",
                    "code_recipe": {
                        "invalid": "cd ~/Documents/@家庭生活/app && npm install # generates node_modules in Documents",
                        "valid": "cd ~/Workspace/projects/family-hub/apps/dashboard && uv run npm install",
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
