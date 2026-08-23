"""L0 Distributed Coordination — 分布式协调原语.

最小可行多 Agent 协调: 消息传递 + 状态同步 + 任务分配.

能力:
  - send_message: Agent 间消息传递
  - broadcast: 广播到所有 Agent
  - claim_task: 认领任务 (分布式锁)
  - sync_state: 状态同步
"""

from __future__ import annotations

import threading
import time
import uuid


class CoordinationBus:
    """协调总线 (进程内, 可扩展为 Redis/NATS)."""

    def __init__(self):
        self._mailboxes: dict[str, list[dict]] = {}
        self._state: dict[str, dict] = {}
        self._claims: dict[str, str] = {}  # task_id → agent_id
        self._lock = threading.Lock()

    def register_agent(self, agent_id: str) -> None:
        """注册 Agent."""
        with self._lock:
            self._mailboxes.setdefault(agent_id, [])
            self._state.setdefault(agent_id, {"status": "idle"})

    def send_message(self, from_agent: str, to_agent: str, payload: dict) -> dict:
        """发送消息."""
        msg = {
            "id": uuid.uuid4().hex,
            "from": from_agent,
            "to": to_agent,
            "payload": payload,
            "timestamp": time.time(),
        }
        with self._lock:
            self._mailboxes.setdefault(to_agent, []).append(msg)
        return msg

    def broadcast(self, from_agent: str, payload: dict) -> list[dict]:
        """广播到所有 Agent."""
        msgs = []
        with self._lock:
            agents = list(self._mailboxes.keys())
        for agent in agents:
            if agent != from_agent:
                msgs.append(self.send_message(from_agent, agent, payload))
        return msgs

    def receive_messages(self, agent_id: str) -> list[dict]:
        """接收消息."""
        with self._lock:
            msgs = self._mailboxes.get(agent_id, [])
            self._mailboxes[agent_id] = []
        return msgs

    def claim_task(self, task_id: str, agent_id: str) -> bool:
        """认领任务 (分布式锁)."""
        with self._lock:
            if task_id in self._claims:
                return self._claims[task_id] == agent_id
            self._claims[task_id] = agent_id
            return True

    def release_task(self, task_id: str, agent_id: str) -> bool:
        """释放任务."""
        with self._lock:
            if self._claims.get(task_id) == agent_id:
                del self._claims[task_id]
                return True
            return False

    def sync_state(self, agent_id: str, state: dict) -> None:
        """同步 Agent 状态."""
        with self._lock:
            self._state[agent_id] = {**self._state.get(agent_id, {}), **state, "_ts": time.time()}

    def get_state(self, agent_id: str) -> dict:
        """获取 Agent 状态."""
        return self._state.get(agent_id, {})

    def get_all_states(self) -> dict:
        """获取所有 Agent 状态."""
        return dict(self._state)
