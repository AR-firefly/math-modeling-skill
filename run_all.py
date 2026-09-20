#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v3.0 全流程编排（seed=42 固定）：清洗 → 逐问求解 → 五样检验 → 灵敏度 → 论文 → 查重风险点 → TeX 单渲染 → 图契约 → process_record

用法：
    python run_all.py --demo                      # demo 合成数据跑通全流程（验证）
    python run_all.py <问题.txt> <数据.csv> <meta.json>   # 真实赛题（meta: {"title","school"}）

产物写当前工作目录（SKILL_ROOT 只读；真实赛题用本文件的绝对路径调用，不复制孤立入口）。
共享语料（优秀论文库）需自备，缺失不阻断运行：参考文献比对自动降级。
"""
import os
import sys
import json
import re
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(ROOT, "src")):
    sys.path.insert(0, os.path.join(ROOT, "src"))
try:
    from math_modeling import (
        ProcessRecorder, DataCleaner, Visualizer, sensitivity_scan, strategy_reason,
        build_paper_content, verify_paper_numbers, write_run_manifest, build_provenance,
        plagiarism_risk_review, render_risk_points, render_tex, validate_references,
        verify_figure_references, verify_citations,
    )
    # C7：共享语料唯一定位点（禁硬编码路径）
    from math_modeling.shared_corpus import SHARED_PAPERS_DIR
except ImportError:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from math_modeling import (
        ProcessRecorder, DataCleaner, Visualizer, sensitivity_scan, strategy_reason,
        build_paper_content, verify_paper_numbers, write_run_manifest, build_provenance,
        plagiarism_risk_review, render_risk_points, render_tex, validate_references,
        verify_figure_references, verify_citations,
    )
    from math_modeling.shared_corpus import SHARED_PAPERS_DIR

SEED = 42
np.random.seed(SEED)

# Windows 控制台默认 GBK，统一 UTF-8 输出避免中文/符号编码崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ═══════════════════ 辅助函数 ═══════════════════

def split_questions(problem_text: str) -> list:
    """按赛题"问题N/第N问/问题一/问题 N"标题切分子问，返回各子问文本列表。"""
    heading = re.compile(r"(?m)^[ \t]*(?:问题\s*([0-9一二三四五六七八九十]+)|第\s*([0-9一二三四五六七八九十]+)\s*问)(?=[：:、.．\s]|$)")
    matches = list(heading.finditer(problem_text))
    if not matches:
        raise ValueError("无法可靠识别题目标题，请明确问题1、问题2等分问")
    def number(token):
        if token.isdigit():
            return int(token)
        digits = {c: i for i, c in enumerate("零一二三四五六七八九")}
        if token == "十": return 10
        if "十" in token:
            left, right = token.split("十")
            return digits.get(left, 1) * 10 + digits.get(right, 0)
        return digits[token]
    ids = [number(m.group(1) or m.group(2)) for m in matches]
    if ids != list(range(1, len(ids) + 1)):
        raise ValueError("问题编号不连续或重复，请先确认题目划分")
    context = problem_text[:matches[0].start()].strip()
    return [((context + "\n\n") if context else "") + problem_text[m.start():matches[i+1].start() if i+1 < len(matches) else len(problem_text)].strip()
            for i, m in enumerate(matches)]



def solve_question(question, df_clean, seed, qi, rec: ProcessRecorder) -> dict:
    """按题型 dispatch 到对应算法求解（demo 用 1D 优化示例；真实赛题 AI 扩展）。
    内部记录逐问思考轨迹 + 赛题判断节。返回结果 dict（含 _algo/_param_ranges/_code_map 元键）。"""
    rec.log("赛题判断", f"Q{qi} 题型：优化（依据：最小化目标函数，demo 示例）")
    rec.log_trace(qi, "题型判断", f"Q{qi} 判断为优化类：单目标无约束最小化")
    rec.log_trace(qi, "算法尝试", "试了网格搜索：粗网格定位近似解")
    rec.log("算法取舍", f"Q{qi}：对比 网格搜索 vs bounded 标量最小化 → 弃网格搜索换精确法（全局最优 + 解析验证）")
    # demo：求 f(x) = (x - a)^2 + b 的最小值
    from scipy.optimize import minimize_scalar
    a, b = 3.0, 0.5

    def f(x):
        return (x - a) ** 2 + b

    res = minimize_scalar(f, bounds=(-10, 10), method="bounded")
    x_opt, f_opt = float(res.x), float(res.fun)
    rec.log_trace(qi, "算法取舍", f"弃网格搜索换 bounded 标量最小化：精确解 x={x_opt:.3f}, f={f_opt:.3f}")
    results = {
        "Q%d_最优x" % qi: round(x_opt, 4),
        "Q%d_最优值" % qi: round(f_opt, 4),
        "_algo": "minimize_scalar(bounded)",
        "_param_ranges": {"a": [a * 0.8, a, a * 1.2]},
        "_code_map": {"Q%d_最优值" % qi: "run_all.py:solve_question",
                      "Q%d_最优x" % qi: "run_all.py:solve_question"},
        "_uncertainties": "目标函数光滑，无局部极小风险；边界假设 ±10 需人工确认",
        "_improvements": "换 GA/SA 处理非光滑目标；多维扩展",
        "_human_checks": "确认目标函数形式与真实赛题一致；复核最优值",
    }
    return results


def run_verifications(results, qi, data, seed) -> dict:
    """Numerical evidence for the quadratic demo only, not contest validation."""
    from scipy.optimize import minimize_scalar
    a, b = 3.0, 0.5
    f = lambda x: (x - a) ** 2 + b
    coarse = np.linspace(-10, 10, 20)
    fine = np.linspace(-10, 10, 39)
    coarse_value = float(np.min(f(coarse)))
    fine_value = float(np.min(f(fine)))
    normal = minimize_scalar(f, bounds=(-10, 10), method="bounded")
    refined = minimize_scalar(f, bounds=(-10, 10), method="bounded", options={"xatol": 1e-8})
    positions = [float(minimize_scalar(lambda x: (x - value) ** 2 + b,
                 bounds=(-10, 10), method="bounded").x) for value in (2.4, 3.0, 3.6)]
    error = abs(float(results[f"Q{qi}_最优x"]) - a)
    if not normal.success or not refined.success or error >= 1e-4:
        raise ValueError("Demo numerical solver or analytic comparison failed")
    evidence = {
        "grid": {"coarse_step": float(coarse[1]-coarse[0]), "fine_step": float(fine[1]-fine[0]),
                 "coarse_objective": coarse_value, "fine_objective": fine_value,
                 "scope": "Actual grid refinement comparison; not proof of mesh independence"},
        "convergence": {"default_objective": float(normal.fun), "refined_objective": float(refined.fun),
                        "difference": abs(float(normal.fun-refined.fun))},
        "sensitivity": {"parameter_values": [2.4, 3.0, 3.6], "optimal_positions": positions},
        "error": {"analytic_optimum": a, "absolute_error": error},
        "comparison": {"coarse_objective": coarse_value, "refined_objective": float(refined.fun)},
    }
    print(f"[Q{qi}] demo diagnostics: " + json.dumps(evidence, ensure_ascii=False))
    return evidence


# 本文件的 demo 图脚本模板特征串；真实路径用它识别"图由 run_all 生成"（C6 守卫）
_DEMO_FIGURE_MARKER = "API composition: one demo metric per axis"


def audit_figure_registry(figures_dir="figures"):
    """真实路径的契约登记校验（C6）：真实运行不画图，只核验作图 Agent 的登记是否合规。

    返回 issues 列表（不阻断，列人工审核方向）：缺 manifest / 缺 data_binding /
    脚本与数据入口按双布局解析不到。
    """
    from pathlib import Path
    fig_dir = Path(figures_dir)
    manifest_path = fig_dir / "figures_manifest.json"
    if not manifest_path.is_file():
        return [f"图契约清单缺失：{manifest_path}（真实路径不代作图，须由作图 Agent 产出）"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"图契约清单解析失败：{exc}"]
    if not isinstance(manifest, list):
        return ["图契约清单必须是列表（Visualizer.save_manifest 的产物）"]
    from math_modeling.verify import resolve_figure_entry
    issues = []
    for figure in manifest:
        no = figure.get("no", "unknown")
        if not figure.get("data_binding"):
            issues.append(f"{no}: 缺 data_binding（作图契约 §四机检必填）")
        for key, default, subdir in (("script", f"{no}.py", "scripts"),
                                     ("data_entrypoint", f"{no}.json", "data")):
            if resolve_figure_entry(fig_dir, figure.get(key), default, subdir) is None:
                issues.append(f"{no}: {key} 放错目录或缺失：{figure.get(key)}")
    return issues


def detect_run_all_generated_figures(figures_dir="figures"):
    """C6 守卫：真实路径下检测图是否由 run_all 的 demo 模板生成（含模板特征串的 .py）。"""
    from pathlib import Path
    fig_dir = Path(figures_dir)
    if not fig_dir.is_dir():
        return []
    found = []
    for script in sorted(fig_dir.rglob("*.py")):
        try:
            text = script.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _DEMO_FIGURE_MARKER in text:
            found.append(str(script.relative_to(fig_dir.parent).as_posix()))
    return found


def _demo_plot_and_register_figures(results_all, out_dir="figures"):
    """Explicit demo-only charts (C6): 只在 `--demo` 调用，真实路径禁止走到这里。

Each demo metric is isolated to avoid mixing unknown units, and ships its exact
script/data. Source is the official Axes.bar API, not a claimed gallery copy.
"""
    from pathlib import Path
    import subprocess
    import matplotlib
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    viz = Visualizer(output_dir=out_dir, dpi=300)
    fig_images = {}
    for key, value in results_all.items():
        match = re.match(r"^(Q\d+)[_.](.+)$", key)
        if not match or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        qkey, metric = match.groups()
        no = f"fig{sum(len(v) for v in fig_images.values()) + 1}"
        data = out / (no + ".json")
        script = out / (no + ".py")
        data.write_text(json.dumps({"metric":metric,"value":value,"question":qkey}, ensure_ascii=False),encoding="utf-8")
        # CONTRACT（作图契约 §四）：demo 的值同样来自 results/results.json，可逐值比对；
        # demo 用扁平布局（figures/figN.py|json|png），正是双布局兼容要保住的既有形态。
        contract = json.dumps({"fig_id": no,
                               "data_binding": {"results_path": "results/results.json",
                                                "kind": "data",
                                                "data_path": str(data).replace("\\", "/"),
                                                "bindings": {"y": f"{qkey}_{metric}"}},
                               "plot_calls": [{"method": "bar", "data_params": ["x", "y"],
                                               "aux_params": ["x_labels"]}]},
                              ensure_ascii=False, indent=4)
        script.write_text("""# Official API: https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.bar.html
# API composition: one demo metric per axis; input and output next to this script.
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
CONTRACT = """ + contract + """
record = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar([record['metric']], [record['value']], color='#3675a9')
ax.set_ylabel(record['metric'] + ' (demo units)')
ax.set_title(record['question'] + ' demo: ' + record['metric'])
ax.axhline(0, color='black', linewidth=0.6)
fig.tight_layout()
fig.savefig(Path(__file__).with_suffix('.png'), dpi=300)
plt.close(fig)
""",encoding="utf-8")
        subprocess.run([sys.executable, str(script.resolve())], check=True)
        viz.register_figure(no, f"{qkey} {metric}（演示）", f"{metric}={value}；仅演示，单位未由真实题目定义", str(data),
                            script=str(script), data_entrypoint=str(data), run_command=f'python "{script}"',
                            dependencies={"matplotlib":matplotlib.__version__},
                            official_url="https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.bar.html",
                            official_api="Axes.bar", adaptation="official_api_composition",
                            changes="每指标独立轴，读本地图数据，输出300dpi PNG", reason="演示复现契约；无同量纲证据不混绘", seed=SEED,
                            data_binding={"results_path": "results/results.json", "kind": "data",
                                          "bindings": {"y": f"{qkey}_{metric}"}})
        viz.mark_reproduced(no)  # 脚本已跑通且 PNG 已落盘 → 状态机自写 reproduced（C3）
        fig_images.setdefault(qkey,[]).append({"path":str(out / (no + ".png")),"caption":f"图{no[3:]} {qkey} {metric}（演示）"})
    return viz.save_manifest(), fig_images



def paper_to_text(paper: dict) -> str:
    """把 PAPER_STRUCT dict 摊平成含全部数字的纯文本，供 verify_paper_numbers 比对。"""
    def flatten(node):
        if isinstance(node, dict):
            return "\n".join(flatten(v) for k,v in node.items() if k not in ("references", "meta", "path", "file", "script", "data_entrypoint") and not k.startswith("_"))
        if isinstance(node, (list, tuple)):
            return "\n".join(flatten(v) for v in node)
        return str(node)
    return flatten(paper)



def load_ref_papers(ref_dir, problem_code="", selected=None):
    """从共享语料目录的 {题号}/{类}/ 载入参考论文文本（.txt 优先）。

    ref_dir 由调用方传入（真实赛题路径用 `shared_corpus.SHARED_PAPERS_DIR`），不在此硬编码。
    """
    from pathlib import Path
    root = Path(ref_dir).resolve()
    if not selected:
        return {}  # No silent full-library loading or claim of reading.
    refs = {}
    for name in selected:
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError(f"参考论文路径不存在或越界: {name}")
        if problem_code and path.relative_to(root).parts[0] != problem_code:
            raise ValueError(f"所选论文与题号不符: {name}")
        text = path.read_text(encoding="utf-8")
        if "扫描版 PDF，无文字层" in text or len(text.strip()) < 100:
            raise ValueError(f"须查看扫描原页，不能把占位文字当已阅读: {name}")
        refs[str(name)] = text
    return refs



# ═══════════════════ 主编排 ═══════════════════

def validate_output_directory(project, *, demo_mode=False):
    """Reject Skill checkouts before constructing any write-capable helpers."""
    from pathlib import Path
    project = Path(project).resolve()
    skill_root = Path(__file__).resolve().parent
    if project == skill_root or skill_root in project.parents:
        raise ValueError("Skill directory is read-only; use an independent project directory")
    # Also recognize another checkout: its outputs must not become our demo target.
    for parent in (project, *project.parents):
        if (parent / "SKILL.md").is_file() and (parent / "src/math_modeling").is_dir():
            raise ValueError("Skill directory is read-only; use an independent project directory")
    if demo_mode:
        for name in ("output", "results", "figures"):
            if (project / name).exists():
                raise ValueError("Demo refuses existing artifact directories; use a fresh directory")
    return project


def _run_demo_pipeline(problem, data_path, meta, seed=42, strict_refs=False):
    """清洗 → 逐问求解 → 五样检验 → 灵敏度 → 论文 → 风险点 → TeX 单渲染 → process_record。

    strict_refs=True（真实赛题）：参考文献必须真实（占位被 validate_references 拦截）；
    strict_refs=False（demo 演示）：占位仅警告不阻断。
    """
    validate_output_directory(os.getcwd(), demo_mode=True)
    rec = ProcessRecorder()
    stage = rec.resume()  # E3 断点恢复
    # 文献借鉴节（v2.1）：记录解题阶段参考的每篇文献；真实赛题由门禁0 文献调研报告逐篇卡片填充。
    # demo 未查文献 → 诚实占位说明，不编造文献（门禁0 产物在真实赛题工作目录产出）。
    rec.log("文献借鉴", "本节记录解题阶段参考的每篇文献：来源 / 参考了它的什么（模型/算法/论证/写法）/ 怎么用到本赛题 / 用了之后效果（见 process_record规格.md §5.5）。demo 流程演示未查文献，此行为占位；真实赛题由门禁0 文献调研报告的逐篇文献卡片填充。")
    df = pd.read_csv(data_path)
    if stage in ("", "清洗前"):
        dc = DataCleaner(df)
        df_clean = dc.apply_all()[dc.best()]
        clean_reason = dc.reason()
        rec.log("数据清洗", clean_reason)
        rec.checkpoint("清洗", "求解")
        # 持久化清洗结果，供断点恢复时真实"沿用上次清洗"
        os.makedirs("results", exist_ok=True)
        df_clean.to_csv("results/df_clean.csv", index=False)
    else:
        clean_path = "results/df_clean.csv"
        if os.path.exists(clean_path):
            df_clean = pd.read_csv(clean_path)
            clean_reason = "（沿用上次清洗，来自 results/df_clean.csv）"
        else:
            dc = DataCleaner(df)
            df_clean = dc.apply_all()[dc.best()]
            clean_reason = dc.reason()
            rec.log("数据清洗", clean_reason)
            rec.checkpoint("清洗", "求解")

    results_all = {}
    code_map = {}
    for qi, q in enumerate(split_questions(problem), 1):
        results = solve_question(q, df_clean, seed, qi, rec)
        results_all.update({k: v for k, v in results.items() if not k.startswith("_")})
        code_map.update(results.get("_code_map", {}))  # 收集数值→代码出处映射
        diagnostics = run_verifications(results, qi, df_clean, seed)
        rec.log("灵敏度", json.dumps(diagnostics, ensure_ascii=False))
        rec.log("不确定点", f"Q{qi}：{results.get('_uncertainties', '暂无')}")
        rec.log("可优化方向", f"Q{qi}：{results.get('_improvements', '暂无')}")
        rec.log("人工审核方向", f"Q{qi}：{results.get('_human_checks', '暂无')}")

    os.makedirs("results", exist_ok=True)
    with open("results/results.json", "w", encoding="utf-8") as f:
        json.dump(results_all, f, ensure_ascii=False, indent=2)
    # 数值归因映射落盘（build_provenance 消费：论文数字→results 字段→代码出处）
    with open("results/_code_map.json", "w", encoding="utf-8") as f:
        json.dump(code_map, f, ensure_ascii=False, indent=2)
    import importlib.metadata as _imeta
    _deps = {}
    for _pkg in ("numpy", "pandas", "scipy", "matplotlib", "scikit-learn", "statsmodels"):
        try:
            _deps[_pkg] = _imeta.version(_pkg)
        except Exception:
            pass
    manifest = write_run_manifest("results", seed, "python run_all.py", [data_path], deps=_deps)
    rec.log("复现", f"run_manifest.json 已生成（seed={seed} + 输入 SHA-256）")

    # Per-question numerical diagnostics above include an actual parameter scan.

    # v2.1 图契约链路：画关键结果图 + 登记契约落盘（M1 修复）；图嵌入论文正文（F1-01）
    # C6：demo 兜底专用（`--demo` 才走到这里）；真实路径不画图，只做契约登记校验。
    figure_manifest, fig_images = _demo_plot_and_register_figures(results_all)
    rec.log("复现", "每图代码、数据及官方API记录：" + open(figure_manifest, encoding="utf-8").read())

    # 论文（结构化 + 数值校验阻断 + 论文参考 + 风险点）
    paper = build_paper_content("results/results.json", meta, clean_reason=clean_reason,
                                images=fig_images)
    ref_issues = validate_references(paper.get("references", []), check_doi=strict_refs)
    if strict_refs:
        assert not ref_issues, f"参考文献不合规: {ref_issues}"
    elif ref_issues:
        print(f"[warn] demo 模式：参考文献 {len(ref_issues)} 条占位未强制（正式赛题必须真实文献）")
    issues, unmatched = verify_paper_numbers("results/results.json", paper_to_text(paper), reverse=True)
    assert not issues, f"数值校验失败: issues={issues}"
    if unmatched:
        rec.log("人工审核方向",
                f"论文 {len(unmatched)} 个数字无 results 出处，需人工审核（防编造）：{', '.join(map(str, unmatched[:10]))}")
    ref_papers = load_ref_papers(SHARED_PAPERS_DIR)
    risk_points = plagiarism_risk_review(paper_to_text(paper), ref_papers)
    render_risk_points(risk_points, "output/risk_points.md")
    rec.log("论文参考与风险点",
            f"参考论文 {len(ref_papers)} 篇；风险点 {len(risk_points)} 处（最高 "
            f"{max((r['level'] for r in risk_points), default='无')}）")

    render_tex(paper, "output/paper.tex")

    # v2.1 图号引用检查（图契约清单 ↔ 正文引用 ↔ 图文件存在，双向 F1-01），issues 列入人工审核
    fig_issues = verify_figure_references(paper, figures_dir="figures")
    if fig_issues:
        rec.log("人工审核方向",
                f"图号引用 {len(fig_issues)} 处待查（图契约/编号/图文件）：{'；'.join(fig_issues[:6])}")
    else:
        # 只记中性事实，不写"通过/一致"乐观断言（防向 process_record 注入未经复核的结论，A7）
        rec.log("论文参考与风险点", "图号引用检查：0 issues")
    # v2.1.1 引用编号对应检查（正文 [N] ↔ 参考文献列表，WARN 级不阻断）
    cit_warns = verify_citations(paper_to_text(paper), paper.get("references", []))
    if cit_warns:
        rec.log("人工审核方向",
                f"参考文献引用对应 {len(cit_warns)} 处待查：{'；'.join(cit_warns)}")

    code_map = json.load(open("results/_code_map.json", encoding="utf-8")) if os.path.exists("results/_code_map.json") else {}
    rec.log("数值归因", build_provenance("results/results.json", paper_to_text(paper), code_map))
    rec.checkpoint("论文", "完成")
    rec.save()

    print("\n[run_all] 全流程完成。产物：output/paper.tex + process_record.md + risk_points.md")
    return manifest


def run_pipeline(problem, data_path, meta, seed=42, strict_refs=True, *,
                 stage="stage1", solver=None, prepare=None, demo_mode=False):
    """Real runs stop after Q1. Explicit demo is isolated from real approvals.

solver(question, dataframe, seed, qi, recorder) returns actual result fields plus
_review (REVIEW_FIELDS), _basis, _basis_files for Q1. prepare is the task-specific
cleaning callback (dataframe, recorder)->dataframe. See execution contract.
"""
    from pathlib import Path
    from math_modeling.workflow import publish_q1, require_q1_approval, set_status
    from math_modeling.frozen_data import freeze_dataframe, load_frozen_dataframe
    validate_output_directory(os.getcwd(), demo_mode=demo_mode)
    if demo_mode:
        if Path("output/workflow_state.json").exists():
            raise ValueError("请在独立演示目录运行，不能覆盖真实任务")
        return _run_demo_pipeline(problem, data_path, meta, seed, strict_refs=False)
    if solver is None or solver is solve_question:
        raise ValueError("真实任务必须提供按题实现的 solver；禁止使用演示求解器")
    if prepare is None:
        raise ValueError("真实任务必须提供按题明确的 prepare 数据处理回调")
    if stage not in ("stage1", "stage2"):
        raise ValueError("stage 必须为 stage1 或 stage2")
    skill_root = Path(__import__("math_modeling").__file__).resolve().parents[2]
    project = Path.cwd().resolve()
    if project == skill_root or skill_root in project.parents:
        raise ValueError("真实任务产物必须写入独立赛题目录，SKILL_ROOT只读")
    questions = split_questions(problem)
    if stage == "stage2":
        state = require_q1_approval(project, problem, data_path, meta.get("q1_basis"), seed=seed)
        if not state.get("frozen_hash"):
            raise ValueError("第一问缺少已冻结清洗数据证据，需重新交付")
        results_all = json.loads(Path("results/q1_results.json").read_text(encoding="utf-8"))
        set_status(project, "stage2_in_progress")
    else:
        results_all = {}
    rec = ProcessRecorder()
    rec.resume()
    try:
        df = load_frozen_dataframe("results/df_clean.json") if stage == "stage2" else prepare(pd.read_csv(data_path, **meta.get("read_csv_options", {})), rec)
    except Exception as exc:
        rec.log("不确定点", f"Data preparation failed: {type(exc).__name__}: {exc}")
        raise
    finally:
        rec.save()
    if not isinstance(df, pd.DataFrame):
        raise ValueError("prepare 必须返回实际用于求解的 DataFrame")
    Path("results").mkdir(exist_ok=True)
    if stage == "stage1":
        freeze_dataframe(df, "results/df_clean.json")
        df.to_csv("results/df_clean.csv", index=False)  # Human-readable export; JSON is authoritative.
    code_map = {}
    if stage == "stage2" and Path("results/q1_evidence.json").is_file():
        code_map.update(json.loads(Path("results/q1_evidence.json").read_text(encoding="utf-8")).get("_code_map", {}))
    selected = [(1, questions[0])] if stage == "stage1" else list(enumerate(questions, 1))[1:]
    for qi, question in selected:
        try:
            result = solver(question, df, seed, qi, rec)
        except Exception as exc:
            rec.log("不确定点", f"Q{qi} solver failed: {type(exc).__name__}: {exc}")
            raise
        finally:
            rec.save()
        if not isinstance(result, dict) or not any(not key.startswith("_") for key in result):
            raise ValueError(f"Q{qi} solver 未返回真实结果")
        public = {k: v for k, v in result.items() if not k.startswith("_")}
        if any(not re.match(rf"^Q{qi}[_.]", key) for key in public):
            raise ValueError(f"Q{qi}结果必须以 Q{qi}_ 或 Q{qi}. 标识，避免串问")
        results_all.update(public)
        code_map.update(result.get("_code_map", {}))
        Path(f"results/q{qi}_evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        rec.log("数值归因", f"Q{qi}实际结果及验证入口：results/q{qi}_evidence.json；质量需独立审查")
        rec.checkpoint(f"Q{qi}求解", "第一问审阅" if stage == "stage1" else "全文审查")
        if stage == "stage1":
            state = publish_q1(project, problem, data_path, public, result.get("_basis"),
                               result.get("_review", {}), result.get("_basis_files", []), seed=seed, question_count=len(questions))
    Path("results/results.json").write_text(json.dumps(results_all, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    Path("results/_code_map.json").write_text(json.dumps(code_map, ensure_ascii=False, indent=2), encoding="utf-8")
    import importlib.metadata
    dependencies = {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "matplotlib")}
    write_run_manifest("results", seed, f"run_pipeline(stage={stage})", [data_path, "results/df_clean.json"], deps=dependencies)
    # C6：真实路径不画图，只做契约登记校验；并检测 figures/ 是否混入 run_all 的 demo 图。
    registry_issues = audit_figure_registry("figures")
    if registry_issues:
        rec.log("人工审核方向", "图契约登记 " + str(len(registry_issues)) + " 处待查：" + "；".join(registry_issues[:6]))
    generated = detect_run_all_generated_figures("figures")
    if generated:
        warning = ("图由 run_all 演示模板生成，不得作为真实赛题产出；"
                   "真实图形须由作图 Agent 独立脚本产出：" + "、".join(generated))
        rec.log("不确定点", warning)
        print("[run_all][warn] " + warning)
    Path("output/人工待办.md").write_text("# 人工待办\n\n- 团队审阅第一问并明确是否批准。\n- 人工填写参考文献前的AI使用声明及AI工具使用详情.pdf。\n- 人工确认最终参赛提交；AI交付状态不代表已经完成上述事项。\n", encoding="utf-8")
    if stage == "stage2":
        paper = meta.get("paper")
        if paper is None:
            rec.log("人工审核方向", "后续计算完成，须由论文手生成完整paper结构及claims；骨架不是完成稿")
        else:
            from math_modeling.verify import verify_paper_numbers
            if not meta.get("claims"):
                raise ValueError("真实论文必须提供结果声明 claims 映射")
            issues, unmatched = verify_paper_numbers("results/results.json", paper_to_text(paper), reverse=True, claims=meta["claims"], non_result_numbers=meta.get("non_result_numbers"))
            if issues or unmatched:
                raise ValueError(f"结果声明待修正：{issues}; {unmatched}")
            from math_modeling.paper_generator import find_paper_placeholders
            if paper.get("_placeholder_issues") or find_paper_placeholders(paper):
                raise ValueError("论文仍有未处理占位符")
            if paper.get("ai_declaration"):
                raise ValueError("AI使用声明必须留空供团队填写")
            references = paper.get("references", [])
            if not references:
                raise ValueError("真实论文需提供实际使用的参考文献")
            issues = validate_references(references, check_doi=True, source_evidence=meta.get("source_evidence", []))
            issues += verify_citations(paper_to_text(paper), references)
            if issues:
                raise ValueError(f"引用待修正：{issues}")
            Path("output/paper.json").write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
            for filename, value in (("claims", meta["claims"]), ("source_evidence", meta.get("source_evidence", [])), ("non_result_numbers", meta.get("non_result_numbers", []))):
                Path(f"output/{filename}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            render_tex(paper, "output/paper.tex")
            references = load_ref_papers(SHARED_PAPERS_DIR, selected=meta.get("selected_papers"))
            if references:
                risk_points = plagiarism_risk_review(paper_to_text(paper), references)
                render_risk_points(risk_points, "output/risk_points.md")
                rec.log("论文参考与风险点", "比对范围：" + "、".join(references) + "；文本载入不等于全文阅读，须附页码/章节阅读证据")
            else:
                Path("output/risk_points.md").write_text("# 文本相似风险检查\n\n未进行参考论文文本比对：未提供 selected_papers。须补充匹配论文及阅读证据后完成审查；此状态不代表零风险。\n", encoding="utf-8")
                rec.log("论文参考与风险点", "未选择参考文本，风险比对未进行；全文阅读与差距对照须独立审查")
        state = set_status(project, "final_awaiting_review")
    rec.save()
    print("第一问交付，等待独立审查及团队批准。" if stage == "stage1" else "后续产物已保存，等待全文独立终审；尚非完成判定。")
    return state


def demo():
    """Run only from a fresh independent project; retain its reproducible input."""
    from pathlib import Path
    project = validate_output_directory(os.getcwd(), demo_mode=True)
    problem = "问题1：求单变量二次函数最小值。\n问题2：验证参数灵敏度。"
    data = project / "demo_input.csv"
    # Exclusive creation prevents accidental overwrite, including concurrent runs.
    with data.open("x", encoding="utf-8", newline="") as handle:
        pd.DataFrame({"x": np.linspace(-10, 10, 21)}).to_csv(handle, index=False)
    return run_pipeline(problem, data, {"title": "单变量优化演示"},
                        seed=SEED, strict_refs=False, demo_mode=True)


if __name__ == "__main__":
    import argparse
    import importlib.util
    parser = argparse.ArgumentParser(description="两阶段建模：真实求解必须显式提供项目模块")
    parser.add_argument("problem", nargs="?")
    parser.add_argument("data", nargs="?")
    parser.add_argument("meta", nargs="?")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--stage", choices=("stage1", "stage2"), default="stage1")
    parser.add_argument("--solver-module", help="项目Python文件，导出solve_question和prepare_data")
    args = parser.parse_args()
    if args.demo:
        demo()
    elif not all((args.problem, args.data, args.meta, args.solver_module)):
        parser.error("真实运行需要问题、数据、meta及--solver-module；演示请显式--demo")
    else:
        # 共享语料（优秀论文库）需自备，缺失不阻断运行：参考文献比对自动降级，
        # 并在 output/risk_points.md 写明「未进行参考论文文本比对，此状态不代表零风险」。
        # 语料供论文阶段「深度参考优秀论文」使用，与门禁0 文献先行（联网检索）无关。
        spec = importlib.util.spec_from_file_location("contest_solver", args.solver_module)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with open(args.problem, encoding="utf-8") as f:
            problem = f.read()
        with open(args.meta, encoding="utf-8") as f:
            meta = json.load(f)
        run_pipeline(problem, args.data, meta, stage=args.stage,
                     solver=module.solve_question, prepare=module.prepare_data)
