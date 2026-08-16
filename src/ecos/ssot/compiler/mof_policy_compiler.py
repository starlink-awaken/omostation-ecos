"""MOF Policy Compiler: Compiles L0 constraints into in-memory executable rules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from ecos.ssot.compiler.ast_inspector import AstDependencyInspector
from ecos.ssot.compiler.command_inspector import CommandSafetyInspector
from ecos.ssot.compiler.models import (
    CompiledPolicySet,
    EvaluationResult,
    PolicyRule,
    RuleSeverity,
)
from ecos.ssot.compiler.path_inspector import PathBoundaryInspector


def _find_constraints_file() -> Path:
    current = Path(__file__).resolve()
    # Try derived v2 (137 rules) first, then base constraints.yaml (36 families)
    candidates = [
        current.parents[3] / ".omo" / "_derived" / "l0-constraints.v2.yaml",
        Path.home() / "Workspace" / "projects" / "ecos" / ".omo" / "_derived" / "l0-constraints.v2.yaml",
        current.parents[2] / "l0" / "constraints.yaml",
        Path.home() / "Workspace" / "projects" / "ecos" / "src" / "ecos" / "l0" / "constraints.yaml",
        Path.home() / "Documents" / "学习进化" / "2-knowledge" / "基建架构" / "L0-constraints.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


class MOFPolicyCompiler:
    """Compiles MOF L0 constraint definitions into structured in-memory execution rules."""

    def __init__(self, constraints_path: Path | None = None) -> None:
        self.constraints_path = constraints_path or _find_constraints_file()
        self.ast_inspector = AstDependencyInspector()
        self.path_inspector = PathBoundaryInspector()
        self.command_inspector = CommandSafetyInspector()
        self._cached_policy_set: CompiledPolicySet | None = None

    def compile(self, force_recompile: bool = False) -> CompiledPolicySet:
        if self._cached_policy_set is not None and not force_recompile:
            return self._cached_policy_set

        if not self.constraints_path.exists():
            policy_set = CompiledPolicySet(
                version="1.0.0",
                generated=datetime.now(timezone.utc).isoformat(),
            )
            self._cached_policy_set = policy_set
            return policy_set

        with open(self.constraints_path, encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}

        version = str(raw_data.get("version", "1.0.0"))
        generated = str(raw_data.get("generated", datetime.now(timezone.utc).isoformat()))

        policy_set = CompiledPolicySet(
            version=version,
            generated=generated,
        )

        constraints_list = raw_data.get("constraints", [])
        if isinstance(constraints_list, list):
            for item in constraints_list:
                if not isinstance(item, dict):
                    continue
                rule_id = str(item.get("id", ""))
                if not rule_id:
                    continue

                # Support both 'type' (required/preferred) and 'severity' (high/medium/low)
                raw_type = str(item.get("type", "")).lower()
                raw_severity = str(item.get("severity", "")).lower()
                if raw_type == "preferred" or raw_severity in ("low", "medium", "preferred"):
                    severity = RuleSeverity.PREFERRED
                elif raw_type == "immutable" or raw_severity == "immutable":
                    severity = RuleSeverity.IMMUTABLE
                else:
                    severity = RuleSeverity.REQUIRED

                # Support both string rule and dict rule_expr {kind: expr, args: [...]}
                raw_rule = item.get("rule") or item.get("rule_expr")
                if isinstance(raw_rule, dict):
                    args = raw_rule.get("args", [])
                    rule_expr = " && ".join(str(a) for a in args) if isinstance(args, list) else str(raw_rule)
                else:
                    rule_expr = str(raw_rule or "")

                violation_code = str(item.get("violation_code") or item.get("violation") or f"E-{rule_id}")
                violation_msg = str(item.get("violation_message") or item.get("description") or "请遵循 L0 协议与架构约束")

                rule = PolicyRule(
                    id=rule_id,
                    dimension=str(item.get("dimension", "QG")),
                    severity=severity,
                    description=str(item.get("description", "")),
                    rule_expr=rule_expr,
                    applies_to=list(item.get("applies_to", ["L0", "L1", "L2", "L3"])),
                    violation_code=violation_code,
                    remediation_hint=violation_msg,
                )
                policy_set.add_rule(rule)

        self._cached_policy_set = policy_set
        return policy_set

    def evaluate_python_code(
        self,
        source_code: str,
        caller_layer: str = "L3",
        policy_set: CompiledPolicySet | None = None,
    ) -> EvaluationResult:
        violations = self.ast_inspector.inspect_code(source_code, caller_layer=caller_layer)
        return EvaluationResult(passed=len(violations) == 0, violations=violations)

    def evaluate_write(
        self,
        target_path: str,
        caller_domain: str = "default",
    ) -> EvaluationResult:
        return self.path_inspector.inspect_write(target_path, caller_domain=caller_domain)

    def evaluate_command(
        self,
        command_line: str,
    ) -> EvaluationResult:
        return self.command_inspector.inspect_command(command_line)


def compile_l0_constraints(path: Path | None = None) -> CompiledPolicySet:
    """Convenience helper to compile and return the active L0 policy set."""
    compiler = MOFPolicyCompiler(constraints_path=path)
    return compiler.compile()
