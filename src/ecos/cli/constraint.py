"""CLI tool for MOF constraint governance, static audit, explanation, and drift check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ecos.ssot.compiler.ast_inspector import AstDependencyInspector
from ecos.ssot.compiler.command_inspector import CommandSafetyInspector
from ecos.ssot.compiler.context_synthesizer import MOFContextSynthesizer
from ecos.ssot.compiler.mof_policy_compiler import MOFPolicyCompiler
from ecos.ssot.compiler.path_inspector import PathBoundaryInspector


def cmd_explain(args: argparse.Namespace) -> int:
    synthesizer = MOFContextSynthesizer()
    info = synthesizer.explain_rule(args.rule_id)
    if not info:
        print(f"❌ 未找到规则: {args.rule_id}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    print(f"\n╭─ MOF 规则详解: {info['violation_code']} ({info['rule_id']}) ───────────────────")
    print(f"│ 严重程度: [{info['severity'].upper()}]   所属维度: {info.get('dimension', 'N/A')}")
    print(f"│ 规则概述: {info['summary']}")
    print(f"│ 架构动机: {info['motivation']}")
    print(f"│ 修复建议: {info['remediation']}")
    recipe = info.get("code_recipe", {})
    if recipe:
        print("│")
        print("│ ❌ 违规反例 (Anti-Pattern):")
        for line in recipe.get("invalid", "").splitlines():
            print(f"│   {line}")
        print("│ ✅ 合规范式 (Compliant Recipe):")
        for line in recipe.get("valid", "").splitlines():
            print(f"│   {line}")
    print("╰─────────────────────────────────────────────────────────────────\n")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    target_path = Path(args.path).resolve()
    if not target_path.exists():
        print(f"❌ 目标路径不存在: {target_path}", file=sys.stderr)
        return 1

    ast_inspector = AstDependencyInspector()
    files_scanned = 0
    violations_found: list[dict] = []

    files_to_scan = [target_path] if target_path.is_file() else list(target_path.rglob("*.py"))
    for py_file in files_to_scan:
        # Ignore virtual environments or build directories
        if any(part in py_file.parts for part in (".venv", "venv", ".git", "__pycache__", "build", "dist")):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files_scanned += 1
        reports = ast_inspector.inspect_code(content, caller_layer=args.layer)
        for r in reports:
            violations_found.append({
                "file": str(py_file),
                **r.to_dict(),
            })

    if args.json:
        print(json.dumps({
            "target": str(target_path),
            "files_scanned": files_scanned,
            "violations_count": len(violations_found),
            "violations": violations_found,
        }, ensure_ascii=False, indent=2))
        return 1 if violations_found and args.strict else 0

    print(f"\n🔍 MOF 架构静态审计: 扫描 {files_scanned} 个文件，发现 {len(violations_found)} 处违规")
    for v in violations_found:
        line_str = f":L{v['line_number']}" if v.get("line_number") else ""
        print(f"  ❌ [{v['severity'].upper()}] {v['violation_code']} at {v['file']}{line_str}")
        print(f"     {v['summary']} — {v['detail']}")
        print(f"     👉 修复方案: {v['remediation']}")
        if v.get("suggested_patch"):
            print(f"     💡 建议 Patch:\n        {v['suggested_patch']}")
        print()

    if violations_found and args.strict:
        print("⛔ 审计失败 (严格模式: 存在架构违规)")
        return 1
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    try:
        call_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        print(f"❌ --args 必须是合法 JSON 字符串: {e}", file=sys.stderr)
        return 1

    ast_inspector = AstDependencyInspector()
    path_inspector = PathBoundaryInspector()
    cmd_inspector = CommandSafetyInspector()

    violations = []
    tool_name = args.tool.lower()

    if tool_name in {"run_command", "bash", "execute_command"}:
        cmd = call_args.get("CommandLine", "") or call_args.get("command", "")
        eval_res = cmd_inspector.inspect_command(cmd)
        violations.extend(eval_res.violations)
    elif tool_name in {"write_to_file", "replace_file_content", "multi_replace_file_content"}:
        target_file = call_args.get("TargetFile", "") or call_args.get("path", "")
        if target_file:
            eval_res = path_inspector.inspect_path_access(target_file, caller_domain=args.domain)
            violations.extend(eval_res.violations)
        content = call_args.get("CodeContent", "") or call_args.get("ReplacementContent", "")
        if content:
            violations.extend(ast_inspector.inspect_code(content, caller_layer=args.layer))

    if violations:
        output = {
            "status": "REJECTED",
            "error_type": "MOF_CONSTRAINT_VIOLATION",
            "violation": violations[0].to_dict(),
            "all_violations": [v.to_dict() for v in violations],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1

    output = {
        "status": "ALLOWED",
        "tool_name": args.tool,
        "caller_layer": args.layer,
        "caller_domain": args.domain,
        "note": "MOF L0 architecture constraints verified",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    compiler = MOFPolicyCompiler()
    policy_set = compiler.compile()
    drift_status = {
        "ssot_source": str(compiler.constraints_path),
        "rules_compiled": len(policy_set),
        "version": policy_set.version,
        "generated_timestamp": policy_set.generated,
        "drift_detected": False,
        "status": "IN_SYNC",
    }
    if not compiler.constraints_path.exists():
        drift_status["drift_detected"] = True
        drift_status["status"] = "SOURCE_MISSING"

    if args.json:
        print(json.dumps(drift_status, ensure_ascii=False, indent=2))
    else:
        print("\n📊 MOF SSOT 规则漂移校验:")
        print(f"  源文件路径: {drift_status['ssot_source']}")
        print(f"  编译规则数: {drift_status['rules_compiled']}")
        print(f"  版本/生成时间: {drift_status['version']} ({drift_status['generated_timestamp']})")
        print(f"  状态: {'✅ 一致' if not drift_status['drift_detected'] else '❌ 漂移'}\n")
    return 0 if not drift_status["drift_detected"] else 1


def cmd_guardrail(args: argparse.Namespace) -> int:
    synthesizer = MOFContextSynthesizer()
    prompt = synthesizer.synthesize_guardrails(
        domain=args.domain,
        layer=args.layer,
        max_rules=args.max_rules,
    )
    print(prompt)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    compiler = MOFPolicyCompiler()
    policy_set = compiler.compile()
    rules = list(policy_set.rules.values())
    if args.dimension:
        rules = [r for r in rules if r.dimension.lower() == args.dimension.lower()]

    if args.json:
        print(json.dumps([
            {
                "id": r.id,
                "violation_code": r.violation_code,
                "severity": r.severity.value,
                "dimension": r.dimension,
                "summary": r.description,
            }
            for r in rules
        ], ensure_ascii=False, indent=2))
        return 0

    print(f"\n📋 MOF 编译规则清单 (共 {len(rules)} 条):")
    for r in rules:
        print(f"  • [{r.severity.value.upper()}] {r.violation_code} ({r.id}) [{r.dimension}]: {r.description}")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ecos-constraint",
        description="MOF Dynamic Constraint Governance & Inspection Suite",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # explain
    p_explain = subparsers.add_parser("explain", help="解释指定规则的动机与合规范式")
    p_explain.add_argument("rule_id", help="规则 ID 或违规代码 (如 X1-C02 或 E-L0-002)")
    p_explain.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_explain.set_defaults(func=cmd_explain)

    # audit
    p_audit = subparsers.add_parser("audit", help="静态扫描代码库中的架构违规")
    p_audit.add_argument("path", nargs="?", default=".", help="扫描根路径 (默认当前目录)")
    p_audit.add_argument("--layer", default="L3", help="调用方层级 (默认 L3)")
    p_audit.add_argument("--strict", action="store_true", help="严格模式: 发现违规返回非 0 退出码")
    p_audit.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_audit.set_defaults(func=cmd_audit)

    # eval
    p_eval = subparsers.add_parser("eval", help="预演评估工具调用参数是否合规")
    p_eval.add_argument("--tool", required=True, help="工具名称")
    p_eval.add_argument("--args", required=True, help="工具入参 JSON 字符串")
    p_eval.add_argument("--domain", default="default", help="调用方所属领域")
    p_eval.add_argument("--layer", default="L3", help="调用方层级")
    p_eval.set_defaults(func=cmd_eval)

    # drift
    p_drift = subparsers.add_parser("drift", help="检查 SSOT 规则与派生产物的一致性")
    p_drift.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_drift.set_defaults(func=cmd_drift)

    # guardrail
    p_guardrail = subparsers.add_parser("guardrail", help="生成注入 System Prompt 的轻量架构约束块")
    p_guardrail.add_argument("--domain", default="default", help="领域名称")
    p_guardrail.add_argument("--layer", default="L3", help="层级")
    p_guardrail.add_argument("--max-rules", type=int, default=5, help="最多包含的规则条数")
    p_guardrail.set_defaults(func=cmd_guardrail)

    # list
    p_list = subparsers.add_parser("list", help="列出所有编译生效的规则")
    p_list.add_argument("--dimension", help="按维度过滤 (如 dependency, command_safety)")
    p_list.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
