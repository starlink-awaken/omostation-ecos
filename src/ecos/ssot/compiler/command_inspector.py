"""Command Safety Inspector for shell command execution governance."""

from __future__ import annotations

import re

from ecos.ssot.compiler.models import EvaluationResult, RuleSeverity, ViolationReport


class CommandSafetyInspector:
    """Inspects shell commands before execution to prevent system pollution and port conflicts."""

    def __init__(
        self,
        disallowed_patterns: list[tuple[str, str, str]] | None = None,
    ) -> None:
        # Tuple format: (regex_pattern, violation_code, description)
        self.disallowed_patterns = disallowed_patterns or [
            (r"\bpip\s+install\s+(-g|--global|--user)\b", "E-CMD-001", "禁止在全局或用户环境直接安装 Python 包 (必须使用 uv 或虚拟环境)"),
            (r"\b(rm\s+-rf\s+/\b|rm\s+-rf\s+~\b)", "E-CMD-002", "禁止对根目录或用户主目录执行递归删除"),
            (r"\bport\s*=\s*(8000|8080|9000)\b", "E-CMD-003", "禁止硬编码系统保留端口 (8000, 8080, 9000)"),
        ]

    def inspect_command(self, command_line: str) -> EvaluationResult:
        violations: list[ViolationReport] = []

        for pattern, code, desc in self.disallowed_patterns:
            if re.search(pattern, command_line, re.IGNORECASE):
                violations.append(
                    ViolationReport(
                        rule_id="X1-C01",
                        violation_code=code,
                        severity=RuleSeverity.REQUIRED,
                        summary="禁止执行的高危或非规范命令",
                        detail=f"命令命中治理规则: {desc}",
                        remediation="请调整命令参数，使用受隔离的运行时或动态端口配置",
                        offending_symbol=command_line,
                    )
                )

        return EvaluationResult(passed=len(violations) == 0, violations=violations)
