#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_submission_zip —— 独立编译参赛提交 ZIP（C9 / 升级计划 §4.1）。

它做什么
--------
把赛题目录里**该交的东西**打进一个 ZIP：`paper.tex`、图片、单独成文件的参考文献、
编译说明。包内**一律相对路径**，**不得出现本机绝对路径**（自检 `no_absolute_paths`
实测断言）。

它不做什么（重要）
------------------
- **不编译**：只打包。在线 Overleaf 是首选编译路径、本地 XeLaTeX 是兜底，两者都不可用时
  标「待编译验证」——本脚本**绝不伪造编译成功**，也不会替你写「已编译」字样。
- **不判分**：包里有 `paper.tex` 不等于编译得过，更不等于论文合格。

独立编译说明（写进包内 `编译说明.md`）
------------------------------------
| 项      | 说明                                                                 |
| ------- | -------------------------------------------------------------------- |
| 首选    | Overleaf 新建项目 → 上传本 ZIP → 主文件设为 `paper.tex` → 用 **XeLaTeX** 编译 |
| 兜底    | 本地 `xelatex paper.tex`（连续跑两次以解析交叉引用与目录）             |
| 失败    | 标「**待编译验证**」，把编译日志一并留存；**不得**在未编译成功时声称已通过 |
| 必备留存 | 主文件、编译器与版本、编译日志、实际 PDF                              |

用法
----
    python "<SKILL_ROOT>/scripts/build_submission_zip.py" --project "<赛题目录>" \\
        --out "submission.zip" [--include-extra 路径 ...] [--json]
    python "<SKILL_ROOT>/scripts/build_submission_zip.py" --self-test

退出码：0 = 打包成功；1 = 有 FAIL 级问题（缺 paper.tex / 检出本机绝对路径）；2 = 用法错误。

诚实说明
--------
本脚本只保证「包内路径是相对的、主文件在」。**它不保证 ZIP 能编译通过**，
也不保证论文内容正确——那要靠实际编译 + 独立审查。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

MAIN_TEX = "output/paper.tex"
README_NAME = "编译说明.md"

# 本机绝对路径指纹：Windows 盘符 / UNC（两种写法）/ POSIX 家目录 / 临时目录
# 说明：**单个**反斜杠不当作路径——LaTeX 里它就是命令前缀（\section、\includegraphics），
# 误报会淹没真信号。要抓的是「两个反斜杠的 UNC」与「// 开头的 UNC」这类明确写法。
ABSOLUTE_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/]{1,2}[^\s\"'{}]*"),            # C:\... 或 C:/...
    re.compile(r"\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_.$-]+"),     # \\server\share（真 UNC）
    re.compile(r"(?<![:\w])//[A-Za-z0-9_.-]+/[A-Za-z0-9_.$-]"),  # //server/share（正斜杠 UNC）
    re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/"),          # /home/x/  /Users/x/
    re.compile(r"/tmp/[A-Za-z0-9_.-]{4,}"),
    re.compile(r"[A-Za-z]:[\\/]Users[\\/]", re.IGNORECASE),
)
# 允许出现的例外：官方 URL、相对路径（`figures/x.png` 不会被上面任何一条命中）
ALLOW_SUBSTRINGS = ("http://", "https://", "\\textbackslash", "C:\\Windows\\Fonts")

README_TEMPLATE = """\
# 编译说明（build_submission_zip 生成）

本 ZIP 由 `scripts/build_submission_zip.py` 打包，包内路径**全部相对路径**，可直接上传 Overleaf。

## 怎么编译

| 路径 | 做法 |
| --- | --- |
| **首选：在线 Overleaf** | 新建项目 → 上传本 ZIP → 主文件设为 `{main}` → 编译器选 **XeLaTeX** |
| **兜底：本地 XeLaTeX** | 解压后在 `{main_dir}/` 下 `xelatex {main_name}`（**连跑两次**以解析交叉引用/目录） |

中文需 XeLaTeX + 系统字体（SimHei / 微软雅黑 / SimSun）；用 pdfLaTeX 会编译失败，不是论文的问题。

## 必须留存的四样（升级计划 C9）

1. 主文件：`{main}`
2. 编译器与版本：`xelatex --version` 的实际输出（**待填**）
3. 编译日志：`paper.log`（**待附**）
4. 实际 PDF：`paper.pdf`（**待附**）

## 编译不通过怎么办

标「**待编译验证**」，把 `paper.log` 一并留存说明卡在哪一步。
**不得在未编译成功时声称已编译通过**——这是本脚本不做编译、也不写「编译成功」的原因。

## 包内清单

{manifest}

> 诚实说明：本 ZIP 只保证「主文件在、路径是相对的」，**不证明能编译通过**，也不证明论文内容正确。
"""


# ───────────────────────── 收集待打包文件 ─────────────────────────

def _posix(path):
    return Path(path).as_posix()


def collect(project, extra=()):
    """返回 (arcname → 源路径) 映射与 problems 列表。全部 arcname 都是相对路径。"""
    project = Path(project).resolve()
    entries, problems = {}, []
    main = project / MAIN_TEX
    if not main.is_file():
        problems.append("缺主文件 %s：无法打包（先完成论文编译产物）" % MAIN_TEX)
    else:
        entries[MAIN_TEX] = main

    # 图片：figures/ 下的 png/pdf（PDF 矢量图也可能进论文）
    for pattern in ("**/*.png", "**/*.pdf", "**/*.svg"):
        for path in sorted((project / "figures").glob(pattern)):
            if path.is_file():
                entries[_posix(path.relative_to(project))] = path

    # 单独成文件的参考文献 / 样式（.bib/.bst/.cls/.sty 与 output/ 下的补充 tex）
    for pattern in ("**/*.bib", "**/*.bst", "**/*.cls", "**/*.sty"):
        for base in (project, project / "output"):
            for path in sorted(base.glob(pattern)):
                if path.is_file():
                    entries[_posix(path.relative_to(project))] = path
    for path in sorted((project / "output").glob("*.tex")):
        if path.is_file() and path.name != "paper.tex":
            entries[_posix(path.relative_to(project))] = path

    for item in extra:
        path = Path(item)
        path = path if path.is_absolute() else (project / path)
        if not path.is_file():
            problems.append("--include-extra 指向的文件不存在：%s" % item)
            continue
        try:
            arcname = _posix(path.resolve().relative_to(project))
        except ValueError:
            arcname = path.name          # 项目外文件平铺进包，绝不带绝对路径
        entries[arcname] = path
    return entries, problems


def absolute_hits(line):
    """单行里检出的本机绝对路径片段；官方 URL 等允许项返回空列表。"""
    if any(allowed in line for allowed in ALLOW_SUBSTRINGS):
        return []
    for pattern in ABSOLUTE_PATTERNS:
        match = pattern.search(line)
        if match:
            return [match.group(0)]
    return []


def scan_absolute_paths(entries, project):
    """扫文本文件里的本机绝对路径。返回 hits 列表。"""
    hits = []
    for arcname, path in entries.items():
        if path.suffix.lower() in (".png", ".pdf", ".jpg", ".jpeg", ".svg", ".zip"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for token in absolute_hits(line):
                hits.append({"file": arcname, "line": lineno, "match": token})
    return hits


# ───────────────────────── 打包 ─────────────────────────

def _readme(entries, main=MAIN_TEX):
    manifest = "\n".join("- `%s`" % name for name in sorted(entries))
    return README_TEMPLATE.format(main=main, main_dir=_posix(Path(main).parent),
                                  main_name=Path(main).name, manifest=manifest)


def build(project, out_path, *, extra=(), strict=False):
    project = Path(project).resolve()
    out_path = Path(out_path)
    report = {"tool": "build_submission_zip", "project": str(project),
              "out": str(out_path), "machine_checks_only": True,
              "compiled": False, "problems": [], "absolute_path_hits": [],
              "packed": [], "level": "FAIL", "passed": False,
              "note": "只打包，不编译；不证明可编译通过，也不证明论文内容正确"}
    entries, problems = collect(project, extra)
    report["problems"].extend(problems)
    hits = scan_absolute_paths(entries, project)
    report["absolute_path_hits"] = hits
    if hits:
        report["problems"].append("检出本机绝对路径 %d 处（包内必须统一相对路径）" % len(hits))
    if strict and not entries:
        report["problems"].append("没有任何可打包文件")
    report["level"] = "FAIL" if report["problems"] else "PASS"
    if report["level"] == "FAIL":
        return report

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for arcname, path in sorted(entries.items()):
            # 写弧名时强制正斜杠 + 禁止绝对/回溯路径（zip slip 防护）
            safe = _safe_arcname(arcname)
            if safe is None:
                report["problems"].append("非法弧名已跳过：%s" % arcname)
                continue
            archive.write(path, safe)
            report["packed"].append({"arcname": safe, "bytes": path.stat().st_size,
                                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        archive.writestr(README_NAME, _readme(entries))
        report["packed"].append({"arcname": README_NAME, "bytes": None, "sha256": None})
    report["level"] = "FAIL" if report["problems"] else "PASS"
    report["passed"] = report["level"] == "PASS"
    report["zip_bytes"] = out_path.stat().st_size
    return report


def _safe_arcname(name):
    normalized = str(name).replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return None
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts) or None


# ───────────────────────── 自检（隔离：全部写入在临时树内） ─────────────────────────

_TEX_OK = r"""\documentclass{article}
\usepackage{graphicx}
\usepackage{ctex}
\title{示例论文}
\begin{document}
\maketitle
\begin{abstract}摘要占一页。\end{abstract}
\section{模型建立}
见图 \ref{fig:demo}。
\begin{figure}[htbp]\centering
\includegraphics[width=0.6\textwidth]{figures/fig1.png}
\caption{示例图}\label{fig:demo}
\end{figure}
\section{参考文献}
\bibliographystyle{plain}\bibliography{refs}
\end{document}
"""

_TEX_ABSOLUTE = "\\includegraphics[width=0.6\\textwidth]{D:\\contest\\figures\\fig1.png}\n"


def _seed(tmp, *, absolute=False, with_bib=True, with_png=True):
    project = tmp / "project"
    (project / "output").mkdir(parents=True)
    tex = _TEX_OK + (_TEX_ABSOLUTE if absolute else "")
    (project / "output" / "paper.tex").write_text(tex, encoding="utf-8")
    if with_bib:
        (project / "output" / "refs.bib").write_text("@article{k, title={T}}\n", encoding="utf-8")
    if with_png:
        (project / "figures").mkdir(parents=True)
        # 最小合法 PNG（1×1）
        (project / "figures" / "fig1.png").write_bytes(
            bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                          "1f15c4890000000a49444154789c6300010000050001'0d0a2db4"
                          .replace("'", "") + "0000000049454e44ae426082"))
    return project


def self_test():
    checks = []

    def case(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:220]})

    with tempfile.TemporaryDirectory(prefix="build_zip_selftest_") as temp:
        tmp = Path(temp)
        good = _seed(tmp / "good")
        report = build(good, tmp / "good" / "submission.zip")
        case("clean_project_packs", report["level"] == "PASS" and report["packed"],
             "level=%s packed=%d problems=%s" % (report["level"], len(report["packed"]),
                                                 report["problems"]))
        with zipfile.ZipFile(tmp / "good" / "submission.zip") as archive:
            names = archive.namelist()
            package_has_abs = any(
                name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/")
                for name in names)
            case("zip_arcnames_relative", not package_has_abs, names)
            case("zip_contains_main_tex", MAIN_TEX in names, names)
            case("zip_contains_figures_and_readme",
                 any(n.startswith("figures/") for n in names) and README_NAME in names, names)
            case("zip_contains_bib", any(n.endswith(".bib") for n in names), names)
            # 包内文本不得含本机绝对路径
            body = "".join(archive.read(n).decode("utf-8", "replace") for n in names
                           if n.endswith((".tex", ".bib", ".md")))
            leaked = [p.pattern for p in ABSOLUTE_PATTERNS if p.search(body)]
            case("no_absolute_paths_in_zip", not leaked, leaked)
            case("readme_warns_not_compiled",
                 "待编译验证" in archive.read(README_NAME).decode("utf-8"), "README 含未编译警告")
            case("report_marks_not_compiled", report["compiled"] is False, report["note"])

        # 反例①：tex 内写死本机绝对路径 → FAIL
        leaky = _seed(tmp / "leaky", absolute=True)
        report = build(leaky, tmp / "leaky" / "s.zip")
        case("absolute_path_in_tex_fails", report["level"] == "FAIL"
             and report["absolute_path_hits"], report["absolute_path_hits"][:1])

        # 反例②：缺主文件 → FAIL（不伪造空的「成功」包）
        noman = _seed(tmp / "noman", with_png=False)
        (noman / "output" / "paper.tex").unlink()
        report = build(noman, tmp / "noman" / "s.zip")
        case("missing_main_tex_fails", report["level"] == "FAIL"
             and any("paper.tex" in p for p in report["problems"]), report["problems"])

        # 反例③：项目外文件（--include-extra）→ 平铺进包、绝不带绝对路径
        outside = tmp / "outside.txt"
        outside.write_text("外部补充材料\n", encoding="utf-8")
        report = build(good, tmp / "good" / "extra.zip", extra=[str(outside)])
        with zipfile.ZipFile(tmp / "good" / "extra.zip") as archive:
            case("outside_extra_flat_relative",
                 report["level"] == "PASS" and "outside.txt" in archive.namelist()
                 and not any(re.match(r"^[A-Za-z]:", n) for n in archive.namelist()),
                 archive.namelist())

        # 反例④：路径回溯弧名被拒
        case("zip_slip_arcname_rejected",
             _safe_arcname("../../etc/passwd") is None
             and _safe_arcname("D:\\x\\y.png") is None
             and _safe_arcname("figures/a.png") == "figures/a.png",
             "合法弧名保留、绝对/回溯弧名返回 None")

        # 反例⑤：ZIP 可被标准库重新打开（不是坏档）
        case("zip_is_readable", zipfile.ZipFile(tmp / "good" / "submission.zip").testzip() is None,
             "testzip() 无损坏条目")

        # 反例⑥：各类本机绝对路径写法必须被抓，相对路径与官方 URL 必须放过
        backslash = chr(92)
        matrix = [
            ("Windows 盘符", "D:" + backslash + "contest" + backslash + "f.png", True),
            ("真 UNC", backslash * 2 + "server" + backslash + "share" + backslash + "f.png", True),
            ("正斜杠 UNC", "//server/share/figs/f.png", True),
            ("POSIX 家目录", "/home/alice/contest/f.png", True),
            ("macOS 家目录", "/Users/alice/contest/f.png", True),
            ("tmp 目录", "/tmp/abc12345/f.png", True),
            ("相对路径", "figures/fig1.png", False),
            ("官方 URL", "https://matplotlib.org/stable/api/_as_gen/axes.html", False),
            ("LaTeX 命令（单反斜杠）",
             backslash + "includegraphics{figures/fig1.png}", False),
        ]
        wrong = [(name, bool(absolute_hits(line)) != expect)
                 for name, line, expect in matrix]
        case("absolute_path_matrix", not any(bad for _, bad in wrong),
             "不符合预期的写法：%s" % [name for name, bad in wrong if bad])
    ok = all(c["ok"] for c in checks)
    return ok, {"self_test_only": True, "project_verified": False, "passed": ok, "checks": checks}


def render_text(report):
    lines = ["参赛提交 ZIP 打包（build_submission_zip）",
             "project: %s" % report["project"], "out: %s" % report["out"],
             "[%s] 打包 %d 个条目，ZIP %s 字节" % (report["level"], len(report["packed"]),
                                              report.get("zip_bytes", 0))]
    for item in report["absolute_path_hits"]:
        lines.append("  FAIL 绝对路径 %s:%s → %s" % (item["file"], item["line"], item["match"]))
    for item in report["problems"]:
        lines.append("  FAIL " + item)
    lines.append("compiled: %s（本脚本只打包，不编译、不写「编译成功」）" % report["compiled"])
    lines.append("note: 包内路径相对 ≠ 能编译通过 ≠ 论文合格；编译结果以实际 xelatex 日志为准")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--project", type=Path, help="赛题目录")
    parser.add_argument("--out", type=Path, default=Path("submission.zip"), help="输出 ZIP 路径")
    parser.add_argument("--include-extra", action="append", default=[],
                        help="额外打包文件（可重复；项目外文件会平铺进包，不带绝对路径）")
    parser.add_argument("--strict", action="store_true")
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
    report = build(args.project, args.out, extra=args.include_extra, strict=args.strict)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
