#!/usr/bin/env python3
"""
mof-relation-builder — M1 关系图谱构建器
========================================
分析 M1 实例间的信号流、任务引用、域共现, 自动生成 depends_on / provides 边.

算法:
  1. 信号流: 节点 A 发射 signal X, 节点 B 的 trigger/description 包含 X → A provides → B depends_on
  2. 任务引用: 节点 A 的 model_driven_ref 指向节点 B 的任务文件 → B depends_on A
  3. 域共现: 同 domain 节点间按描述 token 重叠建立弱关联

输出: 为每个 M1 节点注入 relations 字段.

用法:
    python3 mof-relation-builder.py              # 分析报告
    python3 mof-relation-builder.py --apply      # 写入 M1 节点
    python3 mof-relation-builder.py --json       # JSON 输出
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Set

M1_DIR = Path(__file__).resolve().parent.parent / "mof" / "m1"


def tokenize(text: str) -> Set[str]:
    if not text:
        return set()
    text = text.lower()
    tokens = set(re.findall(r'[a-z][a-z0-9_-]{2,}', text))
    chinese = re.findall(r'[\u4e00-\u9fff]+', text)
    for phrase in chinese:
        for n in (2, 3):
            for i in range(len(phrase) - n + 1):
                tokens.add(phrase[i:i + n])
    return tokens


def load_m1_nodes() -> dict:
    """加载全部 M1 节点"""
    nodes = {}
    if not M1_DIR.exists():
        return nodes
    import yaml
    for f in sorted(M1_DIR.rglob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text()) or {}
            if not isinstance(d, dict) or "id" not in d:
                continue
            desc = " ".join(str(d.get(k, "")) for k in ("name", "title", "description"))
            signals = d.get("signals", []) or []
            if isinstance(signals, str):
                signals = [signals]
            refs = d.get("model_driven_ref", []) or []
            if isinstance(refs, str):
                refs = [refs]
            if isinstance(refs, dict):
                refs = list(refs.values())
            nodes[d["id"]] = {
                "file": str(f.relative_to(M1_DIR.parent.parent.parent.parent)),
                "data": d,
                "tokens": tokenize(desc),
                "signals": set(signals),
                "refs": set(str(r) for r in refs),
                "domain": d.get("domain", ""),
            }
        except Exception:
            continue
    return nodes


def build_relations(nodes: dict) -> dict:
    """构建关系边 {node_id: {depends_on: [...], provides: [...]}}"""
    relations = {nid: {"depends_on": set(), "provides": set()} for nid in nodes}

    # 索引: signal → 发射者
    signal_emitters = {}
    for nid, info in nodes.items():
        for sig in info["signals"]:
            signal_emitters.setdefault(sig, set()).add(nid)

    # 索引: 任务文件名 → 节点
    task_file_to_node = {}
    for nid, info in nodes.items():
        for ref in info["refs"]:
            task_file_to_node[ref] = nid

    for nid, info in nodes.items():
        # 1. 信号流: 我的 signals 被谁消费?
        for sig in info["signals"]:
            for other_nid, other_info in nodes.items():
                if other_nid == nid:
                    continue
                # 其他节点的描述/trigger 包含我的 signal
                if sig.lower() in " ".join(other_info["data"].get(k, "") for k in ("name", "title", "description")).lower():
                    relations[nid]["provides"].add(other_nid)
                    relations[other_nid]["depends_on"].add(nid)

        # 2. 任务引用: 我的 refs 指向谁?
        for ref in info["refs"]:
            for other_nid, other_info in nodes.items():
                if other_nid == nid:
                    continue
                # 其他节点的 id/file 匹配我的 ref
                if other_nid.lower() in ref.lower() or ref.lower().endswith(other_nid.lower() + ".yaml"):
                    relations[nid]["depends_on"].add(other_nid)
                    relations[other_nid]["provides"].add(nid)

        # 3. 域共现: 同 domain 且 token 重叠 > 阈值
        if info["domain"]:
            for other_nod, other_info in nodes.items():
                if other_nod <= nid:  # 避免重复
                    continue
                if other_info["domain"] != info["domain"]:
                    continue
                overlap = len(info["tokens"] & other_info["tokens"])
                union = len(info["tokens"] | other_info["tokens"])
                if union > 0 and overlap / union > 0.15:
                    relations[nid]["provides"].add(other_nod)
                    relations[other_nod]["depends_on"].add(nid)

    # 转换为有序列表
    return {nid: {"depends_on": sorted(v["depends_on"]), "provides": sorted(v["provides"])} for nid, v in relations.items()}


def apply_relations(nodes: dict, relations: dict, dry_run: bool = True) -> int:
    """将 relations 写入 M1 节点"""
    import yaml
    written = 0
    for nid, rel in relations.items():
        if not rel["depends_on"] and not rel["provides"]:
            continue
        info = nodes.get(nid)
        if not info:
            continue
        # Resolve file path: stored relative to M1_DIR.parents[3] (src/)
        f = M1_DIR.parents[3] / info["file"]
        if not f.exists():
            f = Path(info["file"])
        d = info["data"]
        d["relations"] = {
            "depends_on": rel["depends_on"],
            "provides": rel["provides"],
        }
        if not dry_run:
            with open(f, "w") as fh:
                yaml.dump(d, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
        written += 1
    return written


def main():
    parser = argparse.ArgumentParser(description="M1 relation graph builder")
    parser.add_argument("--apply", action="store_true", help="写入 M1 节点")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    nodes = load_m1_nodes()
    relations = build_relations(nodes)

    total_edges = sum(len(v["depends_on"]) + len(v["provides"]) for v in relations.values())
    nodes_with_edges = sum(1 for v in relations.values() if v["depends_on"] or v["provides"])

    if args.json:
        print(json.dumps({"nodes": len(nodes), "edges": total_edges, "nodes_with_edges": nodes_with_edges, "relations": relations}, ensure_ascii=False, indent=2))
        return

    print("=" * 60)
    print("  M1 关系图谱构建报告")
    print("=" * 60)
    print(f"  总节点: {len(nodes)}")
    print(f"  总边数: {total_edges}")
    print(f"  有边节点: {nodes_with_edges}")
    if args.apply:
        written = apply_relations(nodes, relations, dry_run=False)
        print(f"  已写入: {written} 节点")
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    sys.exit(main())
