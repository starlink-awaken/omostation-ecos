#!/usr/bin/env python3
"""mof-kems-bridge — KEMS 域知识资产 → MOF L4KnowledgeObject M1 投影.

Phase D (08-L4知识主权架构蓝图 C2 契约消费者):
  - KEMS (卫健委 _entities/) 是域内嵌套知识体系: 9 实体类 / 211 实例 / 25+ 模型
  - 本工具生成两类投影 (零复制, 不变量 5):
      1. 域知识索引节点  m1/l4_knowledge/KOBJ-<domain>-index.yaml
         (一个域一个, 指向 KEMS SSOT + 类结构 hash)
      2. 模型对象投影    m1/l4_knowledge/KOBJ-<domain>-<slug>.yaml
         (每个 KEMS model 一个, source_ref+hash, 内容留 Documents)
  - 类锚定: KEMS C1-C9 的 id/code 记入索引节点 properties.kems_classes
    (主 MOF 不复制类定义; cartridge 语义归 DomainCartridgeManager 治理)

用法:
    python3 mof-kems-bridge.py --write                 # 生成/刷新
    python3 mof-kems-bridge.py --check                 # 漂移检测 (exit 1 = drift)
    python3 mof-kems-bridge.py --write --domain work-weijian
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

# 仓库根: <ecos>/src/ecos/ssot/tools/ → parents[4] = <ecos>
ECOS_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = ECOS_ROOT / "src/ecos/ssot/mof/m1/l4_knowledge"

# KEMS SSOT 布局约定 (ADR-0110 / 卫健委 metamodel.yaml §二)
KEMS_DOMAINS: dict[str, dict[str, Path]] = {
    "work-weijian": {
        "entities": Path.home() / "Documents/@工作文档/卫健委/_entities",
    },
}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(title: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title.strip())
    return re.sub(r"-+", "-", s).strip("-")[:40] or "untitled"


def _load_kems(domain_id: str, root: Path) -> dict:
    """读 KEMS SSOT: classes.yaml (严格) + metamodel.yaml (容错) + models/*.md frontmatter.

    metamodel.yaml 含非标准 YAML 片段 (裸冒号 flow-mapping), 解析失败只影响
    taxonomy 字段, 不阻断投影 — classes.yaml 才是类结构真值.
    """
    classes_f = root / "ontology/classes.yaml"
    meta_f = root / "ontology/metamodel.yaml"
    classes = yaml.safe_load(classes_f.read_text(encoding="utf-8")) if classes_f.exists() else {}
    meta: dict = {}
    if meta_f.exists():
        try:
            loaded = yaml.safe_load(meta_f.read_text(encoding="utf-8"))
            meta = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError:
            # 从文本层提取 model-taxonomy 的键 (taxonomy 只需类目名)
            keys: list[str] = []
            in_tax = False
            for line in meta_f.read_text(encoding="utf-8").splitlines():
                if line.startswith("model-taxonomy:"):
                    in_tax = True
                    continue
                if in_tax:
                    m = re.match(r"^  (\S+):\s*\{", line)
                    if m:
                        keys.append(m.group(1))
                    elif line.strip() and not line.startswith(" "):
                        break
            meta = {"model-taxonomy": {k: {} for k in keys}}

    models = []
    models_dir = root / "models"
    if models_dir.is_dir():
        for f in sorted(p for p in models_dir.glob("*.md") if p.stem.upper() not in {"README", "INDEX"}):
            text = f.read_text(encoding="utf-8")
            m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
            fm = yaml.safe_load(m.group(1)) if m else {}
            if not isinstance(fm, dict):
                fm = {}
            models.append(
                {
                    "file": f.name,
                    "path": f,
                    "title": str(fm.get("title") or f.stem),
                    "model_type": str(fm.get("type") or fm.get("model_type") or "unknown"),
                    "status": str(fm.get("status") or "active"),
                    "owner": fm.get("owner"),
                    "review_date": fm.get("review-date") or fm.get("last-reviewed"),
                }
            )
    return {
        "domain_id": domain_id,
        "root": root,
        "classes": (classes.get("classes") or []),
        "taxonomy": meta.get("model-taxonomy") or {},
        "models": models,
    }


def _ko_common(domain_id: str, source_ref: Path, now: datetime) -> dict:
    return {
        "api_version": "l4/v1",
        "kind": "KnowledgeObject",
        "schema": "l4.knowledge-object/v1",
        "kind_class": "reference",
        "space_id": "personal-space",
        "domain_id": domain_id,
        "authority": "canonical",
        "lifecycle_state": "canonical",
        "source_ref": str(source_ref),
        "content_hash": _sha256(source_ref),
        "principal": "personal-space-owner",
        "sensitivity": "restricted",
        "visibility": "private",
        "sharing_policy": "deny",
        "retention": "permanent",
        "freshness_policy": "kems-review-90d",
    }


def index_node(kems: dict, now: datetime) -> dict:
    dom = kems["domain_id"]
    classes_f = kems["root"] / "ontology/classes.yaml"
    return {
        "id": f"KOBJ-{dom}-index",
        "type": "L4KnowledgeObject",
        "subtype": "DomainKnowledgeIndex",
        "name": f"{dom} 域知识索引 (KEMS)",
        "description": (
            f"KEMS 域知识体系投影 — {len(kems['classes'])} 实体类 / "
            f"{sum(c.get('instance_count', 0) for c in kems['classes'])} 实例 / "
            f"{len(kems['models'])} 模型. Canonical at {kems['root']}"
        ),
        "status": "canonical",
        "domain": dom,
        "created": now.strftime("%Y-%m-%d"),
        "version": "1.0.0",
        "layer": "L4",
        **_ko_common(dom, classes_f, now),
        "kind_class": "glossary",
        "value_tier": 2,
        "properties": {
            "layer": "L4",
            "kems_classes": [
                {
                    "id": c.get("id"),
                    "code": c.get("code"),
                    "name_cn": c.get("name_cn"),
                    "instance_count": c.get("instance_count", 0),
                }
                for c in kems["classes"]
            ],
            "kems_instance_total": sum(c.get("instance_count", 0) for c in kems["classes"]),
            "model_count": len(kems["models"]),
            "taxonomy": sorted(kems["taxonomy"].keys()),
        },
        "evidence_refs": [str(kems["root"] / "ontology")],
        "model_driven_refs": {"source_file": str(classes_f), "content_hash": _sha256(classes_f)},
        "state_history": [{"state": "canonical", "timestamp": now.isoformat(), "reason": "kems_bridge_projection"}],
    }


TAXONOMY_TO_KIND_CLASS = {
    "ontology": "ontology",
    "domain": "model",
    "data": "fact",
    "view": "reference",
    "strategy": "model",
    "governance": "glossary",
    "analysis": "reference",
}


def model_node(kems: dict, model: dict, now: datetime) -> dict:
    dom = kems["domain_id"]
    slug = _slug(model["title"])
    kind_class = TAXONOMY_TO_KIND_CLASS.get(model["model_type"], "reference")
    node = {
        "id": f"KOBJ-{dom}-{slug}",
        "type": "L4KnowledgeObject",
        "subtype": "KnowledgeModel",
        "name": model["title"],
        "description": (
            f"KEMS {model['model_type']} 模型投影 (status={model['status']}); canonical at {model['path']}"
        ),
        "status": "canonical" if model["status"] == "active" else "archived",
        "domain": dom,
        "created": now.strftime("%Y-%m-%d"),
        "version": "1.0.0",
        "layer": "L4",
        **_ko_common(dom, model["path"], now),
        "kind_class": kind_class,
        "value_tier": 3,
        "properties": {
            "layer": "L4",
            "kems_model_type": model["model_type"],
            "kems_status": model["status"],
            "kems_owner": model.get("owner"),
            "kems_review_date": model.get("review_date"),
        },
        "model_driven_refs": {"source_file": str(model["path"]), "content_hash": _sha256(model["path"])},
        "state_history": [{"state": "canonical", "timestamp": now.isoformat(), "reason": "kems_bridge_projection"}],
    }
    return node


def _node_path(n: dict) -> Path:
    return OUT_DIR / f"{n['id']}.yaml"


def write_nodes(nodes: list[dict]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for n in nodes:
        fp = _node_path(n)
        header = (
            "# M1 Node (generated by mof-kems-bridge — DO NOT HAND-EDIT)\n"
            "# Source of truth: KEMS _entities/ (Documents canonical)\n"
            "# Rebuild: python3 src/ecos/ssot/tools/mof-kems-bridge.py --write\n\n"
        )
        fp.write_text(header + yaml.safe_dump(n, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"  wrote {fp.relative_to(ECOS_ROOT)}")
    return len(nodes)


def check_drift(nodes: list[dict]) -> int:
    """漂移判定: 磁盘节点的 content_hash vs 当前 source_ref 实际 hash.

    注意不与内存重算的 node 比 (node 含 now 时间戳会自漂移),
    只读磁盘节点的 source_ref 重新指纹化 — 真值在 Documents 原件.
    """
    drifts = []
    for n in nodes:
        fp = _node_path(n)
        if not fp.exists():
            drifts.append(f"{n['id']}: node missing")
            continue
        disk = yaml.safe_load(fp.read_text(encoding="utf-8"))
        src = Path(disk.get("source_ref") or "")
        disk_hash = (disk.get("properties") or {}).get("content_hash") or disk.get("content_hash")
        if not src.is_file():
            drifts.append(f"{n['id']}: source_ref 不可达 ({src})")
        elif _sha256(src) != disk_hash:
            drifts.append(f"{n['id']}: hash drift (原件已变, 重新 --write)")
    if drifts:
        print(f"❌ KEMS bridge drift ({len(drifts)}):")
        for d in drifts:
            print(f"  - {d}")
        return 1
    print(f"✅ KEMS bridge 无漂移 ({len(nodes)} 投影与 _entities 一致)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--domain", help="只处理指定 KEMS 域 id (默认全部)")
    args = ap.parse_args()

    now = datetime.now(UTC)
    nodes: list[dict] = []
    for dom_id, spec in KEMS_DOMAINS.items():
        if args.domain and dom_id != args.domain:
            continue
        if not spec["entities"].is_dir():
            print(f"⚠️ {dom_id}: KEMS root 不存在, 跳过 ({spec['entities']})", file=sys.stderr)
            continue
        kems = _load_kems(dom_id, spec["entities"])
        nodes.append(index_node(kems, now))
        for m in kems["models"]:
            nodes.append(model_node(kems, m, now))

    if not nodes:
        print("无可用 KEMS 域", file=sys.stderr)
        return 2
    if args.write:
        n = write_nodes(nodes)
        print(f"✅ {n} 投影节点已写入 {OUT_DIR.relative_to(ECOS_ROOT)}")
        return 0
    if args.check:
        return check_drift(nodes)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
