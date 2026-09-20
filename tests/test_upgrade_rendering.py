"""TeX 单渲染回归（v3.0：禁用 Word，docx 用例已移除）。

v2.0 原文件含 7 个用例，其中 4 个纯 docx（标题颜色/页码域/三线表边框/表格分页保持）
随 C12 禁用 Word 一并移除，备份见 `_deleted_backup/2026-09-10/tests/`。
本文件保留并强化 TeX 路径，另补 comprehensive 全要素样稿（覆盖中文/公式/表格/图片/引用）。
"""
from math_modeling.tex_renderer import render_tex, _render_image


def test_abstract_page_break_before_numbering():
    tex = render_tex({"meta": {"title": "Title"}})
    assert tex.index(r"\newpage") < tex.index(r"\pagenumbering{arabic}")


def test_notes_and_three_line_table():
    """表注与三线表：TeX 侧断言（原 docx 侧断言随 C12 移除）。"""
    paper = {"meta": {"title": "Title"},
             "sections": [{"title": "Results", "paras": ["The table supports the result."],
                           "tables": [{"caption": "Table 1", "headers": ["Metric", "Value"],
                                       "rows": [["Cost", 25]], "notes": "Values in yuan."}]}]}
    tex = render_tex(paper)
    assert "Values in yuan." in tex
    assert r"\toprule" in tex and r"\midrule" in tex and r"\bottomrule" in tex
    assert "Cost" in tex and "25" in tex


def test_image_notes_tex():
    assert "Measured at noon" in _render_image({"path": "image.png", "caption": "Figure 1",
                                                "notes": ["Measured at noon"]})


def test_comprehensive_tex_fixture(tmp_path):
    """全要素样稿：中文正文/公式/表格/图片/引用/特殊字符，TeX 单渲染下齐备。

    对应批次 3 出口条件「样稿覆盖中文/公式/表格/图片/引用/特殊字符」。
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    image = tmp_path / "trend.png"
    fig.savefig(image, dpi=150)
    plt.close(fig)
    paper = {"meta": {"title": "二次增长模型验证", "keywords": ["二次模型", "误差分析"]},
             "abstract": ["建立二次模型解释增长趋势，并采用误差分析检验数值结果。"],
             "sections": [{"title": "模型与结果", "formulas": [r"y=x^2"],
                           "images": [{"path": str(image), "caption": "图1 二次增长趋势",
                                       "notes": "横轴为时间，纵轴为无量纲响应。"}],
                           "tables": [{"caption": "表1 模型预测结果", "headers": ["时间", "响应"],
                                       "rows": [[0, 0], [1, 1], [2, 4]], "notes": "响应为无量纲变量。"}],
                           "paras": ["图1与表1显示，时间增加时响应按平方规律增长，模型预测与计算结果一致[1]。"]}],
             "references": ["参考来源由实际赛题核验后填写，此处仅为排版回归样例。"]}
    tex = render_tex(paper)
    # 中文
    assert "二次增长模型验证" in tex
    # 公式
    assert "y=x^2" in tex
    # 表格（三线表）
    assert r"\toprule" in tex and r"\midrule" in tex and r"\bottomrule" in tex
    assert "响应" in tex
    # 图片
    assert r"\includegraphics" in tex
    # 图注/表注
    assert "横轴为时间，纵轴为无量纲响应。" in tex
    assert "响应为无量纲变量。" in tex
    # 引用标记与参考文献节
    assert "[1]" in tex
    assert r"\section{参考文献}" in tex
    # 不得残留 docx 侧产物标记
    assert "docx" not in tex.lower()
