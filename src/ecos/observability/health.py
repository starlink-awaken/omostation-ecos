"""eCOS Observability — 推理与治理管线可观测性.

暴露推理引擎、约束编译器、M1 健康度的运行时指标.

能力:
  - health_check: 全量健康快照
  - reasoning_status: 推理引擎状态
  - constraint_status: 约束合规状态
  - m1_status: M1 实例健康度
  - metrics: 汇总指标 (JSON)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any


def reasoning_status() -> dict:
    """推理引擎状态."""
    import subprocess
    import sys
    from pathlib import Path
    TOOLS = Path(__file__).resolve().parent.parent / "ssot" / "tools"
    status = {"timestamp": datetime.now(timezone.utc).isoformat()}
    for tool in ["mof-reason", "mof-derive", "mof-gate"]:
        r = subprocess.run(
            [sys.executable, str(TOOLS / f"{tool}.py"), "--json"] if tool == "mof-derive"
            else [sys.executable, str(TOOLS / f"{tool}.py"), "impact", "OMOTASK-P35-W1-W2-COMBO"],
            capture_output=True, text=True, timeout=30,
        )
        status[tool] = {"ok": r.returncode == 0, "output_len": len(r.stdout)}
    return status


def constraint_status() -> dict:
    """约束合规状态."""
    import subprocess
    import sys
    from pathlib import Path
    TOOLS = Path(__file__).resolve().parent.parent / "ssot" / "tools"
    r = subprocess.run(
        [sys.executable, str(TOOLS / "ecos-constraint-compiler.py"), "--enforce", "--json"],
        capture_output=True, text=True, timeout=30,
    )
    import json
    try:
        data = json.loads(r.stdout)
        return {"ok": r.returncode == 0, "data": data}
    except Exception:
        return {"ok": r.returncode == 0, "raw": r.stdout[:200]}


def m1_status() -> dict:
    """M1 实例健康度."""
    import subprocess
    import sys
    from pathlib import Path
    TOOLS = Path(__file__).resolve().parent.parent / "ssot" / "tools"
    r = subprocess.run(
        [sys.executable, str(TOOLS / "mof-scan.py"), "--check-status"],
        capture_output=True, text=True, timeout=30,
    )
    # parse violations count
    violations = 0
    for line in r.stdout.splitlines():
        if "不合规:" in line:
            try:
                violations = int("".join(c for c in line if c.isdigit()) or "0")
            except ValueError:
                pass
    return {"ok": violations == 0, "violations": violations}


def health_check() -> dict:
    """全量健康快照."""
    start = time.time()
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reasoning": reasoning_status(),
        "constraints": constraint_status(),
        "m1": m1_status(),
    }
    result["elapsed_ms"] = round((time.time() - start) * 1000, 1)
    # overall
    all_ok = (
        all(v.get("ok") for v in result["reasoning"].values() if isinstance(v, dict))
        and result["constraints"].get("ok")
        and result["m1"].get("ok")
    )
    result["overall"] = "healthy" if all_ok else "degraded"
    return result


def metrics() -> dict:
    """汇总指标."""
    return {
        "health": health_check(),
        "versions": {"reasoning": "1.0", "constraints": "2.0", "m1": "1.0"},
    }
