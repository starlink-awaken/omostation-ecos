"""L3 Entry — 最小可行入口层.

统一的外部入口, 封装 L2 Engine 和 L1 Scheduler.

架构:
  外部调用 → L3 Entry (api) → L2 Engine (query) / L1 Scheduler (execute)

能力:
  - get_m1: 获取 M1 实例
  - get_m2: 获取 M2 schema
  - search: 搜索
  - execute: 执行工作流
  - health: 健康检查
"""

from __future__ import annotations

import time


class L3Entry:
    """L3 最小入口."""

    def __init__(self):
        self._version = "0.1.0"
        self._start_time = time.time()

    def health(self) -> dict:
        """健康检查."""
        return {
            "status": "ok",
            "version": self._version,
            "uptime": time.time() - self._start_time,
        }

    def get_m1(self, node_id: str | None = None, **kwargs) -> list[dict]:
        """获取 M1 实例."""
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        return engine.query_m1(node_id=node_id, **kwargs)

    def get_m2(self, schema_type: str | None = None) -> list[dict]:
        """获取 M2 schema."""
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        return engine.query_m2(schema_type=schema_type)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """搜索."""
        from ecos.l2.engine.knowledge_engine import L2KnowledgeEngine
        engine = L2KnowledgeEngine()
        return engine.search(query, limit=limit)

    def execute(self, steps: list[dict]) -> dict:
        """执行工作流."""
        from ecos.l1.runtime.scheduler import L1Scheduler
        scheduler = L1Scheduler()
        return scheduler.execute_workflow(steps)
