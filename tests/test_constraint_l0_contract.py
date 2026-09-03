from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
M2_PATH = ROOT / "src/ecos/ssot/mof/m2/constraint_l0.yaml"
M3_PATH = ROOT / "src/ecos/ssot/mof/m3.yaml"


def test_constraint_l0_m2_parent_is_a_registered_m3_element() -> None:
    m2 = yaml.safe_load(M2_PATH.read_text(encoding="utf-8"))
    m3 = yaml.safe_load(M3_PATH.read_text(encoding="utf-8"))

    parent = m2["ConstraintL0"]["m3_parent"]
    assert parent in m3["m3"]["elements"]
    assert parent == "Constraint"
