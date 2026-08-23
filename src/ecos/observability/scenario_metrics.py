"""eCOS Scenario Metrics — 场景可观测指标.

追踪 scene-card 和 journey 的执行指标:
  - 触发次数 / 成功率 / 平均耗时
  - 人类修订率
  - 被采纳产出数
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCENE_DIR = Path(__file__).resolve().parents[5] / "docs" / "scene-cards"


def scan_scene_cards() -> list[dict]:
    """扫描所有 scene-card 状态."""
    import yaml
    scenes = []
    if not SCENE_DIR.exists():
        return scenes
    for f in sorted(SCENE_DIR.glob("*.yaml")):
        try:
            text = f.read_text()
            # parse frontmatter
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    fm = yaml.safe_load(text[3:end])
                    if isinstance(fm, dict):
                        scenes.append({
                            "id": fm.get("scene_id") or f.stem,
                            "title": fm.get("title", ""),
                            "status": fm.get("status", "unknown"),
                            "lifecycle": fm.get("lifecycle", ""),
                            "owner": fm.get("owner", ""),
                            "last_reviewed": fm.get("last-reviewed", ""),
                            "outcome_metric": fm.get("outcome_metric", ""),
                        })
        except Exception:
            continue
    return scenes


def scenario_summary() -> dict:
    """场景汇总指标."""
    scenes = scan_scene_cards()
    status_counts: dict[str, int] = {}
    for s in scenes:
        st = s.get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    active = [s for s in scenes if s.get("status") in ("pilot", "active", "running")]
    inactive = [s for s in scenes if s.get("status") in ("shadow", "draft")]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(scenes),
        "active_count": len(active),
        "inactive_count": len(inactive),
        "status_breakdown": status_counts,
        "active_scenes": [s["id"] for s in active],
        "scenes": scenes,
    }
