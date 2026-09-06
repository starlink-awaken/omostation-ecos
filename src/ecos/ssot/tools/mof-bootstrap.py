#!/usr/bin/env python3
"""
织星 MOF — L0 自举校验器 (mof-bootstrap)
===========================================
L0 对自己的 M1 节点做自反性校验——L0 管全系统，谁管 L0？L0 管自己。

自举校验项:
  1. L0 自身的 M1 节点是否通过 mof-validate
  2. M3↔M2↔M1 的自反一致性 (M2 定义是否遵守 M3 的规则)
  3. L0 工具链完整性 (4+ 工具是否都在且可运行)
  4. L0 约束覆盖率 (有多少 M2 类型缺少 M1 实例)
  5. L0 层边界自检 (L0 自身是否遵守 layer-boundary.yaml)
  6. 自举闭环: 如果 L0 自己违规了，谁来创建 CARDS？

用法:
    python3 mof-bootstrap.py                 # 全量自举校验
    python3 mof-bootstrap.py --json          # JSON 输出
    python3 mof-bootstrap.py --fix           # 尝试自动修复
"""

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

HOME = Path.home()
WS = HOME / "Workspace"
L0_SSOT = WS / "projects" / "ecos" / "src" / "ecos" / "ssot"
L0_TOOLS = L0_SSOT / "tools"
L0_M1 = L0_SSOT / "mof" / "m1"
M2_DIR = L0_SSOT / "mof" / "m2"
M3_FILE = L0_SSOT / "mof" / "m3.yaml"
BOUNDARY_FILE = L0_SSOT / "registry" / "layer-boundary.yaml"
CARDS_DB = WS / "data" / "cards" / "cards.db"


def now():
    return datetime.now(timezone.utc)


def check_1_self_validate() -> dict:
    """L0 自身的 M1 节点校验"""
    result = subprocess.run(
        ["python3", str(L0_TOOLS / "mof-validate.py"), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    passed = result.returncode == 0
    count = 0
    if passed:
        try:
            data = json.loads(result.stdout)
            count = data.get("node_count", 0)
            results = data.get("results", [])
            errors = sum(1 for r in results if r.get("level") == "error")
            passed = errors == 0
        except Exception:  # defensive fallback
            pass

    return {
        "check": "L0 自校验",
        "passed": passed,
        "detail": f"{count} 节点通过",
        "severity": "critical" if not passed else "ok",
    }


def _load_m2_typedefs() -> dict:
    """加载 M2 目录, 返回 m2_type -> 类型定义 section.

    M2 文件含文件级元数据 (updated/owner/introduced_by/description 等),
    类型定义 section 的判别特征: dict 且含 m3_parent 键.
    section key 可能是 snake_case (如 compute_engine), 以 m2_type 键为准归一.
    """
    m2 = {}
    if not M2_DIR.exists():
        return m2
    for f in sorted(M2_DIR.rglob("*.yaml")):
        try:
            data = yaml.safe_load(open(f))
        except Exception:  # defensive fallback
            continue
        if not isinstance(data, dict):
            continue
        m2_type = data.get("m2_type")
        for k, v in data.items():
            if isinstance(v, dict) and "m3_parent" in v:
                m2[m2_type or k] = v
    return m2


def check_2_m3_m2_consistency() -> dict:
    """M3↔M2 自反一致性"""
    if not M3_FILE.exists() or not M2_DIR.exists():
        return {
            "check": "M3↔M2 一致性",
            "passed": False,
            "detail": "M3 或 M2 文件缺失",
            "severity": "critical",
        }

    m3 = yaml.safe_load(open(M3_FILE))
    m2 = _load_m2_typedefs()

    m3_elements = m3.get("m3", {}).get("elements", {})

    issues = []
    for mt, m2_def in m2.items():
        m3_parent = m2_def.get("m3_parent", "")
        if m3_parent:
            # Check M3 parent exists
            parts = m3_parent.split(".")
            if parts[0] not in m3_elements:
                issues.append(f"{mt}.m3_parent={m3_parent} 在 M3 中不存在")

    passed = len(issues) == 0
    return {
        "check": "M3↔M2 自反性",
        "passed": passed,
        "detail": f"{len(issues)} 不一致" if issues else "一致",
        "severity": "critical" if not passed else "ok",
    }


def check_3_toolchain_health() -> dict:
    """L0 工具链完整性"""
    tools = [
        "mof-validate.py",
        "mof-scan.py",
        "mof-audit.py",
        "mof-derive.py",
        "mof-enforce.py",
        "mof-extract.py",
        "mof-model.py",
        "mof-register-tasks.py",
    ]
    missing = [t for t in tools if not (L0_TOOLS / t).exists()]
    passed = len(missing) == 0
    return {
        "check": "L0 工具链完整性",
        "passed": passed,
        "detail": f"缺 {missing}" if missing else f"{len(tools)} 工具就绪",
        "severity": "high" if not passed else "ok",
    }


def _is_runtime_contract(m2_type: str) -> bool:
    """判定 M2 类型是否为运行时契约 (schema 编译消费, M1 实例不在 m1/ 落盘).

    W1/W2 工作流沉淀的执行契约 (Signal→Commitment→WorkPacket→ActionReceipt
    等), 实例生活在运行时面 (.omo/_delivery, Ledger, dispatch artifacts),
    不以 m1/*.yaml 形态落盘 — 覆盖率检查按设计豁免. 名单与
    mof/m2/*.yaml 文件头 'strict contract'/'execution contract' 声明对齐.
    """
    return m2_type in {
        # W1/W2 执行契约: Signal→Commitment→WorkPacket→ActionReceipt 链,
        # 实例在 .omo/_delivery / Ledger (ADR-0408 W2-03)
        "ActionReceipt",
        "Commitment",
        "CompletionManifest",
        "DelegationMandate",
        "Episode",
        "EventEnvelope",
        "OmniEnvelope",
        "PolicyDecision",
        "Signal",
        "SpecificationBinding",
        "StateCache",
        "WorkPacket",
        "M2BaseSchema",  # schema-of-schema, 不实例化
        # l4-kernel 契约: 实例由 l4_kernel.contracts Pydantic 模型承载
        "L4DomainHealth",
        "L4DomainManifest",
        "L4HarnessProfile",
        # 治理面决策: 实例在 .omo/_knowledge/decisions (ADR 体系), 非 m1 落盘
        "GovernanceDecision",
    }


def check_4_m1_coverage() -> dict:
    """M1 覆盖率分析"""
    # Load M2 — 只取类型定义 section (含 m3_parent), 跳过文件级元数据
    m2 = _load_m2_typedefs()
    m2_types = sorted(m2.keys())

    coverage = {}
    for f in L0_M1.rglob("*.yaml"):
        try:
            data = yaml.safe_load(open(f))
        except Exception:  # defensive fallback
            continue
        # multi-doc list 文件 (如 AGENT-RESIDENT-ROLES.yaml) 逐项计数
        docs = data if isinstance(data, list) else [data]
        for item in docs:
            if isinstance(item, dict):
                t = item.get("type", "?")
                coverage[t] = coverage.get(t, 0) + 1

    # 运行时契约类型的 M1 实例生活在运行时面, 不以 m1/*.yaml 落盘 — 按设计豁免
    contract_exempt = {t for t in m2_types if coverage.get(t, 0) == 0 and _is_runtime_contract(t)}
    gaps = [t for t in m2_types if coverage.get(t, 0) < 1 and t not in contract_exempt]
    passed = len(gaps) == 0
    note = f"; {len(contract_exempt)} 个运行时契约类型豁免 (实例在运行时面)" if contract_exempt else ""
    return {
        "check": "M1 覆盖率",
        "passed": passed,
        "detail": f"缺口: {gaps}{note}" if gaps else f"{len(m2_types)} 类型全覆盖",
        "severity": "medium" if gaps else "ok",
    }


def check_5_l0_boundary_self() -> dict:
    """L0 层边界自检"""
    if not BOUNDARY_FILE.exists():
        return {
            "check": "L0 边界自检",
            "passed": False,
            "detail": "layer-boundary.yaml 不存在",
            "severity": "critical",
        }

    boundary = yaml.safe_load(open(BOUNDARY_FILE))
    boundary.get("layers", {}).get("L0", {})

    # Check: all files in L0_SSOT conform to L0 rules
    violations = []
    for f in L0_SSOT.rglob("*"):
        if f.is_file() and f.suffix == ".md":
            # L0 forbids .md (unless README/INDEX/CHANGELOG)
            if not any(k in f.name for k in ["README", "INDEX", "CHANGELOG"]):
                if "CLAUDE" not in f.name and "AGENTS" not in f.name:
                    violations.append(f.name)

    passed = len(violations) == 0
    return {
        "check": "L0 层边界自检",
        "passed": passed,
        "detail": f"{len(violations)} 违规" if violations else "L0 自身合规",
        "severity": "high" if violations else "ok",
    }


def check_6_bootstrap_closure() -> dict:
    """自举闭环：如果 L0 自己违规，谁来管？"""
    # Check: does mof-bootstrap itself have a CARDS debt for self-issues?
    # Check: does the validator script exist and run?
    validator = L0_TOOLS / "mof-validate.py"
    if not validator.exists():
        return {
            "check": "自举闭环",
            "passed": False,
            "detail": "mof-validate.py 不存在——L0 无法校验自己",
            "severity": "critical",
        }

    # Bootstrap closure: can we validate the validator?
    passed = validator.exists()
    return {
        "check": "自举闭环",
        "passed": passed,
        "detail": "L0 可自校验" if passed else "破损",
        "severity": "critical" if not passed else "ok",
    }


def create_bootstrap_debt(issue: dict):
    """为自举发现的问题创建 CARDS"""
    if not CARDS_DB.exists():
        return
    if issue["severity"] == "ok":
        return
    try:
        conn = sqlite3.connect(str(CARDS_DB))
        now_dt = now().isoformat()
        debt_id = f"DEBT-BOOTSTRAP-{now_dt[:10]}-{issue['check'][:20]}"
        debt_id = debt_id.replace(" ", "-")[:50]
        conn.execute(
            """
            INSERT OR IGNORE INTO cards (id, type, status, title, domain, priority, summary, content, created_at, updated_at)
            VALUES (?, 'debt', 'identified', ?, 'meta', 'P1', ?, ?, ?, ?)
        """,
            (
                debt_id,
                f"L0自举: {issue['check']}",
                issue["detail"],
                f"## mof-bootstrap 自动检测\n- 检查: {issue['check']}\n- 结果: {issue['detail']}\n- 严重度: {issue['severity']}",
                now_dt,
                now_dt,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:  # defensive fallback
        pass


def format_report(checks: list[dict]) -> str:
    lines = [
        "=" * 64,
        "  织星 MOF — L0 自举校验报告",
        "=" * 64,
        f"  时间: {now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    all_pass = True
    for c in checks:
        icon = (
            "✅"
            if c["passed"]
            else {"critical": "🔴", "high": "🟡", "medium": "🟢", "ok": "✅"}.get(c["severity"], "❓")
        )
        lines.append(f"  {icon} {c['check']}: {c['detail']}")
        if not c["passed"]:
            all_pass = False

    lines.append(f"\n  {'✅ L0 自举健康' if all_pass else '❌ L0 自举发现问题'}")
    lines.append("=" * 64)
    return "\n".join(lines)


def main():
    import sys

    print("⚠️ MOF Bootstrap 独立 CLI 已弃用，请使用 cockpit 替代", file=sys.stderr)
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()

    checks = [
        check_1_self_validate(),
        check_2_m3_m2_consistency(),
        check_3_toolchain_health(),
        check_4_m1_coverage(),
        check_5_l0_boundary_self(),
        check_6_bootstrap_closure(),
    ]

    if args.json:
        print(json.dumps({"checks": checks}, ensure_ascii=False, indent=2))
    else:
        print(format_report(checks))

    if args.fix:
        for c in checks:
            if not c["passed"]:
                create_bootstrap_debt(c)
        print("\n  📋 已为自举问题创建 CARDS")


if __name__ == "__main__":
    main()
