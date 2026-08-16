"""AST Dependency Inspector for real-time code analysis."""

from __future__ import annotations

import ast

from ecos.ssot.compiler.models import RuleSeverity, ViolationReport


class AstDependencyInspector:
    """Fast AST-based Python code inspector for architecture boundary violations."""

    def __init__(self, layer_disallowed_imports: dict[str, set[str]] | None = None) -> None:
        # e.g., {"L3": {"l4_kernel.internal", "runtime.private"}}
        self.layer_disallowed_imports = layer_disallowed_imports or {
            "L3": {"l4_kernel.internal", "runtime.private", "ecos.internal"},
            "L2": {"l4_kernel.internal"},
            "L1": set(),
        }

    def inspect_code(self, source_code: str, caller_layer: str = "L3") -> list[ViolationReport]:
        violations: list[ViolationReport] = []
        disallowed = self.layer_disallowed_imports.get(caller_layer, set())
        if not disallowed:
            return violations

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            # If code has syntax error, pass through (let compiler/linter catch syntax)
            return violations

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    symbol = alias.name
                    if self._matches_disallowed(symbol, disallowed):
                        violations.append(
                            ViolationReport(
                                rule_id="X1-C02",
                                violation_code="E-L0-002",
                                severity=RuleSeverity.REQUIRED,
                                summary="跨层直连私有模块违规",
                                detail=f"在 {caller_layer} 层直接导入了受保护模块 '{symbol}'",
                                remediation="根据 L0 架构规范，跨层调用必须经由 Agora 路由 ('agora.client') 访问",
                                line_number=getattr(node, "lineno", None),
                                offending_symbol=symbol,
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module
                    for alias in node.names:
                        full_symbol = f"{module_name}.{alias.name}" if module_name else alias.name
                        if self._matches_disallowed(module_name, disallowed) or self._matches_disallowed(full_symbol, disallowed):
                            violations.append(
                                ViolationReport(
                                    rule_id="X1-C02",
                                    violation_code="E-L0-002",
                                    severity=RuleSeverity.REQUIRED,
                                    summary="跨层直连私有模块违规",
                                    detail=f"在 {caller_layer} 层从 '{module_name}' 导入了符号 '{alias.name}'",
                                    remediation="根据 L0 架构规范，跨层调用必须经由 Agora 路由 ('agora.client') 访问",
                                    line_number=getattr(node, "lineno", None),
                                    offending_symbol=module_name,
                                )
                            )
        return violations

    @staticmethod
    def _matches_disallowed(symbol: str, disallowed_set: set[str]) -> bool:
        for prefix in disallowed_set:
            if symbol == prefix or symbol.startswith(f"{prefix}."):
                return True
        return False
