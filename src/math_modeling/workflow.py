"""Persistent Q1 handoff; records explicit external decisions, never invents approval.

This is an orchestration guard, not authentication of the user or a mathematical judge.
Only the coordinating agent records a real team response after independent review.
"""
from __future__ import annotations
import hashlib
import json
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone

REVIEW_FIELDS = ("whole_problem", "dependencies", "assumptions", "model", "algorithm",
                "results", "interpretation", "validation", "sensitivity", "alternatives",
                "uncertainties", "downstream")

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _json_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode("utf-8")).hexdigest()

def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(path)

def _state_path(project):
    return Path(project) / "output/workflow_state.json"

def _load(project):
    path = _state_path(project)
    if not path.exists():
        raise ValueError("缺少第一问状态，必须先交付并取得团队批准")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1 or state.get("mode") != "real":
        raise ValueError("旧记录或演示状态不能作为真实批准")
    return state

def publish_q1(project, problem, data_path, results, basis, review, basis_files, *, seed=42, question_count=None):
    """Publish a reviewable Q1 snapshot; every new publication requires approval.

basis contains substantive model/assumption/algorithm choices; basis_files must
contain Q1 dependencies only, not the entire evolving Q2 orchestration script.
"""
    project = Path(project).resolve()
    if not basis or not basis_files:
        raise ValueError("第一问必须记录实质模型依据及Q1相关代码/数据文件")
    criteria = project / "references/终审运行检查表.md"
    previous = _load(project) if _state_path(project).exists() else None
    if previous:
        if not criteria.is_file() or digest(criteria) != previous.get("criteria_sha256"):
            raise ValueError("冻结终审标准发生变化或旧状态缺标准，请团队复核，禁止自动降低标准")
    else:
        source = Path(__file__).resolve().parents[2] / "references/终审运行检查表.md"
        if criteria.exists() and digest(criteria) != digest(source):
            raise ValueError("项目已有不同终审标准，需先确认；不能自动覆盖")
        criteria.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, criteria)
    missing = [key for key in REVIEW_FIELDS if not review.get(key)]
    fingerprints = {}
    for file in basis_files:
        path = Path(file)
        path = path.resolve() if path.is_absolute() else (project / path).resolve()
        fingerprints[str(path)] = digest(path)
    result_path = project / "results/q1_results.json"
    _write(result_path, results)
    report = project / "output/第一问审阅报告.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    labels = dict(zip(REVIEW_FIELDS, ("全题理解", "各问依赖", "假设及成立条件", "模型与理由", "算法与实现",
                  "计算结果", "结果解释", "验证证据", "灵敏度与鲁棒性", "备选方案", "不确定性", "后续影响")))
    sections = ["# 第一问审阅报告", "状态：待独立审查及团队明确批准。"]
    for key in REVIEW_FIELDS:
        value = review.get(key, "待补充；不得认定第一问完成")
        sections += ["## " + labels[key], value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)]
    sections += ["## 结果与复现入口", "[第一问结果](../results/q1_results.json)"]
    sections += [f"- {path}" for path in fingerprints]
    report.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    state = {"schema_version": 1, "mode": "real", "status": "q1_needs_work" if missing else "q1_awaiting_review",
             "question_count": question_count or max(1, len(re.findall(r"(?m)^\s*(?:问题\s*[0-9一二三四五六七八九十]+|第\s*[0-9一二三四五六七八九十]+\s*问)", problem))),
             "problem_hash": _json_hash(problem), "data_hash": digest(data_path), "data_path": str(Path(data_path).resolve()), "seed": seed,
             "basis_hash": _json_hash(basis), "basis": basis, "basis_files": fingerprints,
             "results_hash": digest(result_path), "report_snapshot_hash": digest(report), "report_content_hash": _report_hash(report),
             "cleaned_hash": digest(project / "results/df_clean.csv") if (project / "results/df_clean.csv").exists() else None,
             "frozen_hash": digest(project / "results/df_clean.json") if (project / "results/df_clean.json").exists() else None,
             "criteria_sha256": digest(criteria), "review": review, "missing": missing, "approval": None,
             "history": (previous.get("history", []) + [{k: v for k, v in previous.items() if k != "history"}]) if previous else []}
    snapshot = project / "output/q1_snapshots" / q1_fingerprint(state)
    snapshot.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report, snapshot / "report.md")
    shutil.copyfile(result_path, snapshot / "results.json")
    _write(snapshot / "state.json", state)
    _write(_state_path(project), state)
    return state

def _report_hash(path):
    # Only normalize known presentation changes. Other edits require review.
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r"(?m)^#{1,6}[ \t]+", "", text)
    # Preserve inline spaces and indentation: m s and ms are different units.
    return _json_hash("\n".join(line.rstrip() for line in text.splitlines() if line.strip()))

def q1_fingerprint(state):
    keys = ("problem_hash", "data_hash", "basis_hash", "basis_files", "results_hash", "report_content_hash", "cleaned_hash", "frozen_hash", "seed", "criteria_sha256", "question_count")
    return _json_hash({key: state.get(key) for key in keys})

def _snapshot_changed(project, state):
    checks = dict(state["basis_files"])
    checks[str(Path(project) / "results/q1_results.json")] = state["results_hash"]
    checks[state["data_path"]] = state["data_hash"]
    checks[str(Path(project) / "references/终审运行检查表.md")] = state.get("criteria_sha256")
    if state.get("cleaned_hash"):
        checks[str(Path(project) / "results/df_clean.csv")] = state["cleaned_hash"]
    if state.get("frozen_hash"):
        checks[str(Path(project) / "results/df_clean.json")] = state["frozen_hash"]
    report = Path(project) / "output/第一问审阅报告.md"
    return (not report.is_file() or _report_hash(report) != state.get("report_content_hash")
            or any(not Path(path).is_file() or digest(path) != expected for path, expected in checks.items()))

def record_team_approval(project, statement, message_reference, independent_review):
    """Call ONLY to transcribe an actual team approval, not model-generated text."""
    state = _load(project)
    if state.get("status") != "q1_awaiting_review" or state.get("missing"):
        raise ValueError("第一问未交付完整，不能记录批准")
    review_path = Path(independent_review).resolve()
    if not statement.strip() or not message_reference.strip() or not review_path.is_file() or not review_path.read_text(encoding="utf-8").strip():
        raise ValueError("必须提供团队真实批准、消息出处与独立审查证据")
    if _snapshot_changed(project, state):
        raise ValueError("第一问交付后发生实质变化，必须重新发布审查")
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError("独立审查须为结构化JSON，不能以任意非空文本代替通过") from exc
    evidence = review.get("evidence", [])
    if (review.get("decision") != "passed" or review.get("open_issues") != []
            or not review.get("reviewer") or not isinstance(evidence, list) or not evidence
            or review.get("q1_fingerprint") != q1_fingerprint(state)):
        raise ValueError("独立审查未通过、问题未关闭或审查版本不匹配")
    evidence_hashes = {}
    for entry in evidence:
        file = Path(entry)
        file = file if file.is_absolute() else Path(project) / file
        if not file.is_file():
            raise ValueError("独立审查证据文件不存在")
        evidence_hashes[str(file.resolve())] = digest(file)
    state["approval"] = {"statement": statement, "evidence_hashes": evidence_hashes, "message_reference": message_reference,
                         "independent_review": str(review_path), "review_hash": digest(review_path),
                         "recorded_at": datetime.now(timezone.utc).isoformat()}
    state["status"] = "q1_approved"
    _write(_state_path(project), state)
    return state

def validate_current_approval(project):
    """Read-only validity check for project auditors; no state change or inference."""
    state = _load(project)
    if state.get("status") not in ("q1_approved", "stage2_in_progress", "final_awaiting_review", "ai_complete") or not state.get("approval"):
        raise ValueError("第一问尚未得到团队明确批准")
    if _snapshot_changed(project, state):
        raise ValueError("第一问实质依据/输入/结果/标准发生变化，需重新审阅批准")
    approval = state["approval"]
    checks = dict(approval.get("evidence_hashes", {}))
    if not approval.get("statement") or not approval.get("message_reference") or not checks:
        raise ValueError("第一问批准缺少真实消息出处或独立证据")
    checks[approval["independent_review"]] = approval["review_hash"]
    if any(not Path(path).is_file() or digest(path) != expected for path, expected in checks.items()):
        raise ValueError("第一问审查证据发生变化，需重新审阅批准")
    review = json.loads(Path(approval["independent_review"]).read_text(encoding="utf-8"))
    if review.get("decision") != "passed" or review.get("open_issues") != [] or review.get("q1_fingerprint") != q1_fingerprint(state):
        raise ValueError("第一问独立审查未通过或版本不匹配")
    return state

def require_q1_approval(project, problem, data_path, basis, *, seed=42):
    state = _load(project)
    try:
        validate_current_approval(project)
        if (state["problem_hash"] != _json_hash(problem) or state["data_hash"] != digest(data_path)
                or state["basis_hash"] != _json_hash(basis) or state.get("seed") != seed):
            raise ValueError("第一问题面、数据、模型或seed发生变化，需重新批准")
    except (ValueError, OSError):
        if state.get("approval"):
            state["status"] = "q1_requires_rereview"
            _write(_state_path(project), state)
        raise
    return state


def validate_stage2_outputs(project, state):
    """Check all questions have stored results before admitting the final review."""
    project = Path(project)
    final_path = project / "results/results.json"
    if not final_path.is_file():
        raise ValueError("缺少第二阶段汇总结果证据")
    results = json.loads(final_path.read_text(encoding="utf-8"))
    for qi in range(1, state.get("question_count", 1) + 1):
        evidence_path = project / ("results/q1_results.json" if qi == 1 else f"results/q{qi}_evidence.json")
        if not evidence_path.is_file():
            raise ValueError(f"Q{qi}尚未交付结果证据，不能进入全文终审")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        fields = {k: v for k, v in evidence.items() if not k.startswith("_")}
        if not fields or any(not re.match(rf"^Q{qi}[_.]", key) or key not in results or results[key] != value for key, value in fields.items()):
            raise ValueError(f"Q{qi}汇总结果与实际交付不一致")
    return results

def set_status(project, status):
    if status not in ("stage2_in_progress", "final_awaiting_review"):
        raise ValueError("自动流程不能自行标记人工批准或AI终审完成")
    state = validate_current_approval(project)
    if status == "final_awaiting_review":
        if state["status"] != "stage2_in_progress":
            raise ValueError("尚未执行第二阶段，不能直接进入全文终审")
        validate_stage2_outputs(project, state)
    state["status"] = status
    _write(_state_path(project), state)
    return state
