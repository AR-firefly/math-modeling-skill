"""E / 批次 2 —— 验收③ **插桩比对**单测（作图契约 §四/§五；出口条件 1、2）。

它回答的唯一问题：**画进图里的数组，逐个值是否等于 `results/` 里的数？**
不是「脚本 dict 里有没有这个键」（那可以造），也不是「`figures/data/*.json` 与
`results.json` 是否相等」（那本就靠复制，比对恒真 = 假验收）。

本文件分三层，逐层加强：
1. `compare()` 单元层 —— 用**桩捕获器**喂入确定入参，判定规则可精确断言
2. 出口条件 2 的三类反例 —— `np.arange` 刻度（不该报）/ 真实数据（该报）/
   轨迹坐标按 `aux` 排除（不该报）
3. 出口条件 1 —— `visualizer.py` **11 个绘图方法各跑一次**（真插桩捕获），
   断言捕获数组与 CONTRACT 声明一致

诚实边界
--------
本检查证明「画进图里的数 = results 里的数」，**不证明这些数算得对**（归门禁2a），
也不证明图好看（归目视检查）。若编程手落盘的 results 本身就是编的，本检查照样 PASS。
"""
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CFB = ROOT / "scripts/check_figure_binding.py"


@pytest.fixture(scope="module")
def cfb():
    spec = importlib.util.spec_from_file_location("e_binding", CFB)
    module = importlib.util.module_from_spec(spec)
    sys.modules["e_binding"] = module
    spec.loader.exec_module(module)
    return module


class StubCapture:
    """桩捕获器：直接喂「已捕获的绘图入参」，避开真跑脚本的开销。"""

    def __init__(self, calls):
        self.calls = calls

    def by_method(self, external_only=True):
        grouped = {}
        for call in self.calls:
            grouped.setdefault(call["method"], []).append(call)
        return grouped


def call(method, positional=(), keyword=None, caller="__main__"):
    return {"method": method, "caller": caller,
            "positional": list(positional), "keyword": dict(keyword or {})}


RESULTS = {"Q1_耗时": [1.0, 2.0, 3.0], "Q1_耗时_std": [0.1, 0.2, 0.3],
           "Q1_轨迹x": [10.0, 20.0], "Q1_轨迹y": [30.0, 40.0], "Q1_基线值": 2.5}


def contract(bindings, plot_calls, **extra):
    body = {"fig_id": "f",
            "data_binding": {"results_path": "results/q1_results.json", "bindings": bindings},
            "plot_calls": plot_calls}
    body.update(extra)
    return body


# ══════════════════ 出口条件 2：三类反例判定正确 ══════════════════
def test_class1_arange_ticks_declared_as_aux_are_not_reported(cfb):
    """反例①「`np.arange` 刻度（不该报）」：刻度列进 `aux_params` → 零 issues 零 warns。"""
    spec = contract({"y": "Q1_耗时"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}])
    capture = StubCapture([call("plot", [[0, 1, 2], RESULTS["Q1_耗时"]])])
    issues, warns = cfb.compare(capture, spec, RESULTS)
    assert issues == [] and warns == [], (issues, warns)


def test_class1b_undeclared_arange_ticks_are_warned_not_silent(cfb):
    """刻度**没声明**时不得静默放过 → WARN 列出（不静默不放过这条必须真跑）。"""
    spec = contract({"y": "Q1_耗时"}, [{"method": "plot", "data_params": ["y"]}])
    capture = StubCapture([call("plot", [[0, 1, 2], RESULTS["Q1_耗时"]])])
    issues, warns = cfb.compare(capture, spec, RESULTS)
    assert issues == []
    assert any("未声明" in w and "x" in w for w in warns), warns


def test_class2_forged_real_data_is_reported(cfb):
    """反例②「真实数据（该报）」：画的是 9.9，results 是 1/2/3 → FAIL 且指出首个差异。"""
    spec = contract({"y": "Q1_耗时"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}])
    capture = StubCapture([call("plot", [[0, 1, 2], [9.9, 9.9, 9.9]])])
    issues, _ = cfb.compare(capture, spec, RESULTS)
    assert issues and "不匹配" in issues[0] and "index 0" in issues[0], issues


def test_class3_trajectory_coordinates_excluded_via_aux(cfb):
    """反例③「轨迹坐标（该按 aux 排除）」：x 是轨迹坐标，列 aux → 不报；y 照比。"""
    spec = contract({"y": "Q1_耗时"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}])
    capture = StubCapture([call("plot", [RESULTS["Q1_轨迹x"], RESULTS["Q1_耗时"]])])
    issues, warns = cfb.compare(capture, spec, RESULTS)
    assert issues == [] and warns == [], (issues, warns)


def test_class3b_trajectory_y_left_undisclosed_is_warned(cfb):
    """轨迹 y 若既不在 data_params 也不在 aux_params → WARN（声明制必须完整）。"""
    spec = contract({"y": "Q1_轨迹y"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}])
    capture = StubCapture([call("plot", [RESULTS["Q1_轨迹x"], RESULTS["Q1_轨迹y"]])])
    issues, _ = cfb.compare(capture, spec, RESULTS)
    assert issues == [], "轨迹 y 已绑到真 results 键，不该 FAIL"
    # 把 aux 去掉一半，未声明的那一半应被 WARN 抓到
    partial = contract({"y": "Q1_轨迹y"}, [{"method": "plot", "aux_params": ["x"]}])
    _, warns = cfb.compare(capture, partial, RESULTS)
    assert any("未声明" in w for w in warns), warns


def test_declared_but_binding_missing_is_fail(cfb):
    """声明了 data_params 却不在 bindings 里 → FAIL（不能靠"声明了就过"）。"""
    spec = contract({"其它键": "Q1_耗时"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}])
    capture = StubCapture([call("plot", [[0, 1, 2], RESULTS["Q1_耗时"]])])
    issues, _ = cfb.compare(capture, spec, RESULTS)
    assert issues and "没有对应 results 键" in issues[0], issues


# ══════════════════ 伪造 data_binding / 声明与路径不符 ══════════════════
def test_declared_method_never_painted_is_fail(cfb):
    """声明画 bar，实际只画了 plot → FAIL（防声明与代码脱钩）。"""
    spec = contract({"y": "Q1_耗时"},
                    [{"method": "bar", "data_params": ["y"], "aux_params": ["x"]}])
    capture = StubCapture([call("plot", [[0, 1, 2], RESULTS["Q1_耗时"]])])
    issues, _ = cfb.compare(capture, spec, RESULTS)
    assert issues and "声明与实际绘图路径不符" in issues[0], issues


def test_wrong_results_key_is_fail(cfb):
    """key 写错（指向不存在的 results 键）→ FAIL，不得当成"没数据可比"放过。"""
    spec = contract({"y": "Q1_不存在的键"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}])
    capture = StubCapture([call("plot", [[0, 1, 2], RESULTS["Q1_耗时"]])])
    issues, _ = cfb.compare(capture, spec, RESULTS)
    assert issues and "不存在" in issues[0], issues


def test_missing_data_binding_is_fail(cfb):
    spec = {"fig_id": "f", "plot_calls": []}
    issues, _ = cfb.compare(StubCapture([]), spec, RESULTS)
    assert issues and "data_binding" in issues[0]


def test_empty_bindings_is_fail(cfb):
    spec = contract({}, [{"method": "plot", "data_params": ["y"]}])
    issues, _ = cfb.compare(StubCapture([]), spec, RESULTS)
    assert issues and "bindings" in issues[0]


def test_missing_plot_calls_is_fail(cfb):
    spec = contract({"y": "Q1_耗时"}, [])
    issues, _ = cfb.compare(StubCapture([]), spec, RESULTS)
    assert issues and "plot_calls" in issues[0]


def test_method_outside_capture_surface_is_fail(cfb):
    spec = contract({"y": "Q1_耗时"}, [{"method": "imshow_typo", "data_params": ["y"]}])
    issues, _ = cfb.compare(StubCapture([]), spec, RESULTS)
    assert issues and "不在捕获面内" in issues[0]


def test_schematic_kind_is_exempt_with_visible_note(cfb):
    """示意图：数值比对豁免，但必须**显式声明** kind，且豁免结论写进报告（不静默）。"""
    spec = {"fig_id": "f", "data_binding": {"kind": "schematic"}, "plot_calls": []}
    issues, warns = cfb.compare(StubCapture([]), spec, RESULTS)
    assert issues == [] and warns and "schematic" in warns[0]


def test_schematic_requires_explicit_kind(cfb):
    """缺省从严：不写 kind = 按数据图全量检查（不得用"不写"自动豁免）。"""
    spec = contract({"y": "Q1_耗时"}, [{"method": "plot", "data_params": ["y"]}])
    issues, _ = cfb.compare(StubCapture([]), spec, RESULTS)
    assert issues, "未声明 kind=schematic 时不得豁免数值比对"


# ── 未声明入参：WARN → --strict FAIL ──────────────────────────────────
def test_undeclared_kwarg_is_warn_then_fail_in_strict(cfb):
    spec = contract({"x": "Q1_耗时"},
                    [{"method": "hist", "data_params": ["x"], "aux_params": []}])
    capture = StubCapture([call("hist", [RESULTS["Q1_耗时"]], {"bins": 7})])
    issues, warns = cfb.compare(capture, spec, RESULTS)
    assert issues == [] and any("bins" in w for w in warns), warns
    strict_issues, strict_warns = cfb.compare(capture, spec, RESULTS, strict=True)
    assert strict_warns == [] and any("bins" in i for i in strict_issues), strict_issues


def test_style_kwargs_are_not_warned(cfb):
    """样式 kwarg（color/hatch/capsize…）不列入声明制——否则每张误差棒图都 WARN。"""
    spec = contract({"y": "Q1_耗时"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}])
    capture = StubCapture([call("plot", [[0, 1, 2], RESULTS["Q1_耗时"]],
                                {"color": "k", "lw": 0.8, "label": "基线", "hatch": "//"})])
    issues, warns = cfb.compare(capture, spec, RESULTS)
    assert issues == [] and warns == [], (issues, warns)


def test_declared_param_not_passed_is_warned(cfb):
    """声明了 yerr 却没画误差棒 → WARN（声明必须与实际调用对得上）。"""
    spec = contract({"y": "Q1_耗时", "yerr": "Q1_耗时_std"},
                    [{"method": "bar", "data_params": ["y"], "kwarg_params": ["yerr"],
                      "aux_params": ["x"]}])
    capture = StubCapture([call("bar", [[0, 1, 2], RESULTS["Q1_耗时"]])])
    issues, warns = cfb.compare(capture, spec, RESULTS)
    assert any("未传入" in w for w in warns), warns


# ── 误差棒走 Axes.bar(yerr=) —— 第 3 版的失效模式，必须钉住 ────────────
def test_errorbar_lives_in_bar_yerr_not_errorbar(cfb):
    spec = contract({"y": "Q1_耗时", "yerr": "Q1_耗时_std"},
                    [{"method": "bar", "data_params": ["y"], "kwarg_params": ["yerr"],
                      "aux_params": ["x", "color"]}])
    good = StubCapture([call("bar", [[0, 1, 2], RESULTS["Q1_耗时"]],
                             {"yerr": RESULTS["Q1_耗时_std"], "color": "k"})])
    assert cfb.compare(good, spec, RESULTS) == ([], [])
    forged = StubCapture([call("bar", [[0, 1, 2], RESULTS["Q1_耗时"]],
                               {"yerr": [9.0, 9.0, 9.0], "color": "k"})])
    issues, _ = cfb.compare(forged, spec, RESULTS)
    assert issues and "yerr" in issues[0], issues


# ── 闭合描边（雷达）：必须显式声明，且只能"首元素精确重复" ──────────────
def test_closed_loop_must_be_explicitly_declared(cfb):
    spec = contract({"y": "Q1_耗时"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}])
    closed = StubCapture([call("plot", [[0, 1, 2, 0], [1.0, 2.0, 3.0, 1.0]])])
    issues, _ = cfb.compare(closed, spec, RESULTS)
    assert issues and "形状不一致" in issues[0], issues


def test_closed_loop_declared_accepts_exact_repeat(cfb):
    spec = contract({"y": "Q1_耗时"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"],
                      "closed_loop": True}])
    closed = StubCapture([call("plot", [[0, 1, 2, 0], [1.0, 2.0, 3.0, 1.0]])])
    assert cfb.compare(closed, spec, RESULTS) == ([], [])


def test_closed_loop_rejects_fabricated_value(cfb):
    """`closed_loop` 只接受「多出的末位 == 首位」的精确相等，**不得**洗白编造数据。"""
    spec = contract({"y": "Q1_耗时"},
                    [{"method": "plot", "data_params": ["y"], "aux_params": ["x"],
                      "closed_loop": True}])
    forged = StubCapture([call("plot", [[0, 1, 2, 0], [1.0, 2.0, 3.0, 9.0]])])
    issues, _ = cfb.compare(forged, spec, RESULTS)
    assert issues and "闭合点不等于首元素" in issues[0], issues


# ── match_values 逐值口径 ─────────────────────────────────────────────
def test_match_values_shape_and_tolerance(cfb):
    assert cfb.match_values([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], 1e-9)[0] is True
    assert cfb.match_values([1.0, 2.0], [1.0, 2.0, 3.0], 1e-9)[0] is False
    assert cfb.match_values([1.0 + 1e-12, 2.0, 3.0], [1.0, 2.0, 3.0], 1e-9)[0] is True
    ok, detail = cfb.match_values([1.0, 2.0, 9.0], [1.0, 2.0, 3.0], 1e-9)
    assert ok is False and "index 2" in detail


def test_match_values_nan_treated_equal(cfb):
    ok, _ = cfb.match_values([1.0, float("nan")], [1.0, float("nan")], 1e-9)
    assert ok is True, "两处都是 NaN 视为相等（不把缺测值当造假）"


def test_results_key_path_resolution(cfb):
    """results 键路径解析：纯键名 / 点号嵌套 / **末尾**下标均可用；缺键/越界返回未找到。"""
    nested = {"flat": 3.0, "a": {"b": [{"c": 7.0}, 8.0]}, "list": [10.0, 20.0]}
    assert cfb._resolve("flat", nested) == (True, 3.0)
    assert cfb._resolve("a.b", nested)[0] is True
    assert cfb._resolve("a.b[0]", nested) == (True, {"c": 7.0})
    assert cfb._resolve("a.b[1]", nested) == (True, 8.0)
    assert cfb._resolve("list[1]", nested) == (True, 20.0)
    for missing in ("nope", "a.missing", "a.b[9]", "list[9]"):
        assert cfb._resolve(missing, nested) == (False, None), missing


def test_indexed_key_path_with_trailing_field_is_a_documented_gap(cfb):
    """**记录已知 bug**：docstring 声称支持 `a.b[0].c`，实际**解析失败**。

    根因：`_resolve` 在 `]` 之后遇到 `.` 时会先 `parts.append(buf)`（此时 `buf` 为空串），
    于是路径里混进一个 `""` 部分，取值必然落空。带下标**结尾**的路径（`a.b[0]`）正常，
    只有「下标后还继续取字段」才失效。

    触发条件苛刻（results 需是 list 套 dict 再取字段），但 docstring 与实现不一致，
    已作为发现交回主 Agent，**不在本测试里绕过**。
    """
    nested = {"a": {"b": [{"c": 7.0}]}}
    # 已修：`]` 之后的 `.` 不再把空串塞进路径，与 docstring 声称的支持范围一致
    assert cfb._resolve("a.b[0].c", nested) == (True, 7.0)
    assert cfb._resolve("a.b[0]", nested) == (True, {"c": 7.0})


# ══════════════════ 出口条件 1：11 个绘图方法各跑一次 ══════════════════
def test_all_eleven_visualizer_methods_bind_correctly(cfb, tmp_path):
    """**出口条件 1**：`visualizer.py` 的 11 个绘图方法各跑一次（真插桩捕获），
    每个方法一份独立脚本 + 独立 CONTRACT，逐一过完整 `compare()` 路径。

    任何方法 CRASH / FAIL / WARN 都会出现在 `failures` 里，本用例即失败。
    """
    project = tmp_path / "project"
    (project / "figures" / "scripts").mkdir(parents=True)
    (project / "results").mkdir(parents=True)
    (project / "results" / "q1_results.json").write_text(
        json.dumps(cfb._METHOD_RESULTS, ensure_ascii=False), encoding="utf-8")
    table, failures = cfb._per_method_table(project, cfb._METHOD_RESULTS, tmp_path)
    assert not failures, "出口条件 1 未收敛：\n%s\n表：%s" % ("\n".join(failures), table)
    expected = ["_line", "_bar", "_scatter", "_box", "_heatmap", "_hist", "_errorbar",
                "_contour", "_contourf", "_radar", "_fill_between"]
    assert len(expected) == 11
    assert len(table) == 11, "11 个方法必须各出一行：%s" % table
    assert all(row.endswith("=PASS") for row in table), table
    assert table == sorted(table, key=lambda r: list(cfb._METHOD_CASES).index(r.split("=")[0]))


def test_capture_surface_covers_every_declared_method(cfb):
    """捕获面必须覆盖 11 个方法实际用到的全部 matplotlib 调用（契约 §五 表）。"""
    body = json.dumps(cfb._METHOD_CASES, default=str)
    for method in ("plot", "bar", "boxplot", "imshow", "hist", "contour", "contourf",
                   "fill", "fill_between", "axhline", "scatter"):
        assert method in body, "捕获面缺 %s" % method
    assert set(cfb.CAPTURED_METHODS) >= {"plot", "bar", "barh", "errorbar", "scatter", "hist",
                                         "boxplot", "imshow", "contour", "contourf",
                                         "pcolormesh", "fill", "fill_between", "axhline",
                                         "axvline", "text"}


# ══════════════════ 端到端：真跑脚本 → 真抓伪造数据 ══════════════════
FORGED_SCRIPT = textwrap.dedent('''\
    from pathlib import Path
    import json
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ROOT = Path(__file__).resolve().parents[2]
    OUT = Path(__file__).resolve().parents[1]
    CONTRACT = {
        "fig_id": "fig03_forged",
        "data_binding": {"results_path": "results/q1_results.json",
                         "bindings": {"y": "Q1_基线_耗时"}},
        "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}],
    }
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [9.9, 9.9, 9.9])      # 伪造：与 results 的 1/2/3 不一致
    fig.savefig(OUT / "fig03_forged.png", dpi=300)
    plt.close(fig)
''')

HONEST_SCRIPT = FORGED_SCRIPT.replace("[9.9, 9.9, 9.9]", "json.loads((ROOT / "
                                     "CONTRACT['data_binding']['results_path'])"
                                     ".read_text(encoding='utf-8'))['Q1_基线_耗时']")


def _run_cli(project, script, *extra):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT / "src"),
                                                      env.get("PYTHONPATH", ""))))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("MPLCONFIGDIR", str(project / "_mplcache"))
    proc = subprocess.run([sys.executable, "-B", str(CFB), "--json", "--script", str(script),
                           "--project", str(project), "--stage", "q1", *extra],
                          cwd=str(project), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    return proc.returncode, json.loads(proc.stdout)


def _seed(tmp_path, source, name="fig03_forged.py"):
    project = tmp_path / "project"
    (project / "figures" / "scripts").mkdir(parents=True)
    (project / "results").mkdir(parents=True)
    (project / "results" / "q1_results.json").write_text(
        json.dumps({"Q1_基线_耗时": [1.0, 2.0, 3.0]}, ensure_ascii=False), encoding="utf-8")
    script = project / "figures" / "scripts" / name
    script.write_text(source, encoding="utf-8")
    return project, script


def test_end_to_end_forged_painted_values_fail(tmp_path):
    """端到端反例：真跑脚本 + 真插桩，画 9.9 而 results 是 1/2/3 → FAIL。"""
    project, script = _seed(tmp_path, FORGED_SCRIPT)
    code, report = _run_cli(project, script)
    assert report["level"] == "FAIL" and code == 1, report
    assert any("不匹配" in issue for issue in report["issues"]), report["issues"]
    assert report["captured_methods"] == ["plot"], report["captured_methods"]


def test_end_to_end_honest_values_pass(tmp_path):
    """同一脚本结构改为真读 results → PASS（证明上面的 FAIL 不是脚本跑不起来）。"""
    project, script = _seed(tmp_path, HONEST_SCRIPT, name="fig03_honest.py")
    code, report = _run_cli(project, script)
    assert report["level"] == "PASS" and code == 0, (report["issues"], report.get("script_error"))


def test_end_to_end_out_of_contract_results_path_fails(tmp_path):
    """`results_path` 指到契约外的文件（如 demo 的 figures/fig1.json）→ FAIL。"""
    project, script = _seed(
        tmp_path, FORGED_SCRIPT.replace("results/q1_results.json", "figures/fig1.json"),
        name="fig03_ooc.py")
    (project / "figures" / "fig1.json").write_text('{"Q1_基线_耗时": [1, 2, 3]}', encoding="utf-8")
    _, report = _run_cli(project, script)
    assert report["level"] == "FAIL"
    assert any("超出契约限定" in issue for issue in report["issues"]), report["issues"]


def test_end_to_end_missing_results_file_fails(tmp_path):
    project, script = _seed(tmp_path, FORGED_SCRIPT, name="fig03_nr.py")
    (project / "results" / "q1_results.json").unlink()
    _, report = _run_cli(project, script)
    assert report["level"] == "FAIL" and any("不存在" in i for i in report["issues"])


def test_end_to_end_script_crash_is_not_a_pass(tmp_path):
    """脚本自身崩溃 ≠ 比对通过 → FAIL 且如实给 `script_error`（不伪造结论）。"""
    project, script = _seed(tmp_path, FORGED_SCRIPT + "\nraise RuntimeError('boom')\n",
                            name="fig03_crash.py")
    _, report = _run_cli(project, script)
    assert report["level"] == "FAIL" and report["script_error"], report


def test_docstring_declares_machine_check_limits():
    """诚实性回归：脚本必须写明「不证明数算得对、也不证明图好看」。"""
    doc = CFB.read_text(encoding="utf-8").split('"""')[1]
    assert "不证明这些数算得对" in doc or "不证明数算得对" in doc
    assert "不证明图好看" in doc or "不证明图" in doc
