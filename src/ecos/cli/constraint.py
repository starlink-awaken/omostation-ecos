"""CLI tool for MOF constraint governance, static audit, explanation, and drift check."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ecos.ssot.compiler.ast_inspector import AstDependencyInspector
from ecos.ssot.compiler.command_inspector import CommandSafetyInspector
from ecos.ssot.compiler.context_synthesizer import MOFContextSynthesizer
from ecos.ssot.compiler.fact_inspector import FactInspector
from ecos.ssot.compiler.mof_policy_compiler import MOFPolicyCompiler
from ecos.ssot.compiler.path_inspector import PathBoundaryInspector
from ecos.ssot.compiler.pitfall_inspector import PitfallInspector
from ecos.ssot.compiler.policy_inspector import PolicyComplianceInspector
from ecos.ssot.compiler.truth_canvas_server import create_truth_canvas_server


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
            violations_found.append(
                {
                    "file": str(py_file),
                    **r.to_dict(),
                }
            )

    if args.json:
        print(
            json.dumps(
                {
                    "target": str(target_path),
                    "files_scanned": files_scanned,
                    "violations_count": len(violations_found),
                    "violations": violations_found,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
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
        print(
            json.dumps(
                [
                    {
                        "id": r.id,
                        "violation_code": r.violation_code,
                        "severity": r.severity.value,
                        "dimension": r.dimension,
                        "summary": r.description,
                    }
                    for r in rules
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"\n📋 MOF 编译规则清单 (共 {len(rules)} 条):")
    for r in rules:
        print(f"  • [{r.severity.value.upper()}] {r.violation_code} ({r.id}) [{r.dimension}]: {r.description}")
    print()
    return 0


# ── Documents Subcommand Suite (ADR-0191) ──────────────────────────────────


def cmd_documents(args: argparse.Namespace) -> int:
    action = getattr(args, "doc_action", None)
    if action == "guardrail":
        synthesizer = MOFContextSynthesizer()
        prompt = synthesizer.synthesize_documents_guardrails(domain_id=args.domain)
        print(prompt)
        return 0

    elif action == "audit":
        target_path = Path(args.path).expanduser().resolve()
        path_inspector = PathBoundaryInspector()
        violations: list[dict] = []
        files_scanned = 0

        if target_path.exists():
            for p in target_path.rglob("*"):
                if p.is_file():
                    files_scanned += 1
                    res = path_inspector.inspect_write(str(p), caller_domain=args.domain)
                    if not res.passed:
                        for v in res.violations:
                            violations.append({"path": str(p), **v.to_dict()})

        if args.json:
            print(
                json.dumps(
                    {
                        "target": str(target_path),
                        "files_scanned": files_scanned,
                        "violations_count": len(violations),
                        "violations": violations,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1 if violations and args.strict else 0

        print(f"\n📑 Documents 双平面纯净度审计: 扫描 {files_scanned} 个文件，发现 {len(violations)} 处违规")
        for v in violations:
            print(f"  ❌ [{v['severity'].upper()}] {v['violation_code']} at {v['path']}")
            print(f"     {v['summary']} — {v['detail']}")
            print(f"     👉 修复方案: {v['remediation']}")
            if v.get("suggested_patch"):
                print(f"     💡 建议:\n        {v['suggested_patch']}")
            print()

        if violations and args.strict:
            print("⛔ Documents 审计失败 (存在双平面违规)")
            return 1
        return 0

    elif action == "sync-clients":
        mode = getattr(args, "mode", "install")
        if args.dry_run:
            mode = "render"
        if not args.json:
            print(f"\n🔄 执行 Documents 多客户端配置 SSOT 同步 [模式: {mode}]...")
        scripts_with_modes = [
            ("bin/gac/documents-claude-desktop-config.py", mode),
            ("bin/gac/documents-zed-profile.py", mode),
            ("bin/gac/documents-codex-profile.py", mode),
            ("bin/gac/documents-zcode-config.py", mode),
            ("bin/gac/documents-chatgpt-tunnel.py", "render" if mode == "render" else "check"),
        ]
        results = []
        for script, script_mode in scripts_with_modes:
            p = Path(script)
            if not p.exists():
                results.append({"script": script, "status": "NOT_FOUND"})
                continue
            if args.dry_run:
                results.append({"script": script, "status": "DRY_RUN_OK", "mode": script_mode})
            else:
                try:
                    res = subprocess.run(
                        [sys.executable, str(p), script_mode], capture_output=True, text=True, timeout=10
                    )
                    status = "OK" if res.returncode == 0 else "FAILED"
                    results.append(
                        {
                            "script": script,
                            "status": status,
                            "mode": script_mode,
                            "output": res.stdout.strip()[:150] or res.stderr.strip()[:150],
                        }
                    )
                except Exception as e:
                    results.append({"script": script, "status": "ERROR", "mode": script_mode, "detail": str(e)})

        if args.json:
            print(json.dumps({"sync_results": results}, ensure_ascii=False, indent=2))
        else:
            for r in results:
                print(f"  • {r['script']} ({r.get('mode', mode)}): {r['status']}")
                if r.get("output"):
                    print(f"    └─ {r['output']}")
            print("✅ 客户端配置同步完成\n")
        return 0

    print("❌ 请指定 documents 子命令: guardrail, audit, sync-clients", file=sys.stderr)
    return 1


# ── Facts Subcommand Suite (ADR-0192 / E-DOC-004) ──────────────────────────


def cmd_facts(args: argparse.Namespace) -> int:
    action = getattr(args, "facts_action", None)
    inspector = FactInspector(max_age_days=getattr(args, "max_age_days", 14))

    if action == "template":
        tpl = inspector.generate_template(domain=args.domain)
        print(tpl)
        return 0

    elif action == "validate":
        raw_path = getattr(args, "path", ".")
        target = Path(raw_path).expanduser().resolve()
        docs_facts_dir = Path("~/Documents/@工作文档").expanduser().resolve()
        if (raw_path == "." or raw_path is None) and docs_facts_dir.exists():
            target = docs_facts_dir

        results = []
        if target.is_file():
            results = [inspector.inspect_file(target)]
        else:
            results = inspector.inspect_directory(target, domain=args.domain if args.domain != "all" else None)

        total_files = len(results)
        valid_count = sum(1 for r in results if r.passed)
        stale_count = sum(1 for r in results if r.passed and not r.is_fresh)
        invalid_count = sum(1 for r in results if not r.passed)

        if args.json:
            print(
                json.dumps(
                    {
                        "target": str(target),
                        "files_scanned": total_files,
                        "valid_facts_count": valid_count,
                        "stale_facts_count": stale_count,
                        "violations_count": invalid_count,
                        "results": [r.to_dict() for r in results],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1 if (invalid_count > 0 or (stale_count > 0 and args.strict)) else 0

        print(f"\n📊 领域事实真源 Schema 校验: 扫描 {total_files} 个文件")
        print(f"  ✅ 合格: {valid_count}   ⚠️ 需保鲜: {stale_count}   ❌ 违规: {invalid_count}\n")

        for r in results:
            if not r.passed:
                print(f"  ❌ [SCHEMA 违规] {r.file_path}")
                for err in r.errors:
                    print(f"     └─ [{err.field}] {err.message}")
            elif not r.is_fresh:
                print(f"  ⚠️ [保鲜预警] {r.entity_id or r.file_path}: {r.freshness_warning}")
            else:
                print(f"  ✅ [合格] {r.entity_id} ({r.domain}) — {r.name or '未命名'}")

        print()
        if invalid_count > 0 or (stale_count > 0 and args.strict):
            print("⛔ 事实校验未通过")
            return 1
        return 0

    if action == "serve":
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8765)
        custom_dir = getattr(args, "dir", None)
        f_dir = Path(custom_dir).expanduser().resolve() if custom_dir else None
        server = create_truth_canvas_server(host=host, port=port, facts_dir=f_dir)
        print("\n🌐 Dual-Plane Truth Canvas Web Server 运行中:")
        print(f"   URL: http://{host}:{port}/")
        print(f"   事实目录: {f_dir or Path('~/Documents/@工作文档').expanduser()}")
        print("   按 Ctrl+C 停止服务...\n")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 服务已优雅退出")
            server.server_close()
        return 0

    print("❌ 请指定 facts 子命令: validate, template, serve", file=sys.stderr)
    return 1


# ── Domain Policy-as-Code Engine (ADR-0193) ──────────────────────────────────


def cmd_policy(args: argparse.Namespace) -> int:
    action = getattr(args, "policy_action", None)
    inspector = PolicyComplianceInspector()

    if action == "explain":
        info = inspector.explain_policy(args.policy_id)
        if not info:
            print(f"❌ 未找到政策规则: {args.policy_id}", file=sys.stderr)
            return 1
        if args.json:
            print(
                json.dumps(
                    {
                        "rule_id": info.rule_id,
                        "domain": info.domain,
                        "title": info.title,
                        "severity": info.severity,
                        "description": info.description,
                        "remediation": info.remediation,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(f"\n╭─ 领域政策规则: {info.rule_id} ─────────────────────────────")
        print(f"│ 标  题: {info.title}")
        print(f"│ 领  域: {info.domain}   [严重级别: {info.severity}]")
        print(f"│ 描  述: {info.description}")
        print(f"│ 处置建议: {info.remediation}")
        print("╰─────────────────────────────────────────────────────────────\n")
        return 0

    if action == "list":
        rules = inspector.list_policies(domain=getattr(args, "domain", None))
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "rule_id": r.rule_id,
                            "domain": r.domain,
                            "title": r.title,
                            "severity": r.severity,
                        }
                        for r in rules
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(f"\n📋 领域 Policy-as-Code 规则列表 (共 {len(rules)} 条):")
        for r in rules:
            print(f"  • [{r.rule_id}] [{r.severity}] ({r.domain}) {r.title}")
        print()
        return 0

    if action == "audit":
        target = args.target
        target_path = Path(target).expanduser().resolve()
        domain = getattr(args, "domain", "auto")

        if target_path.exists() and target_path.is_file():
            report = inspector.audit_file(target_path, domain=domain)
        else:
            report = inspector.audit_text(target, domain=domain, target_name="raw-text-input")

        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 1 if (not report.passed or (len(report.warnings) > 0 and args.strict)) else 0

        print(f"\n📜 领域政策合规审计: {report.target} (领域: {report.domain})")
        if report.passed and len(report.warnings) == 0:
            print("  ✅ 政策合规审计 100% 通过，未发现政策红线违规！\n")
            return 0

        if report.violations:
            print(f"\n  ❌ 发现 {len(report.violations)} 处政策红线违规 (BLOCK):")
            for v in report.violations:
                print(f"     • [{v.rule_id}] {v.title}")
                print(f"       详情: {v.detail}")
                print(f"       建议: {v.remediation}")

        if report.warnings:
            print(f"\n  ⚠️ 发现 {len(report.warnings)} 处合规关注项 (WARN):")
            for w in report.warnings:
                print(f"     • [{w.rule_id}] {w.title}")
                print(f"       详情: {w.detail}")
                print(f"       建议: {w.remediation}")

        print()
        if not report.passed or (len(report.warnings) > 0 and args.strict):
            return 1
        return 0

    print("❌ 请指定 policy 子命令: audit, explain, list", file=sys.stderr)
    return 1


# ── Pitfall & Anti-Pattern Inspector (ADR-0194) ──────────────────────────────


def cmd_pitfall(args: argparse.Namespace) -> int:
    action = getattr(args, "pitfall_action", None)
    inspector = PitfallInspector()

    if action == "explain":
        p = inspector.explain_pitfall(args.pitfall_id)
        if not p:
            print(f"❌ 未找到踩坑条目: {args.pitfall_id}", file=sys.stderr)
            return 1
        if args.json:
            print(
                json.dumps(
                    {
                        "pitfall_id": p.pitfall_id,
                        "title": p.title,
                        "severity": p.severity,
                        "lesson_learned": p.lesson_learned,
                        "safe_recipe": p.safe_pattern_recipe,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(f"\n╭─ Agent 踩坑与反模式: {p.pitfall_id} ────────────────────────")
        print(f"│ 标  题: {p.title}  [严重度: {p.severity}]")
        print(f"│ 经验教训: {p.lesson_learned}")
        print(f"│ 规避配方: {p.safe_pattern_recipe}")
        print("╰─────────────────────────────────────────────────────────────\n")
        return 0

    if action == "list":
        pitfalls = inspector.list_pitfalls()
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "pitfall_id": p.pitfall_id,
                            "title": p.title,
                            "severity": p.severity,
                            "lesson_learned": p.lesson_learned,
                        }
                        for p in pitfalls
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(f"\n🕳️ Agent 架构避坑知识库列表 (共 {len(pitfalls)} 条):")
        for p in pitfalls:
            print(f"  • [{p.pitfall_id}] [{p.severity}] {p.title}")
            print(f"    └─ {p.lesson_learned[:80]}...")
        print()
        return 0

    if action == "scan":
        target = Path(args.path).expanduser().resolve()
        matches: list[Any] = []
        if target.is_file():
            res = inspector.scan_file(target)
            matches.extend(res.matches)
        elif target.is_dir():
            for f in target.rglob("*.py"):
                res = inspector.scan_file(f)
                matches.extend(res.matches)

        if args.json:
            print(
                json.dumps(
                    {
                        "target": str(target),
                        "total_matches": len(matches),
                        "passed": len(matches) == 0,
                        "matches": [
                            {
                                "pitfall_id": m.pitfall_id,
                                "title": m.title,
                                "severity": m.severity,
                                "line": m.line_number,
                                "snippet": m.matched_snippet,
                                "lesson": m.lesson,
                                "recipe": m.recipe,
                            }
                            for m in matches
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1 if (len(matches) > 0 and args.strict) else 0

        print(f"\n🔍 架构避坑扫描: {target}")
        if not matches:
            print("  ✅ 扫描完毕，未发现已知架构反模式与踩坑特征。\n")
            return 0

        print(f"  ⚠️ 发现 {len(matches)} 处潜在踩坑隐患:")
        for m in matches:
            print(f"     • [{m.pitfall_id}] L{m.line_number}: {m.matched_snippet}")
            print(f"       教训: {m.lesson}")
            print(f"       配方: {m.recipe}")
        print()
        if args.strict:
            return 1
        return 0

    print("❌ 请指定 pitfall 子命令: scan, list, explain", file=sys.stderr)
    return 1


# ── Automated Hygiene Patrol Suite (ADR-0192) ──────────────────────────────


def cmd_patrol(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    checks: list[dict[str, Any]] = []

    # 1. MOF SSOT 规则漂移
    compiler = MOFPolicyCompiler()
    policy_set = compiler.compile()
    drift_ok = compiler.constraints_path.exists()
    checks.append(
        {
            "name": "MOF SSOT Policy Compiler",
            "category": "Governance Core",
            "passed": drift_ok,
            "summary": f"编译 {len(policy_set)} 条约束规则 (v{policy_set.version})",
        }
    )

    # 2. Documents 双平面纯净度
    path_inspector = PathBoundaryInspector()
    docs_violations = 0
    docs_path = Path("~/Documents").expanduser().resolve()
    if docs_path.exists():
        for p in docs_path.rglob("*"):
            if p.is_file():
                res = path_inspector.inspect_write(str(p))
                if not res.passed:
                    docs_violations += len(res.violations)
    checks.append(
        {
            "name": "Documents Dual-Plane Cleanliness",
            "category": "ADR-0191 Plane Separation",
            "passed": docs_violations == 0,
            "summary": f"发现 {docs_violations} 处运行时/脚本违规",
        }
    )

    # 3. 领域事实 Schema 校验
    fact_inspector = FactInspector()
    fact_results = fact_inspector.inspect_directory(Path("."))
    fact_invalid = sum(1 for r in fact_results if not r.passed)
    checks.append(
        {
            "name": "Domain Truth Facts Schema & Freshness",
            "category": "ADR-0192 SSOT Truth",
            "passed": fact_invalid == 0,
            "summary": f"扫描 {len(fact_results)} 处事实实体，{fact_invalid} 处违规",
        }
    )

    all_passed = all(c["passed"] for c in checks)

    # 生成 Markdown 巡检报告
    report_lines = [
        "# 🛡️ 全域治理与双平面自动化巡检报告",
        "",
        f"> **巡检时间**: {now_iso}  ",
        f"> **巡检状态**: {'✅ ALL PASS (全域健康)' if all_passed else '⚠️ VIOLATIONS DETECTED (存在风险)'}  ",
        "",
        "## 📊 巡检检查项明细",
        "",
        "| 检查项 | 分类 | 状态 | 详情摘要 |",
        "| :--- | :--- | :---: | :--- |",
    ]
    for c in checks:
        status_icon = "✅ PASS" if c["passed"] else "❌ FAIL"
        report_lines.append(f"| {c['name']} | {c['category']} | {status_icon} | {c['summary']} |")

    report_lines.extend(
        [
            "",
            "## 🚀 处置与自愈指引",
            "",
            "- **规则漂移**: 运行 `ecos-constraint drift` 与 `ecos-constraint compile` 同步规则。",
            "- **Documents 污染**: 运行 `ecos-constraint documents audit` 定位违规文件并清理。",
            "- **事实实体违规**: 运行 `ecos-constraint facts validate` 修复元数据缺失或更新保鲜期。",
            "- **客户端配置**: 运行 `ecos-constraint documents sync-clients` 重新下发 IDE 挂载。",
            "",
            "---",
            "*Report generated by ECOS Automated Governance Engine (ADR-0192)*",
        ]
    )
    report_md = "\n".join(report_lines)

    output_path = getattr(args, "output", None)
    if output_path:
        out_p = Path(output_path).expanduser().resolve()
        import os

        os.makedirs(str(out_p.parent), exist_ok=True)
        with open(str(out_p), "w", encoding="utf-8") as f:
            f.write(report_md)

    if args.json:
        print(
            json.dumps(
                {
                    "patrol_timestamp": now_iso,
                    "all_passed": all_passed,
                    "summary": f"{sum(1 for c in checks if c['passed'])}/{len(checks)} passed",
                    "checks": checks,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(report_md)

    if not all_passed and args.strict:
        return 1
    return 0


def cmd_intent(args: argparse.Namespace) -> int:
    from ecos.ssot.compiler.intent_compiler import IntentSpecCompiler

    compiler = IntentSpecCompiler()
    spec = compiler.compile(args.prompt, domain=args.domain)

    if args.json:
        print(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print("\n╭─ 🧠 意图解构与工程规格编译器 (Intent-to-Spec Compiler) ──────────")
    print(f"│ 原始输入: {spec.raw_prompt}")
    print(f"│ 推断领域: {spec.detected_domain}")
    print(f"│ 意图摘要: {spec.intent_summary}")
    print("├─ 📜 政策红线依赖 (Policy Requirements):")
    if not spec.policy_requirements:
        print("│  (无特定政策红线绑定)")
    for p in spec.policy_requirements:
        print(f"│  • [{p.rule_id}] [{p.severity}] {p.title}")
        print(f"│    └─ 依据: {p.binding_reason}")
    print("├─ 📊 事实真源依赖 (Fact Dependencies):")
    if not spec.fact_requirements:
        print("│  (无特定事实实体绑定)")
    for f in spec.fact_requirements:
        print(f"│  • {f.entity_pattern} (领域: {f.target_domain}, SLA: {f.max_age_days}天)")
        print(f"│    └─ 用途: {f.purpose}")
    print("├─ 👥 多 Agent DAG 拓扑 (Agent DAG Topology):")
    for a in spec.agent_dag:
        print(f"│  • [{a.archetype}] {a.role}: {a.responsibility}")
    if spec.compute_budget:
        cb = spec.compute_budget
        print("├─ ⚡️ 算力与 Token 预算分配 (Compute & Token Budget):")
        print(f"│  • 推荐档位: {cb.recommended_model_tier}")
        print(
            f"│  • 预估上下文: ~{cb.estimated_context_tokens} tokens (安全裕量: {int(cb.safe_headroom_ratio * 100)}%)"
        )
        print(f"│  • 本地 Speculative 投机草稿: {'已启用' if cb.speculative_draft_enabled else '未启用'}")
    print("╰─────────────────────────────────────────────────────────────────\n")
    return 0


def cmd_challenge(args: argparse.Namespace) -> int:
    from ecos.ssot.compiler.shadow_challenger import ShadowChallenger

    challenger = ShadowChallenger()
    target_p = Path(args.target).expanduser().resolve() if Path(args.target).is_file() else None

    if target_p and target_p.exists():
        report = challenger.challenge_file(target_p, domain=args.domain, auto_patch=args.auto_patch)
    else:
        report = challenger.challenge_text(args.target, domain=args.domain, auto_patch=args.auto_patch)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 1 if (not report.passed and args.strict) else 0

    status_icon = "🟢 ALL PASS" if report.passed else "🔴 FLAGGED VULNERABILITIES"
    print("\n⚡️ ─────────────────────────────────────────────────────────────")
    print("   影子红蓝对抗审议大盘 (Shadow Challenger Loop)")
    print(f"   目标: {report.target_name}   状态: {status_icon}   健壮度得分: {report.robustness_score}/100")
    print("─────────────────────────────────────────────────────────────────")

    if not report.challenges:
        print("  ✅ 审议通过：未发现重大审计预算、网络安全等保或科技转化法律漏洞。\n")
        return 0

    print(f"  ⚠️ 影子对抗发现 {len(report.challenges)} 处被攻击风险与合规隐患:")
    for c in report.challenges:
        sev_icon = "🔴" if c.severity == "BLOCK" else "🟡"
        print(f"\n  {sev_icon} [{c.perspective}] [{c.severity}] {c.flaw_title}")
        print(f"     ⚔️  对抗视角: {c.attack_critique}")
        print(f"     🛡️  合规配方: {c.patch_prescription}")

    if report.patched_text and args.auto_patch:
        print("\n  📦 已自动合成增强版合规补丁 (Auto-Patch Generated)")
        if args.output:
            out_p = Path(args.output).expanduser().resolve()
            import os

            os.makedirs(str(out_p.parent), exist_ok=True)
            with open(str(out_p), "w", encoding="utf-8") as f:
                f.write(report.patched_text)
            print(f"  ✅ 补丁已写入: {out_p}")

    print()
    if not report.passed and args.strict:
        return 1
    return 0


def cmd_cartridge(args: argparse.Namespace) -> int:
    from ecos.ssot.compiler.domain_cartridge import DomainCartridgeManager

    manager = DomainCartridgeManager()
    action = args.cartridge_action

    if action == "list":
        cartridges = manager.list_cartridges()
        if args.json:
            print(json.dumps([c.to_dict() for c in cartridges], ensure_ascii=False, indent=2))
            return 0
        print(f"\n📦 长尾领域卡带工坊列表 (Domain Cartridges, 共 {len(cartridges)} 个):")
        for c in cartridges:
            print(f"  • [{c.cartridge_id}] {c.name} (v{c.version})")
            print(f"    领域: {c.domain} | 作者: {c.author}")
            print(f"    规则数: {c.policies_count} | SOP 模板数: {c.sops_count}")
            print(f"    说明: {c.description}")
        print()
        return 0

    if action == "export":
        out_file = args.output
        try:
            exported_path = manager.export_cartridge(args.cartridge_id, output_path=out_file)
            print(f"✅ 领域卡带已成功导出: {exported_path}")
            return 0
        except Exception as e:
            print(f"❌ 导出卡带失败: {e}", file=sys.stderr)
            return 1

    if action == "validate":
        target = Path(args.file).expanduser().resolve()
        ok, errors = manager.validate_cartridge_file(target)
        if args.json:
            print(json.dumps({"file": str(target), "valid": ok, "errors": errors}, ensure_ascii=False, indent=2))
            return 0 if ok else 1

        if ok:
            print(f"✅ 领域卡带校验通过: {target}")
            return 0
        else:
            print(f"❌ 领域卡带校验失败: {target}")
            for err in errors:
                print(f"  • {err}")
            return 1

    print("❌ 请指定 cartridge 子命令: list, export, validate", file=sys.stderr)
    return 1


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

    # documents (ADR-0191)
    p_docs = subparsers.add_parser("documents", help="Workspace x Documents 双平面治理工具组 (ADR-0191)")
    p_docs_sub = p_docs.add_subparsers(dest="doc_action", required=True)

    p_doc_guard = p_docs_sub.add_parser("guardrail", help="生成 Documents 双平面提示词约束块")
    p_doc_guard.add_argument("--domain", default="work-weijian", help="领域名称")

    p_doc_audit = p_docs_sub.add_parser("audit", help="扫描 Documents 目录中的脚本与依赖违规")
    p_doc_audit.add_argument("path", nargs="?", default="~/Documents", help="Documents 扫描根路径")
    p_doc_audit.add_argument("--domain", default="default", help="调用方领域")
    p_doc_audit.add_argument("--strict", action="store_true", help="发现违规返回非 0 退出码")
    p_doc_audit.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_doc_sync = p_docs_sub.add_parser("sync-clients", help="同步生成多客户端 Documents MCP 配置")
    p_doc_sync.add_argument("--mode", choices=["install", "check", "render"], default="install", help="执行模式")
    p_doc_sync.add_argument("--dry-run", action="store_true", help="仅预检不实际写文件")
    p_doc_sync.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_docs.set_defaults(func=cmd_documents)

    # facts (ADR-0192)
    p_facts = subparsers.add_parser("facts", help="领域事实真源 Schema 校验与 SOP 模板引擎 (ADR-0192)")
    p_facts_sub = p_facts.add_subparsers(dest="facts_action", required=True)

    p_facts_validate = p_facts_sub.add_parser("validate", help="校验事实实体 Schema 规范与 14 天保鲜 SLA")
    p_facts_validate.add_argument("path", nargs="?", default=".", help="审计文件或目录路径")
    p_facts_validate.add_argument("--domain", default="all", help="过滤领域名称")
    p_facts_validate.add_argument("--max-age-days", type=int, default=14, help="最大允许的保鲜天数")
    p_facts_validate.add_argument("--strict", action="store_true", help="保鲜预警或违规时退出码非 0")
    p_facts_validate.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_facts_template = p_facts_sub.add_parser("template", help="生成标准领域事实 YAML 模板")
    p_facts_template.add_argument(
        "--domain", default="work-weijian", choices=["work-weijian", "work-transfer", "generic"], help="目标领域"
    )

    p_facts_serve = p_facts_sub.add_parser("serve", help="启动 Dual-Plane Truth Canvas Web 事实大盘 (ADR-0194)")
    p_facts_serve.add_argument("--host", default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    p_facts_serve.add_argument("--port", type=int, default=8765, help="监听端口 (默认 8765)")
    p_facts_serve.add_argument("--dir", help="自定义事实扫描目录")

    p_facts.set_defaults(func=cmd_facts)

    # policy (ADR-0193)
    p_policy = subparsers.add_parser("policy", help="领域 Policy-as-Code 业务规则与公文审查引擎 (ADR-0193)")
    p_policy_sub = p_policy.add_subparsers(dest="policy_action", required=True)

    p_policy_audit = p_policy_sub.add_parser("audit", help="对文档、方案或文本进行领域政策红线合规审计")
    p_policy_audit.add_argument("target", help="目标文档文件路径或输入文本")
    p_policy_audit.add_argument(
        "--domain", default="auto", choices=["auto", "work-weijian", "work-transfer", "all"], help="业务领域"
    )
    p_policy_audit.add_argument("--strict", action="store_true", help="存在警告或违规时退出码非 0")
    p_policy_audit.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_policy_explain = p_policy_sub.add_parser("explain", help="查看指定政策规则详细说明与处置建议")
    p_policy_explain.add_argument("policy_id", help="政策规则 ID (如 E-POL-WJ-001)")
    p_policy_explain.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_policy_list = p_policy_sub.add_parser("list", help="列出所有领域 Policy-as-Code 规则")
    p_policy_list.add_argument("--domain", help="按领域过滤 (work-weijian | work-transfer)")
    p_policy_list.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_policy.set_defaults(func=cmd_policy)

    # pitfall (ADR-0194)
    p_pitfall = subparsers.add_parser("pitfall", help="Agent 架构避坑与反模式检测知识库 (ADR-0194)")
    p_pitfall_sub = p_pitfall.add_subparsers(dest="pitfall_action", required=True)

    p_pitfall_scan = p_pitfall_sub.add_parser("scan", help="扫描代码或目录中的已知架构反模式与踩坑特征")
    p_pitfall_scan.add_argument("path", nargs="?", default=".", help="扫描路径 (文件或目录)")
    p_pitfall_scan.add_argument("--strict", action="store_true", help="发现踩坑隐患时退出码非 0")
    p_pitfall_scan.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_pitfall_list = p_pitfall_sub.add_parser("list", help="列出已知 Agent 避坑条目与经验教训")
    p_pitfall_list.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_pitfall_explain = p_pitfall_sub.add_parser("explain", help="查看指定避坑条目的教训与安全配方")
    p_pitfall_explain.add_argument("pitfall_id", help="避坑条目 ID (如 PITFALL-001)")
    p_pitfall_explain.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_pitfall.set_defaults(func=cmd_pitfall)

    # intent (ADR-0195)
    p_intent = subparsers.add_parser("intent", help="自然语言意图解构与工程规格编译器 (ADR-0195)")
    p_intent_sub = p_intent.add_subparsers(dest="intent_action", required=True)
    p_intent_compile = p_intent_sub.add_parser("compile", help="编译自然语言需求为 Policy/Fact/DAG 执行规格")
    p_intent_compile.add_argument("prompt", help="自然语言需求或意图描述")
    p_intent_compile.add_argument("--domain", default="auto", help="指定领域 (默认 auto)")
    p_intent_compile.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_intent.set_defaults(func=cmd_intent)

    # challenge (ADR-0196)
    p_challenge = subparsers.add_parser("challenge", help="双 Agent 影子红蓝对抗审议与自动打补丁引擎 (ADR-0196)")
    p_challenge.add_argument("target", help="待审议的方案、文本或文件路径")
    p_challenge.add_argument("--domain", default="auto", help="指定领域 (默认 auto)")
    p_challenge.add_argument(
        "--auto-patch", action="store_true", default=True, help="发现漏洞时自动合成合规补丁 (默认开启)"
    )
    p_challenge.add_argument("--no-patch", dest="auto_patch", action="store_false", help="仅审查不生成补丁")
    p_challenge.add_argument("--output", help="将打好补丁的文本保存到指定文件")
    p_challenge.add_argument("--strict", action="store_true", help="存在重大缺陷时返回非 0 退出码")
    p_challenge.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_challenge.set_defaults(func=cmd_challenge)

    # cartridge (ADR-0198)
    p_cartridge = subparsers.add_parser("cartridge", help="长尾领域治理卡带工坊与包管理器 (ADR-0198)")
    p_cartridge_sub = p_cartridge.add_subparsers(dest="cartridge_action", required=True)

    p_cartridge_list = p_cartridge_sub.add_parser("list", help="列出内置与已安装的领域卡带")
    p_cartridge_list.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_cartridge_export = p_cartridge_sub.add_parser("export", help="导出指定领域卡带为 YAML 文件")
    p_cartridge_export.add_argument("cartridge_id", help="卡带 ID (如 cartridge-weijian-v1)")
    p_cartridge_export.add_argument("--output", help="输出文件路径")

    p_cartridge_validate = p_cartridge_sub.add_parser("validate", help="校验领域卡带 YAML 完整性与规范")
    p_cartridge_validate.add_argument("file", help="卡带 YAML 文件路径")
    p_cartridge_validate.add_argument("--json", action="store_true", help="以 JSON 输出")

    p_cartridge.set_defaults(func=cmd_cartridge)

    # patrol (ADR-0192)
    p_patrol = subparsers.add_parser("patrol", help="全域治理与双平面自动化巡检 (ADR-0192)")
    p_patrol.add_argument("--output", help="输出 Markdown 报告文件路径")
    p_patrol.add_argument("--strict", action="store_true", help="发现任何未通过项时退出码非 0")
    p_patrol.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_patrol.set_defaults(func=cmd_patrol)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
