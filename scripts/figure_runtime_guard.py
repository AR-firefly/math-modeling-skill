#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""figure_runtime_guard —— 作图脚本运行时统计守卫（作图契约 §六 第二层）。

用途
----
作图脚本只做**呈现**，不做**推断**：统计量（含误差棒）由编程手算好落盘到 `results/`，
作图手只读常量。AST 预检（`validate_figures.py`）只能降概率、抓不到拼接字符串与
`getattr`；本守卫在**运行时**把统计函数替换为抛异常，把「静态抓不到」的那部分补上。

用法
----
    python "<SKILL_ROOT>/scripts/figure_runtime_guard.py" <绘图脚本.py> [脚本自己的参数...]
    python "<SKILL_ROOT>/scripts/figure_runtime_guard.py" --json <绘图脚本.py>

退出码
------
    0  脚本跑完且无违规（被豁免的违规记 WARN，见下）
    1  脚本自身失败（异常 / 非零退出），且非守卫触发
    2  **FAIL**：捕获到禁用统计调用，且无有效豁免
    3  **WARN**：捕获到禁用统计调用，但有 `# STATS-EXEMPT: <非空理由>` + CONTRACT `statistical_exempt`
       （`--strict` 时按 FAIL 处理）

豁免（作图契约 §六）
--------------------
- 脚本内注释 `# STATS-EXEMPT: <非空理由>`；**空理由 = FAIL**，非空理由 = **WARN**
- 同时要求 CONTRACT 的 `statistical_exempt` 有非空内容（两处都在，防止随手补注释）

关键时序（批次 2 出口条件 3）
-----------------------------
monkeypatch **必须早于目标脚本 import matplotlib**。本文件在 patch 安装前**不 import
matplotlib**（`_install_patches()` 只碰 numpy/scipy/stdlib），因此当目标脚本执行
`matplotlib.use("Agg")`（`visualizer.py` 顶层 import 时锁定后端）时，patch 早已生效。
自检用例 `patch_order` 会实测断言这一点。

绕过面（诚实说明）
------------------
patch 作用在**对象属性**上而不是名字上：`from numpy import std`、`getattr(np, "std")`、
`eval("np.std", {"np": np})`、`__import__("numpy").std` 拿到的都是**同一个被替换的对象**，
因此这些写法绕不过去（自检 `dynamic_bypass` 实测）。

仍然存在的**绕过与豁免边界**（诚实列出，不得当成已封死）：
1. `importlib.reload(numpy)` 或从磁盘重新加载一份 numpy 副本可复位（极罕见，不覆盖）
2. 调用方为**第三方库内部**（如 matplotlib 自己的 `cbook.boxplot_stats` 用 `np.percentile`
   算箱线图须线）时**放行**——守卫拦的是「作图脚本自己算统计量」，不是「绘图库的渲染数学」。
   实测：只有 `np.percentile` 与 `ax.boxplot` 冲突，其余四个零冲突。放行次数记入报告的
   `internal_library_calls`，不静默。
3. `scipy.stats.mstats` 等**子模块命名空间**内的函数未逐个替换（顶层命名空间已覆盖绝大多数用法）
4. 若编程手把 std 算进 `results`、作图手读取即合规——**这是设计意图，不是漏洞**
   （作图契约 §六 职责边界）

> 机检只保证「没调用被禁统计函数」，**不保证图画得对**：数值是否等于 results、图是否好看，
> 分别靠 `check_figure_binding.py` 与人工/多模态目视（作图契约 §八）。
"""
from __future__ import annotations

import argparse
import ast
import importlib.machinery
import json
import re
import runpy
import sys
import traceback
from pathlib import Path

MARK = "FIGURE-RUNTIME-GUARD"

# 被禁统计函数（作图契约 §六 列表，一字不加）
NUMPY_FORBIDDEN = ("std", "var", "percentile", "quantile", "corrcoef")
SCIPY_STATS_SUBMODULES = ("mstats",)          # 额外逐名替换的子模块命名空间
SCIPY_OPTIMIZE_FORBIDDEN = ("curve_fit", "least_squares")
SKLEARN_FORBIDDEN_METHODS = ("fit", "predict")

# 绘图库内部调用放行的包前缀（渲染数学，不是作图脚本的推断）
INTERNAL_PACKAGES = ("matplotlib", "numpy", "scipy", "pandas", "PIL", "contourpy",
                     "cycler", "kiwisolver", "fontTools", "dateutil", "sklearn")


class StatisticsForbiddenError(RuntimeError):
    """作图脚本内出现被禁统计推断调用时抛出（不是普通脚本错误）。"""


VIOLATIONS = []            # [{"function": ..., "caller": ..., "traceback": [...]}]
EXEMPT_CALLS = {}          # {函数名: 放行次数}（绘图库内部调用）
INSTALL_REPORT = {}


# ───────────────────────── 调用方判定 ─────────────────────────

def _caller_module_name():
    """返回 blocked() 直接调用者所属模块名（拿不到返回空串）。"""
    try:
        return sys._getframe(2).f_globals.get("__name__", "") or ""
    except ValueError:  # pragma: no cover - 极深栈
        return ""


def _is_internal(name):
    root = (name or "").split(".")[0]
    return bool(root) and root in INTERNAL_PACKAGES


def _raiser(label, original):
    """把 original 替换为「从作图脚本直接调用即抛异常、被绘图库内部调用则放行」的包装。

    放行分支不是静默绕过：次数累计进 EXEMPT_CALLS，出现在报告里。
    """
    def blocked(*args, **kwargs):
        caller = _caller_module_name()
        if _is_internal(caller):
            EXEMPT_CALLS[label] = EXEMPT_CALLS.get(label, 0) + 1
            return original(*args, **kwargs)
        VIOLATIONS.append({
            "function": label,
            "caller": caller or "<unknown>",
            "traceback": _short_traceback(),
        })
        raise StatisticsForbiddenError(
            f"{MARK}: 作图脚本禁统计推断，调用 {label}（作图契约 §六）；"
            f"统计量须由编程手算好落盘 results/，作图手只读常量")
    blocked.__name__ = getattr(original, "__name__", label)
    blocked.__qualname__ = blocked.__name__
    return blocked


def _short_traceback(limit=6):
    frames = traceback.extract_stack()[:-2]
    return [f"{Path(f.filename).name}:{f.lineno} in {f.name}" for f in frames[-limit:]]


# ───────────────────────── patch 安装 ─────────────────────────

def _bind(owner, name, label, patched):
    """把 owner.name 替换为守卫包装；记账到 patched。"""
    original = getattr(owner, name, None)
    if original is None or not callable(original):
        return
    if getattr(original, "_mm_guard", False):
        return
    wrapper = _raiser(label, original)
    wrapper._mm_guard = True
    setattr(owner, name, wrapper)
    patched.append(label)
    # 同一对象常被定义模块再次暴露（如 numpy._core.fromnumeric.std），一并替换，
    # 堵住 `numpy._core.fromnumeric.std` 这类深路径（不影响放行判定，判据在调用方）。
    module = sys.modules.get(getattr(original, "__module__", "") or "")
    if module is not None and getattr(module, getattr(original, "__name__", ""), None) is original:
        setattr(module, original.__name__, wrapper)


def _install_numpy(patched):
    import numpy as np
    for name in NUMPY_FORBIDDEN:
        _bind(np, name, "numpy." + name, patched)


def _install_scipy(patched):
    try:
        import scipy.stats as stats
        import scipy.optimize as optimize
    except ImportError:  # pragma: no cover - 环境缺 scipy
        return
    for name in dir(stats):
        if name.startswith("_"):
            continue
        obj = getattr(stats, name)
        if callable(obj) and not isinstance(obj, type):
            _bind(stats, name, "scipy.stats." + name, patched)
        elif hasattr(obj, "fit"):        # rv_continuous/rv_discrete 实例（norm/t/chi2…）
            instance_fit = getattr(obj, "fit", None)
            if callable(instance_fit) and not getattr(instance_fit, "_mm_guard", False):
                wrapper = _raiser("scipy.stats.%s.fit" % name, instance_fit)
                wrapper._mm_guard = True
                try:
                    setattr(obj, "fit", wrapper)
                    patched.append("scipy.stats.%s.fit" % name)
                except (AttributeError, TypeError):  # pragma: no cover
                    pass
    for sub in SCIPY_STATS_SUBMODULES:
        try:
            module = importlib.import_module("scipy.stats." + sub)
        except ImportError:
            continue
        for name in dir(module):
            if name.startswith("_"):
                continue
            _bind(module, name, "scipy.stats.%s.%s" % (sub, name), patched)
    for name in SCIPY_OPTIMIZE_FORBIDDEN:
        _bind(optimize, name, "scipy.optimize." + name, patched)


class _WrappedLoader:
    """包装 sklearn 子模块 loader：模块执行完立即替换其内的 fit/predict。"""

    def __init__(self, inner):
        self._inner = inner

    def create_module(self, spec):
        return self._inner.create_module(spec)

    def exec_module(self, module):
        self._inner.exec_module(module)
        _patch_estimator_classes(module)

    def __getattr__(self, item):
        return getattr(self._inner, item)


def _patch_estimator_classes(module):
    patched = []
    for name, obj in list(vars(module).items()):
        if not isinstance(obj, type) or obj.__module__ != module.__name__:
            continue
        for method in SKLEARN_FORBIDDEN_METHODS:
            original = obj.__dict__.get(method)
            if not callable(original) or getattr(original, "_mm_guard", False):
                continue
            wrapper = _raiser("%s.%s.%s" % (module.__name__, name, method), original)
            wrapper._mm_guard = True
            setattr(obj, method, wrapper)
            patched.append("%s.%s" % (name, method))
    return patched


class _SklearnFinder:
    """meta_path finder：sklearn 模块加载后自动替换其内定义的 fit/predict。"""

    def find_spec(self, fullname, path=None, target=None):
        if not (fullname == "sklearn" or fullname.startswith("sklearn.")):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return None
        if isinstance(spec.loader, _WrappedLoader):
            return spec
        spec.loader = _WrappedLoader(spec.loader)
        return spec


def _install_sklearn(patched):
    try:
        import importlib.util
        if importlib.util.find_spec("sklearn") is None:
            return
    except (ImportError, ValueError):  # pragma: no cover
        return
    for finder in sys.meta_path:
        if isinstance(finder, _SklearnFinder):
            return
    sys.meta_path.insert(0, _SklearnFinder())


def install():
    """安装全部统计守卫 patch。**必须在任何 matplotlib import 之前调用。**"""
    if INSTALL_REPORT.get("installed"):
        return INSTALL_REPORT
    patched = []
    _install_numpy(patched)
    _install_scipy(patched)
    _install_sklearn(patched)
    INSTALL_REPORT.update({
        "installed": True,
        "patched": patched,
        # 实测断言点（出口条件 3）：patch 安装时 matplotlib 必须尚未被 import。
        "matplotlib_preloaded": "matplotlib" in sys.modules,
        "sklearn_hook": any(isinstance(f, _SklearnFinder) for f in sys.meta_path),
    })
    return INSTALL_REPORT


# ───────────────────────── 豁免判定 ─────────────────────────

_EXEMPT_RE = re.compile(r"#\s*STATS-EXEMPT\s*:(?P<reason>[^\n]*)")


def _contract_exemptions(source):
    """从脚本源码取 CONTRACT['statistical_exempt']（只做 AST 字面量解析，不执行）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "CONTRACT" for t in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return []
        if not isinstance(value, dict):
            return []
        exempt = value.get("statistical_exempt", [])
        if isinstance(exempt, str):
            return [exempt]
        if isinstance(exempt, (list, tuple)):
            return [x for x in exempt if isinstance(x, str)]
        return []
    return []


def exemption_state(source):
    """返回 (level, detail)。level ∈ {none, empty, valid}。

    空理由 FAIL：`# STATS-EXEMPT:` 后面没有非空文本，且 CONTRACT 侧也没有非空理由。
    """
    reasons = []
    for match in _EXEMPT_RE.finditer(source):
        if not match.group("reason").strip():
            reasons.append("")
    commented = [m.group("reason").strip() for m in _EXEMPT_RE.finditer(source)
                 if m.group("reason").strip()]
    contract = [r.strip() for r in _contract_exemptions(source) if r.strip()]
    detail = {"comment_empty": reasons, "comment_reasons": commented, "contract_reasons": contract}
    if commented and contract:
        return "valid", detail
    if reasons and not commented:
        return "empty", detail
    if commented or contract:
        # 只有一侧 → 不构成豁免（两处都要有，防随手补注释）
        return "empty", detail
    return "none", detail


# ───────────────────────── CLI ─────────────────────────

def run_guarded(script, argv):
    """在守卫下运行脚本，返回报告 dict。"""
    install()
    source = Path(script).read_text(encoding="utf-8-sig")
    level, detail = exemption_state(source)
    report = {"guard": "figure_runtime_guard", "script": str(Path(script).resolve()),
              "machine_checks_only": True, "install": dict(INSTALL_REPORT),
              "exemption": {"level": level, **detail}, "violations": [],
              "internal_library_calls": {}, "script_error": None}
    sys.argv = [str(script)] + list(argv)
    sys.path.insert(0, str(Path(script).resolve().parent))
    # 被守卫脚本的 stdout 重定向到 stderr：终端仍看得见，但不会污染守卫自己的报告流。
    real_stdout, sys.stdout = sys.stdout, sys.stderr
    try:
        runpy.run_path(str(script), run_name="__main__")
    except StatisticsForbiddenError:
        pass
    except SystemExit as exc:                      # 脚本自己 sys.exit()
        if exc.code not in (0, None):
            report["script_error"] = "SystemExit(%r)" % (exc.code,)
    except BaseException:                          # noqa: BLE001 - 报告所有脚本异常
        report["script_error"] = traceback.format_exc(limit=6)
    finally:
        sys.stdout = real_stdout
    report["violations"] = list(VIOLATIONS)
    report["internal_library_calls"] = dict(EXEMPT_CALLS)
    if VIOLATIONS:
        if level == "valid":
            report["level"] = "WARN"
            report["message"] = ("捕获 %d 次禁用统计调用，但存在非空 STATS-EXEMPT 理由 → WARN"
                                 % len(VIOLATIONS))
        elif level == "empty":
            report["level"] = "FAIL"
            report["message"] = ("捕获 %d 次禁用统计调用，且 STATS-EXEMPT 理由为空 → FAIL"
                                 % len(VIOLATIONS))
        else:
            report["level"] = "FAIL"
            report["message"] = "捕获 %d 次禁用统计调用，无豁免 → FAIL" % len(VIOLATIONS)
    elif report["script_error"]:
        report["level"] = "FAIL"
        report["message"] = "脚本自身失败（非守卫触发）"
    else:
        report["level"] = "PASS"
        report["message"] = "未捕获禁用统计调用"
    report["passed"] = report["level"] == "PASS"
    return report


def _exit_code(report, strict):
    if report["level"] == "PASS":
        return 0
    if report["level"] == "WARN":
        return 1 if strict else 3
    return 1 if report["script_error"] and not report["violations"] else 2


def render_text(report):
    lines = ["作图脚本运行时统计守卫（figure_runtime_guard）",
             "script: " + report["script"],
             "install: %d 个函数已替换；安装时 matplotlib 已预载 = %s"
             % (len(report["install"]["patched"]), report["install"]["matplotlib_preloaded"]),
             "[%s] %s" % (report["level"], report["message"])]
    for item in report["violations"]:
        lines.append("  - %s（调用方 %s）" % (item["function"], item["caller"]))
        for frame in item["traceback"]:
            lines.append("      " + frame)
    if report["internal_library_calls"]:
        lines.append("  （绘图库内部调用放行：%s）"
                     % ", ".join("%s×%d" % kv for kv in sorted(report["internal_library_calls"].items())))
    if report["script_error"]:
        lines.append("script_error:")
        lines.extend("  " + row for row in report["script_error"].splitlines())
    lines.append("note: 机检只保证「未调用被禁统计函数」，不证明图画得对；数值一致性与目视须另检")
    return "\n".join(lines)


# ───────────────────────── 自检（隔离：全部写入落在临时树内） ─────────────────────────

_CLEAN_SCRIPT = """\
# 合规作图脚本：只读常量画图，import matplotlib 后再调用统计函数也必须被抓
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
record = {"x": [1, 2, 3], "y": [4, 5, 6]}
fig, ax = plt.subplots()
ax.plot(record["x"], record["y"], marker="o")
ax.set_title("clean")
fig.savefig(Path(__file__).with_suffix(".png"), dpi=300)
plt.close(fig)
print("CLEAN-OK", np.__version__ is not None)
"""

_VIOLATIONS_CASES = {
    "np.std": "import numpy as np\nprint(np.std([1, 2, 3]))\n",
    "np.percentile": "import numpy as np\nprint(np.percentile([1, 2, 3], 50))\n",
    "scipy.stats": "import scipy.stats as st\nprint(st.ttest_ind([1, 2, 3], [2, 3, 4]).pvalue)\n",
    "scipy.optimize.curve_fit": ("import numpy as np\nfrom scipy.optimize import curve_fit\n"
                                 "f = lambda x, a: a * x\nprint(curve_fit(f, [1, 2], [2, 4])[0])\n"),
    "sklearn.fit": ("from sklearn.linear_model import LinearRegression\n"
                    "LinearRegression().fit([[1], [2]], [1, 2])\n"),
    # 反例夹具（非生产代码）：故意用 getattr/__import__/eval 三种动态写法尝试绕过守卫。
    # eval 在这里是**被测对象**——守卫必须证明动态取到的仍是同一被 patch 对象。
    # 该字符串只写进 tempfile 临时目录并由子进程执行，不进入任何产物路径。
    "dynamic_bypass": (
        "import numpy as np, builtins\n"
        "paths = [('getattr', getattr(np, 'std')),\n"
        "         ('dunder_import', __import__('numpy').std),\n"
        "         ('broken_attr', getattr(np, 'std', None)),\n"
        "         ('eval', eval('np.std', {'np': np}))]\n"
        "for label, fn in paths:\n"
        "    try:\n"
        "        fn([1, 2, 3])\n"
        "        print('BYPASSED', label)\n"
        "    except RuntimeError:\n"
        "        pass\n"
        "print('DONE')\n"),
    "boxplot_internal_allowed": (
        "import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\nax.boxplot([[1, 2, 3], [4, 5, 6]])\n"
        "fig.savefig('box.png', dpi=100)\nplt.close(fig)\nprint('BOX-OK')\n"),
}


def self_test():
    """隔离自检：全部写入与子进程 cwd 都在临时目录内。返回 (ok, report)。"""
    import subprocess
    import tempfile

    runner = Path(__file__).resolve()
    checks = []

    def run(script, extra=()):
        return subprocess.run([sys.executable, "-B", str(runner), "--json", str(script), *extra],
                              cwd=str(script.parent), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)

    with tempfile.TemporaryDirectory(prefix="figure_guard_selftest_") as temp:
        work = Path(temp)
        clean = work / "clean_figure.py"
        clean.write_text(_CLEAN_SCRIPT, encoding="utf-8")
        proc = run(clean)
        report = json.loads(proc.stdout)
        checks.append({"name": "clean_script_passes", "ok": proc.returncode == 0
                       and report["level"] == "PASS", "detail": report["message"]})
        # 出口条件 3：patch 安装时 matplotlib 尚未 import（否则后端已锁）
        checks.append({"name": "patch_precedes_matplotlib",
                       "ok": report["install"]["matplotlib_preloaded"] is False,
                       "detail": "matplotlib_preloaded=%s" % report["install"]["matplotlib_preloaded"]})

        import numpy as np
        for name, body in _VIOLATIONS_CASES.items():
            script = work / ("case_%s.py" % name.replace(".", "_"))
            script.write_text(body, encoding="utf-8")
            proc = run(script)
            report = json.loads(proc.stdout)
            if name == "boxplot_internal_allowed":
                ok = proc.returncode == 0 and report["level"] == "PASS"
                detail = "boxplot 内部 np.percentile 放行 %s" % report["internal_library_calls"]
            elif name == "dynamic_bypass":
                # getattr / __import__ / eval 三条动态路径必须都被抓（都调用过且都被拒）
                ok = (proc.returncode == 2 and report["level"] == "FAIL"
                      and len(report["violations"]) >= 4 and "BYPASSED" not in proc.stderr)
                detail = "violations=%d, 无 BYPASSED 输出" % len(report["violations"])
            elif name == "sklearn.fit":
                has_sklearn = True
                try:
                    import importlib.util
                    has_sklearn = importlib.util.find_spec("sklearn") is not None
                except (ImportError, ValueError):
                    has_sklearn = False
                ok = proc.returncode == 2 and report["level"] == "FAIL" and report["violations"]
                detail = ("sklearn 可用" if has_sklearn else "sklearn 缺失（跳过）")
                if not has_sklearn:
                    ok = True
            else:
                ok = proc.returncode == 2 and report["level"] == "FAIL" and bool(report["violations"])
                detail = "violations=%d" % len(report["violations"])
            checks.append({"name": "blocks_" + name, "ok": ok, "detail": detail})

        # 豁免：非空理由 → WARN；空理由 → FAIL；只在注释写、CONTRACT 不写 → 仍 FAIL
        stats_call = "import numpy as np\n# STATS-EXEMPT: %s\nprint(np.std([1, 2, 3]))\n"
        empty_contract = "CONTRACT = {\"fig_id\": \"x\", \"statistical_exempt\": []}\n"
        valid_contract = "CONTRACT = {\"fig_id\": \"x\", \"statistical_exempt\": [\"误差棒由编程手算好\"]}\n"
        cases = {
            "exempt_valid_is_warn": (stats_call % "1.5×IQR 截断仅用于稳定 y 轴，不进结论" + valid_contract, 3, "WARN"),
            "exempt_empty_is_fail": (stats_call % "" + empty_contract, 2, "FAIL"),
            "exempt_comment_only_is_fail": (stats_call % "有理由但 CONTRACT 没写" + empty_contract, 2, "FAIL"),
        }
        for name, (body, code, level) in cases.items():
            script = work / ("case_%s.py" % name)
            script.write_text(body, encoding="utf-8")
            proc = run(script)
            report = json.loads(proc.stdout)
            checks.append({"name": name, "ok": proc.returncode == code and report["level"] == level,
                           "detail": "exit=%d level=%s" % (proc.returncode, report["level"])})
        _ = np  # 显式说明：自检不依赖 numpy 直接调用

    ok = all(c["ok"] for c in checks)
    return ok, {"self_test_only": True, "project_verified": False, "passed": ok, "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("script", nargs="?", type=Path, help="被守卫的绘图脚本")
    parser.add_argument("script_args", nargs="*", help="传给绘图脚本的参数")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--strict", action="store_true", help="WARN 也算不通过")
    parser.add_argument("--self-test", action="store_true", help="隔离自检")
    args = parser.parse_args(argv)
    if getattr(sys.stdout, "reconfigure", None):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.self_test:
        ok, report = self_test()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    if args.script is None:
        parser.error("script 是必填，除非 --self-test")
    if not args.script.is_file():
        print("error: 脚本不存在: %s" % args.script, file=sys.stderr)
        return 2
    report = run_guarded(args.script, args.script_args)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))
    return _exit_code(report, args.strict)


if __name__ == "__main__":
    sys.exit(main())
