#!/usr/bin/env python3
"""画图源码静态预检（matplotlib 版，适配数模国赛 300dpi PNG）。

改编自 nature-figure 的 validate_figure.py（Apache-2.0，nature-skills，作者 Yuan1z0825 等），
见仓库 NOTICE.md。保留了其"无依赖静态预检"的检查框架，把 Nature 期刊口径换成国赛口径：
- 中文字体（SimHei/微软雅黑/SimSun）防乱码
- 禁 rainbow/jet/hsv 配色
- PNG 导出 + dpi ≥ 300
- 采样/数据排除必须显式记录（防五样检验失真）

用法：
    python scripts/validate_figures.py path/to/figure.py
    python scripts/validate_figures.py path/to/figure.py --json
    python scripts/validate_figures.py path/to/figure.py --strict   # WARN 也算不通过
    python scripts/validate_figures.py --self-test
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


LEVEL_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}


@dataclass(frozen=True)
class Finding:
    check_id: str
    level: str
    message: str
    evidence: list[str]

    @property
    def passed(self) -> bool:
        return self.level == "PASS"


def finding(check_id: str, level: str, message: str, evidence: Iterable[str] = ()) -> Finding:
    if level not in LEVEL_ORDER:
        raise ValueError(f"unknown finding level: {level}")
    return Finding(check_id, level, message, list(evidence))


def regex_hits(patterns: Iterable[str], source: str, flags: int = re.IGNORECASE) -> list[str]:
    return [m.group(0).strip() for p in patterns if (m := re.search(p, source, flags))]


def check_syntax(source: str) -> Finding:
    try:
        ast.parse(source)
    except SyntaxError as exc:
        loc = f"line {exc.lineno}" if exc.lineno else "unknown line"
        return finding("SOURCE-SYNTAX", "FAIL", f"Python 语法错误 @ {loc}: {exc.msg}")
    return finding("SOURCE-SYNTAX", "PASS", "源码语法通过")


def check_cn_font(source: str, source_path: Path | None = None) -> Finding:
    hits = regex_hits([r"SimHei|Microsoft YaHei|SimSun|font\.sans-serif|font\.family"],
                      source)
    if hits:
        return finding("CN-FONT", "PASS", "配置了中文字体（SimHei/微软雅黑/SimSun）", hits)
    # 集中式配置：源码 import 的本地模块（如 examples/utils.py）里配了字体 → 不算误报
    if source_path:
        for m in re.finditer(r"(?:from\s+(\w+)\s+import|import\s+(\w+))", source):
            mod = m.group(1) or m.group(2)
            mod_path = source_path.parent / f"{mod}.py"
            if mod_path.is_file():
                try:
                    mod_src = mod_path.read_text(encoding="utf-8-sig")
                except OSError:
                    continue
                if regex_hits([r"SimHei|Microsoft YaHei|SimSun|font\.sans-serif|font\.family"], mod_src):
                    return finding("CN-FONT", "PASS",
                                   f"中文字体集中配置在 import 的本地模块 {mod}.py", [f"{mod}.py: rcParams font.sans-serif"])
    return finding("CN-FONT", "FAIL", "未配置中文字体，图表中文可能乱码（rcParams font.sans-serif 需含 SimHei/微软雅黑）")


# 一层嵌套括号匹配（处理 text(b.get_x()...) 等含函数调用的标注）
_PAIR = r"\((?:[^()]|\([^()]*\))*\)"


def explicit_font_sizes(source: str) -> list[float]:
    # 只查"正文/轴标签级"字号（rcParams 与 axes 标签设置）：
    # 剔除图内局部标注（clabel 等值线/text 数据标注/annotate/set_xticklabels 等），
    # 它们 8-9pt 在 300dpi 下可读，属正常设计，不该当正文字号误报（E2-01）。
    cleaned = re.sub(r"(?:clabel|text|annotate|set_xticklabels|set_yticklabels)" + _PAIR,
                     "", source)
    return [float(v) for v in re.findall(
        r"(?:font\.size|fontsize|labelsize|titlesize|legend\.fontsize)\s*['\"]?\s*[:=]\s*(\d+(?:\.\d+)?)",
        cleaned, re.IGNORECASE)]


def check_font_sizes(source: str) -> Finding:
    sizes = explicit_font_sizes(source)
    if not sizes:
        return finding("FONT-SIZE", "WARN", "未显式设置字号，需人工确认最终尺寸可读")
    minimum = min(sizes)
    if minimum < 10:
        return finding("FONT-SIZE", "FAIL", f"字号低于 10pt 下限（国赛 300dpi 下正文需清晰）：{minimum:g}pt")
    return finding("FONT-SIZE", "PASS", f"显式字号均 ≥10pt（最小 {minimum:g}pt）")


def check_colormaps(source: str) -> Finding:
    hits = regex_hits(
        [r"cmap\s*=\s*['\"](?:jet|rainbow|hsv)['\"]",
         r"plt\.cm\.(?:jet|rainbow|hsv)\b",
         r"\brainbow\s*\("], source)
    if hits:
        return finding("COLOR-MAP", "FAIL", "rainbow/jet/hsv 非出版安全配色（色盲不可辨/灰度失真）", hits)
    return finding("COLOR-MAP", "PASS", "未用 rainbow/jet/hsv 配色")


def check_png_export(source: str) -> Finding:
    has_png = bool(re.search(r"savefig\([^)]*\.png|\.png['\"\s,)]", source, re.IGNORECASE))
    if has_png:
        return finding("EXPORT-PNG", "PASS", "存在 PNG 导出（savefig *.png）")
    return finding("EXPORT-PNG", "WARN", "未发现 PNG 导出语句，确认出图路径是 figures/*.png")


def check_resolution(source: str) -> Finding:
    values = [int(v) for v in re.findall(r"(?:dpi|res)\s*[:=]\s*(\d+)", source, re.IGNORECASE)]
    if not values:
        return finding("RASTER-DPI", "WARN", "未显式设置 DPI，需人工确认 ≥300")
    below = sorted({v for v in values if v < 300})
    if below:
        return finding("RASTER-DPI", "FAIL", f"DPI 低于 300 国赛下限：{below}", [str(v) for v in below])
    return finding("RASTER-DPI", "PASS", f"DPI ≥ 300（{max(values)}）")


def check_sampling(source: str) -> Finding:
    hits = regex_hits([r"np\.random\.choice\s*\(", r"\.sample\s*\(", r"sample_frac\s*\("], source)
    if not hits:
        return finding("DATA-SAMPLING", "PASS", "未发现高置信采样操作")
    documented = bool(re.search(r"sample_size|random_state|sampling_rationale|seed", source, re.IGNORECASE))
    if documented:
        return finding("DATA-SAMPLING", "WARN", "存在采样但已记录参数；确认采样合理且记录在 process_record", hits)
    return finding("DATA-SAMPLING", "WARN", "存在采样但未见参数记录，采样会改变结果需显式说明", hits)


def check_exclusions(source: str) -> Finding:
    hits = regex_hits([r"\.dropna\s*\(", r"drop_na\s*\("], source)
    if not hits:
        return finding("DATA-EXCLUSION", "PASS", "未发现缺失数据排除")
    reported = bool(re.search(r"n_before|n_after|before_count|after_count|excluded_count", source, re.IGNORECASE))
    if reported:
        return finding("DATA-EXCLUSION", "PASS", "缺失排除带前后计数记录", hits)
    return finding("DATA-EXCLUSION", "WARN", "缺失排除无前后计数，需在 process_record 记录丢弃了多少", hits)


def check_demo_data(source: str) -> Finding:
    hits = regex_hits(
        [r"np\.random\.(?:normal|uniform|rand|randn|poisson)\s*\(",
         r"make_(?:classification|regression|blobs)\s*\("], source)
    if not hits:
        return finding("DEMO-DATA", "PASS", "未发现模拟数据生成器")
    isolated = bool(re.search(r"--demo|demo_mode|if\s+.*demo", source, re.IGNORECASE))
    if isolated:
        return finding("DEMO-DATA", "WARN", "存在模拟数据但在 demo 分支内；确认生产绘图不用模拟数据", hits)
    return finding("DEMO-DATA", "WARN", "绘图源码疑似用模拟数据，真实赛题必须用 results/ 真值", hits)


def check_log_guards(source: str) -> Finding:
    log_hits = regex_hits([r"np\.log(?:2|10)?\s*\(", r"set_[xy]scale\s*\(\s*['\"]log", r"scale_[xy]_log10\s*\("], source)
    if not log_hits:
        return finding("LOG-GUARD", "PASS", "未用对数变换")
    guards = regex_hits([r"clip\s*\([^)]*lower\s*=", r"pseudocount|epsilon|eps\b", r"np\.any\s*\([^)]*<=\s*0"], source)
    if guards:
        return finding("LOG-GUARD", "PASS", "对数变换带正性/pseudocount 防护", guards)
    return finding("LOG-GUARD", "WARN", "对数变换无正性防护（数据含 0/负会 NaN）", log_hits)


def _contract_block(source: str) -> dict | None:
    """提取脚本内 CONTRACT 块（作图契约 §四，纯字面 dict）。解析失败返回 None。

    用括号配平扫描而非正则取到第一个 `\\n}`：单行写法 `CONTRACT = {...}` 与
    多行嵌套写法都能吃下，避免"格式合法却报解析失败"的误报。
    """
    match = re.search(r"(?m)^CONTRACT\s*=\s*", source)
    if not match:
        return None
    start = source.find("{", match.end())
    if start < 0 or source[match.end():start].strip():
        return None
    depth, quote, index = 0, None, start
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
            if depth == 0:
                break
        index += 1
    if depth != 0:
        return None
    try:
        value = ast.literal_eval(source[start:index + 1])
    except (ValueError, SyntaxError):
        return None
    return value if isinstance(value, dict) else None


def check_data_binding(source: str, source_path: Path | None = None) -> Finding:
    """作图契约 §四：数据图须能机检数值（results_path + bindings）；示意图显式声明 kind。"""
    contract = _contract_block(source)
    if contract is None:
        return finding("CONTRACT-BINDING", "FAIL",
                       "未找到可解析的 CONTRACT 块（作图契约 §四：须含 fig_id + data_binding + plot_calls）")
    binding = contract.get("data_binding")
    if not isinstance(binding, dict):
        return finding("CONTRACT-BINDING", "FAIL", "CONTRACT 缺 data_binding（机检新增必填字段）")
    kind = binding.get("kind", "data")
    if kind == "schematic":
        return finding("CONTRACT-BINDING", "PASS", "示意图显式声明 kind=schematic，豁免数值比对（作图契约 §一）")
    path = binding.get("results_path")
    if not isinstance(path, str) or not path.strip():
        return finding("CONTRACT-BINDING", "FAIL", "data_binding 缺 results_path（q1: results/q1_results.json）")
    allowed = ("results/q1_results.json", "results/results.json")
    if path.replace("\\", "/").strip() not in allowed:
        return finding("CONTRACT-BINDING", "FAIL",
                       f"results_path 不在契约限定来源内：{path}（只认 {allowed[0]} / {allowed[1]}）")
    if not isinstance(binding.get("bindings"), dict) or not binding["bindings"]:
        return finding("CONTRACT-BINDING", "FAIL", "data_binding.bindings 为空（须声明 绘图参数名 → results 键名）")
    return finding("CONTRACT-BINDING", "PASS",
                   f"data_binding 齐全（{path}，{len(binding['bindings'])} 条绑定）")


_STATS_CALLS = {
    "std": {"std", "nanstd"}, "var": {"var", "nanvar"},
    "percentile": {"percentile"}, "quantile": {"quantile"}, "corrcoef": {"corrcoef"},
    "scipy.stats": {"*"}, "scipy.optimize": {"curve_fit", "least_squares"},
    "sklearn": {"fit", "predict"},
}
_STATS_ATTRS = {"std", "var", "percentile", "quantile", "corrcoef", "fit", "predict",
                "curve_fit", "least_squares", "mode", "sem", "pearsonr", "spearmanr"}


def _stats_targets(node: ast.AST, source: str) -> set[str]:
    """AST 匹配统计/拟合调用（作图契约 §六）。返回命中描述集合。"""
    hits: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "fit" and isinstance(func, ast.Attribute):
            hits.add("sklearn .fit()")
        elif name == "predict":
            hits.add(".predict()")
        elif name in _STATS_ATTRS:
            # 裸名调用（`from numpy import std` 后直接 `std(...)`）时 func 是 ast.Name，
            # 没有 .value 属性。此类同样命中统计禁令，须报出而非崩溃——
            # 否则调用方拿到 AttributeError 而非判定结果（stage_gate 同输入不崩，两侧口径须一致）。
            if isinstance(func, ast.Attribute):
                root = func.value
                root_name = root.attr if isinstance(root, ast.Attribute) else getattr(root, "id", "")
                hits.add(f"{root_name + '.' if root_name else ''}{name}")
            else:
                hits.add(name)
    # 动态绕过（getattr/eval/__import__）拿到的是同一被 patch 对象，运行时守卫仍生效；
    # 但拼接字符串等路径 AST 抓不到——静态层只降概率（作图契约 §六 诚实说明）。
    for m in re.finditer(r"\b(?:getattr|eval|exec)\s*\(\s*['\"](\w+)['\"]", source):
        if m.group(1) in _STATS_ATTRS:
            hits.add(f"dynamic:{m.group(1)}")
    return hits


def _stats_exempt(source: str) -> tuple[bool, list[str]]:
    """`# STATS-EXEMPT: <理由>`：空理由 FAIL，非空降 WARN（作图契约 §六）。"""
    exempts = re.findall(r"#[ \t]*STATS-EXEMPT:[ \t]*([^\n]*)", source)
    meaningful = [item.strip() for item in exempts if item.strip()]
    return bool(exempts), meaningful


def check_no_statistical_inference(source: str, source_path: Path | None = None) -> Finding:
    """作图契约 §六：作图脚本只做呈现，不做推断（统计量由编程手算好落盘）。"""
    contract = _contract_block(source) or {}
    declared = contract.get("statistical_exempt")
    exempted = declared is not None and declared is not False
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return finding("NO-STATS", "FAIL", f"源码语法错误，无法做统计调用扫描：{exc.msg}")
    hits = _stats_targets(tree, source)
    if not hits:
        return finding("NO-STATS", "PASS", "未发现统计推断/拟合调用")
    has_exempt, reasons = _stats_exempt(source)
    if exempted and declared:
        return finding("NO-STATS", "WARN",
                       f"CONTRACT.statistical_exempt 已声明，人工确认豁免范围：{sorted(hits)}", sorted(hits))
    if has_exempt and not reasons:
        return finding("NO-STATS", "FAIL",
                       f"STATS-EXEMPT 理由为空（空理由 FAIL）：{sorted(hits)}", sorted(hits))
    if has_exempt:
        return finding("NO-STATS", "WARN",
                       f"存在统计调用但已记录非空豁免理由（{reasons[0][:60]}），需人工确认：{sorted(hits)}",
                       sorted(hits))
    return finding("NO-STATS", "FAIL",
                   f"脚本含统计推断/拟合调用，应由编程手算好落盘后再画：{sorted(hits)}", sorted(hits))


def _entry_candidates(reference: str, source_path: Path | None) -> list[Path]:
    """把脚本里引用的数据路径解析成候选本地文件（相对脚本、相对项目根、按名）。"""
    if not reference or reference.startswith(("http://", "https://", "data:")):
        return []
    candidates: list[Path] = []
    base = Path(reference)
    if base.is_absolute():
        candidates.append(base)
    if source_path:
        candidates.append(source_path.parent / base)
        candidates.extend(parent / base for parent in list(source_path.parents)[:3])
    candidates.append(Path.cwd() / base)
    candidates.append(Path.cwd() / base.name)
    return candidates


def check_data_entrypoint(source: str, source_path: Path | None = None) -> Finding:
    """作图契约 §三：脚本读取的数据入口必须真实存在（禁"跑起来才 404"）。"""
    if source_path is None:
        return finding("DATA-ENTRY", "WARN", "未提供脚本路径，无法核对数据入口是否落地")
    refs = [ref for ref in re.findall(
        r"(?:read_text|read_bytes|open|read_csv|json\.load|loads)\s*\(\s*(?:Path\s*\(\s*)?['\"]([^'\"\n]+)['\"]",
        source) if re.search(r"\.(?:json|csv|txt|tsv|npy|npz|xlsx)$", ref, re.IGNORECASE)]
    refs = [ref for ref in refs if not ref.startswith(".")]
    if not refs:
        # 用 CONTRACT.data_binding 兜底（数据入口可能由脚本自行落盘）
        binding = (_contract_block(source) or {}).get("data_binding") or {}
        data_path = binding.get("data_path") if isinstance(binding, dict) else None
        if not data_path:
            return finding("DATA-ENTRY", "WARN",
                           "未发现显式数据文件引用，也未见 data_binding.data_path，需人工确认数据入口")
        refs = [data_path]
    missing = [ref for ref in refs
               if not any(candidate.is_file() for candidate in _entry_candidates(ref, source_path))]
    if missing:
        return finding("DATA-ENTRY", "FAIL", f"数据入口不存在：{missing}", missing)
    return finding("DATA-ENTRY", "PASS", f"数据入口存在（{refs}）")


def check_script_runnable(source: str, source_path: Path | None = None) -> Finding:
    """作图契约 §三：脚本可独立运行——语法可解析 + `__file__` 相对定位（禁 cwd/绝对路径）。"""
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return finding("SCRIPT-RUNNABLE", "FAIL", f"脚本语法错误，无法独立运行：{exc.msg}")
    located = bool(re.search(r"__file__", source))
    absolute = re.findall(r"['\"](?:[A-Za-z]:[\\/]|/home/|/Users/|/mnt/)[^'\"]*['\"]", source)
    if absolute:
        return finding("SCRIPT-RUNNABLE", "FAIL",
                       f"脚本含本机绝对路径，换机器必挂：{absolute[:3]}", absolute[:3])
    if not located:
        return finding("SCRIPT-RUNNABLE", "FAIL",
                       "脚本未用 __file__ 相对定位（作图契约 §二硬性规范：空 cwd 独立运行必挂）")
    return finding("SCRIPT-RUNNABLE", "PASS", "语法通过且使用 __file__ 相对定位")


CHECKS: tuple[Callable[[str], Finding], ...] = (
    check_syntax, check_cn_font, check_font_sizes, check_colormaps,
    check_png_export, check_resolution, check_sampling, check_exclusions,
    check_demo_data, check_log_guards,
    check_script_runnable, check_data_entrypoint, check_data_binding,
    check_no_statistical_inference,
)

# 需要脚本路径做文件系统核对的检查（其余只吃源码字符串）
_PATH_AWARE = (check_cn_font, check_script_runnable, check_data_entrypoint, check_data_binding)


def validate_source(source: str, source_path: Path | None = None) -> list[Finding]:
    findings = []
    for check in CHECKS:
        if check in _PATH_AWARE:
            findings.append(check(source, source_path))
        else:
            findings.append(check(source))
    return findings


def summarize(findings: Iterable[Finding], strict: bool = False) -> dict[str, object]:
    rows = list(findings)
    counts = {lvl: sum(r.level == lvl for r in rows) for lvl in ("PASS", "WARN", "FAIL")}
    ready = counts["FAIL"] == 0 and (not strict or counts["WARN"] == 0)
    return {"ready": ready, "strict": strict, "counts": counts}


def render_text(path: Path, findings: list[Finding], strict: bool) -> str:
    summary = summarize(findings, strict)
    lines = ["画图源码静态预检（validate_figures）",
             f"source: {path}", ""]
    for row in findings:
        lines.append(f"[{row.level}] {row.check_id}: {row.message}")
        for item in row.evidence:
            lines.append(f"  - {item}")
    c = summary["counts"]
    lines += ["",
              f"summary: {c['PASS']} pass, {c['WARN']} warn, {c['FAIL']} fail",
              f"verdict: {'READY' if summary['ready'] else 'FIX BEFORE DELIVERY'}",
              "note: 静态预检不校验统计与渲染效果，仍须人工看图"]
    return "\n".join(lines)


GOOD_SAMPLE = '''
import json
from pathlib import Path
import matplotlib as mpl
mpl.rcParams.update({"font.sans-serif": ["SimHei"], "font.size": 11})
import matplotlib.pyplot as plt

CONTRACT = {
    "fig_id": "fig1",
    "data_binding": {"results_path": "results/q1_results.json", "bindings": {"y": "Q1_cost"}},
    "plot_calls": [{"method": "bar", "data_params": ["x", "y"], "aux_params": ["x_labels"]}],
}

record = json.loads(open("figures/data/fig1.json", encoding="utf-8").read())
fig, ax = plt.subplots()
ax.plot([1, 2, 3], record["y"])
fig.savefig(Path(__file__).with_suffix(".png"), dpi=300)
'''

BAD_SAMPLE = '''
import numpy as np
import matplotlib.pyplot as plt
x = np.random.choice(np.random.normal(size=100), 12)
fig, ax = plt.subplots()
ax.imshow(np.zeros((3,3)), cmap="jet")
fig.savefig("figures/fig1.png", dpi=72)
'''

STATS_SAMPLE = '''
import json
from pathlib import Path
import numpy as np
import matplotlib as mpl
mpl.rcParams.update({"font.sans-serif": ["SimHei"], "font.size": 11})
import matplotlib.pyplot as plt

CONTRACT = {"fig_id": "fig1", "data_binding": {"results_path": "results/q1_results.json",
            "bindings": {"y": "Q1_cost"}}}
record = json.loads(open("figures/data/fig1.json", encoding="utf-8").read())
fig, ax = plt.subplots()
band = np.std(record["y"])
ax.errorbar([1, 2], record["y"][:2], yerr=band)
fig.savefig(Path(__file__).with_suffix(".png"), dpi=300)
'''


def _levels(source: str, path: Path | None = None) -> dict[str, str]:
    return {r.check_id: r.level for r in validate_source(source, path)}


def run_self_tests() -> None:
    """自测：正例全 PASS、反例逐项命中（含 v3.0 新增 4 项与反例注入）。"""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="validate_figures_selftest_") as temp:
        project = Path(temp)
        (project / "figures/scripts").mkdir(parents=True)
        (project / "figures/data").mkdir(parents=True)
        (project / "figures/data/fig1.json").write_text('{"y": [1, 2, 3]}', encoding="utf-8")
        script = project / "figures/scripts/fig1.py"
        script.write_text(GOOD_SAMPLE, encoding="utf-8")

        good_f = {r.check_id: r for r in validate_source(GOOD_SAMPLE, script)}
        bad_levels = [f"{k}:{v.level}" for k, v in good_f.items() if v.level != "PASS"]
        assert not bad_levels, bad_levels

        # 反例 1：无 CONTRACT / 无 __file__（放错目录型脚本）
        loose = good_f["SCRIPT-RUNNABLE"]
        assert loose.level == "PASS"
        no_contract = _levels('import matplotlib.pyplot as plt\nplt.savefig("a.png", dpi=300)\n')
        assert no_contract["CONTRACT-BINDING"] == "FAIL", no_contract
        assert no_contract["SCRIPT-RUNNABLE"] == "FAIL", no_contract

        # 反例 2：统计调用（AST）
        stats = _levels(STATS_SAMPLE, script)
        assert stats["NO-STATS"] == "FAIL", stats
        exempt = STATS_SAMPLE.replace(
            "band = np.std(record[\"y\"])",
            "# STATS-EXEMPT:\nband = np.std(record[\"y\"])")
        assert _levels(exempt, script)["NO-STATS"] == "FAIL", "空理由 STATS-EXEMPT 必须 FAIL"
        exempt = STATS_SAMPLE.replace(
            "band = np.std(record[\"y\"])",
            "# STATS-EXEMPT: 仅做稳健区间裁剪，不进结论\nband = np.std(record[\"y\"])")
        assert _levels(exempt, script)["NO-STATS"] == "WARN", "非空理由应降 WARN"

        # 反例 3：数据入口不存在 / results_path 越出契约限定来源
        missing = GOOD_SAMPLE.replace("figures/data/fig1.json", "figures/data/nowhere.json")
        assert _levels(missing, script)["DATA-ENTRY"] == "FAIL", "数据入口缺失必须 FAIL"
        wrong_source = GOOD_SAMPLE.replace("results/q1_results.json", "figures/fig1.json")
        assert _levels(wrong_source, script)["CONTRACT-BINDING"] == "FAIL", "越出限定来源必须 FAIL"

        # 反例 4：本机绝对路径
        absolute = GOOD_SAMPLE.replace('open("figures/data/fig1.json"',
                                       'open("C:/Users/someone/data/fig1.json"')
        assert _levels(absolute, script)["SCRIPT-RUNNABLE"] == "FAIL", "绝对路径必须 FAIL"

        # 原有反例：配色 / DPI / 字号
        bad = _levels(BAD_SAMPLE, project / "figures/scripts/bad.py")
        for cid in ("CN-FONT", "COLOR-MAP", "RASTER-DPI"):
            assert bad[cid] == "FAIL", (cid, bad[cid])
        assert bad["FONT-SIZE"] == "WARN", "bad 样例未设字号应为 WARN"
    print("validate_figures.py self-test: PASS")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", nargs="?", type=Path, help="matplotlib 绘图源码 .py")
    p.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    p.add_argument("--strict", action="store_true", help="WARN 也算不通过")
    p.add_argument("--self-test", action="store_true", help="运行自测")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Windows 默认控制台是 GBK(cp936)；输出一旦含替换字符或 ✓ 类符号，print 就会抛
    # UnicodeEncodeError 并以非零退出码收场——与「检查未通过」不可区分。
    # 其余入口脚本(run_all/stage_gate/gate_audit/...)均有此守卫，本脚本此前漏装。
    if getattr(sys.stdout, "reconfigure", None):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if getattr(sys.stderr, "reconfigure", None):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if args.self_test:
        run_self_tests()
        return 0
    if args.source is None:
        build_parser().error("source 是必填，除非 --self-test")
    if not args.source.is_file():
        print(f"error: 源码不存在: {args.source}", file=sys.stderr)
        return 2
    try:
        source = args.source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = validate_source(source, args.source)
    summary = summarize(findings, args.strict)
    if args.json:
        print(json.dumps({"source": str(args.source), "summary": summary,
                          "findings": [asdict(r) for r in findings]},
                         indent=2, ensure_ascii=False))
    else:
        print(render_text(args.source, findings, args.strict))
    return 0 if summary["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
