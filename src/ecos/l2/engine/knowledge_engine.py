"""L2 Engine — 最小可行知识引擎.

提供 M1/M2  schema 查询能力, 支撑推理引擎和约束编译.

架构:
  L3 → L2 Engine (query) → M1/M2 schemas → 返回结构化知识

能力:
  - query_m1: 查询 M1 实例 (by id, type, domain)
  - query_m2: 查询 M2 schema
  - get_relations: 获取节点关系图
  - search: 全文搜索 M1 实例
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ECOS_SSOT = Path(__file__).resolve().parent.parent.parent / "ssot"


class L2KnowledgeEngine:
    """L2 最小知识引擎."""

    def __init__(self):
        self._m1_cache: dict[str, dict] = {}
        self._m2_cache: dict[str, dict] = {}

    def _load_yaml(self, path: Path) -> dict | list:
        import yaml
        try:
            return yaml.safe_load(path.read_text()) or {}
        except Exception:
            return {}

    def query_m1(self, node_id: str | None = None, node_type: str | None = None,
                 domain: str | None = None) -> list[dict]:
        """查询 M1 实例."""
        m1_dir = ECOS_SSOT / "mof" / "m1"
        results = []
        if not m1_dir.exists():
            return results

        for f in m1_dir.rglob("*.yaml"):
            try:
                data = self._load_yaml(f)
                if not isinstance(data, dict):
                    continue
                if node_id and data.get("id") != node_id:
                    continue
                if node_type and data.get("type", "").lower() != node_type.lower():
                    continue
                if domain and data.get("domain", "").lower() != domain.lower():
                    continue
                results.append(data)
            except Exception:
                continue
        return results

    def query_m2(self, schema_type: str | None = None) -> list[dict]:
        """查询 M2 schema."""
        m2_dir = ECOS_SSOT / "mof" / "m2"
        results = []
        if not m2_dir.exists():
            return results
        for f in sorted(m2_dir.glob("*.yaml")):
            try:
                data = self._load_yaml(f)
                if not isinstance(data, dict):
                    continue
                if schema_type:
                    if data.get("m2_type", "").lower() == schema_type.lower():
                        results.append(data)
                else:
                    results.append(data)
            except Exception:
                continue
        return results

    def get_relations(self, node_id: str) -> dict:
        """获取节点关系."""
        nodes = self.query_m1(node_id=node_id)
        if not nodes:
            return {"error": f"Node {node_id} not found"}
        node = nodes[0]
        return {
            "id": node_id,
            "depends_on": node.get("relations", {}).get("depends_on", []),
            "provides": node.get("relations", {}).get("provides", []),
        }

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """全文搜索 M1 实例."""
        query_lower = query.lower()
        m1_dir = ECOS_SSOT / "mof" / "m1"
        results = []
        if not m1_dir.exists():
            return results
        for f in m1_dir.rglob("*.yaml"):
            if len(results) >= limit:
                break
            try:
                text = f.read_text().lower()
                if query_lower in text:
                    data = self._load_yaml(f)
                    if isinstance(data, dict) and "id" in data:
                        results.append({"id": data["id"], "type": data.get("type", "")})
            except Exception:
                continue
        return results
