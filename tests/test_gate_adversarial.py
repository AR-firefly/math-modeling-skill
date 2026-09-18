"""Adversarial regressions: approval must follow the actual reviewed Q1."""
import json
import pytest
import pandas as pd
import run_all
from math_modeling.workflow import publish_q1, record_team_approval, require_q1_approval, REVIEW_FIELDS


def publish(tmp_path):
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n2\n", encoding="utf-8")
    code = tmp_path / "q1.py"
    code.write_text("# baseline model\n", encoding="utf-8")
    basis = {"model": "baseline", "assumptions": "positive", "algorithm": "sum"}
    review = {key: "baseline evidence" for key in REVIEW_FIELDS}
    publish_q1(tmp_path, "问题1：总和。\n问题2：后续。", data, {"Q1_total": 3}, basis, review, [code])
    return data, basis


def approve(tmp_path):
    evidence = tmp_path / "review.md"
    from math_modeling.workflow import q1_fingerprint
    state = json.loads((tmp_path / "output/workflow_state.json").read_text(encoding="utf-8"))
    evidence.write_text(json.dumps({"decision":"passed", "open_issues":[], "reviewer":"independent-agent", "evidence":[str(tmp_path / "q1.py")], "q1_fingerprint":q1_fingerprint(state)}), encoding="utf-8")
    record_team_approval(tmp_path, "同意", "team message 1", evidence)


def test_substantive_report_edit_invalidates_approval(tmp_path):
    data, basis = publish(tmp_path)
    approve(tmp_path)
    report = tmp_path / "output/第一问审阅报告.md"
    report.write_text("# 第一问审阅报告\n模型已变更，假设与原结论不成立。", encoding="utf-8")
    with pytest.raises(ValueError):
        require_q1_approval(tmp_path, "问题1：总和。\n问题2：后续。", data, basis)


def test_failed_independent_review_cannot_approve(tmp_path):
    publish(tmp_path)
    evidence = tmp_path / "failed_review.md"
    evidence.write_text("独立审查未通过：模型不合理，仍有未关闭问题。", encoding="utf-8")
    with pytest.raises(ValueError):
        record_team_approval(tmp_path, "同意", "team message 2", evidence)


def test_changed_prepared_data_blocks_stage2_before_solver(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data, basis = publish(tmp_path)
    pd.DataFrame({"x": [1, 2]}).to_csv(tmp_path / "results/df_clean.csv", index=False)
    approve(tmp_path)
    calls = []
    def solver(question, df, seed, qi, recorder):
        calls.append(qi)
        return {"Q2_total": int(df.x.sum())}
    def changed_prepare(df, recorder):
        return df * 100
    with pytest.raises(ValueError):
        run_all.run_pipeline("问题1：总和。\n问题2：后续。", data, {"q1_basis": basis},
                             stage="stage2", solver=solver, prepare=changed_prepare)
    assert calls == []


def test_real_stage1_approval_stage2_uses_frozen_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n2\n", encoding="utf-8")
    code = tmp_path / "q1.py"
    code.write_text("# sum baseline", encoding="utf-8")
    basis = {"model": "sum", "assumptions": "numeric", "algorithm": "addition"}
    calls = []
    def prepare(df, recorder):
        return df * 2
    def solver(question, df, seed, qi, recorder):
        calls.append(qi)
        result = {f"Q{qi}_total": int(df.x.sum())}
        if qi == 1:
            result.update(_basis=basis, _basis_files=[str(code)],
                          _review={key: "evidence" for key in REVIEW_FIELDS})
        return result
    problem = "问题1：总和。\n问题2：后续。"
    state = run_all.run_pipeline(problem, data, {}, solver=solver, prepare=prepare)
    assert state["status"] == "q1_awaiting_review" and calls == [1]
    with pytest.raises(ValueError):
        run_all.run_pipeline(problem, data, {"q1_basis": basis}, stage="stage2", solver=solver, prepare=prepare)
    assert calls == [1]
    approve(tmp_path)
    before = (tmp_path / "results/df_clean.csv").read_bytes()
    def forbidden_prepare(df, recorder):
        raise AssertionError("stage2 must not prepare again")
    state = run_all.run_pipeline(problem, data, {"q1_basis": basis}, stage="stage2", solver=solver, prepare=forbidden_prepare)
    assert calls == [1, 2] and state["status"] == "final_awaiting_review"
    assert (tmp_path / "results/df_clean.csv").read_bytes() == before
    assert json.loads((tmp_path / "results/results.json").read_text()) == {"Q1_total": 6, "Q2_total": 6}


@pytest.mark.parametrize("changed", ["result", "review", "seed", "report", "basis", "raw_data"])
def test_approved_snapshot_changes_require_rereview(tmp_path, changed):
    data, basis = publish(tmp_path)
    approve(tmp_path)
    seed = 42
    if changed == "result":
        (tmp_path / "results/q1_results.json").write_text('{"Q1_total":99}', encoding="utf-8")
    elif changed == "review":
        (tmp_path / "review.md").write_text("changed review", encoding="utf-8")
    elif changed == "seed":
        seed = 43
    elif changed == "report":
        path = tmp_path / "output/第一问审阅报告.md"
        path.write_text(path.read_text(encoding="utf-8") + "模型改用另一种假设", encoding="utf-8")
    elif changed == "basis":
        basis = dict(basis, model="changed")
    else:
        data.write_text("x\n99\n", encoding="utf-8")
    with pytest.raises(ValueError):
        require_q1_approval(tmp_path, "问题1：总和。\n问题2：后续。", data, basis, seed=seed)


def test_blank_line_layout_keeps_approval(tmp_path):
    data, basis = publish(tmp_path)
    approve(tmp_path)
    report = tmp_path / "output/第一问审阅报告.md"
    report.write_text(report.read_text(encoding="utf-8").replace("\n\n", "\n\n\n"), encoding="utf-8")
    assert require_q1_approval(tmp_path, "问题1：总和。\n问题2：后续。", data, basis)["status"] == "q1_approved"


def test_frozen_prepared_data_preserves_identifier_types(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n2\n", encoding="utf-8")
    code = tmp_path / "q1.py"
    code.write_text("# identifier-aware model", encoding="utf-8")
    basis = {"model": "identifier lookup"}
    def prepare(df, recorder):
        return pd.DataFrame({"code": ["001", "002"], "x": [1, 2]})
    def solver(question, df, seed, qi, recorder):
        assert df.code.tolist() == ["001", "002"]
        result = {f"Q{qi}_total": 3}
        if qi == 1:
            result.update(_basis=basis, _basis_files=[str(code)],
                          _review={key: "evidence" for key in REVIEW_FIELDS})
        return result
    problem = "问题1：总和。\n问题2：后续。"
    run_all.run_pipeline(problem, data, {}, solver=solver, prepare=prepare)
    approve(tmp_path)
    run_all.run_pipeline(problem, data, {"q1_basis": basis}, stage="stage2", solver=solver, prepare=prepare)
