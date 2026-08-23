#!/usr/bin/env python3
"""
mof-bridge-match — M1 OMOTask ↔ .omo/tasks 内容匹配
====================================================
基于标题/描述 token 重叠度的模糊匹配, 解决命名体系断裂问题
(M1: OMOTASK-P35-W1-W2-COMBO vs tasks: bet-y1q4-t4-01.yaml).

算法:
  1. 提取 M1 title/name/description 的中文+英文 token
  2. 提取 task title/desc 的 token
  3. 计算 Jaccard 相似度 + 关键词加权
  4. 相似度 > 阈值 → 配对

用法:
    python3 mof-bridge-match.py                # 匹配报告
    python3 mof-bridge-match.py --json         # JSON 输出
    python3 mof-bridge-match.py --threshold 0.3  # 自定义阈值
    WORKSPACE_ROOT=/path/to/workspace python3 mof-bridge-match.py
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Set

M1_DIR = Path(__file__).resolve().parent.parent / "mof" / "m1" / "omo_layer"
DEFAULT_WORKSPACE_ROOT = Path(__file__).resolve().parents[6]
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT") or DEFAULT_WORKSPACE_ROOT).expanduser().resolve()
OMO_TASKS_ROOT = WORKSPACE_ROOT / ".omo" / "tasks"


def tokenize(text: str) -> Set[str]:
    """提取中文词和英文单词"""
    if not text:
        return set()
    text = text.lower()
    # 中文按字/词 (2-4 gram), 英文按单词
    tokens = set()
    # 英文 tokens
    tokens.update(re.findall(r"[a-z][a-z0-9_-]{1,}", text))
    # 中文 bigrams
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for phrase in chinese:
        for n in (2, 3, 4):
            for i in range(len(phrase) - n + 1):
                tokens.add(phrase[i : i + n])
    return tokens


def similarity(a: Set[str], b: Set[str]) -> float:
    """Jaccard 相似度"""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def load_m1_tasks() -> list[dict]:
    """加载 M1 OMOTask"""
    tasks = []
    if not M1_DIR.exists():
        return tasks
    import yaml

    for f in sorted(M1_DIR.glob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text()) or {}
            if not isinstance(d, dict):
                continue
            text = " ".join(str(d.get(k, "")) for k in ("name", "title", "description"))
            tasks.append(
                {
                    "id": d.get("id", f.stem),
                    "status": d.get("status", ""),
                    "tokens": tokenize(text),
                    "raw": text[:100],
                }
            )
        except Exception:
            continue
    return tasks


def load_omo_tasks() -> list[dict]:
    """加载 .omo/tasks (全部子目录)"""
    tasks = []
    if not OMO_TASKS_ROOT.exists():
        return tasks
    import yaml

    for f in sorted(OMO_TASKS_ROOT.rglob("*.yaml")):
        try:
            text = f.read_text(encoding="utf-8")
            docs = list(yaml.safe_load_all(text))
            data = docs[0] if docs else {}
            if not isinstance(data, dict):
                continue
            content = " ".join(str(data.get(k, "")) for k in ("title", "desc", "description", "name"))
            rel_dir = f.parent.relative_to(OMO_TASKS_ROOT).parts[0] if f.parent != OMO_TASKS_ROOT else "root"
            tasks.append(
                {
                    "id": data.get("id", f.stem),
                    "dir": str(rel_dir),
                    "status": data.get("status", ""),
                    "tokens": tokenize(content),
                    "raw": content[:100],
                }
            )
        except Exception:
            continue
    return tasks


def match_tasks(m1_tasks: list[dict], omo_tasks: list[dict], threshold: float) -> list[dict]:
    """内容匹配"""
    pairs = []
    used_omo = set()
    for m1 in m1_tasks:
        best_score = 0.0
        best_omo = None
        for i, omo in enumerate(omo_tasks):
            if i in used_omo:
                continue
            score = similarity(m1["tokens"], omo["tokens"])
            if score > best_score:
                best_score = score
                best_omo = i
        if best_omo is not None and best_score >= threshold:
            pairs.append(
                {
                    "m1_id": m1["id"],
                    "m1_status": m1["status"],
                    "omo_id": omo_tasks[best_omo]["id"],
                    "omo_dir": omo_tasks[best_omo]["dir"],
                    "omo_status": omo_tasks[best_omo]["status"],
                    "score": round(best_score, 3),
                }
            )
            used_omo.add(best_omo)
    return pairs


def main():
    parser = argparse.ArgumentParser(description="M1 OMOTask <-> .omo/tasks content match")
    parser.add_argument("--threshold", type=float, default=0.15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    m1 = load_m1_tasks()
    omo = load_omo_tasks()
    pairs = match_tasks(m1, omo, args.threshold)

    if args.json:
        print(json.dumps({"m1_count": len(m1), "omo_count": len(omo), "pairs": pairs}, ensure_ascii=False, indent=2))
        return

    print("=" * 60)
    print("  M1 OMOTask <-> .omo/tasks 内容匹配")
    print("=" * 60)
    print(f"  M1 节点: {len(m1)} | .omo/tasks: {len(omo)} | 阈值: {args.threshold}")
    print(f"  配对成功: {len(pairs)}")
    if pairs:
        print(f"\n  {'M1 ID':35s} {'OMO ID':25s} {'score':6s} {'dir':10s}")
        for p in sorted(pairs, key=lambda x: -x["score"]):
            print(f"  {p['m1_id']:35s} {p['omo_id']:25s} {p['score']:<6.3f} {p['omo_dir']:10s}")
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    sys.exit(main())
