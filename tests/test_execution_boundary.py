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


# ── v3.0 C6：真实路径不画图，并检测 figures/ 是否混入 run_all 演示模板产物 ──
def test_real_path_solver_never_plots_demo_figures(tmp_path, monkeypatch):
    """C6：真实路径跑完不得产生任何图——不建 figures/，更不得有 run_all 模板脚本。"""
    runner = load_runner()
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n2\n", encoding="utf-8")

    def prepare(df, recorder):
        return df

    from math_modeling.workflow import REVIEW_FIELDS
    code = tmp_path / "q1.py"
    code.write_text("# boundary fixture\n", encoding="utf-8")

    def solver(question, df, seed, qi, recorder):
        result = {f"Q{qi}_value": float(df.x.sum())}
        if qi == 1:
            result.update(_basis={"model": "sum"}, _basis_files=[str(code)],
                          _review={key: "evidence" for key in REVIEW_FIELDS})
        return result

    runner.run_pipeline("问题1：求和。", data, {}, solver=solver, prepare=prepare)
    assert not (tmp_path / "figures").exists(), "真实路径不画图，不得创建 figures/"
    assert runner.detect_run_all_generated_figures(str(tmp_path / "figures")) == []
    # 画图函数名已从公开面移除，真实路径无从误调
    assert not hasattr(runner, "plot_and_register_figures")


def test_run_all_generated_figure_guard_detects_demo_template(tmp_path):
    """C6 守卫：真实路径检测到 figures 由 run_all 演示模板生成时必须报警。"""
    runner = load_runner()
    figdir = tmp_path / "figures"
    (figdir / "scripts").mkdir(parents=True)
    (figdir / "scripts" / "fig1.py").write_text(
        "# " + runner._DEMO_FIGURE_MARKER + "\nprint(1)\n", encoding="utf-8")
    (figdir / "scripts" / "fig2.py").write_text("print(2)\n", encoding="utf-8")
    found = runner.detect_run_all_generated_figures(str(figdir))
    assert found == ["figures/scripts/fig1.py"]
    assert runner.detect_run_all_generated_figures(str(tmp_path / "absent")) == []


def test_audit_figure_registry_reports_missing_manifest(tmp_path):
    """C6：真实路径只做契约登记校验，缺清单如实报出（不代绘图）。"""
    runner = load_runner()
    issues = runner.audit_figure_registry(str(tmp_path / "figures"))
    assert issues and "图契约清单缺失" in issues[0]


def test_audit_figure_registry_complete_v3_layout_passes(tmp_path):
    """回归：脚本/数据落在分层位且带 data_binding 时零 issues（默认扩展名不得张冠李戴）。"""
    import json
    runner = load_runner()
    figdir = tmp_path / "figures"
    (figdir / "scripts").mkdir(parents=True)
    (figdir / "data").mkdir(parents=True)
    (figdir / "scripts" / "fig1.py").write_text("print(1)\n", encoding="utf-8")
    (figdir / "data" / "fig1.json").write_text("{}", encoding="utf-8")
    (figdir / "fig1.png").write_bytes(b"x")
    (figdir / "figures_manifest.json").write_text(json.dumps([{
        "no": "fig1", "file": "fig1.png",
        "script": "figures/scripts/fig1.py", "data_entrypoint": "figures/data/fig1.json",
        "data_binding": {"results_path": "results/results.json", "bindings": {"y": "k"}}}]),
        encoding="utf-8")
    assert runner.audit_figure_registry(str(figdir)) == []
