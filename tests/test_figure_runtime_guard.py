"""E / 批次 2 —— 作图脚本统计禁令：**运行时守卫**单测（作图契约 §六 第二层）。

覆盖出口条件 3：**monkeypatch 必须早于 `matplotlib.use("Agg")`**
（`visualizer.py` 顶层在 import 时锁后端）——本文件用实测报告字段
`install.matplotlib_preloaded is False` 断言这一点，而不是只断言「函数存在」。

覆盖出口条件 2 的运行时面：`getattr` / `eval` / `__import__` 动态写法**绕不过**
（patch 作用在对象属性上，动态取到的仍是同一被替换对象），脚本里若打印 `BYPASSED`
即视为守卫失效。

诚实边界
--------
本守卫只保证「没调用被禁统计函数」，**不保证图画得对**；数值一致性与目视另检
（`check_figure_binding.py` / 作图契约 §八）。守卫自身也在 docstring 里列了
残余绕过面（如 `importlib.reload`），本文件断言该声明存在，不假装已封死。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "figure_runtime_guard.py"

# 干净脚本：先 import matplotlib + use("Agg")，再调 np.std —— 时序反例的关键
_MATPLOTLIB_FIRST_THEN_STATS = """\
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
fig.savefig(Path(__file__).with_suffix(".png"), dpi=100)
plt.close(fig)
print(np.std([1, 2, 3]))     # 后端锁定之后才调用统计函数 —— 守卫必须已生效
"""
_MATPLOTLIB_FIRST_THEN_STATS = "from pathlib import Path\n" + _MATPLOTLIB_FIRST_THEN_STATS

_CLEAN = """\
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

record = json.loads('{"x": [1, 2, 3], "y": [4, 5, 6]}')
fig, ax = plt.subplots()
ax.plot(record["x"], record["y"], marker="o")
fig.savefig(Path(__file__).with_suffix(".png"), dpi=300)
plt.close(fig)
print("CLEAN-OK")
"""

# 反例夹具（非生产代码）：故意用 getattr / __import__ / eval 三种动态写法尝试绕过守卫。
# 下面的 eval 是**被测对象**——守卫必须证明动态取到的仍是同一个被 patch 的对象。
# 该字符串只写进 pytest 的 tmp_path 并由子进程执行，不进入任何产物路径。
_DYNAMIC_BYPASS = """\
import numpy as np

paths = [("getattr", getattr(np, "std")),
         ("dunder_import", __import__("numpy").std),
         ("eval", eval("np.std", {"np": np})),
         ("module_attr", np.std)]
for label, fn in paths:
    try:
        fn([1, 2, 3])
        print("BYPASSED", label)
    except RuntimeError:
        pass
print("DONE")
"""

_BARE_IMPORT = "from numpy import std\nprint(std([1, 2, 3]))\n"

_STATS_EXEMPT_EMPTY = ("CONTRACT = {'fig_id': 'x', 'statistical_exempt': []}\n"
                       "import numpy as np\n# STATS-EXEMPT:\nprint(np.std([1, 2, 3]))\n")
_STATS_EXEMPT_VALID = ("CONTRACT = {'fig_id': 'x', 'statistical_exempt': ['误差棒由编程手算好']}\n"
                       "import numpy as np\n"
                       "# STATS-EXEMPT: 误差棒由编程手算好，作图手只读常量\n"
                       "print(np.std([1, 2, 3]))\n")
_STATS_EXEMPT_ONE_SIDED = ("CONTRACT = {'fig_id': 'x', 'statistical_exempt': []}\n"
                           "import numpy as np\n"
                           "# STATS-EXEMPT: 有理由但 CONTRACT 没写\n"
                           "print(np.std([1, 2, 3]))\n")


def _write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def run_guard(script, *extra):
    """子进程跑守卫 CLI（隔离：全局 patch 不污染本进程的 numpy）。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT / "src"), env.get("PYTHONPATH", ""))))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("MPLCONFIGDIR", str(Path(script).parent / "_mplcache"))
    proc = subprocess.run([sys.executable, "-B", str(GUARD), "--json", str(script), *extra],
                          cwd=str(Path(script).parent), env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)
    assert proc.stdout.strip(), "守卫未产出 JSON：%s" % (proc.stdout + proc.stderr)[-400:]
    return proc.returncode, json.loads(proc.stdout), (proc.stderr or "")


# ── 出口条件 3：patch 早于后端加载（实测，不靠声明） ──────────────────
def test_patch_precedes_matplotlib_backend_lock(tmp_path):
    """反例：脚本先 `matplotlib.use("Agg")` 再调 np.std —— 守卫仍须抓到。

    `install.matplotlib_preloaded is False` 证明 patch 安装在目标脚本
    import matplotlib **之前**；若为 True，说明后端已锁、时序错位。
    """
    script = _write(tmp_path, "fig_late_stats.py", _MATPLOTLIB_FIRST_THEN_STATS)
    code, report, _ = run_guard(script)
    assert report["install"]["matplotlib_preloaded"] is False, \
        "patch 晚于 matplotlib 加载，后端已锁定（出口条件 3 不满足）"
    assert report["level"] == "FAIL" and report["violations"], report
    assert any("numpy.std" in v["function"] for v in report["violations"]), report["violations"]
    assert code == 2, "有违规且无豁免 → 退出码 2"


def test_clean_script_reports_backend_not_preloaded(tmp_path):
    """正例：合规脚本 PASS，且报告如实写「安装时 matplotlib 未预载」。"""
    script = _write(tmp_path, "fig_clean.py", _CLEAN)
    code, report, _ = run_guard(script)
    assert code == 0 and report["level"] == "PASS", report["message"]
    assert report["install"]["matplotlib_preloaded"] is False
    assert report["install"]["patched"], "必须至少替换掉 numpy 的 5 个统计函数"


# ── 出口条件 2（动态绕过面）：必须**真跑真抓** ────────────────────────
def test_dynamic_bypass_paths_are_all_blocked(tmp_path):
    """getattr / __import__ / eval / 模块属性四条路径全部被拦，且无 BYPASSED 输出。"""
    script = _write(tmp_path, "fig_bypass.py", _DYNAMIC_BYPASS)
    code, report, stderr = run_guard(script)
    assert code == 2 and report["level"] == "FAIL", report["message"]
    assert len(report["violations"]) >= 4, "四条动态路径都该被抓：%s" % report["violations"]
    assert "BYPASSED" not in stderr, "守卫被绕过：%s" % stderr[-400:]


def test_bare_from_import_is_blocked_at_runtime(tmp_path):
    """`from numpy import std` 在 AST 层抓得到，运行时同样必须抓到（双层一致）。"""
    script = _write(tmp_path, "fig_bare.py", _BARE_IMPORT)
    code, report, _ = run_guard(script)
    assert code == 2 and report["violations"], report


# ── 豁免：空理由 FAIL / 非空 WARN / 单侧 FAIL ─────────────────────────
def test_empty_exempt_reason_fails(tmp_path):
    script = _write(tmp_path, "fig_exempt_empty.py", _STATS_EXEMPT_EMPTY)
    code, report, _ = run_guard(script)
    assert report["level"] == "FAIL" and code == 2, report["message"]
    assert report["exemption"]["level"] == "empty"


def test_valid_exempt_reason_is_warn(tmp_path):
    script = _write(tmp_path, "fig_exempt_valid.py", _STATS_EXEMPT_VALID)
    code, report, _ = run_guard(script)
    assert report["level"] == "WARN" and code == 3, report["message"]
    assert report["exemption"]["level"] == "valid"


def test_one_sided_exempt_reason_fails(tmp_path):
    """只有注释、CONTRACT 没写 → 不构成豁免（防随手补一行注释）。"""
    script = _write(tmp_path, "fig_exempt_sided.py", _STATS_EXEMPT_ONE_SIDED)
    code, report, _ = run_guard(script)
    assert report["level"] == "FAIL" and code == 2
    assert report["exemption"]["level"] == "empty"


# ── 单元级：install() 的实测断言（进程内，用完还原） ───────────────────
def test_install_replaces_numpy_stats_in_process():
    """进程内直测：install() 后 numpy 统计函数确实被替换，调用即抛 StatisticsForbiddenError。

    **用完立即还原**——不还原会污染同进程后续测试（这是守卫的全局副作用）。
    后端时序（`matplotlib_preloaded is False`）只能在**子进程**里断言：
    pytest 进程本身已被其它测试 import 过 matplotlib，恒为 True。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("e_guard_unit", GUARD)
    guard = importlib.util.module_from_spec(spec)
    sys.modules["e_guard_unit"] = guard
    spec.loader.exec_module(guard)

    import numpy as np
    originals = {name: getattr(np, name) for name in guard.NUMPY_FORBIDDEN}
    try:
        report = guard.install()
        assert report["installed"] is True
        assert isinstance(report["matplotlib_preloaded"], bool)
        assert report["sklearn_hook"] in (True, False)
        for name in guard.NUMPY_FORBIDDEN:
            assert getattr(np, name) is not originals[name], "%s 未被替换" % name
        with pytest.raises(guard.StatisticsForbiddenError):
            np.std([1, 2, 3])
        # 动态路径取到的也是同一被替换对象（这才是"绕过无效"的机制）
        with pytest.raises(guard.StatisticsForbiddenError):
            getattr(np, "percentile")([1, 2, 3], 50)
    finally:
        for name, fn in originals.items():
            setattr(np, name, fn)


def test_guard_docstring_declares_residual_bypass():
    """诚实性回归：守卫必须自己写明残余绕过面，不得假装已封死。"""
    doc = GUARD.read_text(encoding="utf-8").split('"""')[1]
    assert "绕过" in doc, "docstring 须列出残余绕过面"
    assert "不保证图画得对" in doc, "docstring 须写明机检不保证图画得对"
    assert "设计意图" in doc or "职责边界" in doc, "docstring 须写明读 results 的统计量即合规"


def test_exit_code_contract_is_documented():
    """退出码 0/1/2/3 的口径写进 docstring，便于 CI 与人工共用一套判读。"""
    doc = GUARD.read_text(encoding="utf-8").split('"""')[1]
    for token in ("0  ", "2  **FAIL**", "3  **WARN**"):
        assert token.replace("  ", " ") in " ".join(doc.split()), token
