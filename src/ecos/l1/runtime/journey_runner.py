"""L1 Journey Runner — 旅程执行器.

加载 journey-spec YAML 并通过 L1 Scheduler 执行.

能力:
  - load_journey: 加载旅程定义
  - execute_journey: 执行完整旅程
  - get_status: 获取执行状态
"""

from __future__ import annotations

import time
from pathlib import Path

JOURNEY_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "docs" / "journey-specs"


class JourneyRunner:
    """旅程执行器."""

    def __init__(self):
        from ecos.l1.runtime.scheduler import L1Scheduler
        self.scheduler = L1Scheduler(source_uri="l1://journey-runner")
        self._executions: list[dict] = []

    def load_journey(self, journey_id: str) -> dict | None:
        """加载旅程定义."""
        import yaml
        for f in JOURNEY_DIR.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text()) or {}
                if isinstance(data, dict):
                    # support both 'id' and 'journey_id' fields
                    if data.get("id") == journey_id or data.get("journey_id") == journey_id:
                        return data
            except Exception:
                continue
        return None

    def list_journeys(self) -> list[str]:
        """列出所有旅程."""
        import yaml
        journeys = []
        for f in sorted(JOURNEY_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text()) or {}
                if isinstance(data, dict):
                    jid = data.get("id") or data.get("journey_id")
                    if jid:
                        journeys.append(jid)
            except Exception:
                continue
        return journeys

    def execute_journey(self, journey_id: str, context: dict | None = None) -> dict:
        """执行完整旅程."""
        journey = self.load_journey(journey_id)
        if not journey:
            return {"error": f"Journey {journey_id} not found"}

        steps = journey.get("steps", [])
        start = time.time()
        results = []
        for step in steps:
            result = self.scheduler.schedule_step(step, context)
            results.append(result)

        execution = {
            "journey_id": journey_id,
            "started_at": start,
            "elapsed_ms": round((time.time() - start) * 1000, 1),
            "total_steps": len(steps),
            "completed": len(results),
            "steps": results,
        }
        self._executions.append(execution)
        return execution

    @property
    def execution_history(self) -> list[dict]:
        return list(self._executions)
