"""Exercise rejection in disposable directories, never against a real checkout."""
import importlib.util
from pathlib import Path

import pytest


def load_runner():
    path = Path(__file__).resolve().parents[1] / "run_all.py"
    spec = importlib.util.spec_from_file_location("boundary_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("nested", [False, True])
def test_pipeline_rejects_skill_tree_before_any_writes(tmp_path, monkeypatch, nested):
    runner = load_runner()
    skill = tmp_path / "fake-skill"
    skill.mkdir()
    target = skill / "nested" if nested else skill
    target.mkdir(exist_ok=True)
    before = list(skill.rglob("*"))
    monkeypatch.setattr(runner, "__file__", str(skill / "run_all.py"))
    monkeypatch.chdir(target)

    def forbidden_recorder():
        pytest.fail("write-capable pipeline reached before directory validation")

    monkeypatch.setattr(runner, "ProcessRecorder", forbidden_recorder)
    with pytest.raises(ValueError, match="Skill"):
        runner.run_pipeline("问题1：测试", "missing.csv", {}, strict_refs=False, demo_mode=True)
    assert list(skill.rglob("*")) == before


def test_demo_rejects_existing_artifacts_before_recorder(tmp_path, monkeypatch):
    runner = load_runner()
    project = tmp_path / "project"
    (project / "results").mkdir(parents=True)
    sentinel = project / "results" / "results.json"
    sentinel.write_bytes(b"original results")
    monkeypatch.chdir(project)
    monkeypatch.setattr(runner, "ProcessRecorder", lambda: pytest.fail("demo may overwrite artifacts"))
    with pytest.raises(ValueError, match="existing|已有"):
        runner.run_pipeline("问题1：测试", "missing.csv", {}, strict_refs=False, demo_mode=True)
    assert sentinel.read_bytes() == b"original results"
