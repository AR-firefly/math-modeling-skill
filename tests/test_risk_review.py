# -*- coding: utf-8 -*-
"""查重风险点清单测试：模拟论文文本 + 模拟参考文本，验证检出高相似段。"""
import pytest
from math_modeling.paper_generator import plagiarism_risk_review


def test_risk_review_detects_similar():
    paper = "本节采用TOPSIS方法进行综合评价，通过计算与正负理想解的距离进行排序。"
    refs = {"参考A": "本节采用TOPSIS方法进行综合评价，通过计算与正负理想解的距离进行排序。"}
    risks = plagiarism_risk_review(paper, refs)
    assert risks and any(r["level"] == "高" for r in risks)


def test_risk_review_marks_dissimilar_clean():
    paper = "本文研究水果种植资源配置问题，采用动态规划建模求解。"
    refs = {"参考B": "本文研究海洋波浪能采集效率优化，采用微分方程建模。"}
    risks = plagiarism_risk_review(paper, refs)
    assert all(r["level"] != "高" for r in risks)


def test_risk_review_output_fields():
    risks = plagiarism_risk_review(
        "深度参考段，与原文完全相同的内容。",
        {"参考": "深度参考段，与原文完全相同的内容。"})
    assert {"paragraph", "ref_source", "similarity", "level", "suggestion"} <= set(risks[0])
