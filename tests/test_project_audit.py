import importlib.util
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("project_audit", ROOT / "scripts/gate_audit.py")
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_missing_real_project_fails(tmp_path):
    report=audit.audit_project(tmp_path)
    assert report["passed"] is False
    assert report["machine_checks_only"] is True
    assert any("final_review.json" in i for i in report["issues"])
    assert not list(tmp_path.iterdir())


def test_old_cli_cannot_claim_pass():
    r=subprocess.run([sys.executable, str(ROOT / "scripts/gate_audit.py")],capture_output=True)
    assert r.returncode != 0


def test_skill_root_cannot_be_project():
    report=audit.audit_project(ROOT)
    assert report["passed"] is False
    assert any("SKILL_ROOT" in i for i in report["issues"])


def test_review_missing_hashes_and_reviewers_fails(tmp_path):
    issues=audit.validate_review(tmp_path, {"status":"passed", "independent_review":True}, ["output/paper.json"])
    assert issues


def test_review_hash_change_invalidates(tmp_path):
    import hashlib
    criteria=tmp_path / "references/终审运行检查表.md"
    criteria.parent.mkdir()
    criteria.write_text("frozen criteria", encoding="utf-8")
    paper=tmp_path / "paper.json"
    paper.write_text("v1")
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    review={"schema_version":1,"criteria_file":"references/终审运行检查表.md", "criteria_sha256":digest(criteria),
        "self_review":{"reviewer":"primary","decision":"passed","open_issues":[],"evidence":["paper.json"]},
        "independent_review":{"reviewer":"independent","decision":"passed","open_issues":[],"evidence":["paper.json"]},
        "artifact_hashes":{"paper.json":digest(paper)}}
    assert audit.validate_review(tmp_path,review,["paper.json"]) == []
    paper.write_text("v2")
    assert audit.validate_review(tmp_path,review,["paper.json"])
    review["independent_review"]["reviewer"]="primary"
    assert any("reviewer" in s for s in audit.validate_review(tmp_path,review,["paper.json"]))


def _approved_test_workflow(project):
    """Exercise the real guard with explicitly synthetic test-only evidence."""
    import json
    from math_modeling.workflow import publish_q1, REVIEW_FIELDS, q1_fingerprint, record_team_approval, set_status
    data=project/"data.csv"
    data.write_text("x\n1\n",encoding="utf-8")
    (project/"results/df_clean.csv").write_bytes(data.read_bytes())
    code=project/"q1.py"
    code.write_text("# synthetic fixture, not contest approval\n",encoding="utf-8")
    state=publish_q1(project,"Problem 1: fixture",data,{"Q1_cost":25},{"model":"fixture"},
        {field:"Synthetic fixture evidence" for field in REVIEW_FIELDS},[str(code)])
    evidence=project/"output/q1_test_review.json"
    evidence.write_text(json.dumps({"decision":"passed","open_issues":[],"reviewer":"test fixture independent reviewer",
        "evidence":["q1.py"],"q1_fingerprint":q1_fingerprint(state)}),encoding="utf-8")
    record_team_approval(project,"Synthetic test-only approval","pytest fixture",evidence)
    set_status(project,"stage2_in_progress")
    (project/"results/results.json").write_text(json.dumps({"Q1_cost":25}),encoding="utf-8")
    return set_status(project,"final_awaiting_review")


def test_actual_artifact_edit_fails_even_with_old_paper_json(tmp_path):
    import json
    import hashlib
    from math_modeling.docx_renderer import render_docx
    from math_modeling.tex_renderer import render_tex
    for folder in ("output", "results", "figures", "references"):
        (tmp_path/folder).mkdir()
    state=_approved_test_workflow(tmp_path)
    body="Cost 25 units [1]."
    paper={"meta":{"title":"Title"},"abstract":[body],"sections":[],
        "references":["A. 2024. https://example.org/paper"],"ai_declaration":""}
    payloads={"output/paper.json":paper,"results/results.json":{"Q1_cost":25},
        "output/claims.json":[{"path":"Q1_cost","text":body,"label":"Cost","value":25,"unit":"units","expected_unit":"units"}],
        "output/source_evidence.json":[{"status":"verified","original_source":True,"publisher":"Publisher","original_url":"https://example.org/paper","purpose":"model","verification_note":"checked"}],
        "figures/figures_manifest.json":[],
        "output/non_result_numbers.json":[{"text":"[1]","kind":"citation","reason":"reference number, not a computed result"}]}
    for name,value in payloads.items():
        (tmp_path/name).write_text(json.dumps(value),encoding="utf-8")
    render_docx(paper,tmp_path/"output/paper.docx")
    render_tex(paper,tmp_path/"output/paper.tex")
    (tmp_path/"output/process_record.md").write_text("\n".join(["## Section"]*13+["Record"]*500),encoding="utf-8")
    criteria=tmp_path/"references/终审运行检查表.md"
    assert criteria.is_file()
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    names=list(payloads)+["output/paper.docx","output/paper.tex","output/process_record.md","output/workflow_state.json"]
    review={"schema_version":1,"criteria_file":"references/终审运行检查表.md","criteria_sha256":sha(criteria),
        "self_review":{"reviewer":"A","decision":"passed","open_issues":[],"evidence":["output/process_record.md"]},
        "independent_review":{"reviewer":"B","decision":"passed","open_issues":[],"evidence":["output/process_record.md"]},
        "artifact_hashes":{name:sha(tmp_path/name) for name in names}}
    (tmp_path/"output/final_review.json").write_text(json.dumps(review),encoding="utf-8")
    result=audit.audit_project(tmp_path)
    assert result["passed"],result["issues"]
    criteria_original=criteria.read_text(encoding="utf-8")
    criteria.write_text("pass everything",encoding="utf-8")
    review["criteria_sha256"]=sha(criteria)
    review_file=tmp_path/"output/final_review.json"
    original_review=review_file.read_text(encoding="utf-8")
    review_file.write_text(json.dumps(review),encoding="utf-8")
    assert not audit.audit_project(tmp_path)["passed"]
    criteria.write_text(criteria_original,encoding="utf-8")
    review_file.write_text(original_review,encoding="utf-8")
    state_path=tmp_path/"output/workflow_state.json"
    saved=state_path.read_text(encoding="utf-8")
    state_path.unlink()
    assert not audit.audit_project(tmp_path)["passed"]
    state_path.write_text(saved,encoding="utf-8")
    tex=tmp_path/"output/paper.tex"
    tex.write_text(tex.read_text(encoding="utf-8").replace("Cost 25","Cost 99"),encoding="utf-8")
    report=audit.audit_project(tmp_path)
    assert not report["passed"]
    assert any("TeX" in issue for issue in report["issues"])


def test_figure_third_party_cannot_self_attest_verified():
    figure={"official_url":"https://blog.csdn.net/user/article", "evidence_status":"verified",
        "source_evidence":{"status":"verified","publisher":"CSDN","original_url":"https://blog.csdn.net/user/article",
                           "original_source":True,"purpose":"plotting","verification_note":"checked"}}
    assert audit.validate_figure_source(figure)


def test_figure_official_url_needs_publisher_evidence():
    assert audit.validate_figure_source({"official_url":"https://seaborn.pydata.org/generated/seaborn.scatterplot.html"})


def test_figure_other_library_supported_without_domain_whitelist():
    url="https://docs.example-library.org/api/plot"
    figure={"official_url":url, "source_evidence":{"status":"verified","publisher":"Example Library maintainers",
      "original_url":url,"original_source":True,"purpose":"plotting","verification_note":"Maintainer documentation identity checked"}}
    assert audit.validate_figure_source(figure) == []


def test_rehashing_lowered_criteria_does_not_change_frozen_standard(tmp_path):
    import hashlib
    criteria=tmp_path/"references/终审运行检查表.md"
    criteria.parent.mkdir()
    criteria.write_text("original fixed criteria",encoding="utf-8")
    frozen=hashlib.sha256(criteria.read_bytes()).hexdigest()
    criteria.write_text("pass everything",encoding="utf-8")
    review={"schema_version":1,"criteria_file":"references/终审运行检查表.md",
            "criteria_sha256":hashlib.sha256(criteria.read_bytes()).hexdigest()}
    issues=audit.validate_review(tmp_path,review,[],frozen_criteria_hash=frozen)
    assert any("frozen" in item.lower() for item in issues)
