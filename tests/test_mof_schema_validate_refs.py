"""Regression coverage for MOF model-driven source references."""

from __future__ import annotations

import ast
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ECOS_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ECOS_ROOT / "src" / "ecos" / "ssot" / "tools" / "mof-schema-validate.py"
M1_ROOT = ECOS_ROOT / "src" / "ecos" / "ssot" / "mof" / "m1"
OMO_C2G_SOURCE = "projects/omo/src/omo/_vendored/c2g/mcp_server.py"


def _validator() -> dict[str, object]:
    return runpy.run_path(str(VALIDATOR))


def _workspace_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Build only the cross-project paths that the validator must resolve."""
    validator_path = tmp_path / "projects/ecos/src/ecos/ssot/tools/mof-schema-validate.py"
    validator_path.parent.mkdir(parents=True)
    validator_path.touch()
    source_path = tmp_path / OMO_C2G_SOURCE
    source_path.parent.mkdir(parents=True)
    source_path.touch()
    return validator_path, source_path


def _validator_for_workspace(validator_path: Path) -> dict[str, object]:
    namespace = _validator()
    namespace["check_m1_node"].__globals__["__file__"] = str(validator_path)
    return namespace


def test_check_refs_reads_source_file_map_from_workspace_root(tmp_path: Path) -> None:
    validator_path, _ = _workspace_fixture(tmp_path)
    namespace = _validator_for_workspace(validator_path)
    check_m1_node = namespace["check_m1_node"]
    issues = check_m1_node(
        {"model_driven_refs": {"source_file": OMO_C2G_SOURCE}},
        {},
        "MCPTool",
        check_refs=True,
    )
    assert issues == []


def test_check_refs_rejects_missing_source_file_from_map(tmp_path: Path) -> None:
    validator_path, _ = _workspace_fixture(tmp_path)
    namespace = _validator_for_workspace(validator_path)
    check_m1_node = namespace["check_m1_node"]
    issues = check_m1_node(
        {"model_driven_refs": {"source_file": "projects/omo/src/omo/_vendored/c2g/missing.py"}},
        {},
        "MCPTool",
        check_refs=True,
    )
    assert issues == ["  - ref path not found: projects/omo/src/omo/_vendored/c2g/missing.py"]


def test_staged_validation_applies_check_refs_to_source_file_map(tmp_path: Path) -> None:
    node = tmp_path / "missing-reference.yaml"
    node.write_text(
        "id: MCPTOOL-test\ntype: MCPTool\ntool_name: test\nserver: test\nmodel_driven_refs:\n  source_file: projects/omo/src/omo/_vendored/c2g/missing.py\n",
        encoding="utf-8",
    )
    namespace = _validator()
    args = SimpleNamespace(strict=True, check_types=False, check_transitions=False, check_refs=True)
    with pytest.raises(SystemExit, match="1"):
        namespace["_validate_specific_files"]([node], args)


def test_c2g_mcp_tools_are_three_protocol_nodes_backed_by_vendored_omo_source() -> None:
    component = yaml.safe_load((M1_ROOT / "component" / "COMP-WS-c2g.yaml").read_text(encoding="utf-8"))
    assert component["model_driven_refs"]["source_file"] == OMO_C2G_SOURCE
    assert component["entry_points"] == [
        {"type": "cli", "command": "c2g", "module": "omo._vendored.c2g.cli:main"},
        {"type": "mcp", "command": "c2g-mcp", "module": "omo._vendored.c2g.mcp_server:mcp"},
    ]
    service = yaml.safe_load((M1_ROOT / "service" / "SVC-C2G-MCP.yaml").read_text(encoding="utf-8"))
    assert service["project"] == "omo"
    assert service["model_driven_refs"] == {
        "source_file": "projects/omo/src/omo/_vendored/c2g/mcp_server.py",
        "package_entry": "projects/omo/pyproject.toml",
    }
    assert service["relations"]["provided_by"] == "COMP-WS-c2g"
    expected = {"MCPTOOL-C2G.yaml": "c2g_bet", "MCPTOOL-C2G-radar.yaml": "c2g_radar", "MCPTOOL-C2G-gc.yaml": "c2g_gc"}
    actual = {}
    for filename, tool_name in expected.items():
        payload = yaml.safe_load((M1_ROOT / "mcptool" / filename).read_text(encoding="utf-8"))
        actual[filename] = payload["tool_name"]
        assert payload["id"] == f"MCPTOOL-C2G-{tool_name.removeprefix('c2g_')}"
        assert payload["type"] == "MCPTool"
        assert payload["m3_parent"] == "BehavioralElement.Protocol"
        assert payload["server"] == "c2g"
        assert payload["relations"]["provided_by"] == "COMP-WS-c2g"
        assert payload["model_driven_refs"]["source_file"] == OMO_C2G_SOURCE
    assert actual == expected


def test_c2g_omo_provider_exports_the_declared_tools() -> None:
    source = ECOS_ROOT.parents[1] / OMO_C2G_SOURCE
    if not source.is_file():
        pytest.skip("OMO sibling checkout is required to verify provider decorators")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    decorated_tools = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        )
    }
    assert decorated_tools == {"c2g_bet", "c2g_radar", "c2g_gc"}


def test_agent_governance_workflow_points_to_canonical_workflow_and_c2g_authorities() -> None:
    workflow = yaml.safe_load(
        (M1_ROOT / "workflow" / "WORKFLOW-AGENT-GOVERNANCE-CONTROL-PLANE.yaml").read_text(encoding="utf-8")
    )
    relations = {relation["type"]: relation for relation in workflow["relations"]}
    assert relations["realizes"]["target"] == ".omo/_truth/registry/agent-workflows/"
    assert relations["routes_strategy"]["target"] == "projects/omo/src/omo/_vendored/c2g"
