import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_selftest_uses_copied_code_and_separate_demo_project(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/gate_audit.py"
    spec = importlib.util.spec_from_file_location("isolated_audit", path)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    fake = tmp_path / "fake-skill"
    (fake / "references").mkdir(parents=True)
    (fake / "run_all.py").write_text("# fixture only", encoding="utf-8")
    monkeypatch.setattr(audit, "ROOT", fake)
    calls = []

    def inspect_run(command, **kwargs):
        calls.append((command, kwargs))
        if "--demo" in command:
            script = Path(command[2])
            assert script.is_absolute()
            assert Path(kwargs["cwd"]).resolve() != script.parent.resolve()
            assert script.read_text(encoding="utf-8") == "# fixture only"
        assert str(fake) not in kwargs["env"]["PYTHONPATH"]
        return SimpleNamespace(returncode=0, stdout="fixture", stderr="")

    monkeypatch.setattr(audit.subprocess, "run", inspect_run)
    assert audit.self_test()["passed"]
    assert len(calls) == 7
