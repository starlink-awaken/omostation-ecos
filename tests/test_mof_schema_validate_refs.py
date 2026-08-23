"""Regression coverage for MOF model-driven source references."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ECOS_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ECOS_ROOT / "src" / "ecos" / "ssot" / "tools" / "mof-schema-validate.py"
M1_ROOT = ECOS_ROOT / "src" / "ecos" / "ssot" / "mof" / "m1"


def _validator() -> dict[str, object]:
    return runpy.run_path(str(VALIDATOR))


def test_check_refs_reads_source_file_map_from_workspace_root(tmp_path: Path) -> None:
    # validator 从 __file__ 上溯推导 repo_root/workspace_root, 跨仓 ref 在
    # workspace_root(projects/ 的父级)下解析。CI runner 只 checkout ecos
    # 自身, 真实兄弟仓 projects/omo 不存在 —— 本测试原先隐式依赖开发者
    # 本机布局, 在 CI 上必红(自 ba5128d 引入起 main CI 持续 failure)。
    # 这里在 tmp_path 构造完整的假 workspace 布局, 并把 namespace 的
    # __file__ 重定向过去(runpy namespace 即被测函数的全局作用域)。
    fake_validator = (
        tmp_path / "ws" / "projects" / "ecos" / "src" / "ecos" / "ssot" / "tools" / "mof-schema-validate.py"
    )
    fake_validator.parent.mkdir(parents=True)
    fake_validator.write_text("# location anchor", encoding="utf-8")
    sibling = tmp_path / "ws" / "projects" / "omo" / "src" / "omo" / "_vendored" / "c2g" / "mcp_server.py"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("# sibling repo file", encoding="utf-8")

    namespace = _validator()
    namespace["__file__"] = str(fake_validator)
    check_m1_node = namespace["check_m1_node"]

    issues = check_m1_node(
        {
            "model_driven_refs": {
                "source_file": "projects/omo/src/omo/_vendored/c2g/mcp_server.py",
            }
        },
        {},
        "MCPTool",
        check_refs=True,
    )

    assert issues == []


def test_check_refs_rejects_missing_source_file_from_map() -> None:
    namespace = _validator()
    check_m1_node = namespace["check_m1_node"]

    issues = check_m1_node(
        {
            "model_driven_refs": {
                "source_file": "projects/omo/src/omo/_vendored/c2g/missing.py",
            }
        },
        {},
        "MCPTool",
        check_refs=True,
    )

    assert issues == [
        "  - ref path not found: projects/omo/src/omo/_vendored/c2g/missing.py"
    ]


def test_staged_validation_applies_check_refs_to_source_file_map(
    tmp_path: Path,
) -> None:
    node = tmp_path / "missing-reference.yaml"
    node.write_text(
        """\
id: MCPTOOL-test
type: MCPTool
tool_name: test
server: test
model_driven_refs:
  source_file: projects/omo/src/omo/_vendored/c2g/missing.py
""",
        encoding="utf-8",
    )
    namespace = _validator()
    args = SimpleNamespace(
        strict=True,
        check_types=False,
        check_transitions=False,
        check_refs=True,
    )

    with pytest.raises(SystemExit, match="1"):
        namespace["_validate_specific_files"]([node], args)


def test_c2g_mcp_tools_are_three_protocol_nodes_backed_by_vendored_omo_source() -> None:
    component = yaml.safe_load(
        (M1_ROOT / "component" / "COMP-WS-c2g.yaml").read_text(encoding="utf-8")
    )
    assert component["model_driven_refs"]["source_file"] == (
        "projects/omo/src/omo/_vendored/c2g/mcp_server.py"
    )
    assert component["entry_points"] == [
        {
            "type": "mcp",
            "command": "c2g-mcp",
            "module": "omo._vendored.c2g.mcp_server:mcp",
        }
    ]

    expected = {
        "MCPTOOL-C2G.yaml": "c2g_bet",
        "MCPTOOL-C2G-radar.yaml": "c2g_radar",
        "MCPTOOL-C2G-gc.yaml": "c2g_gc",
    }
    actual = {}
    for filename, tool_name in expected.items():
        payload = yaml.safe_load((M1_ROOT / "mcptool" / filename).read_text(encoding="utf-8"))
        actual[filename] = payload["tool_name"]
        assert payload["id"] == f"MCPTOOL-C2G-{tool_name.removeprefix('c2g_')}"
        assert payload["type"] == "MCPTool"
        assert payload["m3_parent"] == "BehavioralElement.Protocol"
        assert payload["server"] == "c2g"
        assert payload["relations"]["provided_by"] == "COMP-WS-c2g"
        assert payload["model_driven_refs"]["source_file"] == (
            "projects/omo/src/omo/_vendored/c2g/mcp_server.py"
        )

    assert actual == expected
