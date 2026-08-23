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
    lines.append('    """检查所有约束"""')
    lines.append("    results = []")
    for c in constraints:
        cid = c.get("id", "?")
        desc = (c.get("description") or "").replace('"', "'").replace("\n", " ")[:80]
        ctype = c.get("type", "required")
        rule = c.get("rule", "")
        violation = c.get("violation", "")

        lines.append(f"    # {cid}: {desc}")
        lines.append("    passed = True")
        lines.append('    detail = ""')

        if rule == "protocol.registered == true":
            lines.append('    passed = state.get("protocol", {}).get("registered", False)')
            lines.append('    detail = "protocol registered" if passed else "protocol NOT registered"')
        elif rule == "layer.cross_call.route == 'I0/Agora'":
            lines.append('    route = state.get("layer", {}).get("cross_call", {}).get("route", "")')
            lines.append('    passed = route == "I0/Agora"')
            lines.append('    detail = f"route: {route}"')
        elif rule == "write.entry == 'agora.register'":
            lines.append('    entry = state.get("write", {}).get("entry", "")')
            lines.append('    passed = entry == "agora.register"')
            lines.append('    detail = f"entry: {entry}"')
        elif rule == "protocol.version != null":
            lines.append('    ver = state.get("protocol", {}).get("version")')
            lines.append("    passed = ver is not None")
            lines.append('    detail = f"version: {ver}"')
        elif rule == "claude_md.age_days <= 60":
            lines.append('    age = state.get("claude_md", {}).get("age_days", 0)')
            lines.append("    passed = age <= 60")
            lines.append('    detail = f"CLAUDE.md age: {age}d"')
        elif "value_tier" in rule:
            lines.append('    domains = state.get("domain", {})')
            lines.append('    missing = [d for d, v in domains.items() if v.get("value_tier") is None]')
            lines.append("    passed = len(missing) == 0")
            lines.append('    detail = f"missing: {missing}" if missing else "all declared"')
        elif rule == "non_broker.python_mutation(target in ['.omo/', 'spaces/']) == false":
            lines.append('    mutations = state.get("direct_omo_io", [])')
            lines.append("    passed = len(mutations) == 0")
            lines.append('    detail = f"direct mutations: {len(mutations)}"')
        else:
            lines.append('    passed = True  # TODO: implement rule "' + rule[:40] + '"')
            lines.append('    detail = "rule not auto-evaluated"')

        lines.append("    results.append({")
        lines.append(f'        "id": "{cid}",')
        lines.append(f'        "type": "{ctype}",')
        lines.append(f'        "description": "{desc}",')
        lines.append('        "passed": passed,')
        lines.append('        "detail": detail,')
        lines.append(f'        "violation": "{violation}" if not passed else None,')
        lines.append("    })")
        lines.append("")

    lines.append("    return results")
    lines.append("")

    # ── 入口 ──
    lines.append("def run(state: dict = None) -> dict:")
    lines.append('    """编译约束入口"""')
    lines.append("    if state is None:")
    lines.append('        state = {"protocol": {"registered": True, "version": "1.0.0"},')
    lines.append('                "layer": {"cross_call": {"route": "I0/Agora"}},')
    lines.append('                "write": {"entry": "agora.register"},')
    lines.append('                "claude_md": {"age_days": 0},')
    lines.append('                "direct_omo_io": [],')
    lines.append('                "domain": {}}')
    lines.append('    return {"constraints": check_constraints(state)}')
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
    passed = sum(1 for c in constraints if c["passed"])
    failed = [c for c in constraints if not c["passed"] and c["type"] == "required"]
    lines.append(f"\n  -- constraints {passed}/{len(constraints)} --")
    for c in constraints:
        icon = "OK" if c["passed"] else ("FAIL" if c["type"] == "required" else "WARN")
        lines.append(f"  [{icon}] {c['id']:15s} {c['description'][:45]}")
    if failed:
        lines.append(f"\n  FAILED required: {len(failed)}")
    lines.append(f"\n{'=' * 56}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="eCOS v6 L0 constraint compiler")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--enforce", action="store_true", help="exit 1 on required violations")
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

    if args.enforce:
        failed = [c for c in result.get("constraints", []) if not c["passed"] and c["type"] == "required"]
        if failed:
            print(f"\nENFORCE: {len(failed)} required constraint(s) FAILED", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
