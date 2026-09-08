#!/usr/bin/env python3
"""canonical-traceability — KOS canonical 文档可追溯率量化仪表.

蓝图 2027 目标: canonical 可追溯 ≥98%。
计算: ~/.kos/kos-index.sqlite 中 canonical_path 非空的文档占比。

用法:
    python3 canonical-traceability.py --json    # JSON 输出
    python3 canonical-traceability.py           # 人读输出
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

KOS_DB = Path.home() / ".kos" / "kos-index.sqlite"


def compute() -> dict:
    if not KOS_DB.exists():
        return {"error": f"KOS db not found: {KOS_DB}"}
    conn = sqlite3.connect(str(KOS_DB))
    total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    tracked = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE canonical_path != '' AND canonical_path IS NOT NULL"
    ).fetchone()[0]
    # 按域统计
    by_zone = conn.execute(
        "SELECT zone, COUNT(*) as cnt, "
        "SUM(CASE WHEN canonical_path != '' AND canonical_path IS NOT NULL THEN 1 ELSE 0 END) as tracked "
        "FROM documents GROUP BY zone ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    ratio = (tracked / total * 100) if total else 0.0
    return {
        "total_documents": total,
        "tracked_documents": tracked,
        "traceability_ratio": round(ratio, 1),
        "target": 98.0,
        "meets_target": ratio >= 98.0,
        "by_zone": [
            {"zone": r[0], "total": r[1], "tracked": r[2], "ratio": round(r[2] / r[1] * 100, 1) if r[1] else 0}
            for r in by_zone
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    data = compute()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"📊 Canonical 可追溯率: {data['traceability_ratio']}% ({data['tracked_documents']}/{data['total_documents']})")
        print(f"   蓝图 2027 目标: ≥{data['target']}% → {'✅ 达标' if data['meets_target'] else '❌ 未达标'}")
        print()
        for z in data.get("by_zone", []):
            print(f"  {z['zone']:16} {z['tracked']:5}/{z['total']:5} ({z['ratio']}%)")
    return 0 if data.get("meets_target") else 1


if __name__ == "__main__":
    sys.exit(main())

