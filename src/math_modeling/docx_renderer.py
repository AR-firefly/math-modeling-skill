"""DOCX 渲染：同一 PAPER_STRUCT → python-docx 文档。

规范：表题在表上（复用 TableBuilder，v2.0 已上移）、表头加粗+灰底+居中、
      公式经 formula_renderer 渲染 PNG 嵌入、图题在图下。

用法：
    render_docx(paper, "output/paper.docx")
"""
import os
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

try:
    from .table_builder import TableBuilder
    from .formula_renderer import render_and_embed
except ImportError:
    from table_builder import TableBuilder
    from formula_renderer import render_and_embed


def _setup(doc):
    """正文默认样式：宋体 12pt，1.5 倍行距。"""
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)
    style.paragraph_format.line_spacing = 1.5
    for name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    style.element.rPr.rFonts.set(
        # 中文 eastAsia 字体
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "宋体")


def _add_notes(doc, item):
    notes = item.get("notes", [])
    notes = [notes] if isinstance(notes, str) else (notes or [])
    for index, note in enumerate(notes):
        para = doc.add_paragraph(str(note))
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.keep_with_next = index < len(notes) - 1
        for run in para.runs:
            run.font.size = Pt(10)


def _three_line(table):
    """Override legacy TableBuilder grid locally without changing its public API."""
    table.style = None
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom", "left", "right", "insideH", "insideV"):
        border = OxmlElement("w:" + edge)
        border.set(qn("w:val"), "single" if edge in ("top", "bottom") else "nil")
        border.set(qn("w:sz"), "8")
        borders.append(border)
    table._tbl.tblPr.append(borders)
    for cell in table.rows[0].cells:
        tc = cell._tc.get_or_add_tcPr()
        shading = tc.find(qn("w:shd"))
        if shading is not None:
            tc.remove(shading)
        cb = OxmlElement("w:tcBorders")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        cb.append(bottom)
        tc.append(cb)


def render_docx(paper: dict, out_path: str) -> str:
    """把 PAPER_STRUCT dict 渲染成 .docx，返回落盘路径。"""
    doc = Document()
    _setup(doc)
    meta = paper.get("meta", {})

    # 标题 + 学校
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title_p.add_run(meta.get("title", "（题目）"))
    r.bold = True
    r.font.size = Pt(16)
    # 对齐国赛规范：不输出学校/身份信息；摘要独立一页
    # 摘要
    h = doc.add_heading("摘要", level=1)
    h.paragraph_format.first_line_indent = Cm(0)
    for para in paper.get("abstract", []):
        doc.add_paragraph(para)
    doc.add_paragraph("【关键词】" + "；".join(meta.get("keywords", [])))
    body_section = doc.add_section(WD_SECTION_START.NEW_PAGE)
    body_section.footer.is_linked_to_previous = False
    numbering = OxmlElement("w:pgNumType")
    numbering.set(qn("w:start"), "1")
    body_section._sectPr.append(numbering)
    footer = body_section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)

    # 章节
    for sec in paper.get("sections", []):
        title = sec.get("title", "")
        level = 2 if "求解" in title else 1  # "问题N求解"为子节，其余为章（兼容中文编号标题）
        h = doc.add_heading(title, level=level)
        h.paragraph_format.first_line_indent = Cm(0)
        for fml in sec.get("formulas", []):
            render_and_embed(doc, fml.strip().strip("$"), width_inches=4.5)
        for img in sec.get("images", []):
            if os.path.exists(img.get("path", "")):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run()
                run.add_picture(img["path"], width=Inches(5.5))
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap.paragraph_format.first_line_indent = Cm(0)
                cr = cap.add_run(img.get("caption", ""))
                cr.font.size = Pt(10)
            else:
                doc.add_paragraph(f"[图片缺失: {img.get('path', '')}]")
            _add_notes(doc, img)
        for t in sec.get("tables", []):
            tb = TableBuilder(doc, t.get("headers", []))
            tb.add_rows(t.get("rows", []))
            table = tb.build(caption=t.get("caption", ""))
            _three_line(table)
            repeat = OxmlElement("w:tblHeader")
            table.rows[0]._tr.get_or_add_trPr().append(repeat)
            keep_together = t.get("keep_together", len(t.get("rows", [])) <= 10)
            if keep_together:
                for row in table.rows[:-1]:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            paragraph.paragraph_format.keep_with_next = True
            if t.get("caption"):
                doc.paragraphs[-1].paragraph_format.keep_with_next = True
            if t.get("notes"):
                for cell in table.rows[-1].cells:
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.keep_with_next = True
            _add_notes(doc, t)
        for para in sec.get("paras", []):
            doc.add_paragraph(para)

    # 附录（程序清单，国赛规范）
    appendix = paper.get("appendix", [])
    if appendix:
        doc.add_heading("附录", level=1)
        for item in appendix:
            p = doc.add_paragraph(item)
            p.paragraph_format.first_line_indent = Cm(0)

    # 人工填写位置；不输出自动生成的声明或确认
    doc.add_heading("人工智能使用声明", level=1)
    doc.add_paragraph()

    # 参考文献
    doc.add_heading("参考文献", level=1)
    for ref in paper.get("references", []):
        p = doc.add_paragraph(ref)
        p.paragraph_format.first_line_indent = Cm(0)

    out_path = str(out_path)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path
