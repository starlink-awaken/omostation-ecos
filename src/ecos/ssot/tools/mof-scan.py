#!/usr/bin/env python3
"""
织星 MOF — M1 节点扫描器 (mof-scan)
=====================================
扫描 MOF 实际实例目录 (src/ecos/ssot/mof/m1/) 并产出状态分布报告。
基于 M2 元模型定义，校验 M1 实例的 status 合规性。

扫描源 (主):
  - src/ecos/ssot/mof/m1/**/*.yaml   → 全量 M1 实例 (1400+)
  - src/ecos/ssot/registry/L0-constraints.yaml → Protocol + Specification
  - src/ecos/ssot/mof/m2/*.yaml      → M2 schema 引用

用法:
    python3 mof-scan.py                    # 扫描+输出报告
    python3 mof-scan.py --summary          # 仅输出摘要
    python3 mof-scan.py --json             # JSON 输出
    python3 mof-scan.py --type=Protocol    # 仅扫描指定类型
    python3 mof-scan.py --check-status     # 校验 status 枚举合规性
"""

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ── 路径 (实际 MOF 目录) ──
MOF_ROOT = Path(__file__).resolve().parent.parent / "mof"
M1_DIR = MOF_ROOT / "m1"
M2_DIR = MOF_ROOT / "m2"
CONSTRAINTS_FILE = Path(__file__).resolve().parent.parent / "registry" / "L0-constraints.yaml"
NODES_DIR = MOF_ROOT / "generated" / "nodes"

# 合规 status 枚举 (来自 m3.yaml Element.status)
VALID_STATUSES = {"draft", "active", "deprecated", "superseded", "archived", "proposed", "accepted", "done", "running", "identified", "scored", "scored_active", "aging", "resolved", "recorded", "adopted", "validated", "published", "planned", "stopped", "documented"}


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
            nodes.append({
                "id": data.get("id", f.stem),
                "type": data.get("type", "Unknown"),
                "name": data.get("name", f.stem),
                "status": str(status).strip('"'),
                "path": str(f.relative_to(MOF_ROOT)),
                "subtype": data.get("subtype", ""),
            })
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


def scan_scripts() -> list[dict]:
    """扫描脚本目录 → Artifact 节点"""
    nodes = []
    if not SCRIPTS_DIR.exists():
        return nodes
    for f in sorted(SCRIPTS_DIR.glob("*.py")):
        stat = f.stat()
        # Read docstring for description
        desc = ""
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('"""') and desc == "":
                    desc = line.strip('"').strip()
                    if not desc:
                        continue
                    break
        if not desc:
            desc = f.name
        nodes.append(
            {
                "id": f"ARTIFACT-SCRIPT-{f.stem}",
                "type": "Artifact",
                "subtype": "Script",
                "name": f.stem,
                "description": desc[:120],
                "status": "active",
                "domain": "meta",
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "version": "1.0.0",
                "properties": {
                    "path": str(f.relative_to(DOCS)),
                    "format": "python",
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                },
                "layer": infer_layer(f.stem),
            }
        )
    return nodes


def infer_layer(name: str) -> str:
    """根据脚本名推断所属层"""
    mapping = {
        "ecos-daemon": "L1",
        "ecos-sla": "L1",
        "ecos-healer": "L1",
        "ecos-constraint": "L0",
        "ecos-brief": "L4",
        "ecos-health": "L4",
        "ecos-whoami": "L4",
        "ecos-onboard": "L4",
        "ecos-bootstrap": "L4",
        "ecos-weekly-digest": "L4",
        "ecos-entry": "L4",
        "check-claude": "X2",
        "check-vault": "X1",
        "check-cards": "X4",
        "check-kairon": "X1",
        "kairon-cost": "X3",
        "vault-value": "X3",
        "domain-value": "X3",
        "cards-value": "X3",
        "x3-coverage": "X3",
        "task-status": "X4",
        "runtime-mcp": "L3",
        "fix-debts": "X4",
    }
    for key, layer in mapping.items():
        if key in name:
            return layer
    return "L4"


def scan_protocols() -> list[dict]:
    """扫描 L0-constraints.yaml → Protocol 节点"""
    nodes = []
    if not CONSTRAINTS_FILE.exists():
        return nodes
    import yaml

    with open(CONSTRAINTS_FILE) as f:
        data = yaml.safe_load(f)
    registry = data.get("protocol_registry", [])
    for p in registry:
        nodes.append(
            {
                "id": f"PROTOCOL-{p['id']}",
                "type": "Protocol",
                "name": p["id"],
                "description": p.get("description", ""),
                "status": p.get("status", "active"),
                "domain": "meta",
                "created": p.get("introduced", "2026-01-01"),
                "version": p.get("version", "0.0.0"),
                "properties": {
                    "version_spec": p.get("version", ""),
                    "introduced": p.get("introduced", ""),
                    "half_life": p.get("half_life_days", 180),
                    "registered": True,
                    "value_tier": p.get("value_tier", 3),
                },
                "layer": "L0",
            }
        )
    # Also add the Specification itself
    nodes.append(
        {
            "id": "SPEC-L0-CONSTRAINTS",
            "type": "Specification",
            "name": "L0 协议约束规范",
            "description": "9条约束覆盖 X1-X3 治理维度的协议级规则定义",
            "status": "active",
            "domain": "meta",
            "created": "2026-06-06",
            "version": "1.0.0",
            "properties": {
                "constraints": [c["id"] for c in data.get("constraints", [])],
                "scope": ["L0", "L1", "L2", "L3", "L4", "I0"],
                "enforcement": data.get("execution", {}).get("mode", "warn"),
            },
            "layer": "L0",
        }
    )
    return nodes


def scan_cards() -> list[dict]:
    """扫描 CARDS SQLite → Entity 节点（仅活跃卡片）"""
    nodes = []
    if not CARDS_DB.exists():
        return nodes
    conn = sqlite3.connect(str(CARDS_DB))
    cur = conn.execute("""
        SELECT id, type, title, summary, status, domain, priority, created_at
        FROM cards
        WHERE status NOT IN ('done','resolved','discarded','archived','cancelled','superseded','closed')
        ORDER BY priority, created_at
        LIMIT 20
    """)
    for row in cur.fetchall():
        cid, ctype, title, summary, status, domain, priority, created = row
        nodes.append(
            {
                "id": f"ENTITY-CARD-{cid}",
                "type": "Entity",
                "subtype": "Card",
                "name": title[:60] if title else cid,
                "description": summary[:150] if summary else "",
                "status": "active",
                "domain": domain or "meta",
                "created": created or now(),
                "version": "1.0.0",
                "properties": {
                    "card_type": ctype,
                    "card_status": status,
                    "priority": priority,
                    "entity_type": "concept",
                },
                "layer": "L4",
            }
        )
    conn.close()
    return nodes


def scan_architecture() -> list[dict]:
    """扫描架构文档 → Architecture 节点"""
    nodes = []
    DOCS / "学习进化" / "2-knowledge" / "基建架构" / "eCOS-v5-Architecture-SSOT.md"

    nodes.append(
        {
            "id": "ARCH-ECOS-V5",
            "type": "Architecture",
            "name": "织星架构 (eCOS v6)",
            "description": "5层技术栈(L0-L4) + 4维治理(X1-X4) + 1织物(I0) + 1界面(P0)",
            "status": "active",
            "domain": "meta",
            "created": "2026-06-05",
            "version": "5.3.0",
            "properties": {
                "topology": "layered",
                "components": [
                    "L0-ProtocolWeave",
                    "L1-RuntimeMatrix",
                    "L2-KernelTriPlane",
                    "L3-EntryBridge",
                    "L4-SelfLayer",
                    "I0-Agora",
                    "P0-Product",
                ],
                "connectors": ["MCP", "ACP", "A2A", "BOS_URI"],
                "quality_attrs": {
                    "consistency": "SSOT级联",
                    "auditability": "X1-X4全覆盖",
                },
                "evolution_path": [
                    "v4.2(5+4+1+1)",
                    "v5.0(5+4+1+X4)",
                    "v5.3(织星·MOF基座)",
                ],
            },
            "layer": "multi",
            "sources": [
                str(ARCH_FILE.relative_to(DOCS)) if ARCH_FILE.exists() else "",
                "学习进化/2-knowledge/基建架构/eCOS-v5-Architecture-SSOT.md",
            ],
        }
    )

    nodes.append(
        {
            "id": "MODEL-UNIFIED-ARCH",
            "type": "Model",
            "name": "统一架构模型",
            "description": "5+4+1+1 ↔ L0-L4+X1-X4 双向映射矩阵——三视图统一的 SSOT",
            "status": "active",
            "domain": "meta",
            "created": "2026-06-05",
            "version": "1.1.0",
            "properties": {
                "source": "5+4+1+1 织星架构",
                "mapping": {"功能域视图": "5+4+1+1", "技术栈视图": "L0-L4+X1-X4+I0+P0"},
                "formality": "semiformal",
                "projects_to": ["MADF V1-V8"],
            },
            "layer": "multi",
            "sources": ["@驾驶舱/统一架构模型.md"],
        }
    )

    return nodes


def scan_entities() -> list[dict]:
    """扫描领域知识库 → Entity 节点（领域实体）"""
    nodes = []
    if not ENTITY_DIR.exists():
        return nodes
    for md in ENTITY_DIR.glob("**/实体/*.md"):
        if "template" in md.name.lower() or "模板" in md.name:
            continue
        stat = md.stat()
        name = md.stem
        entity_type = "concept"
        domain = str(md.parent.parent.parent.name) if md.parent.parent.parent != ENTITY_DIR else "领域知识库"
        # Infer entity type from path
        if "人物" in str(md):
            entity_type = "person"
        elif "组织" in str(md):
            entity_type = "organization"
        elif "系统" in str(md):
            entity_type = "system"

        nodes.append(
            {
                "id": f"ENTITY-DOMAIN-{name}",
                "type": "Entity",
                "subtype": "DomainEntity",
                "name": name,
                "description": f"领域实体: {name}",
                "status": "active",
                "domain": domain,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "version": "1.0.0",
                "properties": {
                    "entity_type": entity_type,
                    "sources": [str(md.relative_to(DOCS))],
                    "identity": {"name": name},
                },
                "layer": "L4",
            }
        )
    return nodes


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
    parser.add_argument("--summary", action="store_true", default=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--type", type=str, default="all")
    parser.add_argument("--save", action="store_true", default=False)
    parser.add_argument("--check-status", action="store_true")
    args = parser.parse_args()

    # 主扫描源: 实际 M1 实例目录
    m1_nodes = scan_m1_instances()

    if args.check_status:
        violations = check_status_compliance(m1_nodes)
        print(f"\n── Status 合规校验 ──")
        print(f"  总实例: {len(m1_nodes)}")
        print(f"  不合规: {len(violations)}")
        if violations:
            for v in violations[:20]:
                print(f"    ⚠️ {v['id']}: status={v['status']} ({v['path']})")
        return

    # status 分布统计
    status_counts = Counter(n.get("status", "unknown") for n in m1_nodes)
    type_counts = Counter(n.get("type", "Unknown") for n in m1_nodes)

    if args.summary:
        print("\n── MOF M1 实例扫描 ──")
        print(f"  总实例: {len(m1_nodes)}")
        print(f"\n  状态分布 (Top 10):")
        for st, c in status_counts.most_common(10):
            print(f"    {st:20s}: {c}")
        print(f"\n  类型分布 (Top 10):")
        for tp, c in type_counts.most_common(10):
            print(f"    {tp:20s}: {c}")

        # status 合规校验
        violations = check_status_compliance(m1_nodes)
        print(f"\n  状态合规: {len(m1_nodes) - len(violations)}/{len(m1_nodes)} (不合规 {len(violations)})")
        return

    if args.json:
        print(json.dumps(m1_nodes, ensure_ascii=False, indent=2))

    if args.save:
        saved = save_nodes(all_nodes, args.type)
        print(f"✅ {saved} 个 M1 节点 → {NODES_DIR}/")
    else:
        if args.json:
            print(json.dumps(all_nodes, ensure_ascii=False, indent=2))
        else:
            for n in all_nodes:
                print(f"  {n['type']:15s} {n['id']:40s} {n['name'][:50]}")


if __name__ == "__main__":
    main()
