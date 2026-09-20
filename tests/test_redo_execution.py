import json
from pathlib import Path

import pytest
import run_all


def test_demo_verifications_measure_actual_grids_and_comparison():
    evidence = run_all.run_verifications({"Q1_最优x": 3.0}, 1, None, 42)
    assert isinstance(evidence, dict)
    assert set(evidence) == {"grid", "convergence", "sensitivity", "error", "comparison"}
    assert evidence["grid"]["fine_step"] < evidence["grid"]["coarse_step"]
    assert evidence["comparison"]["refined_objective"] <= evidence["comparison"]["coarse_objective"]
    assert evidence["sensitivity"]["optimal_positions"] == pytest.approx([2.4, 3.0, 3.6])


def test_demo_rejects_checkout_before_creating_input(tmp_path, monkeypatch):
    root = tmp_path / "fake-skill"
    root.mkdir()
    monkeypatch.setattr(run_all, "__file__", str(root / "run_all.py"))
    monkeypatch.chdir(root)
    monkeypatch.setattr(run_all.pd.DataFrame, "to_csv", lambda *a, **k: pytest.fail("demo created input before guard"))
    with pytest.raises(ValueError, match="Skill"):
        run_all.demo()


def test_solver_failure_keeps_real_trial_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")

    def prepare(df, rec):
        rec.log("数据清洗", "PREPARE_EVIDENCE")
        return df

    def solve(*args):
        args[-1].log("算法取舍", "FAILED_TRIAL_EVIDENCE")
        raise RuntimeError("synthetic solver failure")

    with pytest.raises(RuntimeError, match="synthetic"):
        run_all.run_pipeline("问题1：计算。", data, {}, solver=solve, prepare=prepare)
    record = tmp_path / "output/process_record.md"
    assert record.is_file()
    assert "FAILED_TRIAL_EVIDENCE" in record.read_text(encoding="utf-8")
    assert not (tmp_path / "output/workflow_state.json").exists()
