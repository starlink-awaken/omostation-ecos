import json

from ecos.cli.constraint import main as cli_main
from ecos.ssot.compiler.ast_inspector import AstDependencyInspector
from ecos.ssot.compiler.context_synthesizer import MOFContextSynthesizer


def test_context_synthesizer_guardrails():
    synthesizer = MOFContextSynthesizer()
    prompt = synthesizer.synthesize_guardrails(domain="runtime", layer="L3", max_rules=3)
    assert "<mof_architecture_guardrails" in prompt
    assert "</mof_architecture_guardrails>" in prompt
    assert "L3" in prompt


def test_context_synthesizer_explain_rule():
    synthesizer = MOFContextSynthesizer()
    info = synthesizer.explain_rule("E-L0-002")
    assert info is not None
    assert info["violation_code"] == "E-L0-002"
    assert "code_recipe" in info
    assert "agora.client" in info["code_recipe"]["valid"]


def test_ast_inspector_generates_suggested_patch():
    inspector = AstDependencyInspector()
    code = "import runtime.private.credentials as creds"
    violations = inspector.inspect_code(code, caller_layer="L3")
    assert len(violations) == 1
    assert violations[0].suggested_patch is not None
    assert "agora.client" in violations[0].suggested_patch
    assert "bos://governance/mof/auth" in violations[0].suggested_patch


def test_cli_explain(capsys):
    ret = cli_main(["explain", "E-L0-002", "--json"])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["violation_code"] == "E-L0-002"


def test_cli_explain_text(capsys):
    ret = cli_main(["explain", "E-L0-002"])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "MOF 规则详解" in captured


def test_cli_drift(capsys):
    ret = cli_main(["drift", "--json"])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["status"] == "IN_SYNC"


def test_cli_guardrail(capsys):
    ret = cli_main(["guardrail", "--domain", "runtime", "--layer", "L3"])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "<mof_architecture_guardrails" in captured


def test_cli_list(capsys):
    ret = cli_main(["list", "--json"])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert isinstance(data, list)
    assert len(data) > 0


def test_cli_eval_pass(capsys):
    ret = cli_main(["eval", "--tool", "replace_file_content", "--args", '{"TargetFile": "/foo/bar.py", "ReplacementContent": "a = 1"}'])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["status"] == "ALLOWED"


def test_cli_eval_reject(capsys):
    ret = cli_main(["eval", "--tool", "run_command", "--args", '{"CommandLine": "pip install --user flask"}'])
    assert ret == 1
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["status"] == "REJECTED"
    assert data["violation"]["violation_code"] == "E-CMD-001"


def test_cli_audit(tmp_path, capsys):
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("import runtime.private.credentials\n", encoding="utf-8")
    ret = cli_main(["audit", str(tmp_path), "--json", "--strict"])
    assert ret == 1
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["violations_count"] == 1
    assert data["violations"][0]["violation_code"] == "E-L0-002"
