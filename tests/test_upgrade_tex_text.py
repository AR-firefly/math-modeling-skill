"""TeX prose escaping must not turn user labels or code paths into commands."""
from math_modeling.tex_renderer import _escape, render_tex


def test_literal_special_characters_are_escaped():
    text = _escape(r"Cost $5 in C:\data ~ x^2 & 10% #tag {a_b}")
    for escaped in (r"\$", r"\textbackslash{}", r"\textasciitilde{}", r"\textasciicircum{}", r"\&", r"\%", r"\#", r"\{", r"\_", r"\}"):
        assert escaped in text


def test_formula_field_keeps_math_commands():
    tex = render_tex({"sections":[{"title":"模型","formulas":[r"\frac{x^2}{2}"]}]})
    assert r"\[\frac{x^2}{2}\]" in tex
