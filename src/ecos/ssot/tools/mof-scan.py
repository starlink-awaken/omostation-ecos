#!/usr/bin/env python3
"""
织星 MOF — M1 节点扫描器 (mof-scan)
=====================================
扫描 MOF 实际实例目录 (src/ecos/ssot/mof/m1/) 并产出状态分布报告。
基于 M2 元模型定义，校验 M1 实例的 status 合规性。

扫描源:
  - src/ecos/ssot/mof/m1/**/*.yaml   → 全量 M1 实例

用法:
    python3 mof-scan.py                    # 扫描+输出报告
    python3 mof-scan.py --summary          # 仅输出摘要
    python3 mof-scan.py --json             # JSON 输出
    python3 mof-scan.py --type=Protocol    # 仅扫描指定类型
    python3 mof-scan.py --check-status     # 校验 status 枚举合规性
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ── 路径 (实际 MOF 目录) ──
MOF_ROOT = Path(__file__).resolve().parent.parent / "mof"
M1_DIR = MOF_ROOT / "m1"
NODES_DIR = MOF_ROOT / "generated" / "nodes"

# 合规 status 枚举 (来自 m3.yaml Element.status)
VALID_STATUSES = {
    "draft",
    "active",
    "deprecated",
    "superseded",
    "archived",
    "proposed",
    "accepted",
    "done",
    "running",
    "identified",
    "scored",
    "scored_active",
    "aging",
    "resolved",
    "recorded",
    "adopted",
    "validated",
    "published",
    "planned",
    "stopped",
    "documented",
    "standalone",
    "emitted",
    "betted",
    "tracking",
    "predicting",
    "valid",
    # L4 KnowledgeObject 生命周期态 (m2/l4/knowledge-object.yaml stateMachine)
    # canonical / archived 与 L4DomainManifest suspended 等由 M2 schema 语义管辖
    "canonical",
    "suspended",
    "captured",
    "curated",
    "quarantined",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def scan_m1_instances() -> list[dict]:
    """扫描实际 M1 实例目录 → 全量实例报告"""
    nodes = []
    if not M1_DIR.exists():
        return nodes
    for f in sorted(M1_DIR.rglob("*.yaml")):
        try:
            import yaml

            with open(f) as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                continue
            status = data.get("status", "unknown")
            nodes.append(
                {
                    "id": data.get("id", f.stem),
                    "type": data.get("type", "Unknown"),
                    "name": data.get("name", f.stem),
                    "status": str(status).strip('"'),
                    "path": str(f.relative_to(MOF_ROOT)),
                    "subtype": data.get("subtype", ""),
                }
            )
        except Exception:
            continue
    return nodes


def check_status_compliance(nodes: list[dict]) -> list[dict]:
    """校验 status 值是否在合规枚举内"""
    violations = []
    for n in nodes:
        st = n.get("status", "").lower().strip()
        if st and st not in VALID_STATUSES:
            violations.append({"id": n["id"], "status": n["status"], "path": n.get("path", "")})
    return violations


def save_nodes(nodes: list[dict], node_type: str = "all"):
    """保存节点到 nodes/ 目录（使用 yaml.dump 确保格式正确）"""
    import yaml

    NODES_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    for n in nodes:
        if node_type != "all" and n["type"].lower() != node_type.lower():
            continue
        filename = f"{n['id']}.yaml"
        filepath = NODES_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# M1 Node: {n['id']}\n")
            f.write(f"# Type: {n['type']}\n")
            f.write(f"# Generated: {now()}\n\n")
            yaml.dump(n, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        saved += 1
    return saved


def main():
    parser = argparse.ArgumentParser(description="织星 MOF M1 节点扫描器")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--type", type=str, default="all")
    parser.add_argument("--save", action="store_true", default=False)
    parser.add_argument("--check-status", action="store_true")
    args = parser.parse_args()

    # 主扫描源: 实际 M1 实例目录
    m1_nodes = scan_m1_instances()
    if args.type != "all":
        m1_nodes = [node for node in m1_nodes if node.get("type", "").lower() == args.type.lower()]

    if args.check_status:
        violations = check_status_compliance(m1_nodes)
        print("\n── Status 合规校验 ──")
        print(f"  总实例: {len(m1_nodes)}")
        print(f"  不合规: {len(violations)}")
        if violations:
            for v in violations[:20]:
                print(f"    ⚠️ {v['id']}: status={v['status']} ({v['path']})")
        return

    # status 分布统计
    status_counts = Counter(n.get("status", "unknown") for n in m1_nodes)
    type_counts = Counter(n.get("type", "Unknown") for n in m1_nodes)

    if args.json:
        print(json.dumps(m1_nodes, ensure_ascii=False, indent=2))
        return

    if args.save:
        saved = save_nodes(m1_nodes, args.type)
        print(f"✅ {saved} 个 M1 节点 → {NODES_DIR}/")
        return

    if args.summary or not any((args.json, args.save, args.check_status)):
        print("\n── MOF M1 实例扫描 ──")
        print(f"  总实例: {len(m1_nodes)}")
        print("\n  状态分布 (Top 10):")
        for st, c in status_counts.most_common(10):
            print(f"    {st:20s}: {c}")
        print("\n  类型分布 (Top 10):")
        for tp, c in type_counts.most_common(10):
            print(f"    {tp:20s}: {c}")

        # status 合规校验
        violations = check_status_compliance(m1_nodes)
        print(f"\n  状态合规: {len(m1_nodes) - len(violations)}/{len(m1_nodes)} (不合规 {len(violations)})")


if __name__ == "__main__":
    main()
