---
type: ssot
last-reviewed: 2026-08-26
---

# B4-A.1 ECOS C2G authority convergence evidence

Date: 2026-08-23

## Scenario: model-driven source map and staged reference enforcement

Invocation:

```sh
uv run pytest tests/test_mof_schema_validate_refs.py tests/test_l4_contract_schemas.py -q
```

Binary observable: `10 passed`.

The new regression tests prove that a `model_driven_refs.source_file` map is
resolved from the Workspace root, a missing mapped source is rejected, and
`--staged --check-refs` applies that check.

## Scenario: affected C2G M1 nodes

Invocation (using a disposable `GIT_INDEX_FILE`, not the shared index):

```sh
uv run python src/ecos/ssot/tools/mof-schema-validate.py \
  --staged --strict --check-refs --check-types
```

Binary observable: `mof-schema-validate: 4 staged M1 文件全部通过`.

The staged set contains `COMP-WS-c2g` plus the three legal MCPTool nodes:
`c2g_bet`, `c2g_radar`, and `c2g_gc`.  Each points to
`projects/omo/src/omo/_vendored/c2g/mcp_server.py`; the component entry point
is `c2g-mcp = omo._vendored.c2g.mcp_server:mcp`.

## Scenario: M2 MCPTool compatibility

Invocation:

```sh
uv run python src/ecos/ssot/tools/mof-validate.py \
  --type MCPTool --nodes src/ecos/ssot/mof/m1/mcptool --json
```

Binary observable: entries for `MCPTOOL-C2G-bet`, `MCPTOOL-C2G-radar`, and
`MCPTOOL-C2G-gc` each report `passed: true`.

## Residual baseline

The broad `mof-schema-validate.py --focus mcptool --check-refs` scan reports
11 pre-existing `projects/gbrain/src/core/operations.ts` paths.  They are not
C2G nodes and were not changed by this repair.
