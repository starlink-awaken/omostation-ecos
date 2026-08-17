"""Domain Cartridge Factory & Package Manager (ADR-0198).

Encapsulates complete vertical domain governance assets into standardized cartridges:
- Manifest (Metadata, Author, Version)
- Schema definitions (Entity Facts format)
- Policy-as-Code rules (Validation red-lines)
- Standard Operating Procedures (SOP templates)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class DomainCartridgeManifest:
    cartridge_id: str
    name: str
    domain: str
    version: str
    description: str
    author: str
    policies_count: int
    sops_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "cartridge_id": self.cartridge_id,
            "name": self.name,
            "domain": self.domain,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "policies_count": self.policies_count,
            "sops_count": self.sops_count,
        }


BUILTIN_CARTRIDGES: dict[str, dict[str, Any]] = {
    "cartridge-weijian-v1": {
        "manifest": {
            "cartridge_id": "cartridge-weijian-v1",
            "name": "卫健委信息化全周期治理卡带",
            "domain": "work-weijian",
            "version": "1.0.0",
            "description": "提供卫健委政务信息化立项论证、等保三级、信创适配及事实真源 SLA 治理包",
            "author": "卫健委规划信息处 & OmoStation",
            "policies_count": 2,
            "sops_count": 3,
        },
        "policies": [
            {
                "rule_id": "E-POL-WJ-001",
                "title": "重大信息化项目专家论证与信创适配",
                "severity": "BLOCK",
                "trigger_budget_million": 5.0,
            },
            {
                "rule_id": "E-POL-WJ-002",
                "title": "核心医疗数据等保三级与互联互通标准",
                "severity": "BLOCK",
            },
        ],
        "sops": [
            "卫健委信息化立项评审流程.md",
            "全民健康信息平台接口互通规范.md",
            "等保三级定级测评与国密改造SOP.md",
        ],
    },
    "cartridge-transfer-v1": {
        "manifest": {
            "cartridge_id": "cartridge-transfer-v1",
            "name": "国转中心科技成果转化合规卡带",
            "domain": "work-transfer",
            "version": "1.0.0",
            "description": "提供科技成果赋权、作价入股、团队收益 ≥70% 红线审计及 TRL 评估包",
            "author": "国家科技成果转化中心 & OmoStation",
            "policies_count": 2,
            "sops_count": 2,
        },
        "policies": [
            {
                "rule_id": "E-POL-TF-001",
                "title": "科研团队转化收益分配 ≥70% 红线",
                "severity": "BLOCK",
                "min_reward_ratio": 0.70,
            },
            {
                "rule_id": "E-POL-TF-002",
                "title": "产业化项目技术成熟度 (TRL ≥ 6) 准入建议",
                "severity": "WARN",
                "min_trl": 6,
            },
        ],
        "sops": [
            "科技成果作价入股与团队确权SOP.md",
            "技术成熟度TRL自评与中试验证指引.md",
        ],
    },
}


class DomainCartridgeManager:
    """Manager for discovering, exporting, and validating domain cartridges."""

    def __init__(self) -> None:
        self._cartridges = dict(BUILTIN_CARTRIDGES)

    def list_cartridges(self) -> list[DomainCartridgeManifest]:
        res: list[DomainCartridgeManifest] = []
        for c in self._cartridges.values():
            m = c["manifest"]
            res.append(
                DomainCartridgeManifest(
                    cartridge_id=m["cartridge_id"],
                    name=m["name"],
                    domain=m["domain"],
                    version=m["version"],
                    description=m["description"],
                    author=m["author"],
                    policies_count=m["policies_count"],
                    sops_count=m["sops_count"],
                )
            )
        return res

    def get_cartridge(self, cartridge_id: str) -> dict[str, Any] | None:
        return self._cartridges.get(cartridge_id)

    def export_cartridge(self, cartridge_id: str, output_path: str | Path | None = None) -> Path:
        c = self.get_cartridge(cartridge_id)
        if not c:
            raise ValueError(f"未知卡带 ID: {cartridge_id}")

        yaml_content = yaml.safe_dump(c, allow_unicode=True, sort_keys=False)
        out_p = Path(output_path or f"{cartridge_id}.yaml").expanduser().resolve()
        os.makedirs(str(out_p.parent), exist_ok=True)
        with open(str(out_p), "w", encoding="utf-8") as f:
            f.write(yaml_content)
        return out_p

    def validate_cartridge_file(self, file_path: str | Path) -> tuple[bool, list[str]]:
        p = Path(file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return False, [f"文件不存在: {p}"]

        try:
            content = p.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except Exception as e:
            return False, [f"YAML 解析错误: {e}"]

        if not isinstance(data, dict):
            return False, ["卡带根节点必须是 Mapping 字典"]

        errors: list[str] = []
        if "manifest" not in data:
            errors.append("缺少 manifest 元数据块")
        else:
            m = data["manifest"]
            for req in ["cartridge_id", "domain", "version", "name"]:
                if req not in m:
                    errors.append(f"manifest 缺少必填字段: {req}")

        if "policies" not in data or not isinstance(data["policies"], list):
            errors.append("缺少 policies 规则列表")

        return len(errors) == 0, errors
