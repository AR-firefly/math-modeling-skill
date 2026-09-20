"""E / 批次 2 —— `scripts/stage_gate.py` 单测（C16；出口条件 1、3、4）。

为什么单独建这个入口（C16）：`gate_audit.py --project` 的 `required` 清单含
`paper.json` / `paper.tex` / `final_review.json` / `workflow_state.json`，**任一缺失即早退**，
所以第一问阶段根本跑不到产物检查。`stage_gate` 把「第一问就能做的那部分」独立出来。

出口条件 4：`stage_gate` 与 `gate_audit` / `workflow` 的**边界**
- q1 独立跑通不误报（无全文产物也给出结论，且**不早退**）
- final 阶段两者结论一致（`gate_audit` 二次调用 `stage_gate --no-run` 作交叉确认）
- **`stage_gate` 不触碰审批链**：不调用、也不 import
  `record_team_approval` / `set_status` / `publish_q1`（本文件用**子进程**实测，
  不受同进程其它测试已 import `workflow` 的影响）

诚实边界
--------
**机检只保证「有结构」，不保证「内容真实」。** ① 六个标签各写一行就能过机检，
真实性靠门禁3 的语义审 + 与 `results/` 交叉核对；② 只证明脚本能独立跑通且未调用被禁
统计函数，不证明图画得对；③ 只证明「画进图里的数 = results 里的数」，不证明数算得对，
也不替代目视检查（作图契约 §八）。
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SG = ROOT / "scripts/stage_gate.py"

ROLES = ("建模手", "编程手", "论文手", "作图", "信息检索", "审查")
LOG_TAGS = ("[怎么想]", "[试了什么]", "[结果如何]", "[在哪撞墙]", "[怎么改进]", "[最终效果]")
STAMP = "[2026-09-10 09:30]"
LOG_BODY = "\n\n".join("%s %s 示例条目。" % (STAMP, tag) for tag in LOG_TAGS)
RESULTS = {"Q1_基线_耗时": [1.0, 2.0, 3.0],
           "Q1_基线_耗时_std": [0.1, 0.2, 0.3],
           "Q1_改进_耗时": [0.5, 1.0, 1.5]}


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("e_stage_gate", SG)
    module = importlib.util.module_from_spec(spec)
    sys.modules["e_stage_gate"] = module
    spec.loader.exec_module(module)
    return module


GOOD_FIGURE = textwrap.dedent('''\
    # Official API: https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.bar.html
    from pathlib import Path
    import json
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ROOT = Path(__file__).resolve().parents[2]
    OUT = Path(__file__).resolve().parents[1]

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
    y = list(results[binding["y"]])
    yerr = list(results[binding["yerr"]])
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar([0, 1, 2], y, yerr=yerr, color="#0F4D92", edgecolor="black", linewidth=0.6)
    ax.set_title("demo")
    fig.tight_layout()
    fig.savefig(OUT / "fig01_demo.png", dpi=300)
    plt.close(fig)
''')

CWD_DEPENDENT_FIGURE = textwrap.dedent('''\
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CONTRACT = {"fig_id": "fig04",
                "data_binding": {"results_path": "results/q1_results.json",
                                 "bindings": {"y": "Q1_基线_耗时"}},
                "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}]}
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [1.0, 2.0, 3.0])
    fig.savefig("figures/fig04_cwd.png", dpi=100)   # 相对 cwd —— 空 cwd 下必挂
    plt.close(fig)
''')


def build_project(tmp_path, *, name="project", roles=ROLES, log_body=None, figure=GOOD_FIGURE,
                  with_record=False, with_results=True):
    """合成一个最小赛题目录（**本文件自建**，不复用被测脚本的 seeder，避免自证）。"""
    project = tmp_path / name
    (project / "docs").mkdir(parents=True)
    (project / "results").mkdir(parents=True)
    if with_record:
        (project / "output").mkdir(parents=True)
        body = "\n".join("引用来源：docs/log_%s.md" % role for role in ROLES)
        (project / "output" / "process_record.md").write_text("# 过程记录\n\n" + body + "\n",
                                                              encoding="utf-8")
    for role in roles:
        (project / "docs" / ("log_%s.md" % role)).write_text(
            "# %s 试错日志\n\n" % role + (LOG_BODY if log_body is None else log_body),
            encoding="utf-8")
    if with_results:
        (project / "results" / "q1_results.json").write_text(
            json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    if figure is not None:
        (project / "figures" / "scripts").mkdir(parents=True)
        (project / "figures" / "data").mkdir(parents=True)
        (project / "figures" / "scripts" / "fig01_demo.py").write_text(figure, encoding="utf-8")
        (project / "figures" / "data" / "fig01_demo.json").write_text("{}", encoding="utf-8")
        (project / "figures" / "fig01_demo.png").write_bytes(b"\x89PNG placeholder")
        (project / "figures" / "figures_manifest.json").write_text(json.dumps(
            [{"no": "fig1", "title": "基线耗时", "file": "fig01_demo.png",
              "script": "figures/scripts/fig01_demo.py",
              "data_entrypoint": "figures/data/fig01_demo.json"}], ensure_ascii=False, indent=2),
            encoding="utf-8")
    return project


# ══════════════ 出口条件 4：q1 阶段不依赖全文产物 ══════════════
def test_q1_requires_only_q1_artifacts(gate, tmp_path):
    """q1 的依赖清单**只**有 `results/q1_results.json`（不得混入全文产物）。"""
    project = build_project(tmp_path)
    report = gate.gate(project, "q1", run_figures=False)
    deps = next(c for c in report["checks"] if c["id"] == "deps")
    assert deps["level"] == "PASS", deps
    assert deps["detail"]["required"] == ["results/q1_results.json"], deps


def test_q1_passes_without_any_fulltext_artifact(gate, tmp_path):
    """无 `output/`（无 paper.json / paper.tex / final_review / workflow_state）仍给 PASS，
    且**不早退**——逐图检查项一个不少。"""
    project = build_project(tmp_path)
    assert not (project / "output").exists()
    report = gate.gate(project, "q1", run_figures=False)
    assert report["level"] == "PASS", report["issues"]
    assert report["figures"], "不得早退：逐图结论必须产出"
    assert len(report["checks"]) >= 3, report["checks"]


def test_q1_report_never_mentions_fulltext_artifacts(gate, tmp_path):
    """q1 报告全文不得出现全文产物字样（防"悄悄依赖又假装没依赖"）。"""
    project = build_project(tmp_path)
    report = gate.gate(project, "q1", run_figures=False)
    blob = gate.render_text(report) + json.dumps(report, ensure_ascii=False)
    for token in ("paper.json", "paper.tex", "final_review", "workflow_state"):
        assert token not in blob, "%s 不应出现在 q1 阶段" % token


def test_q1_missing_results_is_early_fail(gate, tmp_path):
    """缺 `results/q1_results.json` → FAIL 并点名该文件；不假装其余检查已做完。"""
    project = build_project(tmp_path, with_results=False)
    report = gate.gate(project, "q1", run_figures=False)
    assert report["level"] == "FAIL"
    assert any("q1_results.json" in issue for issue in report["issues"]), report["issues"]
    assert report["figures"] == [], "依赖缺失时应早退，不得产出逐图结论"


def test_results_source_differs_between_stages(gate):
    """同名三义提醒：q1 读 `q1_results.json`，final 才读 `results.json`。"""
    assert gate.STAGE_RESULTS == {"q1": "results/q1_results.json",
                                  "final": "results/results.json"}


def test_skill_root_cannot_be_audited(gate):
    """SKILL_ROOT 自身不能当赛题目录审计（防把 skill 仓库当项目跑）。"""
    report = gate.gate(ROOT, "q1", run_figures=False)
    assert report["level"] == "FAIL"
    assert any("SKILL_ROOT" in issue for issue in report["issues"])


# ══════════════ 出口条件 4：不触碰审批链（子进程实测） ══════════════
BOUNDARY_PROBE = textwrap.dedent('''\
    import ast, importlib.util, json, sys
    from pathlib import Path

    tool = Path(sys.argv[1]); project = Path(sys.argv[2])
    spec = importlib.util.spec_from_file_location("probe_gate", tool)
    module = importlib.util.module_from_spec(spec); sys.modules["probe_gate"] = module
    spec.loader.exec_module(module)
    source = tool.read_text(encoding="utf-8")

    forbidden = {"record_team_approval", "set_status", "publish_q1"}
    called = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in forbidden:
                called.add(name)
    imports_workflow = bool(__import__("re").search(
        r"^\\s*(?:from\\s+math_modeling\\.workflow\\s+import|import\\s+math_modeling\\.workflow)",
        source, __import__("re").M))

    report = module.gate(project, "q1", run_figures=False)
    module.gate(project, "final", run_figures=False)   # final 也不得触碰审批链
    print(json.dumps({"called": sorted(called), "imports_workflow": imports_workflow,
                      "workflow_loaded": "math_modeling.workflow" in sys.modules,
                      "level": report["level"]}, ensure_ascii=False))
''')


def test_never_touches_approval_chain(tmp_path):
    """**出口条件 4 的硬约束**：AST 无审批链调用 + 源码不 import workflow +
    跑完两次 gate（q1/final）后 `math_modeling.workflow` **从未被加载**。

    用子进程实测，避免同进程其它测试已 import workflow 造成的假阴性。
    """
    project = build_project(tmp_path)
    probe = tmp_path / "probe.py"
    probe.write_text(BOUNDARY_PROBE, encoding="utf-8")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-B", str(probe), str(SG), str(project)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, env=env)
    assert proc.stdout.strip(), proc.stderr[-800:]
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["called"] == [], "不得调用审批链函数：%s" % data["called"]
    assert data["imports_workflow"] is False, "不得 import math_modeling.workflow"
    assert data["workflow_loaded"] is False, "跑 gate 后 workflow 不得被加载"


def test_no_approval_function_names_appear_as_calls(gate):
    """同一条约束的进程内版本（与既有 self_test 的判据同源，双保险）。"""
    source = SG.read_text(encoding="utf-8")
    import ast
    called = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            called.add(name)
    assert not (called & {"record_team_approval", "set_status", "publish_q1"})


# ══════════════ ① 六角色日志机检 ══════════════
def test_roles_and_tags_match_contract(gate):
    """六角色 = 6 个 `log_*.md`；六步链标签与 C15 定义逐字一致。"""
    assert gate.ROLES == ROLES
    assert gate.LOG_TAGS == LOG_TAGS
    for role in ROLES:
        assert "log_%s.md" % role in ("docs/log_%s.md" % role)


def test_complete_logs_pass(gate, tmp_path):
    project = build_project(tmp_path)
    issues, detail = gate.check_logs(project)
    assert issues == [], issues
    assert len(detail) == 6
    assert all(row["missing_tags"] == [] and row["timestamps"] >= 1 for row in detail.values())


def test_missing_role_log_fails(gate, tmp_path):
    project = build_project(tmp_path, roles=ROLES[:-1])
    issues, _ = gate.check_logs(project)
    assert any("log_审查.md" in issue for issue in issues), issues


@pytest.mark.parametrize("tag", LOG_TAGS, ids=[t.strip("[]") for t in LOG_TAGS])
def test_each_missing_tag_fails(gate, tmp_path, tag):
    """六个标签**逐个**缺一次都必须被抓（不得只抽查一个）。"""
    project = build_project(tmp_path, log_body=LOG_BODY.replace(tag, ""))
    issues, _ = gate.check_logs(project)
    assert any(tag in issue for issue in issues), issues


def test_missing_timestamp_fails(gate, tmp_path):
    """缺 `[YYYY-MM-DD HH:MM]` 格式时间戳 → FAIL（防用"今天"糊弄）。"""
    project = build_project(tmp_path, log_body=LOG_BODY.replace(STAMP, "今天"))
    issues, _ = gate.check_logs(project)
    assert any("时间戳" in issue for issue in issues), issues


def test_timestamp_format_is_strict(gate):
    """时间戳正则只认 `[YYYY-MM-DD HH:MM]`：近似格式必须不被认。"""
    good = "[2026-09-10 09:30] [怎么想] x"
    bad_variants = ["[2026/09/10 09:30]", "[2026-09-10 9:30]", "[2026-09-10]",
                    "2026-09-10 09:30", "[26-09-10 09:30]"]
    assert gate.TIMESTAMP_RE.findall(good)
    for variant in bad_variants:
        assert not gate.TIMESTAMP_RE.findall(variant), variant


# ══════════════ final 阶段 ══════════════
def _add_final_results(project):
    (project / "results" / "results.json").write_text(
        json.dumps(RESULTS, ensure_ascii=False), encoding="utf-8")


def test_final_requires_process_record(gate, tmp_path):
    project = build_project(tmp_path)
    _add_final_results(project)
    report = gate.gate(project, "final", run_figures=False)
    assert report["level"] == "FAIL"
    assert any("process_record" in issue for issue in report["issues"]), report["issues"]


def test_final_requires_each_role_anchor_in_process_record(gate, tmp_path):
    """process_record 必须引用**每一个**角色日志（缺一个点名一个）。"""
    project = build_project(tmp_path, with_record=True)
    _add_final_results(project)
    record = project / "output" / "process_record.md"
    record.write_text(record.read_text(encoding="utf-8").replace("docs/log_作图.md", ""),
                      encoding="utf-8")
    issues, _ = gate.check_logs(project, report_role="final")
    assert any("log_作图.md" in issue for issue in issues), issues


def test_final_with_record_passes(gate, tmp_path):
    project = build_project(tmp_path, with_record=True)
    _add_final_results(project)
    report = gate.gate(project, "final", run_figures=False)
    assert report["level"] == "PASS", report["issues"]
    assert report["results_path"] == "results/results.json"


def test_final_does_not_read_q1_results(gate, tmp_path):
    """final 阶段只认 `results.json`：只有 q1_results.json 时必须 FAIL。"""
    project = build_project(tmp_path, with_record=True)
    assert (project / "results" / "q1_results.json").is_file()
    report = gate.gate(project, "final", run_figures=False)
    assert report["level"] == "FAIL"
    assert any("results.json" in issue for issue in report["issues"])


# ══════════════ ②(a) 空 cwd 独立运行 ══════════════
def test_cwd_dependent_script_fails_independence(gate, tmp_path):
    """用 cwd 相对路径存图的脚本 → 空 cwd 独立运行 FAIL（脚本须 `__file__` 相对定位）。"""
    project = build_project(tmp_path, figure=CWD_DEPENDENT_FIGURE)
    manifest = project / "figures" / "figures_manifest.json"
    manifest.write_text(json.dumps(
        [{"no": "fig4", "title": "cwd 依赖", "file": "fig04_cwd.png",
          "script": "figures/scripts/fig01_demo.py",
          "data_entrypoint": "figures/data/fig01_demo.json"}], ensure_ascii=False),
        encoding="utf-8")
    report = gate.gate(project, "q1", run_figures=True, timeout=120,
                       scratch=tmp_path / "scratch")
    assert report["level"] == "FAIL"
    assert any("independent_run" in issue for issue in report["issues"]), report["issues"]


def test_render_text_crashes_when_script_unresolved(gate, tmp_path):
    """脚本解析失败时 `render_text` 须给出可读诊断，不得抛 `KeyError: 'script'`。

    历史：此用例原为「钉住已知 bug」。根因是 `_check_figure` 在 `script_err` 非空时
    **提前 return**，没写 `row["script"]`；而 `render_text` 无条件读它。触发条件恰是
    **真有问题要报**的时候（放错目录/脚本缺失），于是人工看到的是 traceback 而非结论；
    `--json` 模式正常，进程返回码仍是 1（解释器给未捕获异常的默认码），CI 的「非 0」
    判据碰巧成立，掩盖了崩溃。已修（`row` 初始化时就位 `script`），本条翻转。
    """
    project = build_project(tmp_path)
    (project / "figures" / "scripts" / "fig01_demo.py").unlink()      # 脚本缺失
    report = gate.gate(project, "q1", run_figures=False)
    assert report["level"] == "FAIL"
    assert report["figures"][0]["checks"]["script_path"]["level"] == "FAIL"
    # row 在任何 return 之前就位 script，故诊断文本可渲染
    assert report["figures"][0]["script"], "script 字段必须就位，render_text 依赖它"
    text = gate.render_text(report)
    assert "[FAIL]" in text and "fig1" in text, text
    assert "script_path" in text, text


def test_json_mode_survives_unresolved_script(gate, tmp_path, capsys):
    """同一输入在 `--json` 模式**不崩**（两侧行为不一致，正是上面 bug 的定位证据）。"""
    project = build_project(tmp_path)
    (project / "figures" / "scripts" / "fig01_demo.py").unlink()
    code = gate.main(["--project", str(project), "--stage", "q1", "--no-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and payload["level"] == "FAIL"


def test_good_script_passes_independence_and_binding(gate, tmp_path):
    """全链路（真跑子进程）：独立运行 + 运行时守卫 + 插桩比对本文件用一条正例钉住。

    这条**慢**（要起 3 个子进程），但它正是 `stage_gate` 存在的理由，不能只测 --no-run。
    """
    project = build_project(tmp_path)
    report = gate.gate(project, "q1", run_figures=True, timeout=180,
                       scratch=tmp_path / "scratch")
    assert report["level"] == "PASS", (report["issues"], report["warns"])
    checks = report["figures"][0]["checks"]
    for name in ("independent_run", "runtime_guard", "binding", "png", "data_binding"):
        assert checks[name]["level"] == "PASS", (name, checks[name])


def test_no_run_skips_execution_checks(gate, tmp_path):
    """`--no-run`（`run_figures=False`）只做落盘/AST：不得出现运行类检查项。"""
    project = build_project(tmp_path)
    report = gate.gate(project, "q1", run_figures=False)
    checks = report["figures"][0]["checks"]
    for name in ("independent_run", "runtime_guard", "binding"):
        assert name not in checks, name
    assert "stats_ast" in checks


def test_no_run_does_not_rewrite_png(gate, tmp_path):
    """只读契约：`run_figures=False` 时不得重写项目内 PNG（gate_audit 交叉确认依赖这点）。"""
    project = build_project(tmp_path)
    png = project / "figures" / "fig01_demo.png"
    before = png.read_bytes()
    gate.gate(project, "q1", run_figures=False)
    assert png.read_bytes() == before


# ══════════════ ③ 伪造数据被插桩抓到（端到端） ══════════════
FORGED_FIGURE = GOOD_FIGURE.replace("ax.bar([0, 1, 2], y, yerr=yerr",
                                    "ax.bar([0, 1, 2], [9.9, 9.9, 9.9], yerr=yerr")


def test_forged_painted_values_fail_end_to_end(gate, tmp_path):
    """画 9.9 而 results 是 1/2/3 → 插桩比对 FAIL（第 1 版"假验收"的修复点）。"""
    project = build_project(tmp_path, figure=FORGED_FIGURE)
    report = gate.gate(project, "q1", run_figures=True, timeout=180,
                       scratch=tmp_path / "scratch")
    assert report["level"] == "FAIL"
    assert any("binding" in issue for issue in report["issues"]), report["issues"]


# ══════════════ --strict 与退出码 ══════════════
def test_strict_upgrades_warn_to_fail(gate, tmp_path):
    """`--strict` 把 WARN 升级为 FAIL，并在报告里留痕（不靠退出码暗示）。"""
    project = build_project(tmp_path)
    (project / "figures" / "data" / "fig01_demo.json").unlink()   # 数据入口缺失 → WARN
    loose = gate.gate(project, "q1", run_figures=False)
    assert loose["level"] == "WARN" and loose["warns"], loose
    strict = gate.gate(project, "q1", run_figures=False, strict=True)
    assert strict["level"] == "FAIL"
    assert strict["strict_upgraded"] == loose["warns"]


def test_main_json_output_is_parseable(gate, tmp_path, capsys):
    project = build_project(tmp_path)
    code = gate.main(["--project", str(project), "--stage", "q1", "--no-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate"] == "stage_gate" and payload["stage"] == "q1"
    assert payload["machine_checks_only"] is True
    assert payload["independent_semantic_review_required"] is True
    assert code == 0


def test_main_exit_code_1_on_failure(gate, tmp_path):
    project = build_project(tmp_path, with_results=False)
    assert gate.main(["--project", str(project), "--stage", "q1", "--no-run"]) == 1


def test_program_exits_2_without_project(gate):
    with pytest.raises(SystemExit) as excinfo:
        gate.main([])
    assert excinfo.value.code == 2


def test_render_text_states_machine_check_limits(gate, tmp_path):
    """诚实性回归：输出必须带「机检只保证有结构」三行说明，不能只给 PASS。"""
    project = build_project(tmp_path)
    text = gate.render_text(gate.gate(project, "q1", run_figures=False))
    assert "机检只保证" in text
    assert "不保证「内容真实」" in text
    assert "目视检查" in text


def test_module_docstring_states_limits():
    doc = SG.read_text(encoding="utf-8").split('"""')[1]
    assert "机检只保证" in doc
    assert "不保证「内容真实」" in doc
    assert "独立语义审查" in doc


def test_self_test_passes():
    """`stage_gate.py --self-test` 隔离自检（批次 2 回归项；全部写入落在临时树内）。"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-B", str(SG), "--self-test"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600, env=env)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-1500:]
    report = json.loads(proc.stdout)
    assert report["passed"] is True
    failed = [c["name"] for c in report["checks"] if not c["ok"]]
    assert failed == [], failed
    assert report["project_verified"] is False, "自检只证明工具自身，不证明项目已核"


# ══════════════ 边界：gate_audit 二次调用（--no-run，只读） ══════════════
def test_gate_audit_cross_check_names_stage_gate_on_failure(tmp_path):
    """`gate_audit.stage_gate_cross_check` 失败时如实点名 stage_gate，不假装已核对。"""
    spec = importlib.util.spec_from_file_location("e_sg_audit", ROOT / "scripts/gate_audit.py")
    audit = importlib.util.module_from_spec(spec)
    sys.modules["e_sg_audit"] = audit
    spec.loader.exec_module(audit)
    project = build_project(tmp_path, with_results=False)          # 必然失败
    issues = audit.stage_gate_cross_check(project, "final")
    assert issues and any("stage_gate" in issue for issue in issues), issues


def test_gate_audit_cross_check_missing_script_is_reported(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("e_sg_audit2", ROOT / "scripts/gate_audit.py")
    audit = importlib.util.module_from_spec(spec)
    sys.modules["e_sg_audit2"] = audit
    spec.loader.exec_module(audit)
    monkeypatch.setattr(type(audit.ROOT), "is_file", lambda self: False)
    issues = audit.stage_gate_cross_check(ROOT, "final")
    assert issues and ("缺失" in issues[0] or "未执行" in issues[0]), issues


def test_cross_check_uses_no_run_to_stay_read_only():
    """边界写死：交叉确认必须带 `--no-run`，否则会重跑绘图脚本、破坏只读契约。"""
    source = (ROOT / "scripts/gate_audit.py").read_text(encoding="utf-8")
    assert '"--no-run"' in source or "'--no-run'" in source
    block = source.split("def stage_gate_cross_check")[1].split("def ")[0]
    assert "--no-run" in block
