"""Domain Fact Inspector and Schema Validator (ADR-0192 / E-DOC-004).

Validates structured truth entities in `_entities/facts/*.yaml`, checks metadata
compliance (schema_version, owner, lifecycle_stage), and enforces freshness SLA (14 days).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class FactValidationError:
    field: str
    message: str
    code: str = "E-FACT-SCHEMA"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class FactInspectionResult:
    file_path: str
    passed: bool
    entity_id: str | None = None
    domain: str | None = None
    name: str | None = None
    owner: str | None = None
    lifecycle_stage: str | None = None
    updated_at: str | None = None
    age_days: int = 0
    is_fresh: bool = True
    freshness_warning: str | None = None
    errors: list[FactValidationError] = field(default_factory=list)
    facts_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "passed": self.passed,
            "entity_id": self.entity_id,
            "domain": self.domain,
            "name": self.name,
            "owner": self.owner,
            "lifecycle_stage": self.lifecycle_stage,
            "updated_at": self.updated_at,
            "age_days": self.age_days,
            "is_fresh": self.is_fresh,
            "freshness_warning": self.freshness_warning,
            "errors": [e.to_dict() for e in self.errors],
            "facts_summary": list(self.facts_data.keys()),
        }


class FactInspector:
    """Inspector for domain fact entities and freshness SLAs."""

    REQUIRED_METADATA_FIELDS = [
        "schema_version",
        "entity_id",
        "domain",
        "name",
        "owner",
        "updated_at",
        "lifecycle_stage",
        "facts",
    ]

    ALLOWED_LIFECYCLE_STAGES = {
        "INITIATION",
        "PLANNING",
        "IMPLEMENTATION",
        "PILOT",
        "OPERATIONAL",
        "EVALUATION",
        "ARCHIVED",
    }

    def __init__(self, max_age_days: int = 14) -> None:
        self.max_age_days = max_age_days

    def inspect_file(self, file_path: Path | str) -> FactInspectionResult:
        p = Path(file_path).resolve()
        errors: list[FactValidationError] = []

        if not p.exists() or not p.is_file():
            return FactInspectionResult(
                file_path=str(p),
                passed=False,
                errors=[FactValidationError(field="file", message=f"文件不存在: {p}", code="E-FACT-NOT-FOUND")],
            )

        try:
            content = p.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except Exception as e:
            return FactInspectionResult(
                file_path=str(p),
                passed=False,
                errors=[FactValidationError(field="yaml", message=f"YAML 解析失败: {e}", code="E-FACT-YAML-ERROR")],
            )

        if not isinstance(data, dict):
            return FactInspectionResult(
                file_path=str(p),
                passed=False,
                errors=[
                    FactValidationError(field="root", message="事实文件根节点必须为映射字典", code="E-FACT-NOT-DICT")
                ],
            )

        # 模式 A: 聚合事实表列表格式 (List-based Fact Table, 如 00-budget.yaml)
        if isinstance(data.get("facts"), list):
            fact_items = data.get("facts", [])
            latest_date_str = None
            for idx, item in enumerate(fact_items):
                if not isinstance(item, dict):
                    errors.append(
                        FactValidationError(
                            field=f"facts[{idx}]", message="事实项必须为字典", code="E-FACT-INVALID-ITEM"
                        )
                    )
                    continue
                if "fid" not in item:
                    errors.append(
                        FactValidationError(
                            field=f"facts[{idx}].fid", message="缺少事实 ID (fid)", code="E-FACT-MISSING-FID"
                        )
                    )
                v_at = item.get("verified_at")
                if v_at:
                    if not latest_date_str or str(v_at) > str(latest_date_str):
                        latest_date_str = str(v_at)

            age_days = 0
            is_fresh = True
            freshness_warning = None
            if latest_date_str:
                try:
                    dt_str = latest_date_str.split("T")[0]
                    updated_date = datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    age_days = max(0, (datetime.now(timezone.utc) - updated_date).days)
                    if age_days > self.max_age_days:
                        is_fresh = False
                        freshness_warning = (
                            f"聚合事实最新验证时间为 {dt_str} (距今 {age_days} 天)，超过 {self.max_age_days} 天保鲜 SLA"
                        )
                except ValueError:
                    pass

            domain = "work-weijian" if "卫健委" in p.parts else "general"
            return FactInspectionResult(
                file_path=str(p),
                passed=len(errors) == 0,
                entity_id=p.stem,
                domain=domain,
                name=f"聚合事实表: {p.name} ({len(fact_items)} 条)",
                owner="规划信息科" if "卫健委" in p.parts else "系统",
                lifecycle_stage="OPERATIONAL",
                updated_at=latest_date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                age_days=age_days,
                is_fresh=is_fresh,
                freshness_warning=freshness_warning,
                errors=errors,
                facts_data={"total_facts": len(fact_items)},
            )

        # 模式 B: 单实体真源格式 (Single Entity Fact SSOT, 如 fact-wj-2026-001.yaml)
        for req_field in self.REQUIRED_METADATA_FIELDS:
            if req_field not in data or data[req_field] is None:
                errors.append(
                    FactValidationError(
                        field=req_field,
                        message=f"缺少必填元数据字段: {req_field}",
                        code="E-FACT-MISSING-FIELD",
                    )
                )

        entity_id = data.get("entity_id")
        domain = data.get("domain")
        name = data.get("name")
        owner = data.get("owner")
        lifecycle_stage = data.get("lifecycle_stage")
        updated_at_raw = data.get("updated_at")
        facts_data = data.get("facts", {}) if isinstance(data.get("facts"), dict) else {}

        # 2. 生命周期枚举校验
        if lifecycle_stage and str(lifecycle_stage).upper() not in self.ALLOWED_LIFECYCLE_STAGES:
            errors.append(
                FactValidationError(
                    field="lifecycle_stage",
                    message=f"非法生命周期状态 '{lifecycle_stage}'，可选值: {sorted(self.ALLOWED_LIFECYCLE_STAGES)}",
                    code="E-FACT-INVALID-STAGE",
                )
            )

        # 3. 保鲜度与日期校验
        age_days = 0
        is_fresh = True
        freshness_warning = None

        if updated_at_raw:
            try:
                # 支持 YYYY-MM-DD 或 ISO 格式
                dt_str = str(updated_at_raw).split("T")[0]
                updated_date = datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                age_days = max(0, (now - updated_date).days)
                if age_days > self.max_age_days:
                    is_fresh = False
                    freshness_warning = (
                        f"事实更新时间为 {dt_str} (距今 {age_days} 天)，超过 {self.max_age_days} 天保鲜 SLA (E-DOC-004)"
                    )
            except ValueError:
                errors.append(
                    FactValidationError(
                        field="updated_at",
                        message=f"非法日期格式: {updated_at_raw}，应为 YYYY-MM-DD",
                        code="E-FACT-INVALID-DATE",
                    )
                )

        passed = len(errors) == 0

        return FactInspectionResult(
            file_path=str(p),
            passed=passed,
            entity_id=str(entity_id) if entity_id else None,
            domain=str(domain) if domain else None,
            name=str(name) if name else None,
            owner=str(owner) if owner else None,
            lifecycle_stage=str(lifecycle_stage).upper() if lifecycle_stage else None,
            updated_at=str(updated_at_raw) if updated_at_raw else None,
            age_days=age_days,
            is_fresh=is_fresh,
            freshness_warning=freshness_warning,
            errors=errors,
            facts_data=facts_data,
        )

    def inspect_directory(self, dir_path: Path | str, domain: str | None = None) -> list[FactInspectionResult]:
        root = Path(dir_path).expanduser().resolve()
        results: list[FactInspectionResult] = []

        if not root.exists():
            return results

        yaml_files = list(root.rglob("*.yaml")) + list(root.rglob("*.yml"))
        for yf in sorted(yaml_files):
            # 跳过虚拟环境、配置及私有索引文件
            if yf.name.startswith("_"):
                continue
            if any(part in yf.parts for part in (".venv", "venv", ".git", "__pycache__", "node_modules")):
                continue
            # 严格审计 _entities/facts/ 目录或名称以 fact- 开头的文件
            is_fact_location = ("_entities" in yf.parts and "facts" in yf.parts) or (yf.parent.name == "facts")
            is_fact_naming = yf.name.lower().startswith("fact-") or yf.stem.lower().startswith("fact-")
            if is_fact_location or is_fact_naming:
                res = self.inspect_file(yf)
                if domain is None or res.domain == domain:
                    results.append(res)

        return results

    def generate_template(self, domain: str = "generic") -> str:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if domain in {"work-weijian", "weijian"}:
            return f"""# 卫健委信息化项目事实真源 (SSOT)
schema_version: v1.0
entity_id: FACT-WJ-{now_str.replace("-", "")}-001
domain: work-weijian
name: 基层医疗卫生信息系统互联互通工程
owner: 信息化推进处
updated_at: '{now_str}'
lifecycle_stage: IMPLEMENTATION  # [INITIATION, PLANNING, IMPLEMENTATION, PILOT, OPERATIONAL, EVALUATION, ARCHIVED]

facts:
  project_code: WJ-2026-HLHT-01
  budget_million_cny: 8.60
  lead_agency: 市卫健委规划信息科
  target_completion: '2026-11-30'
  involved_entities:
    - 社区卫生服务中心 (36家)
    - 乡镇卫生院 (18家)
  core_systems:
    - 公共卫生协同平台
    - 分级诊疗转诊引擎
    - 电子健康卡认证网关
  security_compliance:
    djbh_level: 等保三级
    cryptography_standard: 国密SM2/SM3/SM4
"""
        elif domain in {"work-transfer", "transfer"}:
            return f"""# 科技成果转化项目事实真源 (SSOT)
schema_version: v1.0
entity_id: FACT-TF-{now_str.replace("-", "")}-001
domain: work-transfer
name: 脑机接口康复训练系统转化项目
owner: 成果转化一部
updated_at: '{now_str}'
lifecycle_stage: PILOT  # [INITIATION, PLANNING, IMPLEMENTATION, PILOT, OPERATIONAL, EVALUATION, ARCHIVED]

facts:
  transfer_id: TF-2026-BCI-03
  trl_level: 7  # 技术成熟度 (1~9)
  originating_institution: 国家转化医学中心 / 神经工程实验室
  lead_inventor: 首席科学家团队
  patent_portfolio:
    - ZL202510889911.2 (高信噪比脑电采集电极)
    - ZL202510889912.7 (运动意图在线解码算法)
  target_partner: 医疗机器人产业集团
  milestones:
    - stage: 临床前动物试验
      status: COMPLETED
    - stage: 二类医疗器械注册检验
      status: IN_PROGRESS
"""
        else:
            return f"""# 通用业务事实真源 (SSOT)
schema_version: v1.0
entity_id: FACT-GEN-{now_str.replace("-", "")}-001
domain: {domain}
name: 示例业务实体
owner: 业务负责人
updated_at: '{now_str}'
lifecycle_stage: OPERATIONAL

facts:
  status: ACTIVE
  description: 领域事实描述与结构化指标
  key_metrics:
    metric_a: 100
    metric_b: 99.9%
"""
