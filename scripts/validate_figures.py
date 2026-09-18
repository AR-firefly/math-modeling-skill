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
    # 它们 8-9pt 在 300dpi 下可读，属正常设计，不该当正文字号误报。
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


CHECKS: tuple[Callable[[str], Finding], ...] = (
    check_syntax, check_cn_font, check_font_sizes, check_colormaps,
    check_png_export, check_resolution, check_sampling, check_exclusions,
    check_demo_data, check_log_guards,
)


def validate_source(source: str, source_path: Path | None = None) -> list[Finding]:
    findings = []
    for check in CHECKS:
        if check is check_cn_font:
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


def run_self_tests() -> None:
    good = '''
import matplotlib as mpl
mpl.rcParams.update({"font.sans-serif": ["SimHei"], "font.size": 11})
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([1,2,3])
fig.savefig("figures/fig1.png", dpi=300)
'''
    bad = '''
import numpy as np
import matplotlib.pyplot as plt
x = np.random.choice(np.random.normal(size=100), 12)
fig, ax = plt.subplots()
ax.imshow(np.zeros((3,3)), cmap="jet")
fig.savefig("figures/fig1.png", dpi=72)
'''
    good_f = {r.check_id: r for r in validate_source(good)}
    assert all(f.level == "PASS" for f in good_f.values() if f.check_id != "EXPORT-PNG"), \
        [f"{k}:{v.level}" for k, v in good_f.items() if v.level == "FAIL"]
    bad_f = {r.check_id: r for r in validate_source(bad)}
    for cid in ("CN-FONT", "COLOR-MAP", "RASTER-DPI"):
        assert bad_f[cid].level == "FAIL", (cid, bad_f[cid].level)
    assert bad_f["FONT-SIZE"].level == "WARN", "bad 样例未设字号应为 WARN"
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
