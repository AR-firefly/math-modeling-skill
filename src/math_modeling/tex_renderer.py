"""TeX 渲染：PAPER_STRUCT → .tex 初稿。

原则：忠实渲染已验证的论文内容；渲染后逐页检查排版。
规范：章节 \\section/\\subsection、公式 \\[..\\]、三线表 tabular + \\caption 在表上、
      图 \\includegraphics（图题在下）、\\thebibliography。

用法：
    tex = render_tex(paper)                # 返回字符串（不写盘）
    render_tex(paper, "output/paper.tex")  # 写盘并返回字符串（统一签名）
"""
from __future__ import annotations
import re


def _escape(text):
    """转义 TeX 特殊字符，保留中文字符。"""
    replacements = {"\\": r"\textbackslash{}", "$": r"\$", "&": r"\&", "%": r"\%",
                    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in str(text))



def _caption_above(caption):
    return f"\\caption{{{_escape(caption)}}}"


def _notes(item):
    notes = item.get("notes", [])
    return [notes] if isinstance(notes, str) else notes


def _render_table(t):
    headers, rows = t.get("headers", []), t.get("rows", [])
    n = len(headers)
    lines = ["\\begin{table}[htbp]", "\\centering", _caption_above(t.get("caption", ""))]
    lines.append("\\begin{tabular}{" + "c" * max(n, 1) + "}")
    lines.append("\\toprule")
    lines.append(" & ".join(_escape(h) for h in headers) + " \\\\")
    lines.append("\\midrule")
    for r in rows:
        cells = r if len(r) >= n else r + [""] * (n - len(r))
        lines.append(" & ".join(_escape(c) for c in cells[:n]) + " \\\\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.extend("\\par\\small " + _escape(note) for note in _notes(t))
    lines.append("\\end{table}")
    return "\n".join(lines)


def _render_image(img):
    path = img.get("path", "").replace("\\", "/")
    return ("\\begin{figure}[htbp]\n\\centering\n"
            f"\\includegraphics[width=0.75\\textwidth]{{{path}}}\n"
            f"\\caption{{{_escape(img.get('caption', ''))}}}\n"
            + "\n".join("\\par\\small " + _escape(note) for note in _notes(img)) + "\n"
            "\\end{figure}")


def render_tex(paper: dict, out_path: str | None = None) -> str:
    """把 PAPER_STRUCT dict 渲染成 .tex 字符串；传 out_path 则写盘并返回。

    对齐国赛论文规范：摘要独立一页（含标题+关键词，不超过一页）、正文无目录、
    所有文件无身份/学校信息（不输出 school）、附录程序清单。
    """
    meta = paper.get("meta", {})
    lines = [
        "% 数学建模论文初稿（由 render_tex 生成，人工润色用）",
        "% 编译：xelatex output/paper.tex（在仓库根/工作目录根编译；勿在 output/ 内编译——图路径 figures/ 相对根目录）",
        "% 对齐国赛规范：摘要独立一页、正文无目录、不含身份/学校信息、附录程序清单",
        "\\documentclass[11pt]{article}",
        "\\usepackage{ctex}",
        "\\usepackage{graphicx}",
        "\\usepackage{amsmath, amssymb}",
        "\\usepackage{booktabs}",
        "\\usepackage{geometry}",
        "\\geometry{top=2.54cm, bottom=2.54cm, left=3.18cm, right=3.18cm}",
        "\\pagestyle{plain}",
        "\\begin{document}",
        "\\pagenumbering{gobble}% 摘要页不编页码（国赛规范：从正文开始页码）",
        "\\begin{center}",
        f"\\LARGE {_escape(meta.get('title', '（题目）'))}",
        "\\end{center}",
        "\\vspace{1em}",
        "\\noindent\\textbf{摘要}",
    ]
    for para in paper.get("abstract", []):
        lines.append(f"\\noindent {_escape(para)}\\\\[4pt]")
    lines += ["\\noindent\\textbf{关键词}：" + _escape("；".join(meta.get("keywords", []))), "", "\\newpage", "\\pagenumbering{arabic}"]

    for sec in paper.get("sections", []):
        title = _escape(sec.get("title", ""))
        if re.match(r"^[一二三四五六七八九十]", title):
            lines.append(f"\\section{{{title}}}")
        else:
            lines.append(f"\\subsection{{{title}}}")
        for fml in sec.get("formulas", []):
            expr = fml.strip().strip("$").strip("$$")
            lines.append("\\[" + expr + "\\]")
        for img in sec.get("images", []):
            lines.append(_render_image(img))
        for t in sec.get("tables", []):
            lines.append(_render_table(t))
        for para in sec.get("paras", []):
            lines.append("\\noindent " + _escape(para))
        lines.append("")

    # 附录（程序清单等支撑材料，国赛规范：附录含全部可运行源程序清单）
    appendix = paper.get("appendix", [])
    if appendix:
        lines.append("\\section{附录}")
        for item in appendix:
            lines.append("\\noindent " + _escape(item))
        lines.append("")

    lines.append("\\section{人工智能使用声明}")
    lines.append("\\vspace{3cm}")
    lines.append("\\section{参考文献}")
    lines.append("\\begin{thebibliography}{99}")
    for i, ref in enumerate(paper.get("references", []), 1):
        lines.append(f"\\bibitem{{r{i}}} {_escape(ref)}")
    lines.append("\\end{thebibliography}")
    lines.append("\\end{document}")

    tex = "\n".join(lines)
    if out_path:
        import os
        from pathlib import Path
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(tex)
    return tex
