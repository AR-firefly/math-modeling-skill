#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_figure_binding —— 验收③「作图产出与 results 数值一致」的插桩比对（作图契约 §四/§五）。

它回答的唯一问题
----------------
**画进图里的数组，逐个值是否等于 `results/` 里的数？**

不是「脚本的 dict 里有没有这个键」（那可以造），也不是「`figures/data/*.json` 与
`results.json` 是否相等」（那本就靠复制，见 `run_all.py` 的 `_demo_plot_and_register_figures()`，
比对恒真 = 假验收）。这里 monkeypatch matplotlib，捕获**实际传给绘图函数的入参**，
再经脚本 CONTRACT 的 `data_binding.bindings` 解析回 results 键值逐值比对。

捕获面（与 `visualizer.py` 11 个绘图方法逐一对齐，作图契约 §五）
---------------------------------------------------------------
`plot / bar(含 yerr) / errorbar(含 yerr) / boxplot / fill / fill_between / axhline / axvline /
text / scatter / hist / imshow / contour / contourf / barh(含 xerr) / pcolormesh`

不进的：`ax.grid / set_xticks / set_xlabel / set_ylim / legend / colorbar / clabel` —— 坐标与装饰。

寻址口径（唯一，两段映射，不设第三段）
--------------------------------------
    CONTRACT["data_binding"] = {
        "results_path": "results/q1_results.json",
        "bindings": {"y": "Q1_基线_耗时", "yerr": "Q1_基线_耗时_std"},
    }
- 左值 = **绘图参数名**（matplotlib 侧，e.g. `y`、`yerr`）
- 右值 = **results 键名**
- `data_params` / `kwarg_params` 列出的绘图参数名 → 必须能在 `bindings` 找到 → 逐值比对
- `aux_params` → 排除比对（刻度、类别标签、轨迹坐标）
- **未声明的入参 → WARN 列出（不静默放过）**，`--strict` 视为 FAIL

> 为什么右值不写「脚本 dict 键」：`visualizer.py` 的 `_errorbar()` 读 `d["err"]`，传给
> matplotlib 时形参叫 `yerr=`——**捕获侧只看得到 `yerr`**。以捕获侧命名为准，冲突消失。

### 实跑后追加的三处最小扩展（不替换两段口径，只补「同名/多人参」这一档）

按契约原始 schema 实跑 `visualizer.py` 11 个方法后，发现三种**两段扁平表表达不了**的情形。
三处都写进 `plot_calls[]`（不再多开一套口径），且全部**默认关闭**：

| 扩展                       | 位置                          | 解决什么                                                                 | 不写会怎样                    |
| -------------------------- | ----------------------------- | ------------------------------------------------------------------------ | ----------------------------- |
| `plot_calls[].bindings`    | 该调用的覆盖表（优先全局表） | 同图内**不同对象**用了同名参数（`_fill_between:265` 的 `plot(y=mean)` 与 `:268` 的 `axhline(y=baseline)`） | 后一个对象被拿前一个键比对，误报 |
| 绑定值写成**列表**         | `bindings[name] = [k1, k2]`   | 同一参数**同一对象多次出现**（`_radar:249` 两条 series 都叫 `y`）         | 第二条 series 找不到键        |
| `plot_calls[].closed_loop` | 布尔，默认 False              | 雷达闭合描边：图中数组 = results + **首元素精确重复一次**                 | 形状不一致，11 个方法里唯一一个必挂 |

`closed_loop` 只接受「多出的末位 == 首位」的精确相等，不接受任何别的新数值——
所以它**无法**被用来把编造数据洗成合法。

用法
----
    python "<SKILL_ROOT>/scripts/check_figure_binding.py" --script figures/scripts/fig03_x.py \
        --project "<赛题目录>" --stage q1 [--strict] [--json]
    python "<SKILL_ROOT>/scripts/check_figure_binding.py" --self-test

退出码
------
    0 PASS / 1 FAIL（含 `--strict` 下的 WARN）/ 2 用法错误（脚本或 CONTRACT 不可用）

诚实说明
--------
本检查证明「画进图里的数 = results 里的数」，**不证明这些数算得对**（那归门禁2a），
也不证明图好看（那归目视检查，作图契约 §八）。若编程手落盘的 results 本身就是编的，
本检查照样 PASS。同理，它可以被「不画真数据」规避——所以它只与 `data_params` 声明结合
使用，未声明的入参一律 WARN 列出。
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import runpy
import sys
import traceback
from pathlib import Path

DEFAULT_TOL = 1e-9
RESULTS_BY_STAGE = {"q1": "results/q1_results.json", "final": "results/results.json"}

CAPTURED_METHODS = (
    "plot", "bar", "barh", "errorbar", "scatter", "hist", "boxplot",
    "imshow", "contour", "contourf", "pcolormesh", "fill", "fill_between",
    "axhline", "axvline", "text",
)
# 纯**视觉样式** kwarg：作图契约 §五 明说「hatch/capsize/color 是样式 kwarg，不列入
# data_params/kwarg_params」，故即使未声明也不警告（否则每张误差棒图都会 WARN）。
# 边界：凡是会**改变渲染出的数据形状/位置**的 kwarg（bins/levels/width/height/bottom/
# orientation/density/cumulative/range…）**不在此列**——它们必须显式声明为
# data_params 或 aux_params，否则按「未声明入参」WARN 列出。
STYLE_KWARGS = frozenset("""
color c alpha capsize hatch linewidth lw linewidths linestyle ls marker markersize ms
mew mfc mec label labels edgecolor ec facecolor fc cmap aspect s zorder fontsize ha va
rotation rotation_mode fmt inline extent origin interpolation vmin vmax norm colors
figsize dpi antialiased fill step rwidth stacked log visible clip_on transform url gid
picker snap rasterized path_effects animated clip_path figure data axes linestyles
drawstyle markevery markeredgecolor markeredgewidth markfacecolor sizes colorbar_only
tick_label error_kw ecolor elinewidth barsabove lolims uplims xlolims xuplims
fmt_style colorbar_only_only
""".split())

INTERNAL_PACKAGES = frozenset((
    "matplotlib", "numpy", "scipy", "pandas", "PIL", "contourpy", "cycler",
    "kiwisolver", "fontTools", "dateutil", "mpl_toolkits"))

# 位置参数名 = 绘图函数的**公开形参名**（与 visualizer.py 的调用逐一对齐，作图契约 §五）
POSITIONAL_NAMES = {
    "plot": ["x", "y", "fmt"],
    "bar": ["x", "y"], "barh": ["x", "y"],
    "errorbar": ["x", "y", "yerr", "xerr", "fmt"],
    "scatter": ["x", "y"],
    "hist": ["x"],
    "boxplot": ["x"],
    "imshow": ["X"],
    "contour": ["X", "Y", "Z"], "contourf": ["X", "Y", "Z"],
    "pcolormesh": ["X", "Y", "C"],
    "fill": ["x", "y"],
    "fill_between": ["x", "y1", "y2"],
    "axhline": ["y"], "axvline": ["x"],
    "text": ["x", "y", "s"],
}

# 同义参数名：作图契约 §四 的示例用数模语义名（bar 的 data_params 写 ["x","y"]），
# 而 matplotlib 的形参叫 height/width。两者都接受，槽位按**位置**对齐，
# 具体用哪个名字去查 bindings 以**声明的那个**为准（不替调用方改口径）。
PARAM_ALIASES = {
    "y": ("height",), "x": ("width",),
    "height": ("y",), "width": ("x",),
    "y1": ("lo",), "y2": ("hi",),
}


# ───────────────────────── 捕获器 ─────────────────────────

class BindingCapture:
    """monkeypatch matplotlib Axes 绘图方法，记录**实际入参**。

    必须在目标脚本 import matplotlib 之前 `install()`。
    """

    def __init__(self):
        self.calls = []
        self._installed = False

    def install(self):
        if self._installed:
            return self
        import matplotlib.axes

        for name in CAPTURED_METHODS:
            original = getattr(matplotlib.axes.Axes, name, None)
            if original is None:
                continue
            setattr(matplotlib.axes.Axes, name, self._wrap(name, original))
        self._installed = True
        self.matplotlib_preloaded = "matplotlib" in sys.modules
        return self

    def _wrap(self, name, original):
        capture = self

        def spy(*args, **kwargs):
            # 绑定的 Axes 实例由 matplotlib 作为第 0 个位置参数传入；丢掉它，
            # 位置参数名才能与绘图函数的公开形参对齐（ax.plot(x, y) → ["x", "y"]）。
            entry = {"method": name,
                     "caller": _caller_module(),
                     "positional": [_plain(a) for a in args[1:]],
                     "keyword": {k: _plain(v) for k, v in kwargs.items()}}
            capture.calls.append(entry)
            return original(*args, **kwargs)

        spy.__name__ = name
        return spy

    def external_calls(self):
        """只保留作图脚本自己发出的调用；绘图库内部调用（如 colorbar 画 pcolormesh）单列。"""
        external, internal = [], []
        for call in self.calls:
            root = (call.get("caller") or "").split(".")[0]
            (internal if root in INTERNAL_PACKAGES else external).append(call)
        return external, internal

    def by_method(self, external_only=True):
        grouped = {}
        calls = self.external_calls()[0] if external_only else self.calls
        for call in calls:
            grouped.setdefault(call["method"], []).append(call)
        return grouped


def _caller_module():
    """返回 spy 的直接调用者所属模块名（`matplotlib.colorbar` / `__main__` / …）。"""
    try:
        return sys._getframe(2).f_globals.get("__name__", "") or ""
    except ValueError:  # pragma: no cover
        return ""


def _plain(value):
    """把绘图入参转成可 JSON 化 / 可比较的普通结构；不可比较的保留类型名。"""
    import numpy as np
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "iufb":
            return value.tolist()
        return {"__ndarray__": str(value.dtype)}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if callable(value):
        return {"__callable__": getattr(value, "__name__", "?")}
    return {"__unsupported__": type(value).__name__}


# ───────────────────────── CONTRACT / results ─────────────────────────

def load_contract(script):
    """只做 AST 字面量解析取 CONTRACT，**不执行脚本**（执行交给插桩运行）。"""
    source = Path(script).read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, ["脚本语法错误：%s" % exc]
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "CONTRACT" for t in node.targets):
            try:
                return ast.literal_eval(node.value), []
            except (ValueError, SyntaxError) as exc:
                return None, ["CONTRACT 必须是字面量字典（可 literal_eval）：%s" % exc]
    return None, ["脚本内未找到 CONTRACT 元数据块（作图契约 §四）"]


def _resolve(node, results, prefix=""):
    """按 results 键路径取值，支持 `a.b[0].c` 与纯键名。返回 (found, value)。"""
    if not isinstance(node, str) or not node:
        return False, None
    parts, buf, i = [], "", 0
    while i < len(node):
        ch = node[i]
        if ch == "." and "[" not in buf:
            # 仅当 buf 非空才入栈：`a.b[0].c` 里 `]` 之后紧跟的 `.` 会让 buf 为空，
            # 若照收就会把空串混进路径，取值必然落空（docstring 声称支持该写法）。
            if buf:
                parts.append(buf)
                buf = ""
        elif ch == "[":
            if buf:
                parts.append(buf)
                buf = ""
            end = node.find("]", i)
            if end < 0:
                return False, None
            parts.append(int(node[i + 1:end]))
            i = end
        else:
            buf += ch
        i += 1
    if buf:
        parts.append(buf)

    current = results
    if parts and isinstance(current, dict) and parts[0] in current:
        current = current[parts[0]]
        parts = parts[1:]
    for part in parts:
        if isinstance(part, int):
            if not isinstance(current, (list, tuple)) or part >= len(current):
                return False, None
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                return False, None
            current = current[part]
    return True, current


def _scalar(value):
    import numpy as np
    if isinstance(value, (bool, str)) or value is None:
        return None
    if isinstance(value, np.ndarray):
        return value.astype(float).ravel() if value.dtype.kind in "iufb" else None
    if isinstance(value, np.generic):
        return np.array([value.item()], dtype=float)
    if isinstance(value, (int, float)):
        return np.array([value], dtype=float)
    if isinstance(value, (list, tuple)):
        try:
            return np.array(value, dtype=float).ravel()
        except (TypeError, ValueError):
            return None
    return None


def match_values(actual, expected, tol, closed_loop=False):
    """actual ≈ expected 逐值比对（形状必须一致；NaN 视为相等）。返回 (ok, 说明)。

    closed_loop=True 时（**必须由 plot_calls[].closed_loop 显式声明**，不得默认开）：
    允许实际数组 = results 数组 + 首元素重复一次，用于雷达图的闭合描边
    （`visualizer._radar:249` 的 `list(s["values"]) + [s["values"][0]]`）。
    闭合点必须是首元素的**精确重复**，不接受任何别的新数值。
    """
    import numpy as np
    left, right = _scalar(actual), _scalar(expected)
    if left is None or right is None:
        return (False, "不可数值比对：实际 %s / results %s"
                % (type(actual).__name__, type(expected).__name__))
    if left.shape != right.shape:
        if (closed_loop and left.size == right.size + 1 and left.size > 1
                and left.dtype.kind in "iuf" and right.dtype.kind in "iuf"
                and bool(np.isclose(left[-1], left[0], rtol=0, atol=0))):
            left = left[:-1]
        else:
            return False, "形状不一致：图中 %s vs results %s%s" % (
                left.shape, right.shape,
                "（closed_loop 闭合点不等于首元素）" if closed_loop else "")
    if left.size == 0:
        return True, "空数组"
    both_nan = np.isnan(left) & np.isnan(right)
    close = np.isclose(left, right, rtol=tol, atol=tol, equal_nan=True) | both_nan
    if bool(close.all()):
        return True, "%d 个值全部匹配（容差 %g）" % (left.size, tol)
    bad = int((~close).sum())
    idx = int(np.argmax(~close))
    return False, ("%d/%d 个值不匹配；首个差异 index %d：图中 %r vs results %r"
                   % (bad, left.size, idx, left.ravel()[idx], right.ravel()[idx]))


# ───────────────────────── 比对主体 ─────────────────────────

def compare(capture, contract, results, *, strict=False, tol=DEFAULT_TOL):
    """把捕获到的绘图入参按 CONTRACT 解析回 results，逐值比对。返回 (issues, warns, info)。"""
    issues, warns = [], []
    binding = (contract or {}).get("data_binding")
    if not isinstance(binding, dict):
        return ["CONTRACT 缺 data_binding（作图契约 §四 机检新增必填）"], warns
    if binding.get("kind") == "schematic":
        return issues, ["data_binding.kind=schematic：示意图无数值可比，数值比对豁免（作图契约 §一）"]
    bindings = binding.get("bindings")
    if not isinstance(bindings, dict) or not bindings:
        return ["data_binding.bindings 缺失或为空"], warns

    plot_calls = contract.get("plot_calls")
    if not isinstance(plot_calls, list) or not plot_calls:
        return ["CONTRACT 缺 plot_calls（声明 data_params/kwarg_params/aux_params）"], warns

    for index, spec in enumerate(plot_calls):
        if not isinstance(spec, dict):
            issues.append("plot_calls[%d] 必须是映射" % index)
            continue
        method = spec.get("method")
        if method not in CAPTURED_METHODS:
            issues.append("plot_calls[%d].method=%r 不在捕获面内" % (index, method))
            continue
        captured = capture.by_method().get(method)
        if not captured:
            issues.append("声明了 plot_calls[%d].method=%s，但插桩运行未捕获到该调用"
                          "（声明与实际绘图路径不符）" % (index, method))
            continue
        data_params = list(spec.get("data_params") or [])
        kwarg_params = list(spec.get("kwarg_params") or [])
        aux_params = list(spec.get("aux_params") or [])
        declared = set(data_params) | set(kwarg_params) | set(aux_params)
        # 逐调用覆盖：同一条 bindings 是**扁平**的 {绘图参数名: results 键名}，
        # 若一张图里两个不同对象用了同名参数（plot 的 y=均值 + axhline 的 y=基线值），
        # 扁平表无法区分。plot_calls[].bindings 可选覆盖该调用的绑定（优先于全局表）。
        call_bindings = dict(bindings)
        override = spec.get("bindings")
        if isinstance(override, dict):
            call_bindings.update(override)
        # 位置参数名沿用绘图函数的**公开形参名**（plot→x,y；contour→X,Y,Z；boxplot→x）。
        # 与 visualizer 调用一致；与调用方给的可选 positional_names 合并（后者优先）。
        positional_names = list(spec.get("positional_names")
                                or POSITIONAL_NAMES.get(method, []))

        occurrences = {}
        for call_index, call in enumerate(captured):
            tag = "plot_calls[%d] %s#%d" % (index, method, call_index)
            seen = set()
            for pos, value in enumerate(call["positional"]):
                canonical = positional_names[pos] if pos < len(positional_names) else None
                if canonical is None:
                    # 位置索引名本身**不算**声明；只有在 data_params/aux_params 里显式写了
                    # "argN" 才当作已声明（否则未声明 → WARN，不静默放过）
                    key = "arg%d" % pos
                    if key not in declared:
                        warns.append("%s 第 %d 个位置入参未声明（不在 data_params/aux_params 中；"
                                     "不静默放过）" % (tag, pos))
                    continue
                # 同义名归位：契约示例的 y/lo/hi 与 matplotlib 的 height/y1/y2 视为同一槽位
                name = next((alias for alias in (canonical,) + PARAM_ALIASES.get(canonical, ())
                             if alias in declared), canonical)
                if name not in declared:
                    warns.append("%s 第 %d 个位置入参（%s）未声明（不在 data_params/aux_params 中；"
                                 "不静默放过）" % (tag, pos, canonical))
                    continue
                seen.add(name)
                if name in aux_params:
                    continue
                occurrence = occurrences.get(name, 0)
                occurrences[name] = occurrence + 1
                _check_one(tag, name, value, spec, call_bindings, results, tol, issues,
                           occurrence)
            for name, value in call["keyword"].items():
                if name in seen or name in aux_params or name in STYLE_KWARGS:
                    continue
                if name not in data_params and name not in kwarg_params:
                    if _scalar(value) is not None:
                        warns.append("%s 未声明的绘图入参 %s（未在 data_params/kwarg_params/"
                                     "aux_params 中；不静默放过）" % (tag, name))
                    continue
                seen.add(name)
                occurrence = occurrences.get(name, 0)
                occurrences[name] = occurrence + 1
                _check_one(tag, name, value, spec, call_bindings, results, tol, issues,
                           occurrence)
            for name in data_params + kwarg_params:
                if name not in seen:
                    warns.append("%s 声明了入参 %s，但本次调用未传入" % (tag, name))
    if strict:
        issues.extend(warns)
        warns = []
    return issues, warns


def _check_one(tag, name, value, spec, bindings, results, tol, issues, occurrence=0):
    """单个绘图参数：找 results 键 → 逐值比对。

    `bindings[name]` 支持两种写法：
    - 字符串：该参数每次出现都绑同一个 results 键
    - **列表**：按该参数**第 N 次出现**依次取第 N 个键（雷达图两条 series 都是
      `y`，扁平表无法区分，这正是列表写法要解决的）
    """
    key = bindings.get(name)
    if isinstance(key, (list, tuple)):
        if not key or occurrence >= len(key) or not isinstance(key[occurrence], str):
            issues.append("%s 绘图参数 %s 第 %d 次出现超出 bindings 列表长度"
                          % (tag, name, occurrence + 1))
            return
        key = key[occurrence]
    if not isinstance(key, str) or not key:
        issues.append("%s 绘图参数 %s 在 data_binding.bindings 里没有对应 results 键"
                      % (tag, name))
        return
    found, expected = _resolve(key, results)
    if not found:
        issues.append("%s 绘图参数 %s → results 键 %r 不存在" % (tag, name, key))
        return
    ok, detail = match_values(value, expected, tol, closed_loop=bool(spec.get("closed_loop")))
    if not ok:
        issues.append("%s 绘图参数 %s（results 键 %s）%s" % (tag, name, key, detail))


# ───────────────────────── 单脚本检查 ─────────────────────────

def check_script(script, project, stage="q1", *, strict=False, tol=DEFAULT_TOL, extra_args=()):
    project = Path(project).resolve()
    script = Path(script).resolve()
    report = {"check": "check_figure_binding", "script": str(script), "stage": stage,
              "results_path": RESULTS_BY_STAGE.get(stage, ""), "machine_checks_only": True,
              "issues": [], "warns": [], "captured_methods": [], "internal_plot_calls": [],
              "level": "FAIL", "passed": False, "script_error": None}
    contract, contract_issues = load_contract(script)
    if contract_issues:
        report["issues"].extend(contract_issues)
        return report
    report["fig_id"] = contract.get("fig_id")
    results_rel = (contract.get("data_binding") or {}).get("results_path") \
        or RESULTS_BY_STAGE.get(stage, "")
    if results_rel not in tuple(RESULTS_BY_STAGE.values()):
        report["issues"].append(
            "data_binding.results_path=%r 超出契约限定（q1 只认 results/q1_results.json，"
            "final 只认 results/results.json）" % results_rel)
        return report
    results_path = project / results_rel
    if not results_path.is_file():
        report["issues"].append("results 文件不存在：%s" % results_rel)
        return report
    results = json.loads(results_path.read_text(encoding="utf-8"))
    report["results_path"] = results_rel

    capture = BindingCapture().install()
    cwd = os.getcwd()
    sys.argv = [str(script)] + list(extra_args)
    sys.path.insert(0, str(script.parent))
    real_stdout, sys.stdout = sys.stdout, sys.stderr
    try:
        os.chdir(str(script.parent))          # 脚本必须 __file__ 自定位；这里只保证相对 res 可用
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (0, None):
            report["script_error"] = "SystemExit(%r)" % (exc.code,)
    except BaseException:                      # noqa: BLE001
        report["script_error"] = traceback.format_exc(limit=8)
    finally:
        sys.stdout = real_stdout
        os.chdir(cwd)
    report["captured_methods"] = sorted(capture.by_method())
    report["matplotlib_preloaded"] = getattr(capture, "matplotlib_preloaded", None)
    external, internal = capture.external_calls()
    report["internal_plot_calls"] = sorted({c["method"] for c in internal})
    if report["script_error"]:
        report["issues"].append("脚本运行失败（非比对结论）：见 script_error")
        return report
    issues, warns = compare(capture, contract, results, strict=strict, tol=tol)
    report["issues"].extend(issues)
    report["warns"].extend(warns)
    report["level"] = "FAIL" if report["issues"] else ("WARN" if report["warns"] else "PASS")
    report["passed"] = report["level"] == "PASS"
    return report


def render_text(report):
    lines = ["作图数值绑定比对（check_figure_binding）",
             "script: %s" % report["script"],
             "results: %s（stage=%s）" % (report.get("results_path"), report["stage"]),
             "捕获到的绘图方法: %s" % ", ".join(report["captured_methods"] or ["（无）"]),
             "[%s]" % report["level"]]
    for item in report["issues"]:
        lines.append("  FAIL " + item)
    for item in report["warns"]:
        lines.append("  WARN " + item)
    if report["script_error"]:
        lines.append("script_error:")
        lines.extend("  " + row for row in report["script_error"].splitlines())
    lines.append("note: 只证明「画进图里的数 = results 里的数」，不证明数算得对，也不证明图好看")
    return "\n".join(lines)


# ───────────────────────── 自检（隔离：全部写入在临时树内） ─────────────────────────

# 自检共用真值表：既写进临时工程的 results/q1_results.json，也注入到图脚本
_SELFTEST_RESULTS = {
    "Q1_基线_耗时": [1.0, 2.0, 3.0], "Q1_基线_耗时_std": [0.1, 0.2, 0.3],
    "Q1_改进_耗时": [0.5, 1.0, 1.5], "Q1_改进_耗时_std": [0.05, 0.1, 0.15],
    "Q1_收敛曲线": [1.0, 0.5, 0.25], "Q1_样本": [1.0, 2.0, 2.0, 3.0],
    "Q1_热力": [[1.0, 2.0], [3.0, 4.0]], "Q1_曲面": [[1.0, 2.0], [3.0, 4.0]],
    "Q1_曲面x": [0.0, 1.0], "Q1_曲面y": [0.0, 1.0], "Q1_分布": [1.0, 2.0, 2.0, 3.0],
    "Q1_区间下限": [0.5, 1.0, 1.5], "Q1_区间上限": [1.5, 2.5, 3.5],
    "Q1_基线值": 2.5, "Q1_雷达A": [0.8, 0.6, 0.7], "Q1_雷达B": [0.5, 0.9, 0.4],
    "Q1_离散": [1.0, 3.0, 2.0],
}

_SELFTEST_VIZ = """\
import numpy as np
from math_modeling.visualizer import Visualizer

RESULTS = %r
X = [0, 1, 2]
viz = Visualizer(output_dir=HERE, dpi=300)
viz.plot("line", {"x": X, "y": RESULTS["Q1_基线_耗时"]}, "L", save_name="fig1")
viz.plot("bar", {"x": X, "y": RESULTS["Q1_改进_耗时"]}, "B", save_name="fig2")
viz.plot("errorbar", {"x": X, "y": RESULTS["Q1_基线_耗时"], "err": RESULTS["Q1_基线_耗时_std"]},
         "E", save_name="fig3")
viz.plot("scatter", {"x": X, "y": RESULTS["Q1_离散"]}, "S", save_name="fig4")
viz.plot("box", {"y": [RESULTS["Q1_样本"], RESULTS["Q1_样本"]]}, "BX", save_name="fig5")
viz.plot("heatmap", {"z": np.asarray(RESULTS["Q1_热力"])}, "H", save_name="fig6")
viz.plot("hist", {"y": RESULTS["Q1_分布"], "bins": 3}, "HI", save_name="fig7")
viz.plot("contour", {"x": RESULTS["Q1_曲面x"], "y": RESULTS["Q1_曲面y"],
                     "z": np.asarray(RESULTS["Q1_曲面"]), "levels": 3}, "C", save_name="fig8")
viz.plot("contourf", {"x": RESULTS["Q1_曲面x"], "y": RESULTS["Q1_曲面y"],
                      "z": np.asarray(RESULTS["Q1_曲面"]), "levels": 3}, "CF", save_name="fig9")
viz.plot("radar", {"categories": ["a", "b", "c"],
                   "series": [{"label": "A", "values": RESULTS["Q1_雷达A"]},
                              {"label": "B", "values": RESULTS["Q1_雷达B"]}]}, "R", save_name="fig10")
viz.plot("fill_between", {"x": X, "mean": RESULTS["Q1_基线_耗时"],
                          "lo": RESULTS["Q1_区间下限"], "hi": RESULTS["Q1_区间上限"],
                          "baseline": RESULTS["Q1_基线值"]}, "FB", save_name="fig11")
print("VIZ-DONE")
""" % (_SELFTEST_RESULTS,)

# 11 个 visualizer 绘图方法逐一过**完整 compare() 路径**（§十 出口条件 1）。
# 每个方法一张独立脚本 + 独立 CONTRACT，避免同图多对象的同名参数互相串（如 plot 的 y）。
# 形式：方法名 → (绘图代码, plot_calls, bindings)
_METHOD_CASES = {
    "_line": (
        'viz.plot("line", {"x": R["Q1_横坐标"], "y": R["Q1_基线_耗时"]}, "L", save_name="m")',
        [{"method": "plot", "data_params": ["y"], "aux_params": ["x", "marker", "color"]}],
        {"y": "Q1_基线_耗时"}),
    "_bar": (
        'viz.plot("bar", {"x": R["Q1_横坐标"], "y": R["Q1_改进_耗时"]}, "B", save_name="m")',
        [{"method": "bar", "data_params": ["y"], "aux_params": ["x", "color", "edgecolor", "linewidth"]}],
        {"y": "Q1_改进_耗时"}),
    "_scatter": (
        'viz.plot("scatter", {"x": R["Q1_横坐标"], "y": R["Q1_离散"]}, "S", save_name="m")',
        [{"method": "scatter", "data_params": ["y"], "aux_params": ["x", "s", "alpha", "color"]}],
        {"y": "Q1_离散"}),
    "_box": (
        'viz.plot("box", {"y": [R["Q1_样本"]]}, "BX", save_name="m")',
        [{"method": "boxplot", "data_params": ["x"], "aux_params": []}],
        {"x": "Q1_样本"}),
    "_heatmap": (
        'viz.plot("heatmap", {"z": np.asarray(R["Q1_热力"])}, "H", save_name="m")',
        [{"method": "imshow", "data_params": ["X"], "aux_params": ["cmap", "aspect"]}],
        {"X": "Q1_热力"}),
    "_hist": (
        'viz.plot("hist", {"y": R["Q1_分布"], "bins": 3}, "HI", save_name="m")',
        [{"method": "hist", "data_params": ["x"], "aux_params": ["bins", "edgecolor", "color"]}],
        {"x": "Q1_分布"}),
    # 误差棒在 Axes.bar(yerr=)，不在 Axes.errorbar —— 第 3 版的失效模式
    "_errorbar": (
        'viz.plot("errorbar", {"x": R["Q1_横坐标"], "y": R["Q1_基线_耗时"], '
        '"err": R["Q1_基线_耗时_std"], "baseline": R["Q1_基线值"]}, "E", save_name="m")',
        [{"method": "bar", "data_params": ["y"], "kwarg_params": ["yerr"],
          "aux_params": ["x", "capsize", "hatch", "color", "edgecolor", "linewidth"],
          "bindings": {"y": "Q1_基线_耗时", "yerr": "Q1_基线_耗时_std"}},
         {"method": "axhline", "data_params": ["y"],
          "aux_params": ["color", "ls", "lw", "alpha", "label"],
          "bindings": {"y": "Q1_基线值"}}],
        {}),
    "_contour": (
        'viz.plot("contour", {"x": R["Q1_曲面x"], "y": R["Q1_曲面y"], '
        '"z": np.asarray(R["Q1_曲面"]), "levels": 3}, "C", save_name="m")',
        [{"method": "contour", "data_params": ["Z"],
          "aux_params": ["X", "Y", "levels", "fmt", "colorbar"]}],
        {"Z": "Q1_曲面"}),
    "_contourf": (
        'viz.plot("contourf", {"x": R["Q1_曲面x"], "y": R["Q1_曲面y"], '
        '"z": np.asarray(R["Q1_曲面"]), "levels": 3}, "CF", save_name="m")',
        [{"method": "contourf", "data_params": ["Z"],
          "aux_params": ["X", "Y", "levels", "cmap", "contour_lines"]}],
        {"Z": "Q1_曲面"}),
    # 雷达必须声明 closed_loop：图中数组 = results + 首元素重复一次（visualizer._radar:249）
    "_radar": (
        'viz.plot("radar", {"categories": ["a", "b", "c"], "series": '
        '[{"label": "A", "values": R["Q1_雷达A"]}, {"label": "B", "values": R["Q1_雷达B"]}]}, '
        '"R", save_name="m")',
        [{"method": "plot", "data_params": ["y"], "aux_params": ["x", "color", "lw", "label"],
          "closed_loop": True},
         {"method": "fill", "data_params": ["y"], "aux_params": ["x", "color", "alpha"],
          "closed_loop": True}],
        # 雷达两条 series 都叫 `y`：列表写法按第 N 次出现依次取第 N 个键
        {"y": ["Q1_雷达A", "Q1_雷达B"]}),
    "_fill_between": (
        'viz.plot("fill_between", {"x": R["Q1_横坐标"], "mean": R["Q1_基线_耗时"], '
        '"lo": R["Q1_区间下限"], "hi": R["Q1_区间上限"], "baseline": R["Q1_基线值"]}, '
        '"FB", save_name="m")',
        [{"method": "fill_between", "data_params": ["y1", "y2"],
          "aux_params": ["x", "color", "alpha", "label"]},
         {"method": "axhline", "data_params": ["y"],
          "aux_params": ["color", "ls", "lw", "alpha", "label"],
          "bindings": {"y": "Q1_基线值"}}],
        {}),
}
_METHOD_BINDINGS = {
    "y": "Q1_基线_耗时", "yerr": "Q1_基线_耗时_std", "x": "Q1_样本",
    "y1": "Q1_区间下限", "y2": "Q1_区间上限", "Z": "Q1_曲面",
}
_METHOD_HEAD = """\
from pathlib import Path
import json
import numpy as np
from math_modeling.visualizer import Visualizer
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1]
R = json.loads((ROOT / "results/q1_results.json").read_text(encoding="utf-8"))
CONTRACT = %r
viz = Visualizer(output_dir=str(OUT), dpi=300)
"""
_METHOD_RESULTS = dict(_SELFTEST_RESULTS, **{"Q1_横坐标": [0, 1, 2]})


class _Slice:
    """把捕获器切片成「只含本次运行」的视图，供 compare() 使用。

    用**已见调用 id 集合**过滤，而不是索引切片——外部/内部调用会交错，
    按索引切会在两种列表之间错位（这正是本表第一次跑出来的 bug）。
    """

    def __init__(self, capture, seen):
        self._capture, self._seen = capture, seen

    @classmethod
    def snapshot(cls, capture):
        return cls(capture, {id(call) for call in capture.calls})

    def _fresh(self, calls):
        return [call for call in calls if id(call) not in self._seen]

    def by_method(self, external_only=True):
        grouped = {}
        calls = self._fresh(self._capture.external_calls()[0] if external_only
                            else self._capture.calls)
        for call in calls:
            grouped.setdefault(call["method"], []).append(call)
        return grouped

    def external_calls(self):
        external, internal = self._capture.external_calls()
        return self._fresh(external), self._fresh(internal)


def _per_method_table(project, results, work):
    """§十 出口条件 1：11 个绘图方法各跑一次，列出每个方法的 compare() 结果。

    每个方法一份独立脚本、一份独立 CONTRACT，防止同图多对象的同名参数互相串。
    """
    capture = BindingCapture().install()
    table, failures = [], []
    for method, (code, plot_calls, bindings) in _METHOD_CASES.items():
        contract = {"fig_id": "method%s" % method,
                    "data_binding": {"results_path": "results/q1_results.json",
                                     "bindings": dict(_METHOD_BINDINGS, **bindings)},
                    "plot_calls": plot_calls}
        # 写在真实的 figures/scripts/ 下：脚本用 __file__ 定位 ROOT=parents[2]，
        # 放到别处会解析错项目根（正好也验证了 __file__ 相对定位这一硬规范）
        script = Path(work) / "method%s.py" % method if work.parts[-1] == "scripts" else \
            Path(project) / "figures" / "scripts" / ("method%s.py" % method)
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(_METHOD_HEAD % contract + code + "\n", encoding="utf-8")
        slice_view = _Slice.snapshot(capture)
        real_stdout, sys.stdout = sys.stdout, sys.stderr
        try:
            runpy.run_path(str(script), run_name="__main__")
        except BaseException:                       # noqa: BLE001
            failures.append("%s: 脚本运行失败 %s" % (method,
                                                    traceback.format_exc(limit=2)[-180:]))
            table.append("%s=CRASH" % method)
            continue
        finally:
            sys.stdout = real_stdout
        issues, warns = compare(slice_view, contract, results)
        if issues:
            failures.append("%s: %s" % (method, issues[0][:160]))
            table.append("%s=FAIL" % method)
        elif warns:
            failures.append("%s(WARN): %s" % (method, warns[0][:160]))
            table.append("%s=WARN" % method)
        else:
            table.append("%s=PASS" % method)
    return table, failures


def _match_spot_checks(external, results):
    """自检用真值表：抽各方法的真实捕获入参逐值对 results（验证「捕获=画进图里的数」）。"""
    def first(method):
        calls = external.get(method)
        return calls[0] if calls else None

    def eq(actual, key):
        return match_values(actual, results[key], 1e-9)[0]

    ok = True
    line = first("plot")
    ok &= bool(line) and eq(line["positional"][1], "Q1_基线_耗时")
    bar = first("bar")
    ok &= bool(bar) and eq(bar["positional"][1], "Q1_改进_耗时")
    # 误差棒走 Axes.bar(yerr=)，不在 Axes.errorbar —— 这条正是第 3 版的失效模式
    errorbar_bars = [c for c in external.get("bar", []) if "yerr" in c["keyword"]]
    ok &= bool(errorbar_bars) and eq(errorbar_bars[0]["keyword"]["yerr"], "Q1_基线_耗时_std")
    band = first("fill_between")
    ok &= (bool(band) and eq(band["positional"][1], "Q1_区间下限")
           and eq(band["positional"][2], "Q1_区间上限"))
    hist = first("hist")
    ok &= bool(hist) and eq(hist["positional"][0], "Q1_分布") and hist["keyword"]["bins"] == 3
    # 雷达闭合：图中数组 = results 副本 + 首元素重复一次（visualizer._radar:249）
    radar_fill = first("fill")
    radar_len = [len(c["positional"][1]) for c in external.get("fill", [])]
    ok &= bool(radar_fill) and radar_len == [4, 4]
    radar_arr = external["fill"][0]["positional"][1] + external["fill"][1]["positional"][1]
    ok &= match_values(radar_arr, [0.8, 0.6, 0.7, 0.8, 0.5, 0.9, 0.4, 0.5], 1e-9)[0]
    box = first("boxplot")
    ok &= bool(box) and eq(box["positional"][0][0], "Q1_样本")
    heat = first("imshow")
    ok &= bool(heat) and eq(heat["positional"][0], "Q1_热力")
    axh = first("axhline")
    ok &= bool(axh) and eq(axh["positional"][0], "Q1_基线值")
    return bool(ok)


def self_test():
    import subprocess
    import tempfile

    runner = Path(__file__).resolve()
    checks = []
    with tempfile.TemporaryDirectory(prefix="check_binding_selftest_") as temp:
        work = Path(temp)
        project = work / "project"
        (project / "results").mkdir(parents=True)
        (project / "figures" / "scripts").mkdir(parents=True)
        results = dict(_METHOD_RESULTS)
        (project / "results" / "q1_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(
            (str(Path(runner).resolve().parents[1] / "src"),)), PYTHONDONTWRITEBYTECODE="1",
            MPLCONFIGDIR=str(work / "mpl"))

        def run_case(name, contract, plot_body, expect_level, strict=False):
            script = project / "figures" / "scripts" / ("case_%s.py" % name)
            script.write_text(
                "from pathlib import Path\nHERE = str(Path(__file__).resolve().parent)\n"
                "import numpy as np\n"
                "from math_modeling.visualizer import Visualizer\n"
                "CONTRACT = %r\n" % (contract,) + plot_body, encoding="utf-8")
            command = [sys.executable, "-B", str(runner), "--json",
                       "--script", str(script), "--project", str(project), "--stage", "q1"]
            if strict:
                command.append("--strict")
            proc = subprocess.run(command, cwd=str(work), env=env,
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=300)
            try:
                report = json.loads(proc.stdout)
            except json.JSONDecodeError:
                return {"name": name, "ok": False,
                        "detail": "输出非 JSON：%s" % (proc.stdout + proc.stderr)[-500:]}
            ok = report["level"] == expect_level
            return {"name": name, "ok": ok,
                    "detail": "level=%s expect=%s issues=%d warns=%d"
                              % (report["level"], expect_level, len(report["issues"]),
                                 len(report["warns"])),
                    "first_issue": (report["issues"] or [""])[0][:220]}

        # 坐标/刻度用 np.arange（不来自 results）→ 列 aux_params → 不该报（出口条件 2 反例①）
        axis = [0, 1, 2]
        axis_contract = {
            "fig_id": "case",
            "data_binding": {"results_path": "results/q1_results.json",
                             "bindings": {"y": "Q1_基线_耗时"}},
            "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}],
        }
        checks.append(run_case("aux_axis_ticks_not_reported", axis_contract, """
viz = Visualizer(output_dir=HERE, dpi=300)
viz.plot("line", {"x": %r, "y": %r}, "t", save_name="ok")
print("OK")
""" % (axis, results["Q1_基线_耗时"]), "PASS"))

        # 伪造成绩单：CONTRACT 声明绑到 results 键，但画的是编的数 → 必须 FAIL（反例②）
        checks.append(run_case("forged_painted_data_is_fail", axis_contract, """
viz = Visualizer(output_dir=HERE, dpi=300)
viz.plot("line", {"x": %r, "y": [9.0, 9.0, 9.0]}, "t", save_name="bad")
print("OK")
""" % (axis,), "FAIL"))

        # 声明写错键名 → 必须 FAIL
        wrong_key = dict(axis_contract)
        wrong_key = {"fig_id": "case",
                     "data_binding": {"results_path": "results/q1_results.json",
                                      "bindings": {"y": "Q1_不存在的键"}},
                     "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}]}
        checks.append(run_case("wrong_results_key_is_fail", wrong_key, """
viz = Visualizer(output_dir=HERE, dpi=300)
viz.plot("line", {"x": %r, "y": %r}, "t", save_name="bad")
print("OK")
""" % (axis, results["Q1_基线_耗时"]), "FAIL"))

        # 未声明的、影响渲染数据的入参（hist 的 bins）→ WARN；--strict 下 FAIL（反例③）
        hist_contract = {
            "fig_id": "case",
            "data_binding": {"results_path": "results/q1_results.json",
                             "bindings": {"x": "Q1_分布"}},
            "plot_calls": [{"method": "hist", "data_params": ["x"], "aux_params": []}],
        }
        hist_body = """
viz = Visualizer(output_dir=HERE, dpi=300)
viz.plot("hist", {"y": %r, "bins": 7}, "t", save_name="h")
print("OK")
""" % (results["Q1_分布"],)
        checks.append(run_case("undeclared_bins_is_warn", hist_contract, hist_body, "WARN"))
        checks.append(run_case("undeclared_bins_is_fail_in_strict", hist_contract, hist_body,
                               "FAIL", strict=True))
        # 同一张图把 bins 声明进 aux_params → 不再警告
        hist_ok = dict(hist_contract)
        hist_ok = {"fig_id": "case",
                   "data_binding": {"results_path": "results/q1_results.json",
                                    "bindings": {"x": "Q1_分布"}},
                   "plot_calls": [{"method": "hist", "data_params": ["x"], "aux_params": ["bins"]}]}
        checks.append(run_case("declared_bins_passes", hist_ok, hist_body, "PASS"))

        # 雷达闭合声明：closed_loop 开启后，图里多出的闭合点（首元素重复）不误报；
        # 未声明 closed_loop 时必须按形状不一致抓住（防拿"闭合"当万能挡箭牌）
        radar_contract = {
            "fig_id": "case",
            "data_binding": {"results_path": "results/q1_results.json",
                             "bindings": {"y": "Q1_雷达A"}},
            "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"],
                            "closed_loop": True}],
        }
        radar_body = """
viz = Visualizer(output_dir=HERE, dpi=300)
viz.plot("radar", {"categories": ["a", "b", "c"],
                   "series": [{"label": "A", "values": %r}]}, "R", save_name="r")
print("OK")
""" % (results["Q1_雷达A"],)
        checks.append(run_case("radar_closed_loop_declared_passes", radar_contract, radar_body,
                               "PASS"))
        radar_strict_contract = {
            "fig_id": "case",
            "data_binding": {"results_path": "results/q1_results.json",
                             "bindings": {"y": "Q1_雷达A"}},
            "plot_calls": [{"method": "plot", "data_params": ["y"], "aux_params": ["x"]}],
        }
        checks.append(run_case("radar_without_closed_loop_is_shape_fail",
                               radar_strict_contract, radar_body, "FAIL"))

        # 声明的 method 与实际绘图路径不符 → FAIL（防声明与代码脱钩）
        mismatch = {"fig_id": "case",
                    "data_binding": {"results_path": "results/q1_results.json",
                                     "bindings": {"y": "Q1_基线_耗时"}},
                    "plot_calls": [{"method": "bar", "data_params": ["y"], "aux_params": ["x"]}]}
        checks.append(run_case("declared_method_not_painted_is_fail", mismatch, """
viz = Visualizer(output_dir=HERE, dpi=300)
viz.plot("line", {"x": %r, "y": %r}, "t", save_name="m")
print("OK")
""" % (axis, results["Q1_基线_耗时"]), "FAIL"))

        # results_path 超出契约限定（指到 demo 的 figures/fig1.json）→ FAIL
        out_of_contract = {"fig_id": "case",
                           "data_binding": {"results_path": "figures/fig1.json",
                                            "bindings": {"y": "Q1_基线_耗时"}},
                           "plot_calls": [{"method": "plot", "data_params": ["y"],
                                           "aux_params": ["x"]}]}
        checks.append(run_case("results_path_out_of_contract_is_fail", out_of_contract, """
viz = Visualizer(output_dir=HERE, dpi=300)
viz.plot("line", {"x": %r, "y": %r}, "t", save_name="o")
print("OK")
""" % (axis, results["Q1_基线_耗时"]), "FAIL"))

        # 真实 visualizer 11 方法全跑一遍：捕获面覆盖
        viz_script = project / "figures" / "scripts" / "all_methods.py"
        viz_script.write_text("from pathlib import Path\n"
                              "HERE = str(Path(__file__).resolve().parent)\n"
                              + _SELFTEST_VIZ, encoding="utf-8")
        capture = BindingCapture().install()
        real_stdout, sys.stdout = sys.stdout, sys.stderr
        try:
            runpy.run_path(str(viz_script), run_name="__main__")
        except BaseException:  # noqa: BLE001
            checks.append({"name": "visualizer_11_methods", "ok": False,
                           "detail": traceback.format_exc(limit=4)[-400:]})
        else:
            external = capture.by_method()
            every = capture.by_method(external_only=False)
            got = sorted(every)
            want = ["axhline", "bar", "boxplot", "contour", "contourf", "errorbar", "fill",
                    "fill_between", "hist", "imshow", "plot", "scatter"]
            checks.append({"name": "visualizer_11_methods", "ok": all(m in got for m in want),
                           "detail": "全量捕获 %s；作图脚本自身调用 %s"
                                     % (got, sorted(external)),
                           "missing": [m for m in want if m not in got]})
            # radar 的 fill/plot 与 fill_between 的 axhline/text 必须真被捕获
            checks.append({"name": "radar_fill_captured",
                           "ok": len(external.get("fill", [])) >= 2,
                           "detail": "作图脚本自身 fill×%d（雷达两条序列）"
                                     % len(external.get("fill", []))})
            checks.append({"name": "errorbar_baseline_axhline_captured",
                           "ok": "axhline" in external,
                           "detail": "作图脚本自身 axhline×%d" % len(external.get("axhline", []))})
            # 真值表：11 个 visualizer 方法 + 捕获到的真实入参必须能与 results 对上
            checks.append({"name": "captured_values_match_results",
                           "ok": _match_spot_checks(external, results),
                           "detail": "对 plot/bar/errorbar-yerr/fill_between/hist/bins 抽样逐值比对"})
        finally:
            sys.stdout = real_stdout

        # §十 出口条件 1：11 个绘图方法各跑一次，逐一过完整 compare() 路径，列出每个方法结果
        table, failures = _per_method_table(project, results, work)
        checks.append({"name": "per_method_binding_table", "ok": not failures,
                       "detail": "  ".join(table), "failures": failures})
    ok = all(c["ok"] for c in checks)
    return ok, {"self_test_only": True, "project_verified": False, "passed": ok, "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--script", type=Path, help="被检查的绘图脚本")
    parser.add_argument("--project", type=Path, help="赛题目录（results/ 所在根）")
    parser.add_argument("--stage", choices=("q1", "final"), default="q1")
    parser.add_argument("--tol", type=float, default=DEFAULT_TOL, help="数值容差（默认 1e-9 精确）")
    parser.add_argument("--strict", action="store_true", help="未声明入参的 WARN 视为 FAIL")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if getattr(sys.stdout, "reconfigure", None):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.self_test:
        ok, report = self_test()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    if not args.script or not args.project:
        parser.error("--script 与 --project 必填，除非 --self-test")
    report = check_script(args.script, args.project, stage=args.stage, strict=args.strict,
                          tol=args.tol)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
