"""L1 Runtime — 最小可行调度器.

基于 L0 OmniEnvelope 总线协议, 提供工作流步骤调度能力.

架构:
  L3 Entry → L1 Runtime (scheduler) → L0 Bus → 执行器

能力:
  - schedule_step: 调度单步执行
  - execute_workflow: 顺序执行工作流
  - emit_event: 通过 L0 bus 发射事件
"""

from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger(__name__)


class L1Scheduler:
    """L1 最小调度器."""

    def __init__(self, source_uri: str = "l1://runtime"):
        self.source_uri = source_uri
        self._execution_log: list[dict] = []

    def emit_event(self, plane: str, topic: str, payload: dict) -> dict:
        """通过 L0 bus 协议发射事件."""
        try:
            from ecos.l0.bus.protocol import OmniEnvelope

            envelope = OmniEnvelope(
                trace_id=uuid.uuid4().hex,
                plane=plane,
                topic=topic,
                source_uri=self.source_uri,
                payload=payload,
            )
            return envelope.model_dump()
        except ImportError:
            # Fallback without pydantic
            return {
                "id": uuid.uuid4().hex,
                "trace_id": uuid.uuid4().hex,
                "timestamp": time.time(),
                "plane": plane,
                "topic": topic,
                "source_uri": self.source_uri,
                "payload": payload,
            }

    def schedule_step(self, step: dict, context: dict | None = None) -> dict:
        """调度单步执行."""
        step_name = step.get("name", "unnamed")
        result = {
            "step": step_name,
            "status": "scheduled",
            "timestamp": time.time(),
            "action": step.get("action"),
            "agent_role": step.get("agent_role"),
        }
        self._execution_log.append(result)
        return result

    def execute_workflow(self, steps: list[dict], context: dict | None = None) -> dict:
        """顺序执行工作流."""
        results = []
        for step in steps:
            result = self.schedule_step(step, context)
            results.append(result)
        return {
            "total": len(steps),
            "executed": len(results),
            "steps": results,
        }

    @property
    def execution_log(self) -> list[dict]:
        return list(self._execution_log)
