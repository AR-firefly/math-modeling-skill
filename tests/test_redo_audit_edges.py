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


# ── v3.0 C3：manifest 状态机机检（reproduced 哈希 / verified 独立审查 / 哈希外部锚）──
def _figure_project(tmp_path, status="reproduced", **overrides):
    """构造一张图的三元组 + manifest 项，返回 (figure_dict, paths)。"""
    import json
    import sys
    from math_modeling.visualizer import figure_artifact_hash
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    for folder in ("figures/scripts", "figures/data", "references", "docs"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    criteria = tmp_path / "references/终审运行检查表.md"
    criteria.write_text("frozen criteria", encoding="utf-8")
    script = tmp_path / "figures/scripts/fig1.py"
    data = tmp_path / "figures/data/fig1.json"
    png = tmp_path / "figures/fig1.png"
    script.write_text("print(1)\n", encoding="utf-8")
    data.write_text('{"y": 1}', encoding="utf-8")
    png.write_bytes(b"\x89PNG" * 40)
    digest = figure_artifact_hash(script, png, data)
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json", "evidence_status": status,
              "artifact_hash": digest}
    figure.update(overrides)
    return figure


def test_reproduced_hash_must_match_disk(tmp_path):
    """C3：磁盘三元组变了而 manifest 未重新生成 → FAIL（状态不脱钩）。"""
    audit = audit_module()
    figure = _figure_project(tmp_path)
    assert audit.validate_figure_evidence(tmp_path, figure) == []
    (tmp_path / "figures/scripts/fig1.py").write_text("print(2)\n", encoding="utf-8")
    issues = audit.validate_figure_evidence(tmp_path, figure)
    assert any("与磁盘三元组不符" in i for i in issues), issues


def test_reproduced_demands_valid_hash(tmp_path):
    audit = audit_module()
    figure = _figure_project(tmp_path, artifact_hash="deadbeef")
    assert any("artifact_hash" in i for i in audit.validate_figure_evidence(tmp_path, figure))
    figure = _figure_project(tmp_path)
    (tmp_path / "figures/scripts/fig1.py").unlink()
    assert any("缺件" in i for i in audit.validate_figure_evidence(tmp_path, figure))


def test_verified_needs_independent_reviewer(tmp_path):
    """verified 只由审查 Agent 写：reviewer 非空且不得是作图 Agent 本人。"""
    audit = audit_module()
    figure = _figure_project(tmp_path, status="verified")
    digest = audit._sha256(tmp_path / "references/终审运行检查表.md")
    figure.update(criteria_sha256=digest, evidence_hashes={})
    assert any("reviewer" in i for i in audit.validate_figure_evidence(tmp_path, figure))
    figure.update(reviewer="作图Agent")
    assert any("本人" in i for i in audit.validate_figure_evidence(tmp_path, figure))
    figure.update(reviewer="independent-reviewer")
    issues = audit.validate_figure_evidence(tmp_path, figure)
    assert any("evidence_hashes" in i for i in issues)
    assert any("外部锚" in i for i in issues), "缺 docs/log_审查.md 外部锚必须 FAIL"


def test_verified_hash_external_anchor_and_frozen_criteria(tmp_path):
    """C3：artifact_hash 必须同时出现在审查侧 log_审查.md；criteria_sha256 须匹配冻结基线。"""
    audit = audit_module()
    figure = _figure_project(tmp_path, status="verified")
    evidence = tmp_path / "docs/fig1_review.md"
    evidence.write_text("independent observations", encoding="utf-8")
    criteria_digest = audit._sha256(tmp_path / "references/终审运行检查表.md")
    figure.update(reviewer="independent-reviewer",
                  evidence_hashes={"docs/fig1_review.md": audit._sha256(evidence)},
                  criteria_sha256=criteria_digest)
    log = tmp_path / "docs/log_审查.md"
    log.write_text("图1 独立观察：无裁切。\n", encoding="utf-8")
    issues = audit.validate_figure_evidence(tmp_path, figure, review_log_text=log.read_text(encoding="utf-8"),
                                            frozen_criteria_hash=criteria_digest)
    assert any("外部锚" in i for i in issues), "未记入审查侧 artifact_hash 必须 FAIL"
    log.write_text("图1 artifact_hash=" + figure["artifact_hash"] + "\n", encoding="utf-8")
    assert audit.validate_figure_evidence(tmp_path, figure, review_log_text=log.read_text(encoding="utf-8"),
                                          frozen_criteria_hash=criteria_digest) == []
    # 冻结基线不匹配 → FAIL（防绕过冻结标准）
    issues = audit.validate_figure_evidence(tmp_path, figure, review_log_text=log.read_text(encoding="utf-8"),
                                            frozen_criteria_hash="0" * 64)
    assert any("冻结基线" in i for i in issues), issues
    # 证据文件被改 → FAIL
    evidence.write_text("changed", encoding="utf-8")
    issues = audit.validate_figure_evidence(tmp_path, figure, review_log_text=log.read_text(encoding="utf-8"),
                                            frozen_criteria_hash=criteria_digest)
    assert any("证据哈希不符" in i for i in issues), issues


def test_unknown_evidence_status_fails(tmp_path):
    """缺省从严：未知状态不得当成通过。"""
    audit = audit_module()
    figure = _figure_project(tmp_path, status="looks_fine_to_me")
    assert any("unknown evidence_status" in i for i in audit.validate_figure_evidence(tmp_path, figure))


def test_backslash_paths_normalized_in_gate_audit(tmp_path):
    """C5：manifest 反斜杠值先归一化再解析（非 Windows 侧不误报）。"""
    audit = audit_module()
    figure = _figure_project(tmp_path, script="figures\\scripts\\fig1.py",
                             data_entrypoint="figures\\data\\fig1.json")
    assert audit.validate_figure_evidence(tmp_path, figure) == []
    assert audit.normalize_manifest_path("figures\\scripts\\fig1.py") == "figures/scripts/fig1.py"
