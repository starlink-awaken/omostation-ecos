"""pytest conftest — add scripts to sys.path for all tests"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ECOS_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = str(ECOS_ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

L0_DERIVED = ECOS_ROOT / ".omo" / "_derived" / "l0-constraints.v2.yaml"


@pytest.fixture(scope="session", autouse=True)
def ensure_l0_derived_plane():
    """确保 L0 派生面存在 (l0-constraints.v2.yaml, 137 rules).

    派生面被 gitignore (ADR-0137: checkout 时从 tracked SSOT 重建), 但 CI
    (ecos ci.yml / 主仓 cascading-test) 在 checkout 后不会自动重建, 导致
    MOFPolicyCompiler 回退到 base constraints.yaml (67 条), 测试断言
    len(policy_set.rules) >= 100 失败。session 开始前若缺失则运行生成器。
    """
    if L0_DERIVED.exists():
        return
    gen = ECOS_ROOT / "bin" / "gen-l0-constraints.py"
    if not gen.exists():
        return
    result = subprocess.run(
        [sys.executable, str(gen)],
        cwd=ECOS_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"L0 派生面缺失且自动生成失败: {L0_DERIVED}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


@pytest.fixture
def ssb_key(monkeypatch, tmp_path):
    """Opt-in hermetic SSB signing key.

    Only tests that request this fixture get a random key installed into the
    canonical ssb_auth module (tmp KEY_FILE, SSB_KEY env removed). Tests that
    do NOT request it keep observing the real fail-closed no-key behavior
    (_load_key() -> None, compute_signature() -> None).
    """
    from ecos.l0.ssb import ssb_auth as auth

    key_file = tmp_path / ".ssb_key"
    key = os.urandom(32)
    key_file.write_bytes(key)

    monkeypatch.delenv("SSB_KEY", raising=False)
    monkeypatch.setattr(auth, "KEY_FILE", key_file)
    return key
