"""L0 Role Registry — 角色原语.

定义 Agent 角色及其协作契约, 支撑多 Agent 协调.

能力:
  - register_role: 注册角色
  - get_role: 获取角色定义
  - list_roles: 列出所有角色
  - check_capability: 检查角色是否具备某能力
"""

from __future__ import annotations

import threading

# 内置默认角色
DEFAULT_ROLES = {
    "orchestrator": {
        "description": "编排者 — 分解任务、调度执行",
        "capabilities": ["decompose", "schedule", "monitor", "synthesize"],
        "inputs": ["goal", "context"],
        "outputs": ["plan", "status"],
    },
    "executor": {
        "description": "执行者 — 执行具体步骤",
        "capabilities": ["execute", "report", "escalate"],
        "inputs": ["step", "context"],
        "outputs": ["result", "artifacts"],
    },
    "auditor": {
        "description": "审计者 — 校验合规、检测异常",
        "capabilities": ["audit", "validate", "detect_drift", "report"],
        "inputs": ["target", "policy"],
        "outputs": ["findings", "verdict"],
    },
    "researcher": {
        "description": "研究者 — 搜索知识、分析信息",
        "capabilities": ["search", "analyze", "summarize", "cite"],
        "inputs": ["query", "scope"],
        "outputs": ["findings", "sources"],
    },
    "challenger": {
        "description": "挑战者 — 红队测试、发现盲点",
        "capabilities": ["red_team", "falsify", "stress_test", "propose_alternative"],
        "inputs": ["claim", "evidence"],
        "outputs": ["counter_evidence", "alternatives"],
    },
}


class RoleRegistry:
    """角色注册表 (线程安全)."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._roles = dict(DEFAULT_ROLES)
            return cls._instance

    def register_role(self, name: str, definition: dict) -> None:
        """注册角色."""
        self._roles[name] = definition

    def get_role(self, name: str) -> dict | None:
        """获取角色定义."""
        return self._roles.get(name)

    def list_roles(self) -> list[str]:
        """列出所有角色."""
        return sorted(self._roles.keys())

    def check_capability(self, role: str, capability: str) -> bool:
        """检查角色是否具备某能力."""
        r = self._roles.get(role)
        if not r:
            return False
        return capability in r.get("capabilities", [])

    def find_roles_with_capability(self, capability: str) -> list[str]:
        """查找具备某能力的所有角色."""
        return [name for name, defn in self._roles.items() if capability in defn.get("capabilities", [])]
