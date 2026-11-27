---
type: ssot
last_updated: 2026-11-27
last-reviewed: 2026-11-27
owner: governance-team
lifecycle: entry
status: active
---

# eCOS 运营脚本

> v1.1 | 2026-11-27
> 本目录是 eCOS 运营脚本的 git 版本管理面；运行时路径 `~/.ecos/scripts/` 自 2026-06-07 起是指向本目录的 symlink。

## 与 ~/.ecos/scripts/ 的关系

| | ~/.ecos/scripts/ | ecos/scripts/ |
|:--|:-----------------|:--------------|
| **角色** | 运行时路径（symlink → 本目录，2026-06-07 起） | git 版本管理 |
| **修改** | 直接编辑本目录即生效 | git 管理 |
| **同步** | 无需复制 | — |

**原则**: 在 `ecos/scripts/` 改 → 提交 → 运行时路径即刻生效（同一目录）。

## 核心脚本清单

| 脚本 | 功能 | daemon 周期 |
|------|------|:-----------:|
| `ecos-daemon.py` | 自治运维守护进程 (6h) | 主循环 |
| `ecos-weekly-digest.py` | 每周健康摘要 | 每 28 周期 |
| `ecos-sla-tracker.py` | SLA 记录 | 每周期 |
| `ecos-healer.py` | 自治愈 | 有错误时 |
| `bos-registry-daemon.py` | BOS 路由自动同步 | 手动/定时 |
| `check-disk-usage.py` | SharedDisk 空间告警 | 每周期 |
| `ecos-onboard.py` | 新机器引导 | 一次性 |
| `ecos-bootstrap.py/sh` | 冷启动安装 | 一次性 |

## 改一个脚本

```bash
vim scripts/ecos-daemon.py
python3 ~/.ecos/scripts/ecos-daemon.py --once     # symlink 指向本目录, 立即生效
git add scripts/ && git commit -m "fix daemon paths"
```

> 新增脚本同样只需落在本目录并提交；运行路径会自动看到它（symlink）。
> 脚本规模不在本文档维护 —— 见 `docs/generated/capability-registry.yaml` 或本目录清单。


## 架构变更 2026-06-07

**之前**: `~/.ecos/scripts/` 是独立目录，与 git 无关，靠手动 `cp` 同步。
**之后**: `~/.ecos/scripts/` → symlink → `ecos/scripts/`，改动即生效、有版本管理。

回滚: `~/.ecos/scripts.bak/` 是切换前的备份。
