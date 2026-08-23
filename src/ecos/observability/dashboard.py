#!/usr/bin/env python3
"""eCOS Unified Dashboard — Agent + Governance + Execute 三联面板.

用法:
    python3 dashboard.py              # 全量面板
    python3 dashboard.py --json       # JSON 输出
    python3 dashboard.py agents       # 仅 Agent 面板
    python3 dashboard.py governance    # 仅治理面板
    python3 dashboard.py execute       # 仅执行面板
    python3 dashboard.py --watch 10    # 每 10s 刷新
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "ssot" / "tools"


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -1, str(e)


def panel_agents() -> dict:
    """Agent 面板 — 检测运行中的 agent 进程."""
    agents = []
    # 检测关键进程
    checks = [
        ("signal-poller", "signal-poller"),
        ("agent-tick-daemon", "agent-tick"),
        ("governance-scanner", "governance-scanner"),
        ("evolution-agent", "evolution-agent"),
        ("knowledge-foundry", "knowledge-foundry"),
        ("autoloop-daily", "autoloop"),
        ("mof-predictive", "mof-predictive-loop"),
        ("mof-scan", "mof-scan"),
    ]
    for name, keyword in checks:
        rc, out = _run(["pgrep", "-fl", keyword])
        running = rc == 0 and out.strip()
        agents.append({
            "name": name,
            "status": "running" if running else "silent",
            "pid": out.strip().split("\n")[0].split()[0] if running else None,
        })
    running_count = sum(1 for a in agents if a["status"] == "running")
    return {
        "agents": agents,
        "running": running_count,
        "total": len(agents),
        "healthy": running_count >= len(agents) // 2,
    }


def panel_governance() -> dict:
    """治理面板 — 约束合规 + M1 健康 + 推理引擎."""
    # M1 compliance
    rc, out = _run([sys.executable, str(TOOLS / "mof-scan.py"), "--check-status"])
    violations = 0
    for line in out.splitlines():
        if "不合规:" in line:
            try:
                violations = int("".join(c for c in line if c.isdigit()) or "0")
            except ValueError:
                pass

    # Constraint compiler
    rc2, out2 = _run([sys.executable, str(TOOLS / "ecos-constraint-compiler.py"), "--enforce", "--json"])
    try:
        import json as _json
        cc_data = _json.loads(out2)
        cc_failed = cc_data.get("constraint_compiler", {}).get("failed_required", 0)
    except Exception:
        cc_failed = -1

    # Reasoning engines
    reasoning = {}
    # mof-reason: impact analysis
    rc_r, _ = _run([sys.executable, str(TOOLS / "mof-reason.py"), "impact", "ACTION-ACP-IMPLEMENT"])
    reasoning["mof-reason"] = "ok" if rc_r == 0 else "fail"
    # mof-derive: full report
    rc_d, out_d = _run([sys.executable, str(TOOLS / "mof-derive.py")])
    reasoning["mof-derive"] = "ok" if rc_d == 0 and ("覆盖率" in out_d or "coverage" in out_d.lower()) else "fail"
    # mof-gate: gate check
    rc_g, out_g = _run([sys.executable, str(TOOLS / "mof-gate.py")])
    reasoning["mof-gate"] = "ok" if rc_g == 0 and "违规: 0" in out_g else "fail"

    return {
        "m1": {"violations": violations, "compliant": violations == 0},
        "constraints": {"failed_required": cc_failed, "compliant": cc_failed == 0},
        "reasoning": reasoning,
        "healthy": violations == 0 and cc_failed == 0,
    }


def panel_execute() -> dict:
    """执行面板 — L1/L2/L3 可用性."""
    checks = {}
    # L1 Scheduler
    try:
        from ecos.l1.runtime.scheduler import L1Scheduler
        s = L1Scheduler()
        s.schedule_step({"name": "ping"})
        checks["l1_scheduler"] = "ok"
    except Exception as e:
        checks["l1_scheduler"] = f"fail: {e}"

    # L2 Engine
    try:
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        count = len(engine.query_m1())
        checks["l2_engine"] = f"ok ({count} nodes)"
    except Exception as e:
        checks["l2_engine"] = f"fail: {e}"

    # L3 Entry
    try:
        from ecos.l3.entry.api import L3Entry
        h = L3Entry().health()
        checks["l3_entry"] = f"ok ({h['status']})"
    except Exception as e:
        checks["l3_entry"] = f"fail: {e}"

    failed = sum(1 for v in checks.values() if v.startswith("fail"))
    return {"components": checks, "healthy": failed == 0}


def render_text(data: dict) -> str:
    """渲染文本面板."""
    lines = []
    lines.append("=" * 64)
    lines.append(f"  eCOS Unified Dashboard — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 64)

    # Agents
    ag = data["agents"]
    icon = "🟢" if ag["healthy"] else "🔴"
    lines.append(f"\n  {icon} Agents: {ag['running']}/{ag['total']} running")
    for a in ag["agents"]:
        icon_a = "✓" if a["status"] == "running" else "✗"
        lines.append(f"    [{icon_a}] {a['name']:25s} {a['status']}")

    # Governance
    gov = data["governance"]
    icon_g = "🟢" if gov["healthy"] else "🔴"
    lines.append(f"\n  {icon_g} Governance")
    lines.append(f"    M1 violations: {gov['m1']['violations']}")
    lines.append(f"    Constraint failed: {gov['constraints']['failed_required']}")
    for tool, status in gov["reasoning"].items():
        icon_t = "✓" if status == "ok" else "✗"
        lines.append(f"    [{icon_t}] {tool}")

    # Execute
    ex = data["execute"]
    icon_e = "🟢" if ex["healthy"] else "🔴"
    lines.append(f"\n  {icon_e} Execute")
    for comp, status in ex["components"].items():
        icon_c = "✓" if not status.startswith("fail") else "✗"
        lines.append(f"    [{icon_c}] {comp}: {status}")

    overall = ag["healthy"] and gov["healthy"] and ex["healthy"]
    lines.append(f"\n  Overall: {'🟢 HEALTHY' if overall else '🔴 DEGRADED'}")
    lines.append(f"\n{'=' * 64}")
    return "\n".join(lines)


def check_alerts(data: dict) -> list[dict]:
    """检查告警条件, 返回告警列表."""
    alerts = []
    # P0: M1 violations
    if data["governance"]["m1"]["violations"] > 0:
        alerts.append({"level": "P0", "msg": f"M1 violations: {data['governance']['m1']['violations']}"})
    # P0: Constraint failed
    if data["governance"]["constraints"]["failed_required"] > 0:
        alerts.append({"level": "P0", "msg": f"Constraint failed: {data['governance']['constraints']['failed_required']}"})
    # P1: Core agents (signal-poller, agent-tick) silent
    core = ["signal-poller", "agent-tick-daemon"]
    core_silent = [a for a in data["agents"]["agents"] if a["name"] in core and a["status"] != "running"]
    if len(core_silent) == len(core):
        alerts.append({"level": "P1", "msg": "Core agents silent: " + ", ".join(a["name"] for a in core_silent)})
    elif data["agents"]["running"] == 0:
        alerts.append({"level": "P2", "msg": "All agents silent"})
    # P1: Reasoning engine fail
    for tool, status in data["governance"]["reasoning"].items():
        if status == "fail":
            alerts.append({"level": "P1", "msg": f"Reasoning engine fail: {tool}"})
    # P2: Execute component fail
    for comp, status in data["execute"]["components"].items():
        if status.startswith("fail"):
            alerts.append({"level": "P2", "msg": f"Execute component fail: {comp}"})
    return alerts


def main():
    parser = argparse.ArgumentParser(description="eCOS Unified Dashboard")
    parser.add_argument("panel", nargs="?", choices=["agents", "governance", "execute"])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--watch", type=int, default=0, help="刷新间隔(秒)")
    parser.add_argument("--check", action="store_true", help="CI 模式: P0/P1 退出码 1")
    args = parser.parse_args()

    def gather():
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents": panel_agents(),
            "governance": panel_governance(),
            "execute": panel_execute(),
        }

    data = gather()
    alerts = check_alerts(data)

    if args.check:
        # CI 模式: 有 P0/P1 告警则 exit 1
        critical = [a for a in alerts if a["level"] in ("P0", "P1")]
        if critical:
            for a in critical:
                print(f"[{a['level']}] {a['msg']}", file=sys.stderr)
            sys.exit(1)
        print("OK: no P0/P1 alerts")
        sys.exit(0)

    if args.watch > 0:
        while True:
            data = gather()
            if args.json:
                print(json.dumps({"data": data, "alerts": check_alerts(data)}, ensure_ascii=False, indent=2))
            else:
                print("\033[2J\033[H")
                print(render_text(data))
                alerts = check_alerts(data)
                if alerts:
                    print(f"\n  ⚠️  {len(alerts)} alert(s):")
                    for a in alerts:
                        print(f"    [{a['level']}] {a['msg']}")
            time.sleep(args.watch)
    else:
        if args.json:
            print(json.dumps({"data": data, "alerts": alerts}, ensure_ascii=False, indent=2))
        else:
            print(render_text(data))
            if alerts:
                print(f"\n  ⚠️  {len(alerts)} alert(s):")
                for a in alerts:
                    print(f"    [{a['level']}] {a['msg']}")


if __name__ == "__main__":
    sys.exit(main())
