"""Regression tests for real stage gates, independent of contest mathematics."""
import json
from pathlib import Path
import pytest
import run_all


def test_background_is_context_not_an_extra_question():
    parts = run_all.split_questions("背景：运输任务。\n问题1：建立模型。\n问题2：优化路线。")
    assert len(parts) == 2
    assert "背景" in parts[0] and "问题1" in parts[0]
    assert "问题2" in parts[1]


def test_real_entry_never_uses_demo_solver(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="solver"):
        run_all.run_pipeline("问题1：求解。", str(data), {})
    assert not (tmp_path / "results/results.json").exists()


def test_q1_gate_preserves_approval_for_layout_only(tmp_path):
    from math_modeling.workflow import publish_q1, record_team_approval, require_q1_approval
    data = tmp_path / "input.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    basis = {"model": "x squared", "assumptions": ["x real"], "algorithm": "analytic"}
    review = {k: "evidence explanation" for k in ("whole_problem", "dependencies", "assumptions", "model", "algorithm", "results", "interpretation", "validation", "sensitivity", "alternatives", "uncertainties", "downstream")}
    code = tmp_path / "q1.py"
    code.write_text("x = 1\n", encoding="utf-8")
    publish_q1(tmp_path, "题面", data, {"Q1_x": 1}, basis, review, [code])
    with pytest.raises(ValueError, match="批准"):
        require_q1_approval(tmp_path, "题面", data, basis)
    evidence = tmp_path / "review.md"
    from math_modeling.workflow import q1_fingerprint
    state = json.loads((tmp_path / "output/workflow_state.json").read_text(encoding="utf-8"))
    evidence.write_text(json.dumps({"decision":"passed", "open_issues":[], "reviewer":"independent-agent", "evidence":[str(code)], "q1_fingerprint":q1_fingerprint(state)}), encoding="utf-8")
    record_team_approval(tmp_path, "团队确认第一问，可以继续", "用户本轮明确消息", evidence)
    report = tmp_path / "output/第一问审阅报告.md"
    report.write_text(report.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    require_q1_approval(tmp_path, "题面", data, basis)
    data.write_text("x\n2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="变化"):
        require_q1_approval(tmp_path, "题面", data, basis)


def test_legacy_state_and_missing_review_cannot_approve(tmp_path):
    from math_modeling.workflow import record_team_approval
    with pytest.raises(ValueError):
        record_team_approval(tmp_path, "同意", "消息", tmp_path / "missing.md")


def test_paper_text_excludes_bibliography_but_includes_table_notes():
    paper={"abstract":["结论"],"sections":[{"title":"结果","tables":[{"caption":"表A", "headers":["成本"], "rows":[["100元"]],"notes":"条件固定"}]}],"appendix":["附录说明"],"references":["不要作为正文自证[9]"]}
    body=run_all.paper_to_text(paper)
    assert "不要作为正文自证" not in body
    assert "成本" in body and "条件固定" in body and "附录说明" in body


def test_demo_figure_has_rebuild_script_and_data(tmp_path):
    manifest,_=run_all.plot_and_register_figures({"Q1.cost":100.0},str(tmp_path))
    figures=json.loads(Path(manifest).read_text(encoding="utf-8"))
    assert figures and figures[0].get("script") and figures[0].get("data_entrypoint")
    assert Path(figures[0]["script"]).is_file()
    assert Path(figures[0]["data_entrypoint"]).is_file()


def test_criteria_are_frozen_at_first_publication(tmp_path):
    from math_modeling.workflow import publish_q1, REVIEW_FIELDS
    data=tmp_path / "input.csv"; data.write_text("x\n1\n",encoding="utf-8")
    code=tmp_path / "q1.py"; code.write_text("x=1",encoding="utf-8")
    args=(tmp_path,"题面",data,{"Q1_x":1},{"model":"sum"},{k:"evidence" for k in REVIEW_FIELDS},[code])
    state=publish_q1(*args)
    assert state.get("criteria_sha256")
    criteria=tmp_path / "references/终审运行检查表.md"
    criteria.write_text("所有论文直接通过",encoding="utf-8")
    with pytest.raises(ValueError,match="标准"):
        publish_q1(*args)


def test_report_hash_does_not_erase_meaningful_unit_spacing(tmp_path):
    from math_modeling.workflow import _report_hash
    report=tmp_path/"report.md"
    report.write_text("# Model\nUnit: m s\n",encoding="utf-8")
    before=_report_hash(report)
    report.write_text("# Model\nUnit: ms\n",encoding="utf-8")
    assert _report_hash(report) != before


def test_stage2_persists_final_evidence_and_risk_scope(tmp_path, monkeypatch):
    from math_modeling.workflow import REVIEW_FIELDS, record_team_approval, q1_fingerprint
    monkeypatch.chdir(tmp_path)
    data=tmp_path/"data.csv"; data.write_text("x\n1\n2\n",encoding="utf-8")
    code=tmp_path/"q1.py"; code.write_text("# synthetic workflow fixture",encoding="utf-8")
    basis={"model":"sum"}
    def solver(question,df,seed,qi,rec):
        result={f"Q{qi}_value": float(df.x.sum() if qi==1 else df.x.mean()), "_code_map":{f"Q{qi}_value":"q1.py:synthetic_fixture"}}
        if qi==1: result.update(_basis=basis,_basis_files=[str(code)],_review={key:"Synthetic evidence" for key in REVIEW_FIELDS})
        return result
    prepare=lambda df,rec:df
    problem="问题1：求和。\n问题2：均值。"
    state=run_all.run_pipeline(problem,data,{},solver=solver,prepare=prepare)
    review=tmp_path/"review.json"
    review.write_text(json.dumps({"decision":"passed","open_issues":[],"reviewer":"test independent",
        "evidence":[str(code)],"q1_fingerprint":q1_fingerprint(state)}),encoding="utf-8")
    record_team_approval(tmp_path,"Synthetic test approval","pytest only",review)
    body="总和=3单位；均值=1.5单位，依据[1]。"
    claims=[{"path":f"Q{qi}_value","text":body,"label":label,"value":value,"unit":"单位","expected_unit":"单位"}
            for qi,label,value in ((1,"总和",3),(2,"均值",1.5))]
    meta={"q1_basis":basis,"paper":{"meta":{"title":"测试模型"},"abstract":["建立求和模型与均值模型。"],
         "sections":[{"title":"结果","paras":[body]}],"references":["A. 2024. https://example.org/paper"]},
         "claims":claims,"non_result_numbers":[{"text":"[1]","kind":"citation","reason":"test bibliography identifier"}],
         "source_evidence":[{"status":"verified","original_source":True,"publisher":"Synthetic test publisher",
             "original_url":"https://example.org/paper","purpose":"model","verification_note":"Test fixture only"}]}
    state=run_all.run_pipeline(problem,data,meta,stage="stage2",solver=solver,prepare=prepare)
    assert state["status"] == "final_awaiting_review"
    for name in ("paper.json","paper.tex","paper.docx","claims.json","source_evidence.json","non_result_numbers.json","risk_points.md"):
        assert (tmp_path/"output"/name).is_file(),name
    assert (tmp_path/"results/_code_map.json").is_file()
    assert "未进行" in (tmp_path/"output/risk_points.md").read_text(encoding="utf-8")
