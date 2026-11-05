from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

import yaml


def ensure_text_file(path: Path, initial_text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(initial_text, encoding="utf-8")


def append_jsonl_record(path: Path, entry: dict[str, Any]) -> None:
    """追加一条 JSONL 记录, 写期间持排他锁。

    X2 budget integrity standard §3「并发控制」要求: 所有 JSONL 写入必须通过
    `fcntl.flock` 取排他锁, 确保多进程并发时数据完整 —— 没有锁时两个进程的
    写入可能交错, 产出半行 JSON (后续按行解析会读到坏记录)。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_yaml_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
