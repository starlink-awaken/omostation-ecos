"""P2 (2026-10-10): ecos-constraint-compiler 诚实性回归 — CI 实际执行体.

背景 (adversarial audit): `ecos-ci.yml:42 "L0 constraint compiler (enforce)"` 调用
`src/ecos/ssot/tools/ecos-constraint-compiler.py --enforce`。旧实现 `run()` 无参时
硬编码健康默认 state, 8 个有分支的规则读常量默认 (恒绿), 其余 24 条 else 分支
`passed=True  # TODO`, 令整个 `--enforce` 装饰性 (report 报 PASS 但无任何强制力)。

本套件钉住修复后的诚实语义:
  - 无 state 调用: **全部**约束 status=not_evaluated, 绝无假 pass;
  - --enforce 报告 NOT EVALUATED 桶, 而不是把未评估规则当 pass;
  - 喂真实 state: 有分支的规则真评估, 违反 required 可红 (exit 1);
  - X3-C02 用真谓词 (value_tier==1 ⇒ cost_attribution != 'none'), 不冒充 X3-C01。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ECOS = Path(__file__).resolve().parent.parent
TOOL = ECOS / "src/ecos/ssot/tools/ecos-constraint-compiler.py"
CONSTRAINTS = ECOS / "src/ecos/ssot/registry/L0-constraints.yaml"


def _run_tool(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _compile_and_load():
    """编译一次并动态加载生成的模块 (避免写 /tmp 相互覆盖污染其他用例)."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "compiled.py"
        r = _run_tool("--output", str(out))
        assert r.returncode == 0, r.stdout + r.stderr
        spec = importlib.util.spec_from_file_location("compiled_cc", out)
        assert spec is not None and spec.loader is not None
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m


@pytest.mark.skipif(not CONSTRAINTS.exists(), reason="L0 registry not checked out")
def test_no_state_means_all_not_evaluated():
    """无 state: 绝不能有任何 pass —— 旧实现恒绿的根因是硬编码健康 state."""
    m = _compile_and_load()
    res = m.run()["constraints"]
    assert res, "必须产出约束结果"
    assert all(c["status"] == "not_evaluated" for c in res), (
        f"无 state 时不得出现 pass/fail: "
        f"{[(c['id'], c['status']) for c in res if c['status'] != 'not_evaluated'][:5]}"
    )
    assert all(c["passed"] is None for c in res), "passed 必须为 None, 而非 True"


@pytest.mark.skipif(not CONSTRAINTS.exists(), reason="L0 registry not checked out")
def test_enforce_reports_not_evaluated_not_pass():
    """--enforce 无 state: 输出必须含 NOT EVALUATED, 且不得声称 constraints pass.

    这是 P2 测试契约: 编译器报告『不可执行』而不是『通过』。
    """
    r = _run_tool("--enforce")
    assert r.returncode == 0, r.stdout + r.stderr  # 只有真 FAIL(评估过)才 exit 1
    assert "NOT EVALUATED" in r.stdout + r.stderr, r.stdout + r.stderr
    # 报告头部不得出现 "0 pass / ... / 0 not_evaluated" —— 必须承认未评估
    assert "not_evaluated" in r.stdout
    assert "pass" in r.stdout  # 头部结构 "0 pass / 0 fail / 32 not_evaluated"
    rj = _run_tool("--enforce", "--json")
    data = json.loads(rj.stdout)
    ne = [c for c in data["constraints"] if c["status"] == "not_evaluated"]
    assert len(ne) == len(data["constraints"]), "无 state 时全部约束都应 not_evaluated"


@pytest.mark.skipif(not CONSTRAINTS.exists(), reason="L0 registry not checked out")
def test_enforce_exits_1_on_real_required_failure():
    """喂带违规的 state: 有分支的 required 规则真红 (exit 1)."""
    m = _compile_and_load()
    res = m.run({
        "protocol": {"registered": False, "version": None},
        "layer": {"cross_call": {"route": "direct"}},
        "write": {"entry": "other"},
        "claude_md": {"age_days": 100},
        "direct_omo_io": [".omo/x"],
        "domain": {"k": {"value_tier": 1, "cost_attribution": "none"}},
    })["constraints"]
    failed = [c for c in res if c["status"] == "fail" and c["type"] == "required"]
    assert any(c["id"] in ("X1-C01", "X1-C02", "X1-C03", "CR-OMO-DIRECT-IO-01",
                           "X2-C01", "X2-C03", "X3-C02") for c in failed), (
        f"合成违规必须让分支规则红: {[(c['id'], c['status']) for c in res]}"
    )


@pytest.mark.skipif(not CONSTRAINTS.exists(), reason="L0 registry not checked out")
def test_x3_c02_uses_real_predicate_not_x3_c01():
    """P3 defuse: X3-C02 (value_tier==1 ⇒ cost_attribution != 'none')
    不得再用 X3-C01 的谓词 (value_tier is None) 冒充."""
    m = _compile_and_load()
    # 所有域都声明了 value_tier (X3-C01 会绿) 但 tier-1 域 cost_attribution=none
    res = m.run({
        "protocol": {"registered": True, "version": "1.0"},
        "layer": {"cross_call": {"route": "I0/Agora"}},
        "write": {"entry": "agora.register"},
        "claude_md": {"age_days": 0},
        "direct_omo_io": [],
        "domain": {
            "k1": {"value_tier": 1, "cost_attribution": "none"},
            "k2": {"value_tier": 2, "cost_attribution": "planned"},
        },
    })["constraints"]
    by_id = {c["id"]: c for c in res}
    assert by_id["X3-C01"]["status"] == "pass", "X3-C01: 所有域都声明了 value_tier 应绿"
    assert by_id["X3-C02"]["status"] == "fail", "X3-C02: tier-1 cost_attribution=none 必须红"
    assert "tier-1" in by_id["X3-C02"]["detail"], "X3-C02 必须用真谓词 detail"


@pytest.mark.skipif(not CONSTRAINTS.exists(), reason="L0 registry not checked out")
def test_healthy_state_passes_branch_rules():
    """喂健康 state: 有分支的规则全绿, 无分支规则仍 not_evaluated (不假绿)."""
    m = _compile_and_load()
    res = m.run({
        "protocol": {"registered": True, "version": "1.0.0"},
        "layer": {"cross_call": {"route": "I0/Agora"}},
        "write": {"entry": "agora.register"},
        "claude_md": {"age_days": 0},
        "direct_omo_io": [],
        "domain": {"d1": {"value_tier": 1, "cost_attribution": "implemented"}},
    })["constraints"]
    by_id = {c["id"]: c for c in res}
    for rid in ("X1-C01", "X1-C02", "X1-C03", "CR-OMO-DIRECT-IO-01", "X2-C01", "X2-C03", "X3-C01", "X3-C02"):
        assert by_id[rid]["status"] == "pass", f"{rid} 健康 state 应绿: {by_id[rid]}"
    ne = [c for c in res if c["status"] == "not_evaluated"]
    assert ne, "无编译器分支的规则必须仍显式 not_evaluated, 不能被当作 pass"