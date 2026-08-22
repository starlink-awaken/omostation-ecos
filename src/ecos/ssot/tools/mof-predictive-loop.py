#!/usr/bin/env python3
"""
mof-predictive-loop — 预测治理闭环
====================================
串联约束编译 + M0 衰减 + M1 健康度 → 统一预测报告.

管线:
  L0-constraints.yaml → ecos-constraint-compiler → 约束合规状态
  M0-snapshot.yaml   → 协议衰减计算          → 剩余价值预测
  M1 instances       → mof-scan --check-status → 实例健康度

输出: 综合预测报告 (当前状态 + 趋势 + 预测行动)

用法:
    python3 mof-predictive-loop.py              # 文本报告
    python3 mof-predictive-loop.py --json       # JSON 输出
    python3 mof-predictive-loop.py --enforce    # 预测性失败则 exit 1
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ECOS = TOOLS_DIR.parent.parent.parent.parent  # projects/ecos
COMPILER = ECOS / "src" / "ecos" / "ssot" / "tools" / "ecos-constraint-compiler.py"
SCAN = ECOS / "src" / "ecos" / "ssot" / "tools" / "mof-scan.py"
SLA = ECOS / "src" / "ecos" / "ssot" / "tools" / "mof-sla.py"
M0_FILE = ECOS / "src" / "ecos" / "ssot" / "mof" / "m0" / "snapshot.yaml"


def run_tool(cmd: list[str]) -> tuple[int, str, str]:
    """运行工具, 返回 (returncode, stdout, stderr)"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


def load_m0() -> dict:
    """加载 M0 快照"""
    try:
        import yaml
        return yaml.safe_load(M0_FILE.read_text()) or {}
    except Exception:
        return {}


def predict_actions(constraints_result: dict, m0: dict, scan_violations: int) -> list[str]:
    """基于当前状态 + 趋势生成预测行动"""
    actions = []

    # 约束违规 → 立即行动
    failed = [c for c in constraints_result.get("constraints", []) if not c.get("passed") and c.get("type") == "required"]
    for f in failed:
        actions.append(f"[IMMEDIATE] Fix {f['id']}: {f.get('description', '')[:50]}")

    # M1 不合规 → 归档或修复
    if scan_violations > 0:
        actions.append(f"[IMMEDIATE] Fix {scan_violations} M1 status violations (mof-scan --check-status)")

    # M0 协议衰减 → 预测性提醒
    protocols = m0.get("protocols", {})
    for pid, pdata in protocols.items():
        remaining = pdata.get("remaining_pct", 100)
        if remaining < 30:
            actions.append(f"[PREDICT] Protocol {pid} near expiry ({remaining:.0f}% remaining) — plan refresh")
        elif remaining < 50:
            actions.append(f"[WATCH] Protocol {pid} aging ({remaining:.0f}% remaining)")

    if not actions:
        actions.append("[OK] All systems nominal — no predicted actions")

    return actions


def main():
    parser = argparse.ArgumentParser(description="MOF predictive governance loop")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--enforce", action="store_true", help="exit 1 on immediate actions needed")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()

    # 1. 约束编译 (用相对路径, 避免 uv run 绝对路径问题)
    rc, cout, cerr = run_tool(
        ["uv", "run", "python3", "src/ecos/ssot/tools/ecos-constraint-compiler.py", "--json"]
    )
    try:
        constraint_result = json.loads(cout) if cout.strip() else {"error": cerr or "no output"}
    except json.JSONDecodeError:
        constraint_result = {"error": "compiler output parse failed", "raw": cout[:200]}

    # 2. M1 健康度
    rc2, cout2, _ = run_tool(["uv", "run", "python3", str(SCAN), "--check-status"])
    scan_violations = 0
    for line in cout2.splitlines():
        if "不合规:" in line or "violations:" in line:
            try:
                scan_violations = int("".join(c for c in line if c.isdigit()) or "0")
            except ValueError:
                pass

    # 3. M0 快照
    m0 = load_m0()

    # 4. 预测行动
    actions = predict_actions(constraint_result, m0, scan_violations)

    report = {
        "generated_at": now,
        "constraint_compiler": {
            "status": "ok" if rc == 0 else "fail",
            "failed_required": len([c for c in constraint_result.get("constraints", []) if not c.get("passed") and c.get("type") == "required"]),
        },
        "m1_health": {
            "violations": scan_violations,
            "status": "ok" if scan_violations == 0 else "fail",
        },
        "m0_snapshot": {
            "protocols": len(m0.get("protocols", {})),
            "generated_at": m0.get("generated_at", "unknown"),
        },
        "predicted_actions": actions,
        "overall_status": "healthy" if rc == 0 and scan_violations == 0 else "action_required",
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("  MOF 预测治理闭环报告")
        print("=" * 60)
        print(f"  时间: {now}")
        print(f"  约束编译: {'PASS' if rc == 0 else 'FAIL'} ({report['constraint_compiler']['failed_required']} required violations)")
        print(f"  M1 健康:  {'OK' if scan_violations == 0 else f'{scan_violations} violations'}")
        print(f"  M0 协议:  {report['m0_snapshot']['protocols']} protocols tracked")
        print(f"  总体:     {report['overall_status']}")
        print()
        print("  ── 预测行动 ──")
        for a in actions:
            print(f"    {a}")
        print(f"\n{'=' * 60}")

    if args.enforce and report["overall_status"] != "healthy":
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
