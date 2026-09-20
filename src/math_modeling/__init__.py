"""
数学建模国赛全流程 v3.0 — 核心工具包

组件：
    build_paper_content          : 结构化论文内容层（PAPER_STRUCT，tex_renderer 消费）
    plagiarism_risk_review       : 查重风险点清单（深度参考优秀论文后的自审）
    DataCleaner                  : 数据清洗（六策略多方案对比 + 理由）
    Visualizer                   : 可视化（基于数据自主选图，300dpi）
    verify_paper_numbers 等      : 数值强制校验 + 数值归因 + run_manifest
    sensitivity_scan 等          : 灵敏度分析
    ProcessRecorder              : process_record 心路历程 + 断点恢复

v3.0 变更：禁用 Word，只出 LaTeX。移除全部 Word 渲染链路（被删符号与文件清单
见 `_deleted_backup/2026-09-10/README.md`，可据 git commit hash 精确回滚）。
"""
from .paper_generator import (build_paper_content, plagiarism_risk_review,
                              render_risk_points, validate_references)
from .tex_renderer import render_tex
from .data_cleaner import DataCleaner
from .visualizer import Visualizer
from .verify import (verify_paper_numbers, write_run_manifest, build_provenance,
                     verify_figure_references, verify_citations)
from .sensitivity import sensitivity_scan, joint_sensitivity, strategy_reason
from .process_recorder import ProcessRecorder

__all__ = [
    'build_paper_content',
    'plagiarism_risk_review', 'render_risk_points', 'validate_references',
    'render_tex',
    'DataCleaner', 'Visualizer',
    'verify_paper_numbers', 'write_run_manifest', 'build_provenance', 'verify_figure_references',
    'verify_citations',
    'sensitivity_scan', 'joint_sensitivity', 'strategy_reason',
    'ProcessRecorder',
]
