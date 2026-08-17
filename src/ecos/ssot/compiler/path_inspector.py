"""Path Boundary Inspector for real-time filesystem operation governance.

Enforces Workspace x Documents Dual-Plane boundary rules (ADR-0191):
- E-DOC-001: Prohibits creating executable scripts (.py, .sh, .bash, .js, .ts, .rb, .go) in Documents.
- E-DOC-002: Prohibits creating environment/cache directories (node_modules, .venv, etc.) in Documents.
- E-DOC-003: Prohibits unauthorized cross-domain writes (DIP-02).
"""

from __future__ import annotations

from pathlib import Path

from ecos.ssot.compiler.models import EvaluationResult, RuleSeverity, ViolationReport


DOCUMENTS_ROOT_KEYWORDS = (
    "documents",
    "@公共",
    "@驾驶舱",
    "@工作文档",
    "@学习进化",
    "@家庭生活",
    "@创意创作",
    "@个人",
    "@opc",
)

SCRIPT_EXTENSIONS = (
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".rb",
    ".go",
    ".rs",
)

FORBIDDEN_DOC_DIRS = (
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
)


class PathBoundaryInspector:
    """Inspects file read/write operations against domain boundaries and protected roots."""

    def __init__(
        self,
        protected_roots: list[str] | None = None,
        allowed_domain_roots: dict[str, list[str]] | None = None,
    ) -> None:
        self.protected_roots = [
            self._normalize(p)
            for p in (protected_roots or ["@工作文档", "documents/weijian/_entities/facts"])
        ]
        self.allowed_domain_roots = {
            domain: [self._normalize(r) for r in roots]
            for domain, roots in (
                allowed_domain_roots
                or {
                    "work-weijian": ["documents/weijian", "@工作文档/卫健委"],
                    "core-runtime": ["projects/runtime", ".omo/state"],
                }
            ).items()
        }

    @staticmethod
    def _normalize(path_str: str) -> str:
        p = Path(path_str).as_posix().lstrip("./")
        return p

    def is_documents_path(self, norm_target: str) -> bool:
        """Check whether normalized path belongs to Documents content plane."""
        target_lower = norm_target.lower()
        return any(
            target_lower == kw.lower()
            or target_lower.startswith(f"{kw.lower()}/")
            or f"/{kw.lower()}/" in target_lower
            for kw in DOCUMENTS_ROOT_KEYWORDS
        )

    def inspect_write(self, target_path: str, caller_domain: str = "default") -> EvaluationResult:
        norm_target = self._normalize(target_path)
        violations: list[ViolationReport] = []

        # 1. Documents Content Plane Dual-Plane Inspection (ADR-0191)
        if self.is_documents_path(norm_target):
            # Rule E-DOC-001: No executable scripts in Documents
            if any(norm_target.endswith(ext) for ext in SCRIPT_EXTENSIONS):
                script_name = Path(norm_target).name
                suggested_dest = f"scripts/{caller_domain}/{script_name}" if caller_domain != "default" else f"scripts/{script_name}"
                violations.append(
                    ViolationReport(
                        rule_id="X4-C15",
                        violation_code="E-DOC-001",
                        severity=RuleSeverity.REQUIRED,
                        summary="禁止在 Documents 内容域写入可执行代码脚本",
                        detail=f"路径 '{target_path}' 位于 Documents 内容平面，严禁直接落地可执行代码 (ADR-0191)",
                        remediation=f"请将执行逻辑与代码落地到 Workspace 工程平面 (如 '{suggested_dest}')，Documents 仅保留纯内容/事实/SOP",
                        offending_symbol=target_path,
                        suggested_patch=f"# Move script execution logic to Workspace\n# Write to: {suggested_dest}\n# Reference via SOP in {target_path.replace(script_name, 'SOP.md')}",
                    )
                )

            # Rule E-DOC-002: No package/runtime dependencies in Documents
            if any(forbidden in norm_target.split("/") for forbidden in FORBIDDEN_DOC_DIRS):
                violations.append(
                    ViolationReport(
                        rule_id="X4-C16",
                        violation_code="E-DOC-002",
                        severity=RuleSeverity.REQUIRED,
                        summary="禁止在 Documents 内容域引入依赖/缓存环境",
                        detail=f"路径 '{target_path}' 包含运行时依赖或缓存目录 (ADR-0191)",
                        remediation="依赖管理必须在 Workspace 对应子项目中通过 uv 或 npm 管理，Documents 保持零依赖纯净",
                        offending_symbol=target_path,
                    )
                )

        # 2. Protected Roots & Cross-domain Authority Check (DIP-02)
        is_protected = any(
            norm_target == r or norm_target.startswith(f"{r}/") for r in self.protected_roots
        )
        if is_protected:
            allowed_roots = self.allowed_domain_roots.get(caller_domain, [])
            is_domain_authorized = any(
                norm_target == r or norm_target.startswith(f"{r}/") for r in allowed_roots
            )
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
