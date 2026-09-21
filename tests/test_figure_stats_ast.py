"""E / 批次 2 —— 作图脚本统计禁令：**静态 AST 检查器**单测（作图契约 §六 第一层）。

覆盖出口条件：本文件对应 §十 中的「禁统计推断（AST）」面，为 `stage_gate.py`
（`find_stats_calls` / `contract_literal` / `exemption_level` / `check_stats_ast`）
与 `validate_figures.py`（`check_no_statistical_inference`）提供回归。

诚实边界（务必连读）
--------------------
**AST 只能「降概率」，不是真判据。** 真判据是运行时守卫（`figure_runtime_guard.py`）
+ 职责边界（统计量由编程手算好落盘、作图手只读常量）。

本文件记录的两条**已知覆盖缺口**（`test_bare_import_*`，实测确认，非猜测）：

1. `from scipy.optimize import curve_fit; curve_fit(...)` → `stage_gate` 与
   `validate_figures` **都抓不到**（两边的判据都要求 `scipy.optimize.` 点号前缀）
2. `from scipy.stats import ttest_ind; ttest_ind(...)` → **都抓不到**
3. `m = LinearRegression(); m.fit(X, y)` 这种「先赋值再调用」的裸名 `.fit()`
   → `stage_gate` 抓不到（它要求接收者名里含 model/clf/reg/… 等词）；
   `validate_figures` 抓得到（它对**任意** `.fit()` 报）。

这些缺口**不是本测试放行**，而是显式记录下来，让「静态层覆盖率」可复核——
补上它们要靠运行时守卫（同目录 `test_figure_runtime_guard.py` 实测动态写法也绕不过）。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(module_name, relative):
    """按既有范式（test_redo_audit_edges.py）用 importlib 加载 scripts/ 下的脚本。"""
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module      # dataclass 模块需要登记（validate_figures）
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return load_script("e_stats_stage_gate", "scripts/stage_gate.py")


@pytest.fixture(scope="module")
def vf():
    return load_script("e_stats_validate_figures", "scripts/validate_figures.py")


# ── 1. numpy 统计函数必须被抓 ──────────────────────────────────────────
NP_CASES = [
    ("std", "import numpy as np\nnp.std([1, 2, 3])\n", "np.std"),
    ("var", "import numpy as np\nnp.var([1, 2, 3])\n", "np.var"),
    ("percentile", "import numpy as np\nnp.percentile([1, 2, 3], 50)\n", "np.percentile"),
    ("quantile", "import numpy as np\nnp.quantile([1, 2, 3], 0.5)\n", "np.quantile"),
    ("corrcoef", "import numpy as np\nnp.corrcoef([1, 2], [3, 4])\n", "np.corrcoef"),
    ("numpy_full_prefix", "import numpy\nnumpy.percentile([1, 2, 3], 50)\n", "numpy.percentile"),
]


@pytest.mark.parametrize("name,source,expect", NP_CASES, ids=[c[0] for c in NP_CASES])
def test_numpy_stats_are_detected(gate, name, source, expect):
    hits = gate.find_stats_calls(source)
    assert hits is not None, "语法合法的源码不应返回 None"
    assert expect in hits, "%s 未被 AST 抓到：%s" % (name, hits)


# ── 2. scipy.stats / scipy.optimize / sklearn 必须被抓 ─────────────────
# 说明：这三条用的是「点号全名」写法（因为实测只有这种写法两边都抓得到）；
# 裸名写法见 test_bare_import_* 的缺口记录。
SCIPY_CASES = [
    ("scipy.stats_attr",
     "import scipy.stats\nscipy.stats.pearsonr([1, 2], [3, 4])\n", "scipy.stats.pearsonr"),
    ("from_scipy_import_stats",
     "from scipy import stats\nstats.ttest_ind([1, 2], [3, 4])\n", "stats.ttest_ind"),
    ("scipy_optimize_curve_fit",
     "import scipy.optimize\nscipy.optimize.curve_fit(f, [1], [2])\n", "scipy.optimize.curve_fit"),
    ("scipy_optimize_least_squares",
     "import scipy.optimize\nscipy.optimize.least_squares(f, [1])\n", "scipy.optimize.least_squares"),
]


@pytest.mark.parametrize("name,source,expect", SCIPY_CASES, ids=[c[0] for c in SCIPY_CASES])
def test_scipy_calls_are_detected(gate, name, source, expect):
    hits = gate.find_stats_calls(source)
    assert expect in hits, "%s 未被 AST 抓到：%s" % (name, hits)


def test_sklearn_fit_and_predict_are_detected(gate):
    """sklearn 的 .fit()/.predict() —— 接收者名带 model/clf 词根时被抓。"""
    fit_src = ("from sklearn.linear_model import LinearRegression\n"
               "model = LinearRegression()\nmodel.fit([[1], [2]], [1, 2])\n")
    predict_src = "clf.predict(X)\n"
    assert any("fit" in hit for hit in gate.find_stats_calls(fit_src)), \
        gate.find_stats_calls(fit_src)
    assert any("predict" in hit for hit in gate.find_stats_calls(predict_src)), \
        gate.find_stats_calls(predict_src)


def test_validate_figures_catches_bare_sklearn_fit(vf):
    """validate_figures 对**任意** `.fit()` 都报（比 stage_gate 严），交叉确认。"""
    src = ("from sklearn.linear_model import LinearRegression\n"
           "m = LinearRegression()\nm.fit([[1], [2]], [1, 2])\n")
    assert vf.check_no_statistical_inference(src, None).level == "FAIL"


# ── 3. 已知覆盖缺口：必须**真跑**确认，不能只断言函数存在 ─────────────
# 两个检查器的覆盖并不一致，逐条把**实际**行为钉住（缺口闭合时本表会失败，提醒更新）。
# (用例名, 源码, stage_gate 期望命中, validate_figures 期望结论)
COVERAGE_MATRIX = [
    ("from_scipy.stats_import_ttest_ind",
     "from scipy.stats import ttest_ind\nttest_ind([1, 2], [3, 4])\n", [], "PASS"),
    ("scipy_optimize_alias",
     "import scipy.optimize as opt\nopt.least_squares(f, [1])\n", [], "FAIL"),
    ("numpy_bare_std",
     "from numpy import std\nprint(std([1, 2, 3]))\n", ["std"], "FAIL"),
]


@pytest.mark.parametrize("name,source,sg_hits,vf_level", COVERAGE_MATRIX,
                         ids=[c[0] for c in COVERAGE_MATRIX])
def test_static_coverage_matrix(gate, vf, name, source, sg_hits, vf_level):
    """静态层的**实际覆盖**逐条记录（哪些抓得到、哪些抓不到）。

    抓不到的一律由运行时守卫兜底（`test_figure_runtime_guard.py` 实测：patch 作用在
    对象属性上，`getattr`/`__import__`/`eval` 拿到的都是同一被替换对象）。
    `numpy_bare_std` 一行属**崩溃**而非判定，见下面的 bug 钉住用例。
    """
    assert gate.find_stats_calls(source) == sg_hits, \
        "stage_gate 覆盖已变化，请同步更新本表"
    if name == "numpy_bare_std":
        return                      # 该行会崩，结论由 test_validate_figures_crashes_on_bare_stats_name 钉
    assert vf.check_no_statistical_inference(source, None).level == vf_level, \
        "validate_figures 覆盖已变化，请同步更新本表"


def test_assigned_receiver_fit_is_a_documented_stage_gate_gap(gate):
    """`m = LinearRegression(); m.fit(...)`：接收者名不含词根 → stage_gate 漏；运行时守卫抓。"""
    src = ("from sklearn.linear_model import LinearRegression\n"
           "m = LinearRegression()\nm.fit([[1], [2]], [1, 2])\n")
    assert gate.find_stats_calls(src) == [], "缺口已闭合，请同步更新本记录"


# ── 3b. **bug 钉住**：validate_figures 对「裸名统计函数」直接崩溃（交回主 Agent，不自行修）
# 根因：`_stats_targets` 的 `root = func.value` 把 `func` 当成 `ast.Attribute`，
# 但 `func` 可能是 `ast.Name`（裸名调用）→ AttributeError，整支检查器抛异常退出。
# 触发面（实测，两类）：`std(...)`（std 在 _STATS_ATTRS）、
#                      `curve_fit(...)`（curve_fit 也在 _STATS_ATTRS）
# 影响：CLI 退出码 1 + 堆栈，**不是** FAIL finding——调用方拿到的是崩溃而非判定。
CRASHING_BARE_NAMES = [
    ("numpy_std", "from numpy import std\nprint(std([1, 2, 3]))\n", "std"),
    ("scipy_curve_fit", "from scipy.optimize import curve_fit\ncurve_fit(f, [1], [2])\n", "curve_fit"),
]


@pytest.mark.parametrize("name,source,expected", CRASHING_BARE_NAMES, ids=[c[0] for c in CRASHING_BARE_NAMES])
def test_validate_figures_reports_bare_stats_name(vf, name, source, expected):
    """裸名统计调用（`from numpy import std` 后直接 `std(...)`）须报 FAIL，不得崩溃。

    历史：此用例原为「钉住已知 bug」，断言抛 AttributeError。根因是 `_stats_targets`
    在 `func` 为 `ast.Name` 时仍取 `func.value`。已修（改为分支处理裸名→直接记命中），
    本用例随之翻转为断言正确行为，与 `test_stage_gate_does_not_crash_on_bare_stats_name`
    的 stage_gate 侧口径一致。
    """
    result = vf.check_no_statistical_inference(source, None)
    assert result.level == "FAIL", result
    blob = " ".join(str(x) for x in (result.message, *(result.evidence or [])))
    assert expected in blob, blob


def test_stage_gate_does_not_crash_on_bare_stats_name(gate):
    """同一输入在 stage_gate 侧**不崩**（两侧行为不一致，正是上面 bug 的定位证据）。"""
    hits = gate.find_stats_calls("from numpy import std\nprint(std([1, 2, 3]))\n")
    assert hits == ["std"], hits


# ── 4. 合规脚本必须零命中（防过度拦截） ────────────────────────────────
CLEAN_SOURCES = {
    "plain_mean": "import numpy as np\nx = np.array([1, 2, 3])\nprint(x.mean())\n",
    "read_constants": ("import json\nfrom pathlib import Path\n"
                       "r = json.loads(Path('r.json').read_text(encoding='utf-8'))\n"
                       "y = r['Q1_耗时']\nprint(y)\n"),
    "no_call_at_all": "x = 1\ny = 2\n",
}


@pytest.mark.parametrize("name", sorted(CLEAN_SOURCES))
def test_clean_sources_are_not_flagged(gate, name):
    assert gate.find_stats_calls(CLEAN_SOURCES[name]) == []


# ── 5. 豁免：空理由 FAIL，非空理由 WARN（两处都要有） ──────────────────
def _contract(exempt):
    return ('CONTRACT = {"fig_id": "f", "statistical_exempt": %r,\n'
            '            "data_binding": {"results_path": "results/q1_results.json",\n'
            '                              "bindings": {"y": "Q1"}},\n'
            '            "plot_calls": []}\n' % (exempt,))


def test_empty_exemption_reason_fails(gate):
    """`# STATS-EXEMPT:` 后无文本 + CONTRACT 空 → FAIL（防随手补一行注释）。"""
    src = _contract([]) + "import numpy as np\n# STATS-EXEMPT:\nprint(np.std([1, 2, 3]))\n"
    level, detail = gate.check_stats_ast(Path("x.py"), src)
    assert level == "FAIL", detail
    assert "np.std" in detail["hits"]


def test_nonempty_exemption_is_warn(gate):
    """非空理由**两处都在** → 降 WARN（不是 PASS，仍需人工确认）。"""
    src = (_contract(["1.5×IQR 截断仅用于稳定 y 轴，不进任何结论"])
           + "import numpy as np\n"
             "# STATS-EXEMPT: 1.5×IQR 截断仅用于稳定 y 轴，不进任何结论\n"
             "print(np.std([1, 2, 3]))\n")
    level, detail = gate.check_stats_ast(Path("x.py"), src)
    assert level == "WARN", detail
    assert detail["exempt_reason"], "WARN 必须把豁免理由带进报告（不静默放过）"


def test_comment_only_exemption_is_fail(gate):
    """只写注释、CONTRACT 没写 → 仍 FAIL（两处都要有）。"""
    src = (_contract([])
           + "import numpy as np\n# STATS-EXEMPT: 有理由但 CONTRACT 没写\n"
             "print(np.std([1, 2, 3]))\n")
    assert gate.check_stats_ast(Path("x.py"), src)[0] == "FAIL"


def test_contract_only_exemption_is_fail(gate):
    """只有 CONTRACT、脚本里没注释 → 仍 FAIL。"""
    src = _contract(["有理由"]) + "import numpy as np\nprint(np.std([1, 2, 3]))\n"
    assert gate.check_stats_ast(Path("x.py"), src)[0] == "FAIL"


def test_stats_source_without_exemption_fails(gate):
    src = "import numpy as np\nprint(np.std([1, 2, 3]))\n"
    level, detail = gate.check_stats_ast(Path("x.py"), src)
    assert level == "FAIL" and detail["hits"]


# ── 6. CONTRACT 字面量解析（不执行脚本） ──────────────────────────────
def test_contract_literal_rejects_non_literal(gate):
    contract, err = gate.contract_literal("CONTRACT = {'a': compute()}\n")
    assert contract is None and "literal_eval" in err


def test_contract_literal_reports_missing_block(gate):
    contract, err = gate.contract_literal("x = 1\n")
    assert contract is None and "CONTRACT" in err


def test_contract_literal_reports_syntax_error(gate):
    contract, err = gate.contract_literal("def broken(:\n")
    assert contract is None and "语法错误" in err


def test_contract_literal_reads_plain_dict(gate):
    contract, err = gate.contract_literal(
        "CONTRACT = {'fig_id': 'f', 'data_binding': {'bindings': {'y': 'Q1'}}}\n")
    assert err is None and contract["fig_id"] == "f"


# ── 7. 空数组边界：find_stats_calls 对无调用源码返回空（不是 None） ─────
def test_no_calls_returns_empty_list_not_none(gate):
    assert gate.find_stats_calls("x = 1\n") == []
    assert gate.find_stats_calls("def broken(:\n") is None, "语法错误才返回 None"
