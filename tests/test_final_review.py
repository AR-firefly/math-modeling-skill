"""Independent final review probes, intentionally regression-focused."""
import json
import pytest
from math_modeling.workflow import publish_q1, record_team_approval, q1_fingerprint, REVIEW_FIELDS, set_status


def test_final_status_requires_actual_stage2_evidence(tmp_path):
    data=tmp_path / "data.csv"
    data.write_text("x\n1\n",encoding="utf-8")
    code=tmp_path / "q1.py"
    code.write_text("# first question only",encoding="utf-8")
    state=publish_q1(tmp_path,"问题1：求和。\n问题2：优化。",data,{"Q1_sum":1},
        {"model":"sum"},{key:"evidence" for key in REVIEW_FIELDS},[code])
    review=tmp_path / "review.json"
    review.write_text(json.dumps({"decision":"passed","open_issues":[],"reviewer":"independent",
        "evidence":[str(code)],"q1_fingerprint":q1_fingerprint(state)}),encoding="utf-8")
    record_team_approval(tmp_path,"同意","test-only team approval",review)
    with pytest.raises(ValueError):
        set_status(tmp_path,"final_awaiting_review")


def test_artifact_reverse_numbers_and_tex_layout(tmp_path):
    import importlib.util
    from math_modeling.tex_renderer import render_tex
    root=__import__("pathlib").Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location("final_audit",root/"scripts/gate_audit.py")
    audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    (tmp_path/"results").mkdir(); (tmp_path/"output").mkdir()
    (tmp_path/"results/results.json").write_text('{"cost":25}',encoding="utf-8")
    claim={"path":"cost","text":"Cost 25 units","label":"Cost","value":25,"unit":"units","expected_unit":"units"}
    (tmp_path/"output/claims.json").write_text(json.dumps([claim]),encoding="utf-8")
    (tmp_path/"output/non_result_numbers.json").write_text(json.dumps([{"text":"[1]","kind":"citation","reason":"reference identifier"}]),encoding="utf-8")
    paper={"meta":{"title":"Title"},"abstract":["Cost 25 units [1]."],"sections":[],"references":["2026 reference"]}
    tex=render_tex(paper)
    assert audit.verify_artifact_numbers(tmp_path,paper,"Cost 25 units [1].",tex) == []
    changed=dict(paper,abstract=["Cost 25 units [1]. Extra gain 900 units."])
    issues=audit.verify_artifact_numbers(tmp_path,changed,"Cost 25 units [1]. Extra gain 900 units.",render_tex(changed))
    assert all(any(label in issue and "900" in issue for issue in issues) for label in ("JSON","DOCX","TeX"))


def test_tex_readable_preserves_math_but_removes_geometry():
    import importlib.util
    root=__import__("pathlib").Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location("tex_audit",root/"scripts/gate_audit.py")
    audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    tex=r"\geometry{left=3.18cm}\begin{document}\vspace{1em}Cost 25 units\\[4pt]\includegraphics[width=0.75\textwidth]{fig2.png}\[x=4\]\section{人工智能使用声明}\vspace{3cm}"
    text=audit.tex_readable_body(tex)
    assert "3.18" not in text and "0.75" not in text and "4pt" not in text and "fig2" not in text
    assert "25" in text and "x=4" in text
