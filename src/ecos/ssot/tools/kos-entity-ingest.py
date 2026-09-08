#!/usr/bin/env python3
"""kos-entity-ingest — M1 ENTITY-SSOT-* 投影 → ~/.kos/kos-index.sqlite kos_entities.

KOS 知识桥消费端 (MOF 侧 mof-entity-ssot 的对偶):
  - MOF 侧: @公共/_entities → m1/entity_ssot/ENTITY-SSOT-*.yaml (解析键 SSOT)
  - KOS 侧: 本工具把投影灌入 ~/.kos 主知识库 kos_entities 表
  - 幂等: INSERT OR REPLACE (以 entity_id 为唯一键)
  - zone: 'mof-ssot' (与 kos 的 'gbrain' / 'documents' 等来源区隔)
  - 不写 kos_relations / kos_entity_docs (留给后续 gbrain 消费)

用法:
    python3 kos-entity-ingest.py --dry-run    # 预览
    python3 kos-entity-ingest.py --write      # 灌入
    python3 kos-entity-ingest.py --status     # 查看当前灌入统计
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

MOF_M1 = Path(__file__).resolve().parents[1] / "mof" / "m1"
SSOT_DIR = MOF_M1 / "entity_ssot"
KOS_DB = Path.home() / ".kos" / "kos-index.sqlite"


def _load_projection_nodes() -> list[dict]:
    if not SSOT_DIR.is_dir():
        return []
    nodes = []
    for f in sorted(SSOT_DIR.glob("ENTITY-SSOT-*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("type") != "Entity":
            continue
        nodes.append(data)
    return nodes


def _upsert(conn: sqlite3.Connection, node: dict) -> str:
    """INSERT OR REPLACE 单个实体, 返回操作类型 (insert/replace)."""
    props = node.get("properties") or {}
    identity = node.get("identity") or {}
    name = node.get("name") or identity.get("name") or node["id"]
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    aliases = json.dumps([name, *identity.get("aliases", [])], ensure_ascii=False)
    desc = node.get("description", "")[:200]
    source_ref = (node.get("sources") or [""])[0]
    metadata = json.dumps(
        {
            "mof_node_id": node["id"],
            "fm_id": props.get("fm_id"),
            "scope": props.get("scope"),
            "domains": props.get("domains", []),
            "content_hash": props.get("content_hash"),
            "entity_category": props.get("entity_category"),
        },
        ensure_ascii=False,
    )

    op = "replace" if existing else "insert"

    conn.execute(
        """
        INSERT OR REPLACE INTO kos_entities
        (entity_id, entity_type, label, aliases, description, zone,
         source, status, version, confidence, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            node.get("entity_type", "Concept"),
            name,
            aliases,
            desc,
            "mof-ssot",
            source_ref,
            node.get("status", "active"),
            1,
            0.95,
            now,
            now,
            metadata,
        ),
    )
    return op


def do_write(nodes: list[dict]) -> int:
    conn = sqlite3.connect(str(KOS_DB))
    ins = rep = 0
    try:
        for n in nodes:
            name = n.get("name") or n["id"]
            op = _upsert(conn, n)
            if op == "insert":
                ins += 1
            else:
                rep += 1
        conn.commit()
    finally:
        conn.close()
    print(f"✅ KOS 灌入完成: {ins} 新增 / {rep} 更新 → {KOS_DB}")
    return 0


def do_status() -> int:
    if not KOS_DB.exists():
        print("KOS db 不存在:", KOS_DB)
        return 1
    conn = sqlite3.connect(str(KOS_DB))
    total = conn.execute("SELECT COUNT(*) FROM kos_entities").fetchone()[0]
    mof = conn.execute(
        "SELECT COUNT(*) FROM kos_entities WHERE zone = 'mof-ssot'"
    ).fetchone()[0]
    rel = conn.execute("SELECT COUNT(*) FROM kos_relations").fetchone()[0]
    docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    conn.close()
    print(f"kos_entities: {total} (mof-ssot: {mof}) | kos_relations: {rel} | documents: {docs}")
    return 0


def _parse_global_relations(path: Path) -> list[dict]:
    """解析 global-relations.md Markdown 表格 → 三元组列表."""
    text = path.read_text(encoding="utf-8")
    triples = []
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 3 or cells[0] in ("主体", "实体", "源", ""):
            continue
        if cells[0] == "---" or set(cells[0]) <= {"-", ":", " "}:
            continue
        triples.append(
            {
                "source_id": cells[0],
                "relation_type": cells[1],
                "target_raw": cells[2],
                "confidence": cells[3] if len(cells) > 3 else "unconfirmed",
                "source_ref": cells[4] if len(cells) > 4 else "global-relations.md",
            }
        )
    return triples


def do_ingest_relations(relations_path: Path) -> int:
    """解析 global-relations.md → 灌入 ~/.kos/kos_relations."""
    if not relations_path.exists():
        print(f"关系文件不存在: {relations_path}", file=sys.stderr)
        return 2
    triples = _parse_global_relations(relations_path)
    if not triples:
        print("无可解析的三元组", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(KOS_DB))
    ins = 0
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    try:
        for t in triples:
            conn.execute(
                """
                INSERT OR REPLACE INTO kos_relations
                (source_id, relation_type, target_id, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    t["source_id"],
                    t["relation_type"],
                    t["target_raw"],
                    0.9 if t["confidence"] == "confirmed" else 0.7,
                    "global-relations.md",
                    now,
                ),
            )
            ins += 1
        conn.commit()
    finally:
        conn.close()
    print(f"✅ kos_relations 灌入完成: {ins} 条三元组 → {KOS_DB}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--relations", action="store_true", help="解析 global-relations.md → kos_relations")
    ap.add_argument(
        "--relations-path",
        type=Path,
        default=Path.home() / "Documents/@公共/_entities/关系/global-relations.md",
    )
    args = ap.parse_args()

    if args.relations:
        return do_ingest_relations(args.relations_path)
    if args.status:
        return do_status()

    nodes = _load_projection_nodes()
    if not nodes:
        print("无投影节点 (先运行 mof-entity-ssot.py --write)", file=sys.stderr)
        return 2

    if args.dry_run:
        for n in nodes:
            name = n.get("name") or n["id"]
            print(f"  {n['id']}  entity_type={n.get('entity_type')}  name={name}")
        print(f"共 {len(nodes)} 个实体 (dry-run)")
        return 0
    if args.write:
        return do_write(nodes)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
