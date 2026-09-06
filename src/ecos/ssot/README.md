---
type: ssot
last_updated: 2026-09-04
last-reviewed: 2026-08-26
owner: governance-team
---

# 织星 L0 — 协议编织层

> eCOS v6.3 | 织星架构 (Stellar Weave) | 2026-06-06
> L0 是 MetaOS 的架构 DNA 编译器——系统的自我描述与治理引擎

---

## 快速导航

| 你想做什么 | 去这里 |
|-----------|--------|
| 理解 L0 的架构 | 读本文 |
| 查看系统拓扑 | `registry/topology.yaml` |
| 查看架构模式 | `registry/patterns.yaml` |
| 查看层边界规则 | `registry/layer-boundary.yaml` |
| 查看协议注册表 | `registry/L0-constraints.yaml` |
| 查看元模型定义 | `mof/m2/` (M2 元模型, 计数以实际文件为准) |
| 查看全量资产节点 | `mof/m1/` (M1 节点, 计数见 `bin/mof/check-mof-capabilities-drift.py`) |
| 运行架构校验 | `python3 tools/mof-validate.py` |
| 运行自举检查 | `python3 tools/mof-bootstrap.py` |
| 运行漂移审计 | `python3 tools/mof-audit.py` |
| 运行层合规检查 | `python3 tools/mof-enforce.py` |

---

## 架构

```
ssot/                               ← L0 SSOT
├── README.md                       ← 本文件
├── validator.py                    ← 统一入口校验器
│
├── registry/                       ← 注册表
│   ├── topology.yaml               ← 6层拓扑·包依赖
│   ├── patterns.yaml               ← 7 架构模式
│   ├── layer-boundary.yaml         ← 层边界规则
│   ├── L0-constraints.yaml         ← 9 约束定义
│   └── governance/                 ← 治理配置
│       ├── x3-value-stack.yaml
│       ├── agent-manifest.yaml
│       ├── hooks.yaml
│       └── kos-index.yaml
│
├── mof/                            ← 织星 MOF 引擎
│   ├── m3.yaml                     ← M3 元元模型 (19类型·17关系)
│   ├── m2/                         ← M2 元模型 (每类型一个文件)
│   ├── m1/                         ← M1 节点 (按类型分目录)
│   ├── m0/snapshot.yaml            ← M0 运行时快照
│   └── ontology.yaml               ← 本体映射
│
└── tools/ (43 个)                   ← 工具链
    ├── mof-validate.py             ← M1↔M2 校验
    ├── mof-scan.py                 ← 自动扫描 → M1
    ├── mof-model.py                ← 全量资产建模
    ├── mof-audit.py                ← M1↔M0 漂移审计
    ├── mof-derive.py               ← 本体推理
    ├── mof-extract.py              ← 逆向提炼
    ├── mof-enforce.py              ← 层合规强制执行
    ├── mof-sla.py                  ← SLA 执行 + M0快照
    ├── mof-bootstrap.py            ← L0 自举校验
    └── mof-register-tasks.py       ← 任务/脚本注册
```

## MOF 四层模型

```
M3  元元模型     19 Element 类型 · 17 Relation 类型
     ↓ 定义"定义的方式"
M2  元模型       每类型一个 schema 文件 (架构·协议·模式·流程·实体...)
     ↓ 定义"每一种东西长什么样"
M1  节点声明     全系统的模型化表达 (计数以实际文件为准)
     ↓ 声明"系统中有哪些东西"
M0  运行时快照    daemon 每 6h 刷新 (实际运行状态)
     ↑ 反馈"系统实际在怎么跑"
```

## 工具链与 daemon 循环

```
daemon 每 6h:
  bootstrap → enforce → sla → audit → health-check → digest
```

## 数字快照

> 节点/类型/工具计数是易变事实, 不在本文件硬编码 (doc-ssot 契约 + ecos CLAUDE.md "以实际文件为准").

| 维度 | 权威读源 |
|------|------|
| M2 schema 数 | `find ssot/mof/m2 -name "*.yaml" \| wc -l` |
| M1 节点数 | `find ssot/mof/m1 -name "*.yaml" \| wc -l`; 注册表镜像 `.omo/_truth/registry/mof-capabilities.yaml::model_stats` |
| 工具链 | `ls ssot/tools/*.py \| wc -l`; 能力登记 同上 `::tools` |
| 校验状态 | `python3 tools/mof-schema-validate.py --json` |
| 注册表漂移 | `python3 bin/mof/check-mof-capabilities-drift.py --json` |
