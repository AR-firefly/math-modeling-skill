"""
数学建模国赛全流程 v2.0 — 核心工具包

组件：
    PaperConfig / PaperGenerator : 论文配置 + 生成器（docx 能力，兼容 v1.0）
    build_paper_content          : 结构化论文内容层（PAPER_STRUCT，双渲染器消费）
    plagiarism_risk_review       : 查重风险点清单（深度参考优秀论文后的自审）
    TableBuilder                 : 三线表（表题在上）
    render_latex / render_and_embed : LaTeX → PNG 渲染
    DataCleaner                  : 数据清洗（六策略多方案对比 + 理由）
    Visualizer                   : 可视化（基于数据自主选图，300dpi）
    verify_paper_numbers 等      : 数值强制校验 + 数值归因 + run_manifest
    sensitivity_scan 等          : 灵敏度分析
    ProcessRecorder              : process_record 心路历程 + 断点恢复
"""
from .paper_generator import (PaperConfig, PaperGenerator,
                              build_paper_content, plagiarism_risk_review,
                              render_risk_points, validate_references)
from .table_builder import TableBuilder
from .formula_renderer import render_latex, render_and_embed
from .tex_renderer import render_tex
from .docx_renderer import render_docx
from .data_cleaner import DataCleaner
from .visualizer import Visualizer
from .verify import (verify_paper_numbers, write_run_manifest, build_provenance,
                     verify_figure_references, verify_citations)
from .sensitivity import sensitivity_scan, joint_sensitivity, strategy_reason
from .process_recorder import ProcessRecorder

__all__ = [
    'PaperConfig', 'PaperGenerator', 'build_paper_content',
    'plagiarism_risk_review', 'render_risk_points', 'validate_references',
    'TableBuilder', 'render_latex', 'render_and_embed',
    'render_tex', 'render_docx',
    'DataCleaner', 'Visualizer',
    'verify_paper_numbers', 'write_run_manifest', 'build_provenance', 'verify_figure_references',
    'verify_citations',
    'sensitivity_scan', 'joint_sensitivity', 'strategy_reason',
    'ProcessRecorder',
]
