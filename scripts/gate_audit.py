#!/usr/bin/env python3
"""Read-only project artifact audit. Use --project DIR, or isolated --self-test.
Machine checks never replace independent semantic review or award judgment.

v3.0 增补（C3/C5/C16，见 references/作图契约.md §七）：

- **manifest 状态机机检**（`validate_figure_evidence`）：`reproduced` 必须有
  `artifact_hash = sha256(脚本 + 数据入口 + PNG)` 且与磁盘现算值一致（磁盘变了而 manifest 没
  重新生成 → FAIL）；`verified` 还须 `reviewer` 非空且不等于作图 Agent、`evidence_hashes`
  逐一可核、`criteria_sha256` 匹配冻结基线。
- **哈希外部锚**：`artifact_hash` 必须同时记入审查侧 `docs/log_审查.md`。作图 Agent 单方面
  重写 manifest 的状态或哈希 → 与审查侧记录不符 → FAIL。
- **final 阶段二次调用 `stage_gate.py`** 作交叉确认（stage_gate 只读产物，不碰审批链）。

⚠️ **诚实说明**（体例同 C3/C4）：审查 Agent 与作图 Agent 都是 AI 扮演，
「`reviewer` 非空」本身**不构成独立性的证明**。真独立性来自**证据哈希外部锚**
（审查侧独立记录 `docs/log_审查.md`）+ **`criteria_sha256` 绑定冻结基线**。
哈希能防「手改状态」，**不能防「数据编造」**——若编程手落盘的 results 本身就是编的，
哈希照样一致；后一条只能靠 `stage_gate.py` 的插桩比对（验收③：证明"画进图里的数 =
results 里的数"）与人工复核。
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 状态机四态（作图契约 §七）；缺省从严：未知状态直接 FAIL，不得当成通过。
FIGURE_STATUSES = ("incomplete", "pending_verification", "reproduced", "verified")
# 作图 Agent 的角色标识（归一化后比较：去空白/下划线/连字符 + 小写）
FIGURE_AGENT_ROLES = ("作图agent", "绘图agent", "绘制agent", "figureagent", "figureauthor")
REVIEW_LOG = "docs/log_审查.md"


def normalize_manifest_path(value):
    """manifest 内路径一律正斜杠（作图契约 §二）；反斜杠登记值在此归一化。"""
    return value.replace("\\", "/").strip() if isinstance(value, str) else value


def is_figure_agent(reviewer):
    """`reviewer` 是否就是作图 Agent 本人（防自证）。"""
    if not isinstance(reviewer, str):
        return False
    return re.sub(r"[\s_\-]", "", reviewer).lower() in FIGURE_AGENT_ROLES


def _sha256(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _project_file(project, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("Evidence path must be project-relative")
    path = (project / name).resolve()
    if project not in path.parents or not path.is_file():
        raise ValueError(f"Missing or outside-project evidence: {name}")
    return path


def _figure_artifact_paths(project, figure):
    """按契约路径语义解析图的三元组（file 相对 figures/；script/data_entrypoint 相对项目根）。"""
    paths = {}
    for key, prefix in (("script", ""), ("data_entrypoint", ""), ("file", "figures")):
        value = normalize_manifest_path(figure.get(key))
        try:
            relative = (Path(prefix) / value).as_posix() if value else ""
            paths[key] = _project_file(project, relative)
        except (ValueError, OSError):
            paths[key] = None
    return paths


def validate_figure_evidence(project, figure, *, review_log_text=None, frozen_criteria_hash=None):
    """C3 状态机机检：reproduced 的 artifact_hash、verified 的独立审查证据 + 哈希外部锚。

    诚实说明见模块 docstring：哈希外部锚 + 冻结基线能防「手改状态」，防不了「数据编造」。
    """
    import hashlib

    project = Path(project).resolve()
    issues = []
    status = figure.get("evidence_status")
    if status not in FIGURE_STATUSES:
        return [f"unknown evidence_status: {status!r}（只认 {list(FIGURE_STATUSES)}）"]
    if status in ("incomplete", "pending_verification"):
        return issues  # 未到 reproduced，无哈希可核；由"必须 verified"的总判据兜底

    paths = _figure_artifact_paths(project, figure)
    missing = [key for key, path in paths.items() if path is None]
    if missing:
        return [f"不能核验 {status}：三元组缺件 {missing}（放错目录也算缺件）"]

    from math_modeling.visualizer import figure_artifact_hash
    recomputed = figure_artifact_hash(paths["script"], paths["file"],
                                      paths["data_entrypoint"] if figure.get("data_entrypoint") else None)
    recorded = figure.get("artifact_hash")
    if not isinstance(recorded, str) or not re.fullmatch(r"[0-9a-f]{64}", recorded):
        issues.append("reproduced/verified 缺合法 artifact_hash（sha256 十六进制 64 位）")
    elif recomputed is None:
        issues.append("artifact_hash 无法核验：三元组存在不可读文件")
    elif recorded != recomputed:
        issues.append(
            "artifact_hash 与磁盘三元组不符：脚本/数据入口/PNG 已变化而 manifest 未重新生成，"
            "状态应退回 pending_verification")

    if status != "verified":
        return issues  # reproduced 只核哈希；verified 才核审查证据

    # —— verified 强校验（只由审查 Agent 写）——
    reviewer = figure.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        issues.append("verified 缺 reviewer")
    elif is_figure_agent(reviewer):
        issues.append("verified 的 reviewer 就是作图 Agent 本人，不构成独立审查")
    if isinstance(figure.get("author"), str) and figure.get("author").strip() == (
            reviewer or "").strip():
        issues.append("verified 的 reviewer 与 author 相同，不构成独立审查")

    evidence_hashes = figure.get("evidence_hashes")
    if not isinstance(evidence_hashes, dict) or not evidence_hashes:
        issues.append("verified 缺 evidence_hashes（证据文件逐一 hash）")
    else:
        for name, digest in evidence_hashes.items():
            try:
                path = _project_file(project, normalize_manifest_path(name))
                if _sha256(path) != digest:
                    issues.append(f"审查证据哈希不符或已过期：{name}")
            except (ValueError, OSError) as exc:
                issues.append(f"审查证据不可核：{exc}")

    criteria_hash = figure.get("criteria_sha256")
    if not isinstance(criteria_hash, str) or not criteria_hash:
        issues.append("verified 缺 criteria_sha256（须绑定冻结的终审标准基线）")
    else:
        criteria = project / "references/终审运行检查表.md"
        if not criteria.is_file():
            issues.append("verified 无法核验 criteria_sha256：references/终审运行检查表.md 不存在")
        elif hashlib.sha256(criteria.read_bytes()).hexdigest() != criteria_hash:
            issues.append("verified 的 criteria_sha256 与当前终审标准不符")
        elif frozen_criteria_hash is not None and criteria_hash != frozen_criteria_hash:
            issues.append("verified 的 criteria_sha256 不匹配冻结基线（冻结标准被绕过）")

    # —— 哈希外部锚：artifact_hash 同时记入审查侧 docs/log_审查.md ——
    if isinstance(recorded, str) and recorded:
        if review_log_text is None:
            issues.append(f"verified 缺哈希外部锚：{REVIEW_LOG} 不存在，无法与审查侧记录比对")
        elif recorded not in review_log_text:
            issues.append(
                f"缺哈希外部锚：artifact_hash 未出现在 {REVIEW_LOG}——作图侧单方面重写状态或哈希，"
                "与审查侧记录不符")
    return issues


def stage_gate_cross_check(project, stage="final"):
    """C16：final 阶段二次调用 stage_gate.py 作交叉确认。

    stage_gate 只读产物、不碰审批链（不调用 record_team_approval/set_status/publish_q1）。
    脚本缺失时如实报告"未执行交叉确认"，不假装已核对。

    传 `--no-run` 是刻意的：本文件对外承诺 "Read-only project artifact audit"，
    而 stage_gate 的默认 run_figures=True 会**子进程重跑绘图脚本**（在项目内重写 PNG）。
    为守住只读契约，交叉确认只覆盖落盘/AST/契约/PNG 存在性这类只读可判项；
    「空 cwd 独立跑通 / 运行时守卫 / 插桩比对」由用户按作图契约 §九 直接调 stage_gate 完成。
    """
    script = ROOT / "scripts/stage_gate.py"
    if not script.is_file():
        return ["stage_gate.py 缺失：final 阶段交叉确认未执行（不得视为通过）"]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / "src"))),
               PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--project", str(project),
             "--stage", stage, "--no-run"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"stage_gate 交叉确认无法执行：{type(exc).__name__}: {exc}"]
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip().replace("\n", " ")[-800:]
        return [f"stage_gate({stage}) 交叉确认未通过：{detail}"]
    return []


def validate_figure_source(figure):
    """Check recorded publisher evidence; independent review verifies its truth."""
    from urllib.parse import urlparse
    issues = []
    url = figure.get("official_url", "")
    evidence = figure.get("source_evidence")
    excluded = ("csdn.net", "baidu.com", "xiaohongshu.com", "zhihu.com",
                "weibo.com", "toutiao.com", "bilibili.com", "jianshu.com", "data-to-viz.com")
    for candidate in (url, evidence.get("original_url", "") if isinstance(evidence, dict) else ""):
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("https", "http") or not host:
            issues.append("Figure source must identify an original official HTTP(S) document")
        if any(host == domain or host.endswith("." + domain) for domain in excluded):
            issues.append("Excluded figure documentation source: " + host)
        if host in ("github.com", "raw.githubusercontent.com") and "AR-firefly/prompt-library" in parsed.path:
            issues.append("TRIZ exception is not plotting API documentation")
    fields = ("publisher", "original_url", "purpose", "verification_note")
    if (not isinstance(evidence, dict) or evidence.get("status") != "verified"
            or evidence.get("original_source") is not True
            or any(not isinstance(evidence.get(k), str) or not evidence[k].strip() for k in fields)):
        issues.append("Figure needs verified publisher/original-source evidence, not a domain alone")
    elif evidence["original_url"] != url:
        issues.append("Figure official URL does not match publisher evidence")
    return issues


def validate_review(project, review, artifact_names, *, frozen_criteria_hash=None):
    import hashlib
    project = Path(project).resolve()
    issues = []
    if not isinstance(review, dict) or review.get("schema_version") != 1:
        return ["Final review schema_version must be 1"]
    try:
        name = review.get("criteria_file")
        if name != "references/终审运行检查表.md":
            issues.append("Final review criteria_file must identify frozen criteria")
        criteria = _project_file(project, name)
        if frozen_criteria_hash is not None and hashlib.sha256(criteria.read_bytes()).hexdigest() != frozen_criteria_hash:
            issues.append("Final review differs from frozen criteria baseline")
        if hashlib.sha256(criteria.read_bytes()).hexdigest() != review.get("criteria_sha256"):
            issues.append("Final review criteria hash mismatch")
    except (ValueError, OSError) as exc:
        issues.append(str(exc))
    reviewers = []
    review_evidence = set()
    for role in ("self_review", "independent_review"):
        part = review.get(role)
        if not isinstance(part, dict):
            issues.append(f"Missing {role}")
            continue
        reviewer = part.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            issues.append(f"{role}: missing reviewer")
        reviewers.append(reviewer)
        if part.get("decision") != "passed" or part.get("open_issues") != []:
            issues.append(f"{role}: unresolved review")
        evidence = part.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            issues.append(f"{role}: missing evidence")
        else:
            for name in evidence:
                try:
                    _project_file(project, name)
                    review_evidence.add(name)
                except (ValueError, OSError) as exc:
                    issues.append(f"{role}: {exc}")
    if len(reviewers) == 2 and reviewers[0] == reviewers[1]:
        issues.append("Independent reviewer must differ from self reviewer")
    hashes = review.get("artifact_hashes", {})
    if not isinstance(hashes, dict):
        return issues + ["artifact_hashes must be a mapping"]
    for name in set(artifact_names) | set(hashes) | review_evidence:
        try:
            path = _project_file(project, name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != hashes.get(name):
                issues.append(f"Missing or stale review artifact hash: {name}")
        except (ValueError, OSError) as exc:
            issues.append(str(exc))
    return issues


def tex_readable_body(tex):
    """Conservative extraction for this renderer; unknown content stays visible.

    Remove preamble and known layout arguments, never arbitrary numeric commands
    or mathematical expressions. This is not a general TeX interpreter.
    """
    text = tex.split(r"\begin{document}", 1)[-1]
    text = text.split(r"\section{人工智能使用声明}", 1)[0]
    text = re.sub(r"(?<!\\)%[^\n]*", "", text)
    text = re.sub(r"\\includegraphics\*?(?:\[[^\]]*\])?\{[^}]*\}", "", text)
    text = re.sub(r"\\(?:vspace|hspace)\*?\{[^}]*\}", "", text)
    text = re.sub(r"\\\\(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"\\(?:begin|end)\{(?:table|figure|center|tabular)\}(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"\\pagenumbering\{[^}]*\}", "", text)
    text = re.sub(r"\\([_%&#{}$])", r"\1", text)
    # Decode named literal escapes emitted by tex_renderer after layout parsing.
    # Inserting a literal backslash earlier could accidentally form a TeX command.
    for escaped, literal in ((r"\textasciitilde{}", "~"), (r"\textasciicircum{}", "^"),
                             (r"\textbackslash{}", "\\")):
        text = text.replace(escaped, literal)
    return text


def verify_artifact_numbers(project, paper, tex_body, tex):
    """Verify both mapped and unclassified numbers in structured and actual text."""
    from math_modeling.verify import verify_paper_numbers
    project = Path(project)
    def flatten(node):
        if isinstance(node, dict):
            return "\n".join(flatten(value) for key, value in node.items()
                             if key not in ("references", "meta", "path") and not key.startswith("_"))
        if isinstance(node, (list, tuple)):
            return "\n".join(flatten(value) for value in node)
        return str(node)
    claims = json.loads((project / "output/claims.json").read_text(encoding="utf-8"))
    exception_path = project / "output/non_result_numbers.json"
    exceptions = json.loads(exception_path.read_text(encoding="utf-8")) if exception_path.exists() else []
    if not isinstance(exceptions, list):
        return ["non_result_numbers.json must contain a list"]
    issues = []
    bodies = (("JSON", flatten(paper)), ("TeX", tex_readable_body(tex)))
    for label, body in bodies:
        # A classification can concern a title or other text appearing only in a
        # rendered artifact. Validate it in the applicable representation.
        relevant = [entry for entry in exceptions if not isinstance(entry, dict)
                    or not isinstance(entry.get("text"), str) or entry["text"] in body]
        found, unmatched = verify_paper_numbers(project / "results/results.json", body,
            claims=claims, reverse=True, non_result_numbers=relevant)
        issues.extend(label + ": " + item for item in found)
        if unmatched:
            issues.append(f"{label}: unclassified numeric claims: {', '.join(unmatched)}")
    for entry in exceptions:
        if isinstance(entry, dict) and isinstance(entry.get("text"), str) and not any(entry["text"] in body for _, body in bodies):
            issues.append("Non-result numeric classification not found in any artifact: " + entry["text"])
    return issues


def audit_project(project):
    project = Path(project).resolve()
    issues = []
    report = {"machine_checks_only": True, "independent_semantic_review_required": True,
              "project": str(project), "passed": False, "issues": issues}
    if project == ROOT or ROOT in project.parents:
        issues.append("SKILL_ROOT cannot be audited as a contest project")
        return report
    required = ["output/paper.json", "output/paper.tex",
                "output/claims.json", "output/source_evidence.json", "output/process_record.md",
                "output/final_review.json", "results/results.json", "figures/figures_manifest.json",
                "output/workflow_state.json"]
    for name in required:
        if not (project / name).is_file():
            issues.append("Missing: " + name)
    if issues:
        return report
    try:
        def read(name):
            return json.loads((project / name).read_text(encoding="utf-8"))
        from math_modeling.workflow import validate_current_approval
        state = validate_current_approval(project)
        from math_modeling.workflow import validate_stage2_outputs
        validate_stage2_outputs(project, state)
        if state.get("status") not in ("final_awaiting_review", "ai_complete"):
            issues.append("Real project has not completed stage2 for final review")
        if not state.get("criteria_sha256"):
            issues.append("Missing frozen criteria baseline in real workflow state")
        paper = read("output/paper.json")
        claims = read("output/claims.json")
        sources = read("output/source_evidence.json")
        figures = read("figures/figures_manifest.json")
        review = read("output/final_review.json")
        if paper.get("_placeholder_issues"):
            issues.append("paper.json contains unresolved placeholders")
        if paper.get("ai_declaration", ""):
            issues.append("AI declaration must remain blank for the team")
        from math_modeling.paper_generator import find_paper_placeholders
        if find_paper_placeholders(paper):
            issues.append("Paper contains unresolved placeholder text")
        from math_modeling.paper_generator import validate_references
        from math_modeling.verify import verify_paper_numbers, verify_citations, verify_figure_references
        if not isinstance(sources, list):
            issues.append("source_evidence.json must contain a list")
            sources = []
        issues.extend(validate_references(paper.get("references", []), source_evidence=sources))
        tex = (project / "output/paper.tex").read_text(encoding="utf-8")
        declaration = re.search(r"\\section\{人工智能使用声明\}(.*?)\\section\{参考文献\}", tex, re.S)
        if not declaration or re.sub(r"\\vspace\{[^}]*\}|\s+", "", declaration.group(1)):
            issues.append("TeX declaration must be blank before references")
        # Inspect the actual rendered artifact, never synthesize prose from results.
        tex_body = tex.split(r"\section{人工智能使用声明}")[0]
        tex_body = re.sub(r"\\([_%&#{}])", r"\1", tex_body)
        if not isinstance(claims, list) or not claims:
            issues.append("Missing nonempty result claim mapping")
        else:
            issues.extend(verify_artifact_numbers(project, paper, tex_body, tex))
            issues.extend(verify_citations(tex_body, paper.get("references", [])))
        if not isinstance(figures, list):
            raise ValueError("figure manifest must be a list")
        if figures or any(section.get("images") for section in paper.get("sections", [])):
            issues.extend(verify_figure_references(paper, figures_dir=str(project / "figures")))
        hashed_artifacts = [name for name in required if name != "output/final_review.json"]
        if (project / "output/non_result_numbers.json").is_file():
            hashed_artifacts.append("output/non_result_numbers.json")
        # 哈希外部锚：审查侧 docs/log_审查.md 不存在即无法比对，如实报缺失（不作静默放过）
        review_log = project / REVIEW_LOG
        review_log_text = review_log.read_text(encoding="utf-8") if review_log.is_file() else None
        for figure in figures:
            no = figure.get("no", "unknown")
            issues.extend(f"{no}: {item}" for item in validate_figure_source(figure))
            # 必填键 11 → 12：增 data_binding（作图契约 §四，机检新增必填）
            for key in ("script", "data_entrypoint", "run_command", "dependencies", "official_url",
                        "official_api", "adaptation", "changes", "reason", "title", "conclusion",
                        "data_binding"):
                if not figure.get(key):
                    issues.append(f"{no}: missing {key}")
            for key, prefix in (("file", "figures"), ("script", ""), ("data_entrypoint", "")):
                value = normalize_manifest_path(figure.get(key))
                try:
                    relative = (Path(prefix) / value).as_posix() if isinstance(value, str) else ""
                    _project_file(project, relative)
                    hashed_artifacts.append(relative)
                except (ValueError, OSError):
                    issues.append(f"{no}: missing local {key}")
            issues.extend(f"{no}: {item}" for item in validate_figure_evidence(
                project, figure, review_log_text=review_log_text,
                frozen_criteria_hash=state.get("criteria_sha256")))
            if figure.get("evidence_status") != "verified":
                issues.append(f"{no}: reproduction and source evidence not verified")
        record = (project / "output/process_record.md").read_text(encoding="utf-8")
        if len(record.splitlines()) < 500 or len(re.findall(r"^## ", record, re.M)) < 13:
            issues.append("Process record does not meet existing 500-line / 13-section contract")
        issues.extend(validate_review(project, review, hashed_artifacts,
                                      frozen_criteria_hash=state.get("criteria_sha256")))
        # C16：final 阶段二次调用 stage_gate.py 作交叉确认（只读产物，不碰审批链）
        issues.extend(stage_gate_cross_check(project, "final"))
    except Exception as exc:
        issues.append(f"Invalid artifact: {type(exc).__name__}: {exc}")
    report["passed"] = not issues
    return report


def self_test():
    """Copy only runnable assets; all writes and child cwd stay in a temporary tree."""
    with tempfile.TemporaryDirectory(prefix="math_skill_selftest_") as temp:
        work = Path(temp) / "skill"
        work.mkdir()
        demo_project = Path(temp) / "demo-project"
        demo_project.mkdir()
        for folder in ("src", "tests", "examples", "scripts", "algorithms"):
            source = ROOT / folder
            if source.exists():
                shutil.copytree(source, work / folder, ignore=shutil.ignore_patterns("__pycache__", "results", "figures", "output", ".pytest_cache"))
        (work / "references").mkdir(exist_ok=True)
        for reference in (ROOT / "references").glob("*.md"):
            shutil.copy2(reference, work / "references" / reference.name)
        shutil.copy2(ROOT / "run_all.py", work / "run_all.py")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(work), str(work / "src"))),
                   PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1",
                   MPLCONFIGDIR=str(work / "mpl"),
                   # 子进程输出走管道；不锁 UTF-8 时中文 Windows 下以 cp936 写出，
                   # 被 encoding="utf-8" 读取后变成 U+FFFD，再 print 到 gbk 终端即崩
                   PYTHONIOENCODING="utf-8")
        commands = [[sys.executable, "-B", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                    [sys.executable, "-B", str(work / "run_all.py"), "--demo"],
                    [sys.executable, "-B", "scripts/validate_figures.py", "--self-test"],
                    # C16：命令集 7 → 8 条，stage_gate 进回归集（否则它自己无回归）
                    [sys.executable, "-B", "scripts/stage_gate.py", "--self-test"]]
        commands += [[sys.executable, "-B", str(work / "examples" / script)] for script in
                     ("main.py", "评价_TOPSIS_demo.py", "预测_GM11_demo.py", "机理_ODE_demo.py")]
        results = []
        for command in commands:
            cwd = demo_project if "--demo" in command else (work / "examples" if "examples" in str(command[-1]) else work)
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=600)
            results.append({"command": command, "exit_code": result.returncode,
                            "output": (result.stdout + result.stderr)[-2000:]})
        return {"self_test_only": True, "project_verified": False,
                "passed": all(r["exit_code"] == 0 for r in results), "checks": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", type=Path)
    group.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    # Windows 默认控制台是 GBK(cp936)。子进程输出里有替换字符(U+FFFD)时，
    # print 到 gbk stdout 会抛 UnicodeEncodeError 并以退出码 1 收场——
    # 与「检查未通过」不可区分。其余入口脚本(run_all/stage_gate/...)均有此守卫，
    # 本脚本此前漏装，在中文 Windows 默认终端下必崩。
    if getattr(sys.stdout, "reconfigure", None):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if getattr(sys.stderr, "reconfigure", None):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    result = self_test() if args.self_test else audit_project(args.project)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
