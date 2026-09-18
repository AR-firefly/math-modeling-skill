import hashlib
import importlib.util
from pathlib import Path


def audit_module():
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location("redo_audit_edges",root/"scripts/gate_audit.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_independent_evidence_requires_and_preserves_hash(tmp_path):
    audit=audit_module()
    criteria=tmp_path/"references/终审运行检查表.md"
    criteria.parent.mkdir();criteria.write_text("fixed criteria",encoding="utf-8")
    paper=tmp_path/"paper.json";paper.write_text("paper",encoding="utf-8")
    evidence=tmp_path/"independent-notes.md";evidence.write_text("original findings",encoding="utf-8")
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    review={"schema_version":1,"criteria_file":"references/终审运行检查表.md","criteria_sha256":digest(criteria),
        "self_review":{"reviewer":"author","decision":"passed","open_issues":[],"evidence":["paper.json"]},
        "independent_review":{"reviewer":"reviewer","decision":"passed","open_issues":[],"evidence":["independent-notes.md"]},
        "artifact_hashes":{"paper.json":digest(paper)}}
    assert any("independent-notes.md" in issue for issue in audit.validate_review(tmp_path,review,["paper.json"]))
    review["artifact_hashes"]["independent-notes.md"]=digest(evidence)
    assert audit.validate_review(tmp_path,review,["paper.json"]) == []
    evidence.write_text("changed findings",encoding="utf-8")
    assert any("independent-notes.md" in issue for issue in audit.validate_review(tmp_path,review,["paper.json"]))


def test_tex_literal_symbols_match_readable_claims():
    audit=audit_module()
    text=audit.tex_readable_body(r"\begin{document}Cost 25 \$; \textasciitilde{}x; \textasciicircum{}2; C:\textbackslash{}data\section{人工智能使用声明}")
    assert "Cost 25 $" in text
    assert "~x" in text and "^2" in text and "C:\\data".replace("\\\\","\\") in text
