"""Path Boundary Inspector for real-time filesystem operation governance."""

from __future__ import annotations

from pathlib import Path

from ecos.ssot.compiler.models import EvaluationResult, RuleSeverity, ViolationReport


class PathBoundaryInspector:
    """Inspects file read/write operations against domain boundaries and protected roots."""

    def __init__(
        self,
        protected_roots: list[str] | None = None,
        allowed_domain_roots: dict[str, list[str]] | None = None,
    ) -> None:
        self.protected_roots = [self._normalize(p) for p in (protected_roots or ["@工作文档", "documents/weijian/_entities/facts"])]
        self.allowed_domain_roots = {
            domain: [self._normalize(r) for r in roots]
            for domain, roots in (allowed_domain_roots or {
                "work-weijian": ["documents/weijian", "@工作文档/卫健委"],
                "core-runtime": ["projects/runtime", ".omo/state"],
            }).items()
        }

    @staticmethod
    def _normalize(path_str: str) -> str:
        p = Path(path_str).as_posix().lstrip("./")
        return p

    def inspect_write(self, target_path: str, caller_domain: str = "default") -> EvaluationResult:
        norm_target = self._normalize(target_path)
        violations: list[ViolationReport] = []

        # 1. Check if target path is in protected roots
        is_protected = any(norm_target == r or norm_target.startswith(f"{r}/") for r in self.protected_roots)
        if is_protected:
            allowed_roots = self.allowed_domain_roots.get(caller_domain, [])
            is_domain_authorized = any(norm_target == r or norm_target.startswith(f"{r}/") for r in allowed_roots)
            if not is_domain_authorized:
                violations.append(
                    ViolationReport(
                        rule_id="X1-C03",
                        violation_code="E-L0-003",
                        severity=RuleSeverity.REQUIRED,
                        summary="跨域越权写入受保护目录",
                        detail=f"Domain '{caller_domain}' 试图写入受保护路径 '{target_path}'",
                        remediation=f"请确保作业具备 '{caller_domain}' 的写入权限或通过统一 Agora 注册入口写入",
                        offending_symbol=target_path,
                    )
                )

        return EvaluationResult(passed=len(violations) == 0, violations=violations)

    inspect_path_access = inspect_write
