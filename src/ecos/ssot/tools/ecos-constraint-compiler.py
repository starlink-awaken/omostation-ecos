#!/usr/bin/env python3
"""
eCOS v6 L0 — 协议编译器 (ecos-constraint-compiler)
=====================================================
从 L0-constraints.yaml 读取协议约束 → 编译为可执行的强制规则模块。

管线:
  src/ecos/ssot/registry/L0-constraints.yaml (输入)
    → ecos-constraint-compiler.py (编译)
      → /tmp/ecos-compiled-constraints.py (输出)
        → import & 执行

用法:
    python3 ecos-constraint-compiler.py                  # 编译 + 报告
    python3 ecos-constraint-compiler.py --json           # JSON 输出
    python3 ecos-constraint-compiler.py --output /path   # 指定输出
    python3 ecos-constraint-compiler.py --enforce        # 违反 required 则 exit 1
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── 路径 (实际位置) ──
CONSTRAINTS_FILE = Path(__file__).resolve().parent.parent / "registry" / "L0-constraints.yaml"
DEFAULT_OUTPUT = Path("/tmp") / "ecos-compiled-constraints.py"


def load_yaml(path: Path) -> dict:
    import yaml

    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def compile_constraints(data: dict) -> str:
    """将 YAML 约束编译为 Python 模块"""
    constraints = data.get("constraints", [])
    now = datetime.now(timezone.utc)

    lines = []
    lines.append("# eCOS v6 L0 — 编译约束 (自动生成, 勿手改)")
    lines.append("# 源: src/ecos/ssot/registry/L0-constraints.yaml")
    lines.append(f"# 编译时间: {now.isoformat()}")
    lines.append(f"# 约束数: {len(constraints)}")
    lines.append("")
    lines.append("")

    # ── 约束注册表 ──
    lines.append("# ── 约束注册表 ──")
    lines.append("CONSTRAINTS = [")
    for c in constraints:
        cid = c.get("id", "?")
        desc = (c.get("description") or "").replace('"', "'").replace("\n", " ")[:80]
        ctype = c.get("type", "required")
        rule = c.get("rule", "")
        violation = c.get("violation", "")
        dimension = c.get("dimension", "")
        applies = c.get("applies_to", [])
        entry = (
            '    {"id": "' + cid + '", "type": "' + ctype + '", "dimension": "' + dimension + '",\n'
            '     "description": "' + desc + '", "rule": "' + rule + '",\n'
            '     "violation": "' + violation + '", "applies_to": ' + str(applies) + " },"
        )
        lines.append(entry)
    lines.append("]")
    lines.append("")

    # ── 约束检查 ──
    lines.append("def check_constraints(state: dict) -> list[dict]:")
    lines.append('    """Check all constraints. status: pass | fail | not_evaluated."""')
    lines.append("    results = []")
    for c in constraints:
        cid = c.get("id", "?")
        desc = (c.get("description") or "").replace('"', "'").replace("\n", " ")[:80]
        ctype = c.get("type", "required")
        rule = c.get("rule", "")
        violation = c.get("violation", "")

        lines.append(f"    # {cid}: {desc}")
        lines.append("    passed = None")
        lines.append("    evaluated = False")
        lines.append('    detail = ""')

        if rule == "protocol.registered == true":
            lines.append("    evaluated = True")
            lines.append('    passed = state.get("protocol", {}).get("registered", False)')
            lines.append('    detail = "protocol registered" if passed else "protocol NOT registered"')
        elif rule == "layer.cross_call.route == 'I0/Agora'":
            lines.append("    evaluated = True")
            lines.append('    route = state.get("layer", {}).get("cross_call", {}).get("route", "")')
            lines.append('    passed = route == "I0/Agora"')
            lines.append('    detail = f"route: {route}"')
        elif rule == "write.entry == 'agora.register'":
            lines.append("    evaluated = True")
            lines.append('    entry = state.get("write", {}).get("entry", "")')
            lines.append('    passed = entry == "agora.register"')
            lines.append('    detail = f"entry: {entry}"')
        elif rule == "protocol.version != null":
            lines.append("    evaluated = True")
            lines.append('    ver = state.get("protocol", {}).get("version")')
            lines.append("    passed = ver is not None")
            lines.append('    detail = f"version: {ver}"')
        elif rule == "claude_md.age_days <= 60":
            lines.append("    evaluated = True")
            lines.append('    age = state.get("claude_md", {}).get("age_days", 0)')
            lines.append("    passed = age <= 60")
            lines.append('    detail = f"CLAUDE.md age: {age}d"')
        elif rule == "domain.value_tier != null":
            # X3-C01 的真谓词 (域必须声明 value_tier)。注意必须是**精确**字符串匹配:
            # `elif "value_tier" in rule:` 会同时吞掉 X3-C02 (rule 含 value_tier 但谓词
            # 不同) —— X3-C02 走下方显式分支, 绝不用 X3-C01 的谓词冒充 (P3 defuse)。
            lines.append("    evaluated = True")
            lines.append('    domains = state.get("domain", {})')
            lines.append('    missing = [d for d, v in domains.items() if v.get("value_tier") is None]')
            lines.append("    passed = len(missing) == 0")
            lines.append('    detail = f"missing: {missing}" if missing else "all declared"')
        elif rule == "domain.value_tier == 1 implies domain.cost_attribution != 'none'":
            # X3-C02 的真谓词 (tier-1 域必须有成本归因)。真宿主:
            #   bin/gac/check-l0-constraints.py::check_x3_c02 (P3, 读 ecos
            #   governance/x3-value-stack.yaml)。这里若喂了 state 也做真评估。
            lines.append("    evaluated = True")
            lines.append('    domains = state.get("domain", {})')
            lines.append("    bad = [")
            lines.append("        d for d, v in domains.items()")
            lines.append('        if v.get("value_tier") == 1 and str(v.get("cost_attribution", "none")).lower() == "none"')
            lines.append("    ]")
            lines.append("    passed = len(bad) == 0")
            lines.append('    detail = f"tier-1 no attribution: {bad}" if bad else "tier-1 OK"')
        elif rule == "non_broker.python_mutation(target in ['.omo/', 'spaces/']) == false":
            # 真实数据源: 本分支的 state['direct_omo_io'] 没有任何组件填充 —— 默认
            # run() 不再硬编码健康 state (见下方 run()), 因此无 state 时该规则是
            # not_evaluated, 不再恒绿 (audit F2, 2026-10-10 标注)。
            # 该约束的**真实执行宿主**是 `omo.cli lint direct-omo-io` →
            # projects/ecos/scripts/contract_gatekeeper.py (AST 扫描 .omo//spaces/ 直写,
            # CI governance-check.yml 执行; 合成违规实测 exit 1)。
            lines.append("    evaluated = True")
            lines.append('    mutations = state.get("direct_omo_io", [])')
            lines.append("    passed = len(mutations) == 0")
            lines.append('    detail = f"direct mutations: {len(mutations)}"')
        else:
            # 无编译器分支 — 必须**响亮地**不可执行, 不能当作通过 (P2, 2026-10-10)。
            # 这些规则的强制力必须由别处宿主提供 (大部分未接线, 见 wiring-coverage)。
            lines.append('    detail = "rule not auto-evaluated (no compiler branch; no state producer)"')

        lines.append("    results.append({")
        lines.append(f'        "id": "{cid}",')
        lines.append(f'        "type": "{ctype}",')
        lines.append(f'        "description": "{desc}",')
        lines.append('        "passed": passed,')
        lines.append('        "evaluated": evaluated,')
        lines.append('        "status": ("pass" if passed else ("fail" if evaluated else "not_evaluated")),')
        lines.append('        "detail": detail,')
        lines.append(f'        "violation": "{violation}" if evaluated and not passed else None,')
        lines.append("    })")
        lines.append("")

    lines.append("    return results")
    lines.append("")

    # ── 入口 ──
    lines.append("def run(state: dict = None) -> dict:")
    lines.append('    """Run compiled constraints. No-state => all not_evaluated."""')
    lines.append("    return {\"constraints\": check_constraints(state) if state is not None else _no_state_results()}")
    lines.append("")
    lines.append("")
    lines.append("def _no_state_results() -> list[dict]:")
    lines.append('    """无 state 时: 所有规则 not_evaluated (绝不当作 pass)."""')
    lines.append("    out = []")
    lines.append("    for c in CONSTRAINTS:")
    lines.append("        out.append({")
    lines.append('            "id": c["id"],')
    lines.append('            "type": c["type"],')
    lines.append('            "description": c["description"],')
    lines.append('            "passed": None,')
    lines.append('            "evaluated": False,')
    lines.append('            "status": "not_evaluated",')
    lines.append('            "detail": "no state supplied; not evaluated (real host required)",')
    lines.append('            "violation": None,')
    lines.append("        })")
    lines.append("    return out")
    lines.append("")
    return "\n".join(lines)


def write_compiled(code: str, output_path: Path) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(code)
    return {
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "source": str(CONSTRAINTS_FILE),
        "output": str(output_path),
        "hash": hashlib.sha256(code.encode()).hexdigest()[:16],
    }


def load_compiled(output_path: Path):
    spec = importlib.util.spec_from_file_location("compiled_constraints", output_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_compiled(output_path: Path) -> dict:
    module = load_compiled(output_path)
    if module is None:
        return {"error": "compile module load failed"}
    try:
        return module.run()
    except Exception as e:
        return {"error": f"runtime error: {e}"}


def format_report(result: dict) -> str:
    lines = []
    lines.append("=" * 56)
    lines.append("  eCOS v6 L0 — 编译约束报告")
    lines.append("=" * 56)
    constraints = result.get("constraints", [])
    evaluated = [c for c in constraints if c.get("evaluated")]
    not_eval = [c for c in constraints if not c.get("evaluated")]
    passed = sum(1 for c in constraints if c["status"] == "pass")
    failed = [c for c in constraints if c["status"] == "fail"]
    lines.append(f"\n  -- constraints: {passed} pass / {len(failed)} fail / {len(not_eval)} not_evaluated (of {len(constraints)}) --")
    for c in constraints:
        if c["status"] == "pass":
            icon = "OK"
        elif c["status"] == "fail":
            icon = "FAIL" if c["type"] == "required" else "WARN"
        else:
            icon = "NE"  # not_evaluated: 响亮地不可执行, 不是 pass
        lines.append(f"  [{icon}] {c['id']:15s} {c['description'][:45]}")
    if failed:
        lines.append(f"\n  FAILED required: {len(failed)}")
    if not_eval:
        lines.append(f"\n  NOT EVALUATED required: {sum(1 for c in not_eval if c['type'] == 'required')} "
                     f"(这些规则没有编译器分支或没有 state 生产者 — **不是 pass**, 见 detail)")
    lines.append(f"\n{'=' * 56}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="eCOS v6 L0 constraint compiler")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--enforce", action="store_true", help="exit 1 on required violations")
    parser.add_argument(
        "--enforce-strict",
        action="store_true",
        help=(
            "exit 1 on required violations AND on any required rule that was NOT "
            "EVALUATED (no state producer / no compiler branch). Use for CI steps that "
            "must not be green while enforcing nothing (P2 truth-telling, 2026-10-10)."
        ),
    )
    args = parser.parse_args()

    if not CONSTRAINTS_FILE.exists():
        print(f"ERROR: constraints file not found: {CONSTRAINTS_FILE}", file=sys.stderr)
        sys.exit(2)

    data = load_yaml(CONSTRAINTS_FILE)
    code = compile_constraints(data)
    state = write_compiled(code, Path(args.output))
    result = run_compiled(Path(args.output))

    if args.json:
        print(json.dumps({**result, "compiler": state}, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))
        print(f"  hash: {state['hash']}  output: {args.output}")

    if args.enforce or args.enforce_strict:
        failed = [c for c in result.get("constraints", []) if c["status"] == "fail" and c["type"] == "required"]
        if failed:
            print(f"\nENFORCE: {len(failed)} required constraint(s) FAILED", file=sys.stderr)
            sys.exit(1)
        not_eval_required = [
            c for c in result.get("constraints", [])
            if c["status"] == "not_evaluated" and c["type"] == "required"
        ]
        if not_eval_required:
            # P2 (2026-10-10): 未评估的 required 规则绝不当作 pass —— 响亮地报出来。
            # 普通 --enforce: exit 0 (只有真 FAIL 才 exit 1); 但输出/JSON 明确区分
            # not_evaluated。--enforce-strict: 未评估的 required 规则也 exit 1,
            # 供 CI 中"标为 enforce 就必须 enforce"的步骤使用 (truth-telling)。
            print(
                f"\nENFORCE: {len(not_eval_required)} required constraint(s) NOT EVALUATED "
                "(no compiler branch or no state producer — **not enforced here**)",
                file=sys.stderr,
            )
            if args.enforce_strict:
                print(
                    "ENFORCE-STRICT: required rules were not evaluated → step cannot be green.",
                    file=sys.stderr,
                )
                sys.exit(3)


if __name__ == "__main__":
    sys.exit(main())
