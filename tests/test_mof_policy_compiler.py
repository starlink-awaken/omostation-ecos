"""Tests for MOF Policy Compiler and Dynamic Governance Inspectors (Phase 1)."""

from __future__ import annotations

import time


from ecos.ssot.compiler.ast_inspector import AstDependencyInspector
from ecos.ssot.compiler.command_inspector import CommandSafetyInspector
from ecos.ssot.compiler.models import (
    CompiledPolicySet,
    EvaluationResult,
    RuleSeverity,
    ViolationReport,
)
from ecos.ssot.compiler.mof_policy_compiler import (
    MOFPolicyCompiler,
    compile_l0_constraints,
)
from ecos.ssot.compiler.path_inspector import PathBoundaryInspector


def test_models_violation_and_evaluation():
    v = ViolationReport(
        rule_id="X1-C02",
        violation_code="E-L0-002",
        severity=RuleSeverity.REQUIRED,
        summary="Bypass Agora router",
        detail="Direct import of l4_kernel internal in L3",
        remediation="Use agora.client protocol stub instead",
        line_number=14,
        offending_symbol="l4_kernel.internal",
    )
    assert v.rule_id == "X1-C02"
    assert v.to_dict()["violation_code"] == "E-L0-002"
    assert v.to_dict()["line_number"] == 14

    res_clean = EvaluationResult(passed=True, violations=[])
    assert res_clean.passed
    assert not res_clean.has_required_violations

    res_violated = EvaluationResult(passed=False, violations=[v])
    assert not res_violated.passed
    assert res_violated.has_required_violations
    assert len(res_violated.violations) == 1


def test_ast_dependency_inspector_detects_forbidden_imports():
    inspector = AstDependencyInspector(
        layer_disallowed_imports={
            "L3": {"l4_kernel.internal", "runtime.private"},
            "L2": {"l4_kernel.internal"},
        }
    )

    clean_code = """
import json
from agora.client import query
from runtime.protocol import L0Registry

def run():
    return query("health")
"""
    violations = inspector.inspect_code(clean_code, caller_layer="L3")
    assert len(violations) == 0

    bad_code = """
import os
import l4_kernel.internal.db as db
from runtime.private import secret_key

def hack():
    pass
"""
    violations = inspector.inspect_code(bad_code, caller_layer="L3")
    assert len(violations) == 2
    symbols = {v.offending_symbol for v in violations}
    assert "l4_kernel.internal.db" in symbols
    assert "runtime.private" in symbols
    assert any(v.line_number == 3 for v in violations)


def test_path_boundary_inspector_detects_unauthorized_writes():
    inspector = PathBoundaryInspector(
        protected_roots=["@工作文档", "documents/weijian/_entities/facts"],
        allowed_domain_roots={
            "work-weijian": ["documents/weijian", "@工作文档/卫健委"],
            "core-runtime": ["projects/runtime", ".omo/state"],
        },
    )

    # Authorized write
    ok_res = inspector.inspect_write(
        target_path="documents/weijian/report.json",
        caller_domain="work-weijian",
    )
    assert ok_res.passed

    # Unauthorized cross-domain write
    bad_res = inspector.inspect_write(
        target_path="@工作文档/卫健委/confidential.yaml",
        caller_domain="untrusted-agent",
    )
    assert not bad_res.passed
    assert len(bad_res.violations) == 1
    assert bad_res.violations[0].rule_id == "X1-C03"


def test_command_safety_inspector_detects_dangerous_commands():
    inspector = CommandSafetyInspector(
        disallowed_patterns=[
            (r"\bpip\s+install\s+(-g|--global)\b", "E-CMD-001", "禁止全局安装 Python 包"),
            (r"\b(rm\s+-rf\s+/|rm\s+-rf\s+~)\b", "E-CMD-002", "禁止根目录或用户主目录递归删除"),
            (r"\bport\s*=\s*(8000|8080|9000)\b", "E-CMD-003", "禁止硬编码系统保留端口"),
        ]
    )

    clean_cmd = "uv run pytest tests/unit -v"
    assert inspector.inspect_command(clean_cmd).passed

    bad_cmd_1 = "pip install --global requests"
    res1 = inspector.inspect_command(bad_cmd_1)
    assert not res1.passed
    assert res1.violations[0].violation_code == "E-CMD-001"

    bad_cmd_2 = "python app.py --port=8000"
    res2 = inspector.inspect_command(bad_cmd_2)
    assert not res2.passed
    assert res2.violations[0].violation_code == "E-CMD-003"


def test_mof_policy_compiler_compiles_full_l0_rules():
    compiler = MOFPolicyCompiler()
    policy_set = compiler.compile()

    assert isinstance(policy_set, CompiledPolicySet)
    assert len(policy_set.rules) >= 100  # 137 L0 rules from constraints.yaml
    assert policy_set.version != ""

    # Test dimension filtering
    x1_rules = policy_set.get_rules_by_dimension("X1")
    assert len(x1_rules) > 0
    x2_rules = policy_set.get_rules_by_dimension("X2")
    assert len(x2_rules) > 0

    # Test rule lookup
    x1_c02 = policy_set.get_rule("X1-C02")
    assert x1_c02 is not None
    assert x1_c02.dimension == "X1"
    assert x1_c02.violation_code == "E-L0-002"
    assert x1_c02.severity == RuleSeverity.REQUIRED


def test_mof_policy_compiler_fast_evaluation_performance():
    compiler = MOFPolicyCompiler()
    policy_set = compiler.compile()

    test_code = """
import sys
from agora.client import Client
import json

def process():
    c = Client()
    return c.get_status()
"""
    # Evaluate 100 times to test latency
    start = time.perf_counter()
    for _ in range(100):
        res = compiler.evaluate_python_code(test_code, caller_layer="L3", policy_set=policy_set)
        assert res.passed
    elapsed = time.perf_counter() - start

    # Average latency per evaluation must be < 5ms
    avg_ms = (elapsed / 100) * 1000
    assert avg_ms < 5.0, f"Average evaluation latency too high: {avg_ms:.2f}ms"


def test_compile_l0_constraints_helper():
    policy_set = compile_l0_constraints()
    assert isinstance(policy_set, CompiledPolicySet)
    assert len(policy_set.rules) > 0
