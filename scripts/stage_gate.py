#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stage_gate —— 分阶段产物门禁（第一问即可运行，不必等全文产物）。

为什么单独建一个入口（C16）
--------------------------
`gate_audit.py --project` 的 `required` 清单含 `output/paper.json` / `paper.tex` /
`final_review.json` / `workflow_state.json`，**任一缺失即早退**，因此第一问阶段根本跑不到
产物检查。本脚本把「第一问就能做的那部分」独立出来：

| 项       | q1 阶段                                                                | final 阶段            |
| -------- | ---------------------------------------------------------------------- | --------------------- |
| 依赖     | `docs/log_*.md`、`figures/`（含 manifest）、`results/q1_results.json`  | 追加 `output/process_record.md` |
| **不依赖** | 任何全文产物（paper.json / paper.tex / final_review / workflow_state） | —                     |

`gate_audit --project` 在 final 阶段会二次调用本脚本作交叉确认。

`results/q1_results.json` 的语义（同名三义，别读错）
--------------------------------------------------
- `workflow.py:70`：**Q1 的权威产物**就是 `results/q1_results.json`
- `run_all.py:429`：`results/results.json` 要到 `run_pipeline` **末尾**才写
- `workflow.py:95`：`publish_q1` 把 q1_results.json 复制进快照并**改名**为 `results.json`
所以 **q1 阶段明确读 `q1_results.json`**，`final` 阶段才读 `results.json`。

与 `workflow.py` 的边界（硬约束）
--------------------------------
本脚本**只读产物，不碰审批链**：不调用、也不 import `record_team_approval` /
`set_status` / `publish_q1`。自检用例 `never_touches_approval_chain` 实测断言
`math_modeling.workflow` 从未被加载。

三项验收的机检（升级计划 §6.1）
------------------------------
| #   | 内容                     | 做法                                                                  |
| --- | ------------------------ | --------------------------------------------------------------------- |
| ①   | 六角色日志落盘且被引用   | 6 个 `docs/log_*.md` 存在 + 六标签各 ≥1 次 + `[YYYY-MM-DD HH:MM]` ≥1 条；final 追加查 `output/process_record.md` 引用锚点 |
| ②   | 脚本独立可运行、无统计推断 | (a) 子进程**空 cwd** 跑脚本 → 断言 PNG 确实被重新写出；(b) AST；(c) 运行时守卫 |
| ③   | 作图产出与 results 一致   | 插桩运行捕获实际绘图入参 → 经 CONTRACT `data_binding` 解析回 results 逐值比对 |

用法
----
    python "<SKILL_ROOT>/scripts/stage_gate.py" --project "<赛题目录>" --stage q1
    python "<SKILL_ROOT>/scripts/stage_gate.py" --project "<赛题目录>" --stage final
    python "<SKILL_ROOT>/scripts/stage_gate.py" --self-test

退出码：0 = PASS（或仅 WARN 且未加 `--strict`）；1 = FAIL；2 = 用法错误。

诚实说明（务必连读）
-------------------
**机检只保证「有结构」，不保证「内容真实」。**
- ① 六个标签各写一行就能过机检；日志写的是不是真话，只能靠门禁3 的语义审 + 与 `results/` 交叉核对
- ② 只证明「脚本能独立跑通、没调用被禁统计函数」，不证明图画得对
- ③ 只证明「画进图里的数 = results 里的数」，**不证明这些数算得对**（归门禁2a），
  也不证明图好看（归目视检查，作图契约 §八）
本脚本是**静态/结构预检**，任何一项 PASS 都不能替代独立语义审查。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "figure_runtime_guard.py"
BINDING = ROOT / "scripts" / "check_figure_binding.py"

ROLES = ("建模手", "编程手", "论文手", "作图", "信息检索", "审查")
LOG_TAGS = ("[怎么想]", "[试了什么]", "[结果如何]", "[在哪撞墙]", "[怎么改进]", "[最终效果]")
TIMESTAMP_RE = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]")
STAGE_RESULTS = {"q1": "results/q1_results.json", "final": "results/results.json"}

# AST 统计禁令（作图契约 §六；与 validate_figures.py 同源口径）
NUMPY_STATS = {"std", "var", "percentile", "quantile", "corrcoef"}
SCIPY_OPTIMIZE = {"curve_fit", "least_squares"}
SKLEARN_METHODS = {"fit", "predict"}
EXEMPT_RE = re.compile(r"#\s*STATS-EXEMPT\s*:(?P<reason>[^\n]*)")


# ═══════════════════════ 验收 ① 六角色日志 ═══════════════════════

def check_logs(project, *, report_role=None):
    """六角色日志落盘 + 六标签齐全 + 时间戳格式。返回 (issues, detail)。"""
    issues, detail = [], {}
    for role in ROLES:
        rel = "docs/log_%s.md" % role
        path = project / rel
        if not path.is_file():
            issues.append("缺日志文件：%s" % rel)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        missing = [tag for tag in LOG_TAGS if tag not in text]
        stamps = len(TIMESTAMP_RE.findall(text))
        detail[rel] = {"bytes": len(text.encode("utf-8")), "missing_tags": missing,
                       "timestamps": stamps}
        if missing:
            issues.append("%s 缺六步链标签：%s" % (rel, " ".join(missing)))
        if not stamps:
            issues.append("%s 缺 `[YYYY-MM-DD HH:MM]` 格式时间戳" % rel)
    if report_role is not None:
        record = project / "output/process_record.md"
        if not record.is_file():
            issues.append("final 阶段缺 output/process_record.md（无法核对六角色日志被引用）")
        else:
            text = record.read_text(encoding="utf-8", errors="replace")
            for role in ROLES:
                anchor = "log_%s.md" % role
                if anchor not in text:
                    issues.append("process_record.md 未引用 %s 角色日志（锚点 %s 缺席）"
                                  % (role, anchor))
    return issues, detail


# ═══════════════════════ manifest 与路径解析 ═══════════════════════

def load_manifest(project):
    """读 figures/figures_manifest.json；返回 (figures, issues)。"""
    path = project / "figures" / "figures_manifest.json"
    if not path.is_file():
        return [], ["缺 figures/figures_manifest.json（图契约未登记）"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], ["figures_manifest.json 解析失败（需 UTF-8）：%s" % exc]
    if not isinstance(data, list) or not data:
        return [], ["figures_manifest.json 必须是非空列表"]
    return data, []


def _norm(path_like):
    """manifest 路径归一化（C5：一律正斜杠；反斜杠视为不规范但仍解析）。

    **绝对路径返回空串 → 调用方按「字段无效」处理**，而不是悄悄改写成相对路径：
    悄悄 lstrip 会把 `C:/x/y.py` 变成 `C:/x/y.py` 之外的东西，或把 `/etc/passwd`
    洗成 `etc/passwd` 而看起来合法——那会让「本机绝对路径」这条红线失去抓手。
    """
    raw = str(path_like or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return ""
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def resolve_script(project, figure):
    """解析脚本路径：**先分层**（figures/scripts/…）→ **再扁平**（figures/…）→ 两处都没有 = FAIL。

    这正是 C5「放错目录必须被抓到」的判定顺序：兼容扁平只为不打断既有 demo，
    不得因为兼容扁平面放过「放错目录」。
    """
    raw = _norm(figure.get("script"))
    if not raw:
        return None, ("script 字段为空或为绝对路径（manifest 内路径必须相对项目根，"
                      "见作图契约 §二）：%r" % figure.get("script"))
    candidates = []
    if raw.startswith("figures/"):
        candidates.append(project / raw)
        rest = raw[len("figures/"):]
        candidates += [project / "figures/scripts" / rest, project / "figures" / rest]
    else:
        candidates.append(project / "figures/scripts" / Path(raw).name)
        candidates.append(project / "figures" / Path(raw).name)
    layered = [c for c in candidates if "scripts" in c.parts]
    flat = [c for c in candidates if "scripts" not in c.parts]
    for group, label in ((layered, "分层"), (flat, "扁平")):
        for path in group:
            if path.is_file():
                return path, None
    return None, "脚本不存在（分层 figures/scripts/ 与扁平 figures/ 两处都没有）：%s" % raw


def resolve_data_entrypoint(project, figure):
    raw = _norm(figure.get("data_entrypoint"))
    if not raw:
        return None
    for path in (project / raw, project / "figures/data" / Path(raw).name,
                 project / "figures" / Path(raw).name):
        if path.is_file():
            return path
    return None


def resolve_png(project, figure):
    """`file` 相对 figures/（C5 语义写死）。"""
    raw = _norm(figure.get("file"))
    if raw:
        path = project / "figures" / raw
        return path if path.is_file() else None
    no = figure.get("no")
    if no:
        path = project / "figures" / ("%s.png" % no)
        return path if path.is_file() else None
    return None


# ═══════════════════════ 验收 ②(b) 静态 AST ═══════════════════════

def _dotted(node):
    """把 Attribute/Name 链还原成点号名（np.std / scipy.stats.ttest_ind）。"""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def find_stats_calls(source):
    """返回源码中命中统计禁令的调用名列表（AST，降概率用；真判据在运行时守卫）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        if not name:
            continue
        tail = name.rsplit(".", 1)[-1]
        if name.startswith("scipy.stats.") or name.startswith("stats."):
            hits.append(name)
        elif tail in NUMPY_STATS and ("np." in name or "numpy." in name or "." not in name):
            hits.append(name)
        elif name.startswith("scipy.optimize.") and tail in SCIPY_OPTIMIZE:
            hits.append(name)
        elif tail in SKLEARN_METHODS and re.search(r"(?:clf|model|reg|estimator|scaler|tree|net|svm|knn)", name, re.I):
            hits.append(name)
    return sorted(set(hits))


def contract_literal(source):
    """AST 字面量解析 CONTRACT（不执行脚本）。返回 (contract|None, error|None)。"""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, "语法错误：%s" % exc
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "CONTRACT" for t in node.targets):
            try:
                return ast.literal_eval(node.value), None
            except (ValueError, SyntaxError) as exc:
                return None, "CONTRACT 必须可 literal_eval：%s" % exc
    return None, "脚本内缺 CONTRACT 元数据块（作图契约 §四）"


def exemption_level(source, contract):
    """豁免判定（作图契约 §六）：**空理由 FAIL，非空理由降 WARN**。

    非空理由须**两处都在**——脚本注释 `# STATS-EXEMPT: <非空理由>` +
    CONTRACT 的 `statistical_exempt` 非空。只有一侧不构成豁免（防随手补一行注释）。
    """
    comments = list(EXEMPT_RE.finditer(source))
    nonempty = [m.group("reason").strip() for m in comments if m.group("reason").strip()]
    has_empty = any(not m.group("reason").strip() for m in comments)
    exempt = contract.get("statistical_exempt") if isinstance(contract, dict) else None
    if isinstance(exempt, str):
        contract_reasons = [exempt.strip()] if exempt.strip() else []
    elif isinstance(exempt, (list, tuple)):
        contract_reasons = [str(x).strip() for x in exempt if str(x).strip()]
    else:
        contract_reasons = []
    if nonempty and contract_reasons:
        return "WARN"
    return "FAIL"


def check_stats_ast(script, source):
    """返回 (level, detail)：PASS / WARN（有效豁免）/ FAIL。"""
    contract, _ = contract_literal(source)
    hits = find_stats_calls(source) or []
    if not hits:
        return "PASS", {"hits": []}
    level = exemption_level(source, contract)
    return level, {"hits": hits,
                   "exempt_reason": [m.group("reason").strip() for m in EXEMPT_RE.finditer(source)
                                     if m.group("reason").strip()]}


# ═══════════════════════ 子进程执行（②(a) 与 ③） ═══════════════════════

def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), env.get("PYTHONPATH", "")))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_isolated(script, scratch, timeout):
    """在**空 cwd**（临时目录）里跑脚本，断言产出 PNG 确实被重新写出。"""
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    result = {"command": [sys.executable, "-B", str(script)], "cwd_empty": True}
    try:
        proc = subprocess.run(result["command"], cwd=str(scratch), env=_env(),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
        result["exit_code"] = proc.returncode
        result["stdout_tail"] = (proc.stdout or "")[-400:]
        result["stderr_tail"] = (proc.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        result["exit_code"] = None
        result["stderr_tail"] = "超时 %ss" % timeout
    except OSError as exc:
        result["exit_code"] = None
        result["stderr_tail"] = "无法启动子进程：%s" % exc
    return result


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_independence(project, figure, scratch, timeout):
    """②(a)：空 cwd 跑脚本 → PNG 被重新写出。返回 (level, detail)。"""
    script, err = resolve_script(project, figure)
    if script is None:
        return "FAIL", {"error": err}
    targets = _png_targets(project, figure)
    before = [_digest(p) for p in targets if p.is_file()]
    run = run_isolated(script, scratch, timeout)
    after_exists = [p.is_file() for p in targets]
    after = [_digest(p) for p in targets if p.is_file()]
    changed = [a != b for a, b in zip(after, before)] if len(after) == len(before) else None
    ok = run.get("exit_code") == 0 and all(after_exists)
    # 哈希相同不算失败（脚本可能是确定性的），但必须在报告里如实区分「重跑写出」与「沿用旧文件」
    detail = {"script": str(script), "exit_code": run.get("exit_code"),
              "png_exists": after_exists, "png_rewritten": changed,
              "stdout_tail": run.get("stdout_tail", ""), "stderr_tail": run.get("stderr_tail", "")}
    if not ok:
        detail["error"] = "空 cwd 独立运行未跑通或未产出 PNG（脚本须用 __file__ 相对定位）"
    return ("PASS" if ok else "FAIL"), detail


def _png_targets(project, figure):
    """`file` 优先（相对 figures/），缺失时才回落到 `{no}.png`——与 gate_audit 同口径，
    不能两个都要（否则 `file=fig01_demo.png` 的图会被 `{no}.png=fig1.png` 拖成 FAIL）。"""
    name = _norm(figure.get("file")) or ("%s.png" % figure["no"] if figure.get("no") else "")
    return [project / "figures" / name] if name else []


def check_runtime_guard(script, timeout):
    """②(c)：运行时统计守卫。"""
    if not GUARD.is_file():
        return "FAIL", {"error": "figure_runtime_guard.py 缺席：%s" % GUARD}
    try:
        proc = subprocess.run([sys.executable, "-B", str(GUARD), "--json", str(script)],
                              cwd=str(Path(script).parent), env=_env(), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
        report = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError, json.JSONDecodeError) as exc:
        return "FAIL", {"error": "运行时守卫未能给出结论：%s" % exc}
    return report.get("level", "FAIL"), {"violations": report.get("violations", []),
                                         "message": report.get("message", "")}


def check_binding(script, project, stage, strict, timeout):
    """③：插桩比对（画进图里的数 vs results）。"""
    if not BINDING.is_file():
        return "FAIL", {"error": "check_figure_binding.py 缺席：%s" % BINDING}
    command = [sys.executable, "-B", str(BINDING), "--json", "--script", str(script),
               "--project", str(project), "--stage", stage]
    if strict:
        command.append("--strict")
    try:
        proc = subprocess.run(command, cwd=str(project), env=_env(), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
        report = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError, json.JSONDecodeError) as exc:
        return "FAIL", {"error": "插桩比对未能给出结论：%s" % exc}
    return report.get("level", "FAIL"), {"issues": report.get("issues", []),
                                         "warns": report.get("warns", []),
                                         "internal_plot_calls": report.get("internal_plot_calls", [])}


# ═══════════════════════ 主检查 ═══════════════════════

def gate(project, stage="q1", *, strict=False, timeout=600, scratch=None, run_figures=True):
    project = Path(project).resolve()
    report = {"gate": "stage_gate", "stage": stage, "project": str(project),
              "machine_checks_only": True, "independent_semantic_review_required": True,
              "checks": [], "figures": [], "issues": [], "warns": [],
              "results_path": STAGE_RESULTS[stage], "level": "FAIL", "passed": False}
    if project == ROOT or ROOT in project.parents:
        report["issues"].append("SKILL_ROOT 不能当作赛题目录审计")
        return report

    def add(check_id, level, detail):
        report["checks"].append({"id": check_id, "level": level, "detail": detail})
        if level == "FAIL":
            report["issues"].append("%s: %s" % (check_id, _brief(detail)))
        elif level == "WARN":
            report["warns"].append("%s: %s" % (check_id, _brief(detail)))

    # 依赖产物
    required = ["results/%s" % Path(STAGE_RESULTS[stage]).name]
    if stage == "final":
        required.append("output/process_record.md")
    missing = [name for name in required if not (project / name).is_file()]
    add("deps", "FAIL" if missing else "PASS",
        {"required": required, "missing": missing, "results_path": STAGE_RESULTS[stage]})
    if missing:
        report["level"] = "FAIL"
        return report

    # ① 六角色日志（final 阶段追加 process_record 引用锚点）
    log_issues, log_detail = check_logs(project, report_role=("final" if stage == "final" else None))
    add("roles_logs", "FAIL" if log_issues else "PASS", {"files": log_detail,
                                                         "problems": log_issues})
    # ② 作图
    figures, manifest_issues = load_manifest(project)
    add("figure_manifest", "FAIL" if manifest_issues else "PASS",
        {"entries": len(figures), "problems": manifest_issues})
    scratch = Path(scratch or tempfile.mkdtemp(prefix="stage_gate_scratch_"))
    for figure in figures:
        row = _check_figure(project, figure, stage, strict, timeout, scratch, run_figures)
        report["figures"].append(row)
        # 逐图结论必须折进总体判定，否则画错图也能拿 PASS
        for name, result in row["checks"].items():
            if result["level"] == "FAIL":
                report["issues"].append("%s / %s: %s" % (row["no"], name, _brief(result["detail"])))
            elif result["level"] == "WARN":
                report["warns"].append("%s / %s: %s" % (row["no"], name, _brief(result["detail"])))
    if strict and report["warns"] and not report["issues"]:
        # --strict：WARN 升级为 FAIL（口径与 validate_figures.py 一致，写在报告里不靠退出码暗示）
        report["issues"].extend("--strict: " + item for item in report["warns"])
        report["strict_upgraded"] = list(report["warns"])
        report["warns"] = []
    report["level"] = ("FAIL" if report["issues"] else ("WARN" if report["warns"] else "PASS"))
    report["passed"] = report["level"] == "PASS"
    return report


def _brief(detail):
    if isinstance(detail, dict):
        for key in ("problems", "missing", "error", "issues", "violations"):
            value = detail.get(key)
            if value:
                return "; ".join(map(str, value)) if isinstance(value, list) else str(value)
        return json.dumps({k: v for k, v in detail.items() if k != "files"},
                          ensure_ascii=False)[:240]
    return str(detail)[:240]


def _check_figure(project, figure, stage, strict, timeout, scratch, run_figures):
    no = str(figure.get("no", "?"))
    # script 是 render_text 的必读字段，须在**任何** return 之前就位；
    # 否则脚本解析失败（恰是最该报诊断的时候）会让人类可读模式抛 KeyError，
    # 人工看到 traceback 而非结论。
    row = {"no": no, "title": figure.get("title", ""), "script": str(figure.get("script") or "?"),
           "checks": {}, "level": "PASS"}
    script, script_err = resolve_script(project, figure)
    if script_err:
        row["checks"]["script_path"] = {"level": "FAIL", "detail": script_err}
        row["level"] = "FAIL"
        return row
    row["script"] = str(script)
    source = script.read_text(encoding="utf-8-sig", errors="replace")

    if resolve_data_entrypoint(project, figure) is None:
        row["checks"]["data_entrypoint"] = {"level": "WARN",
                                            "detail": "数据入口 %r 不存在（扁平/分层均未找到）"
                                                      % figure.get("data_entrypoint")}

    contract, contract_err = contract_literal(source)
    if contract_err:
        row["checks"]["contract"] = {"level": "FAIL", "detail": contract_err}
    else:
        binding = (contract or {}).get("data_binding")
        level = "PASS" if isinstance(binding, dict) and binding.get("bindings") else "FAIL"
        row["checks"]["data_binding"] = {
            "level": level, "kind": (binding or {}).get("kind", "data") if isinstance(binding, dict) else None,
            "detail": "" if level == "PASS" else "data_binding/bindings 缺失（作图契约 §四 必填）"}

    level, detail = check_stats_ast(script, source)
    row["checks"]["stats_ast"] = {"level": level, "detail": detail}

    if run_figures:
        level, detail = check_independence(project, figure, scratch / ("run_%s" % no), timeout)
        row["checks"]["independent_run"] = {"level": level, "detail": detail}
        level, detail = check_runtime_guard(script, timeout)
        row["checks"]["runtime_guard"] = {"level": level, "detail": detail}
        level, detail = check_binding(script, project, stage, strict, timeout)
        row["checks"]["binding"] = {"level": level, "detail": detail}
    # PNG 落盘判定放在独立运行**之后**：脚本自己会写 PNG，跑完再判才有意义
    png = resolve_png(project, figure)
    row["checks"]["png"] = ({"level": "PASS", "detail": str(png)} if png else
                            {"level": "FAIL", "detail": "PNG 缺席：figures/%s（脚本未写出或路径不符）"
                                                        % _norm(figure.get("file"))})
    order = {"FAIL": 2, "WARN": 1, "PASS": 0}
    row["level"] = max((c["level"] for c in row["checks"].values()), key=lambda x: order[x])
    return row


def render_text(report):
    lines = ["分阶段产物门禁（stage_gate）",
             "project: %s" % report["project"],
             "stage: %s（results 来源 %s）" % (report["stage"], report["results_path"]),
             ""]
    for check in report["checks"]:
        lines.append("[%s] %s" % (check["level"], check["id"]))
    if report["figures"]:
        lines.append("")
        lines.append("逐图：")
        for row in report["figures"]:
            lines.append("  [%s] %s %s（%s）" % (row["level"], row["no"], row["title"], row["script"]))
            for name, result in row["checks"].items():
                lines.append("      [%s] %s" % (result["level"], name))
    lines.append("")
    lines.append("verdict: %s" % report["level"])
    lines.append("诚实说明：机检只保证「有结构」，不保证「内容真实」——")
    lines.append("  ① 六标签各写一行即可过机检，真实性靠门禁3 语义审 + 与 results 交叉核对；")
    lines.append("  ② 只证明脚本能独立跑通且未调用被禁统计函数，不证明图画得对；")
    lines.append("  ③ 只证明「画进图里的数 = results 里的数」，不证明数算得对，也不替代目视检查。")
    return "\n".join(lines)


# ═══════════════════════ 自检（隔离：全部写入在临时树内） ═══════════════════════

_GOOD_FIGURE = """\
# Official API: https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.bar.html
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]          # figures/scripts/x.py -> 项目根
OUT = Path(__file__).resolve().parents[1]           # -> figures/

CONTRACT = {
    "fig_id": "fig01_demo",
    "data_binding": {
        "results_path": "results/q1_results.json",
        "bindings": {"y": "Q1_基线_耗时", "yerr": "Q1_基线_耗时_std"},
    },
    "plot_calls": [{
        "method": "bar",
        "data_params": ["y"],
        "kwarg_params": ["yerr"],
        "aux_params": ["x", "color", "edgecolor", "linewidth"],
    }],
}

results = json.loads((ROOT / CONTRACT["data_binding"]["results_path"]).read_text(encoding="utf-8"))
binding = CONTRACT["data_binding"]["bindings"]
y = [results[binding["y"]][i] for i in range(3)]
yerr = [results[binding["yerr"]][i] for i in range(3)]
fig, ax = plt.subplots(figsize=(4, 3))
ax.bar([0, 1, 2], y, yerr=yerr, color="#0F4D92", edgecolor="black", linewidth=0.6)
ax.set_title("demo")
fig.tight_layout()
fig.savefig(OUT / "fig01_demo.png", dpi=300)
plt.close(fig)
"""

_BAD_STATS_FIGURE = """\
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
CONTRACT = {"fig_id": "fig02", "data_binding": {"results_path": "results/q1_results.json",
            "bindings": {"y": "Q1_基线_耗时"}},
            "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}]}
OUT = Path(__file__).resolve().parents[1]
y = list(np.std([[1, 2], [3, 4]], axis=1))
fig, ax = plt.subplots()
ax.plot([0, 1], y)
fig.savefig(OUT / "fig02_bad.png", dpi=100)
plt.close(fig)
"""

_FORGED_FIGURE = """\
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
CONTRACT = {"fig_id": "fig03", "data_binding": {"results_path": "results/q1_results.json",
            "bindings": {"y": "Q1_基线_耗时"}},
            "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}]}
OUT = Path(__file__).resolve().parents[1]
fig, ax = plt.subplots()
ax.plot([0, 1, 2], [9.9, 9.9, 9.9])     # 编的数据：与 results 不一致
fig.savefig(OUT / "fig03_forged.png", dpi=100)
plt.close(fig)
"""

_CWD_DEPENDENT_FIGURE = """\
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
CONTRACT = {"fig_id": "fig04", "data_binding": {"results_path": "results/q1_results.json",
            "bindings": {"y": "Q1_基线_耗时"}},
            "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}]}
fig, ax = plt.subplots()
ax.plot([0, 1, 2], [1, 2, 3])
fig.savefig("figures/fig04_cwd.png", dpi=100)   # 相对 cwd —— 空 cwd 下必挂
plt.close(fig)
"""

_TIMESTAMP = "[2026-09-10 09:30]"
_LOG_BODY = "\n\n".join("%s %s 示例条目：见 docs/log_*.md 格式约定。" % (_TIMESTAMP, tag)
                        for tag in LOG_TAGS)


def _seed_project(project, *, roles=ROLES, figures=None, with_record=False, log_body=None):
    (project / "docs").mkdir(parents=True, exist_ok=True)
    (project / "results").mkdir(parents=True, exist_ok=True)
    (project / "figures" / "scripts").mkdir(parents=True, exist_ok=True)
    (project / "figures" / "data").mkdir(parents=True, exist_ok=True)
    if with_record:
        (project / "output").mkdir(parents=True, exist_ok=True)
    for role in roles:
        (project / "docs" / ("log_%s.md" % role)).write_text(
            "# %s 试错日志\n\n" % role + (log_body if log_body is not None else _LOG_BODY),
            encoding="utf-8")
    results = {"Q1_基线_耗时": [1.0, 2.0, 3.0], "Q1_基线_耗时_std": [0.1, 0.2, 0.3]}
    (project / "results" / "q1_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if with_record:
        body = "\n".join("引用来源：docs/log_%s.md" % role for role in ROLES)
        (project / "output" / "process_record.md").write_text(
            "# 过程记录\n\n" + body + "\n", encoding="utf-8")
    manifest = []
    for entry in figures or []:
        (project / "figures" / "scripts" / entry["script_name"]).write_text(entry["source"],
                                                                            encoding="utf-8")
        (project / "figures" / "data" / entry["data_name"]).write_text("{}", encoding="utf-8")
        manifest.append({"no": entry["no"], "title": entry["title"], "file": entry["file"],
                         "script": "figures/scripts/%s" % entry["script_name"],
                         "data_entrypoint": "figures/data/%s" % entry["data_name"]})
    if manifest:
        (project / "figures" / "figures_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def _ordered_figure():
    return {"no": "fig1", "title": "基线耗时（演示）", "file": "fig01_demo.png",
            "script_name": "fig01_demo.py", "data_name": "fig01_demo.json",
            "source": _GOOD_FIGURE}


def self_test():
    """隔离自检：全部写入与子进程 cwd 都在临时树内。"""
    checks = []

    def case(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:240]})

    with tempfile.TemporaryDirectory(prefix="stage_gate_selftest_") as temp:
        root = Path(temp)
        scratch = root / "scratch"
        env = _env()
        real_env = os.environ
        os.environ = env
        try:
            # 1) 正例：q1 全绿
            good = root / "good"
            _seed_project(good, figures=[_ordered_figure()])
            report = gate(good, "q1", scratch=scratch / "good")
            case("q1_all_green", report["level"] == "PASS",
                 "level=%s issues=%s" % (report["level"], report["issues"]))
            # 边界：不碰审批链（用 AST 判调用，避免匹配到本文件里的字符串字面量）
            forbidden = {"record_team_approval", "set_status", "publish_q1"}
            called = {_dotted(node.func).rsplit(".", 1)[-1]
                      for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
                      if isinstance(node, ast.Call) and _dotted(node.func)}
            imports_workflow = bool(re.search(
                r"^\s*(?:from\s+math_modeling\.workflow\s+import|import\s+math_modeling\.workflow)",
                Path(__file__).read_text(encoding="utf-8"), re.M))
            case("never_touches_approval_chain",
                 not (called & forbidden) and not imports_workflow
                 and "math_modeling.workflow" not in sys.modules,
                 "未 import workflow；AST 未发现 %s 调用" % sorted(forbidden))

            # q1 阶段不依赖全文产物：无 output/ 也能给出结论、且不早退
            case("q1_does_not_need_fulltext_artifacts",
                 not (good / "output").exists() and report["level"] == "PASS"
                 and not any(token in " ".join(report["issues"])
                             for token in ("paper.json", "paper.tex", "final_review", "workflow_state")),
                 "output/ 缺席，q1 仍给 PASS 且不早退")

            # 2) 缺一个角色日志 → FAIL
            short = root / "short_roles"
            _seed_project(short, roles=ROLES[:-1], figures=[_ordered_figure()])
            report = gate(short, "q1", scratch=scratch / "short")
            case("missing_role_log_fails", report["level"] == "FAIL"
                 and any("log_审查.md" in i for i in report["issues"]), report["issues"][:1])

            # 3) 日志缺标签 / 缺时间戳 → FAIL
            for label, body in (("missing_tag", _LOG_BODY.replace("[最终效果]", "")),
                                ("missing_timestamp", _LOG_BODY.replace(_TIMESTAMP, "今天"))):
                path = root / ("log_%s" % label)
                _seed_project(path, figures=[_ordered_figure()], log_body=body)
                report = gate(path, "q1", scratch=scratch / label)
                case("log_%s_fails" % label, report["level"] == "FAIL",
                     [i for i in report["issues"] if "log_" in i][:1])

            # 4) ②(a) 空 cwd 独立运行：用 cwd 相对路径存图的脚本必须挂
            cwd_dep = root / "cwd_dep"
            entry = _ordered_figure()
            entry.update(no="fig4", file="fig04_cwd.png", script_name="fig04_cwd.py",
                         data_name="fig04_cwd.json", source=_CWD_DEPENDENT_FIGURE)
            _seed_project(cwd_dep, figures=[entry])
            report = gate(cwd_dep, "q1", scratch=scratch / "cwd_dep")
            case("cwd_dependent_script_fails", report["level"] == "FAIL",
                 [i for i in report["issues"] if "independent_run" in i][:1])

            # 5) ②(b) AST + ②(c) 运行时守卫：写 np.std
            bad = root / "bad_stats"
            entry = _ordered_figure()
            entry.update(no="fig2", file="fig02_bad.png", script_name="fig02_bad.py",
                         data_name="fig02_bad.json", source=_BAD_STATS_FIGURE)
            _seed_project(bad, figures=[entry])
            report = gate(bad, "q1", scratch=scratch / "bad_stats")
            row = report["figures"][0]["checks"]
            case("stats_ast_fails", row.get("stats_ast", {}).get("level") == "FAIL",
                 row.get("stats_ast", {}).get("detail"))
            case("runtime_guard_fails", row.get("runtime_guard", {}).get("level") == "FAIL",
                 row.get("runtime_guard", {}).get("detail", {}).get("violations"))

            # 6) ③ 伪造数据（画的是 9.9，results 是 1/2/3）→ FAIL
            forged = root / "forged"
            entry = _ordered_figure()
            entry.update(no="fig3", file="fig03_forged.png", script_name="fig03_forged.py",
                         data_name="fig03_forged.json", source=_FORGED_FIGURE)
            _seed_project(forged, figures=[entry])
            report = gate(forged, "q1", scratch=scratch / "forged")
            row = report["figures"][0]["checks"]
            case("forged_painted_values_fail", row.get("binding", {}).get("level") == "FAIL",
                 row.get("binding", {}).get("detail", {}).get("issues", [])[:1])

            # 7) 放错目录（脚本既不在分层也不在扁平）→ FAIL
            misplaced = root / "misplaced"
            _seed_project(misplaced, figures=[_ordered_figure()])
            (misplaced / "figures" / "scripts" / "fig01_demo.py").unlink()
            report = gate(misplaced, "q1", scratch=scratch / "misplaced")
            case("misplaced_script_fails", report["level"] == "FAIL"
                 and any("script_path" in i or "脚本不存在" in i for i in report["issues"]),
                 report["issues"][:1])

            # 7b) manifest 路径分隔符归一化与绝对路径拒绝（出口条件 7 的非 Windows 面）
            sep = root / "sep_case"
            _seed_project(sep, figures=[_ordered_figure()])
            mpath = sep / "figures" / "figures_manifest.json"
            manifest = json.loads(mpath.read_text(encoding="utf-8"))
            manifest[0]["script"] = manifest[0]["script"].replace("/", "\\")  # 反斜杠仍须解析
            mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            report = gate(sep, "q1", scratch=scratch / "sep")
            case("backslash_path_still_resolves",
                 "script_path" not in report["figures"][0]["checks"],
                 report["figures"][0]["checks"].get("script_path"))
            manifest[0]["script"] = "C:\\contest\\figures\\scripts\\fig01_demo.py"
            mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            report = gate(sep, "q1", scratch=scratch / "sep2")
            case("absolute_manifest_path_fails",
                 report["figures"][0]["checks"].get("script_path", {}).get("level") == "FAIL",
                 report["figures"][0]["checks"].get("script_path", {}).get("detail"))
            # 归一化函数本身：绝对路径返回空串，反斜杠相对路径转正斜杠
            case("norm_rejects_absolute_and_normalizes",
                 _norm("C:\\a\\b.py") == "" and _norm("/etc/x.py") == ""
                 and _norm("figures\\scripts\\x.py") == "figures/scripts/x.py"
                 and _norm("./figures/x.py") == "figures/x.py",
                 "绝对→'', 反斜杠→正斜杠, './'→去前缀")

            # 8) ② 声明与实际绘图路径不符 / 契约缺失
            no_contract = root / "no_contract"
            entry = _ordered_figure()
            entry.update(no="fig5", file="fig05.png", script_name="fig05_nc.py",
                         data_name="fig05.json",
                         source="from pathlib import Path\nimport matplotlib\n"
                                "matplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
                                "OUT = Path(__file__).resolve().parents[1]\n"
                                "fig, ax = plt.subplots()\nax.plot([0, 1], [1, 2])\n"
                                "fig.savefig(OUT / 'fig05.png', dpi=100)\n")
            _seed_project(no_contract, figures=[entry])
            report = gate(no_contract, "q1", scratch=scratch / "no_contract")
            case("missing_contract_fails",
                 report["figures"][0]["checks"].get("contract", {}).get("level") == "FAIL",
                 report["figures"][0]["checks"].get("contract", {}).get("detail"))

            # 10) final 阶段：缺 process_record → FAIL；补齐引用锚点 → PASS
            final_missing = root / "final_missing"
            _seed_project(final_missing, figures=[_ordered_figure()])
            (final_missing / "results" / "results.json").write_text(
                json.dumps({"Q1_基线_耗时": [1.0, 2.0, 3.0],
                            "Q1_基线_耗时_std": [0.1, 0.2, 0.3]}, ensure_ascii=False),
                encoding="utf-8")
            report = gate(final_missing, "final", scratch=scratch / "final_missing")
            case("final_requires_process_record", report["level"] == "FAIL"
                 and any("process_record" in i for i in report["issues"]), report["issues"][:1])

            final_ok = root / "final_ok"
            _seed_project(final_ok, figures=[_ordered_figure()], with_record=True)
            (final_ok / "results" / "results.json").write_text(
                json.dumps({"Q1_基线_耗时": [1.0, 2.0, 3.0],
                            "Q1_基线_耗时_std": [0.1, 0.2, 0.3]}, ensure_ascii=False),
                encoding="utf-8")
            report = gate(final_ok, "final", scratch=scratch / "final_ok")
            case("final_with_record_passes", report["level"] == "PASS",
                 "level=%s issues=%s" % (report["level"], report["issues"]))

            # 11) 无豁免与有效豁免：空理由 FAIL，非空理由 WARN
            for label, comment in (("empty_reason", "# STATS-EXEMPT:\n"),
                                   ("valid_reason", "# STATS-EXEMPT: 1.5×IQR 截断仅稳定 y 轴\n")):
                project = root / ("exempt_%s" % label)
                entry = _ordered_figure()
                entry.update(no="fig6", file="fig06.png", script_name="fig06.py",
                             data_name="fig06.json",
                             source="from pathlib import Path\nimport numpy as np\n"
                                    "import matplotlib\nmatplotlib.use('Agg')\n"
                                    "import matplotlib.pyplot as plt\n"
                                    "CONTRACT = {'fig_id': 'f', 'statistical_exempt': %r,\n"
                                    "            'data_binding': {'results_path': "
                                    "'results/q1_results.json', 'bindings': {'y': 'Q1'}},\n"
                                    "            'plot_calls': []}\n" % (["有理由"] if "valid" in label else [])
                                    + comment
                                    + "print(np.std([1, 2, 3]))\n")
                _seed_project(project, figures=[entry])
                level, _ = check_stats_ast(project / "figures/scripts/fig06.py",
                                           (project / "figures/scripts/fig06.py").read_text(
                                               encoding="utf-8"))
                case("stats_exempt_%s" % label,
                     level == ("WARN" if "valid" in label else "FAIL"), "level=%s" % level)
        finally:
            os.environ = real_env
    ok = all(c["ok"] for c in checks)
    return ok, {"self_test_only": True, "project_verified": False, "passed": ok, "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--project", type=Path, help="赛题目录")
    parser.add_argument("--stage", choices=("q1", "final"), default="q1")
    parser.add_argument("--strict", action="store_true", help="WARN 也算不通过")
    parser.add_argument("--timeout", type=int, default=600, help="单个脚本子进程超时（秒）")
    parser.add_argument("--no-run", action="store_true", help="跳过运行类检查（只做落盘/AST）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if getattr(sys.stdout, "reconfigure", None):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.self_test:
        ok, report = self_test()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    if not args.project:
        parser.error("--project 必填，除非 --self-test")
    report = gate(args.project, args.stage, strict=args.strict, timeout=args.timeout,
                  run_figures=not args.no_run)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))
    # WARN 未加 --strict 时不算不通过；加了 --strict 时已在 gate() 内升级为 FAIL
    return 0 if report["level"] in ("PASS", "WARN") else 1


if __name__ == "__main__":
    sys.exit(main())
