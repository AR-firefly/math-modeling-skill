# 🏆 数学建模国赛全流程 Skill v2.0

> 现行阶段、来源、创新、人工声明及交付边界见 `references/执行与交付契约.md`；原细则在当前阶段范围内执行，不代替团队第一问批准或全文独立终审。

> 从问题分析到论文生成的一站式数学建模竞赛工具箱（v2.0，基于近十年真题实证）

> ⚠️ **本仓库不含优秀论文库**。下文提到 `references/优秀论文/` 的地方，指的是历年国赛优秀论文资料（约 516 MB），需要你自己准备。没有它工作流不会中断——查重比对会自动跳过，并在 `output/risk_points.md` 里写明「未进行参考论文文本比对」。

> 从 v1.0 升级到 v2.0 改了什么，见下方「v1.0 → v2.0 的变化」一节，或 [CHANGELOG.md](CHANGELOG.md)。

## 设计理念

数学建模竞赛里，AI 能写代码、能算、能写论文，但方向判断得人来做。这套 skill 把流程拆成可审查的环节，每个环节有明确的依据要求和验收标准：

- **一切基于运行结果**——论文里的结果性数字必须来自求解产物，改数字必须重跑，校验双向（结果 → 论文、论文 → 结果）。
- **质量靠独立审查**——门禁由独立 Subagent 审计，给成功标准不给步骤；自审与独审分开，不以自评分通关。
- **过程可核验**——AI 的决策、试错、取舍全部落到过程记录，人能对照着优化，也能复现。

## 这是什么？

一套面向**全国大学生数学建模竞赛**的完整人机协作工作流：**读题 → 数据清洗（多方案对比）→ 算法索引检索 → 逐问求解 → 五样检验 → 灵敏度 → 基于事实写论文（深度参考优秀论文）→ 查重风险点清单 → 双渲染 → 过程记录**。

定位：**AI 透明工作、人主导优化**。AI完成建模求解与完整论文，并按固定标准自审/独审返工（基于赛题/参考论文/求解结果生成），团队决定审阅和提交，AI仍需完成全部质量改进（润色措辞、深化论证、改写规避查重）。

## 文件结构

```
math-modeling-skill/
│
├── SKILL.md                       ← 入口：三角色渐进加载（建模/编程/论文）+ 门禁 + AI 行为边界
├── README.md                      ← 本文件（结构导航）
├── TUTORIAL.md                    ← 使用教程：安装/跑管线/接入赛题/断点恢复/读过程记录
├── CHANGELOG.md                   ← 版本更新说明（v1.0 → v2.0 的变化）
├── LICENSE                        ← AGPL-3.0
├── NOTICE.md                      ← 第三方素材署名与许可说明
├── pyproject.toml                 ← 包配置（v2.0.0，8 依赖）
├── requirements.txt               ← 依赖清单（运行）
├── requirements-dev.txt           ← 开发依赖（测试）
├── results_demo_data.csv          ← 示例数据
├── .gitignore                     ← 忽略产物（output/results/figures）
├── .gitattributes                 ← 换行符规则
├── run_all.py                     ← 两阶段编排：run_pipeline（Q1真实交付→团队批准→后续与全文）
│
├── methodology/                   ← 方法论（保留 5 篇心法）
│   ├── AI协作心法.md              ← 人机协作哲学：沟通/安全/自检/Karpathy原则
│   ├── 分步工作流.md              ← 9 阶段详细流程（Phase0-8）：每步谁做什么
│   ├── 写作心法.md                ← 论文写作规范：标题/摘要/模型格式/结构
│   ├── 算法选型指南.md            ← 算法选择决策树 + 题型→算法映射 + 五大题型定位
│   └── process_record规格.md      ← 心路历程写作标准（13 节 + 试错链六步 + 算法心路 + 文献借鉴）
│
├── data_cleaning/                 ← 数据清洗（AI 主动探索多方案）
│   └── DATA_CLEANING_GUIDE.md     ← 六方案速查 + 对比标准（方差/KS分布保留度）+ 决策流程
│
├── algorithms/                    ← 算法知识库（近十年真题实证，65 算法，每文件带注释+真题出处）
│   ├── README.md                  ← 四大类导航
│   ├── 01_optimization/           ← 优化类（整数/0-1/动态规划/元启发式/图论/排队论/博弈论/参数优化…）
│   ├── 02_evaluation/             ← 评价类（TOPSIS/AHP/熵权/聚类/分类/统计检验/对应分析…）
│   ├── 03_prediction/             ← 预测类（回归/时间序列/灰色GM/插值/参数估计…）
│   └── 04_physical_mechanism/     ← 机理类（运动学/ODE/热传导/FFT/Radon/几何/光学…）
│
├── src/math_modeling/             ← 核心代码（pip install 后可导入）
│   ├── paper_generator.py         ← 结构化论文内容（PAPER_STRUCT）+ 论文参考 + 查重风险点 + 文献标准
│   ├── visualizer.py              ← 可视化：基于数据特征自主选图，300dpi
│   ├── data_cleaner.py            ← 数据清洗：多方案自动对比 + 选择理由
│   ├── verify.py                  ← 三层数值校验 + 数值归因 + run_manifest
│   ├── sensitivity.py             ← 灵敏度分析：单参数/多参数联合
│   ├── process_recorder.py        ← process_record 心路历程生成 + 断点恢复
│   ├── tex_renderer.py            ← .tex 渲染（可编辑源码，对齐国赛规范）
│   ├── docx_renderer.py           ← .docx 渲染（表题上/图题下）
│   ├── table_builder.py           ← 三线表构建（表题在上）
│   ├── formula_renderer.py        ← 公式渲染 PNG 嵌入
│   ├── frozen_data.py             ← 冻结数据（类型保真，第二阶段不重清洗）
│   ├── workflow.py                ← 流程编排
│   └── __init__.py                ← 包导出
│
├── references/                    ← 参考文档
│   ├── 执行与交付契约.md          ← 阶段、来源、创新、人工声明及交付边界
│   ├── 图表规范.md                ← 选图决策表 + 图题下/表题上/300dpi
│   ├── 图契约.md                  ← 画图前先写核心结论 + 证据链 + 图类型 + 编号
│   ├── 去AI味写作.md              ← 论文表述质量（第三轮自审对照）
│   ├── Subagent质检.md            ← 门禁六节点独立审计成功标准（文献先行/建模/代码/论文成稿/论文质量/process_record）
│   ├── 终审运行检查表.md          ← 固定终审标准（自审/独审/修复/重算/复审）
│   ├── 文献调研报告模板.md        ← 门禁0 文献先行：六维评分 + 逐篇文献卡片
│   ├── 数学建模国赛评价表.md      ← 评审维度参考
│   ├── 优秀论文/                  ← 近五年（2021-2025）优秀论文库，题号(A-E)→四类分层（⚠️ 本仓库不含，需自备）
│   ├── 国赛参赛规则2026.pdf       ← 参赛纪律（AI 辅助但人负全责、引用规范列文献）
│   ├── 国赛论文规范2026.pdf       ← 论文格式规范（摘要一页/正文≤30页/附录程序清单/无身份信息）
│   └── 近5年数模国赛A-E赛题规律与2026命题趋势解读.pdf ← 第三方历史分析，不默认读取或当官方依据
│
├── examples/                      ← 可运行示例（四类题型，五类检验逐项审适用性）
│   ├── main.py                    ← 优化类示例（AGV 协同调度）
│   ├── 评价_TOPSIS_demo.py        ← 评价类
│   ├── 预测_GM11_demo.py          ← 预测类
│   ├── 机理_ODE_demo.py           ← 机理类
│   ├── config.py / utils.py       ← 公共配置与工具
│   └── tsp_solver.py / vrptw_ga.py / nsga2.py / layout_optimizer.py
│                                  ← 优化类分阶段求解（TSP → VRPTW → 多目标 → 布局）
│
├── tests/                         ← 单元测试（20 个）
│   ├── test_data_cleaner.py / test_visualizer.py / test_verify.py / test_sensitivity.py
│   ├── test_algorithm_catalog.py / test_risk_review.py / test_frozen_data.py
│   ├── test_execution_boundary.py / test_validate_figures.py / test_selftest_isolation.py
│   ├── test_artifacts.py / test_foundations.py / test_rendering.py / test_tex_text.py
│   ├── test_workflow.py / test_audit_edges.py / test_execution_flow.py
│   └── test_final_review.py / test_gate_adversarial.py / test_project_audit.py
│
├── scripts/                       ← 辅助脚本
│   ├── preprocess_papers.py       ← 优秀论文预处理（近五年无损：PDF 提取文本/扫描按页）
│   ├── copy_refs.py               ← 复制三规则 PDF
│   ├── gate_audit.py              ← 门禁审计脚本
│   └── validate_figures.py        ← 图表静态校验（配色/尺寸/图契约）
│
└── output/                        ← 产出物（每次运行生成，git 忽略）
    ├── paper.tex                  ← 论文源码（人深度编辑、润色微调）
    ├── paper.docx                 ← Word 版（对齐国赛提交格式）
    ├── process_record.md          ← AI 完整可核验决策摘要与实验记录（人对照着去优化）——核心产出物
    └── risk_points.md             ← 查重风险点清单（人工按清单改写规避）
```

## 核心原则

1. **事实铁律**：一切基于代码运行结果，论文结果性数字按指标/单位/条件与 results/ 对应，技术强制校验（verify 不一致阻断）
2. **seed=42 固定**：所有随机算法可复现；元启发式跑 3 次报均值±标准差（标明误差定义）
3. **深度参考优秀论文**（库需自备）：AI 写论文时读 `references/优秀论文/` 对应题型论文全文借鉴（结构/论证/表述）；`build_paper_content` 提供骨架，**不自动写完整初稿**。写后自审产出查重风险点清单，人工按清单改写规避；AI 不编造参考文献
4. **文献标准**（skill 自定）：绝大部分近五年（2021-2026）、经典著作可例外；总数 ≤ 10 篇（上限非固定）；标准格式 + DOI/URL；文献必须真实
5. **SKILL_ROOT 只读**：skill 仓库只读，产物写用户赛题工作目录

## 运行方式

**前置（必做，否则 import 报模块找不到）**：

```bash
pip install -e "<SKILL_ROOT绝对路径>"          # 安装包 + 依赖（含 pymupdf）；或 export PYTHONPATH=<仓库>/src
```

（自备了优秀论文库的话，可以另跑 `python scripts/preprocess_papers.py --big "<大汇总目录>"` 做预处理；**比赛运行不需要它**。）

- **SKILL_ROOT（skill 仓库）只读**；四类示例仅在独立临时副本运行并落盘，不能在Skill源目录产生结果
- **真实赛题**：从独立赛题cwd用Skill入口绝对路径运行，不复制孤立脚本，产物（results/figures/output）写在工作目录，不污染 skill 仓库
- 测试：`python -m pytest tests/ -v`；仅全文终审可机检项（第一问不可用作前置）：`python "<SKILL_ROOT绝对路径>/scripts/gate_audit.py" --project "<赛题目录绝对路径>"`

## 安全声明

- **优秀论文库需自备**（本仓库不含）。准备时请先**去姓名重命名**、屏蔽手机号等 PII 再入库
- **⚠️ 扫描版论文风险**：2021/2022/2024 部分论文为扫描图（无文字层），AI 视觉读图时**封面/内页可能含学校名或队员姓名**——交前须人工复核删除身份信息（国赛规范：所有文件不能有身份和学校信息）
- 遵守各竞赛学术诚信规则；查重责任在参赛队（AI 只列风险点，不替人决策）

## 适用人群

- **数学建模参赛者**——国赛 / 美赛 / 各类校赛，从读题到交论文的全流程
- **带队老师**——需要可核验的建模过程与质量把关机制
- **想学 AI 协作的人**——这套分工与门禁对数学建模之外的工作同样可用

## v1.0 → v2.0 的变化

v1.0 是「4 个算法示例 + 论文生成框架」，v2.0 扩成了全流程工作流。

| 项目       | v1.0     | v2.0                                  |
| ---------- | -------- | ------------------------------------- |
| 文件数     | 23       | 147                                   |
| 算法       | 4 个示例 | 四大类 65 个（每个带注释 + 真题出处） |
| 核心模块   | 3 个     | 13 个                                 |
| 测试文件   | 无       | 20 个                                 |
| 方法论文档 | 4 篇     | 5 篇                                  |
| 规范文档   | 无       | 11 份                                 |

**v2.0 新增的能力**

- **算法知识库**：65 个算法按优化 / 评价 / 预测 / 机理四类归档，每个带适用情况、联动算法、可跑代码模板、近十年真题出处
- **数据清洗**：六方案速查 + 对比标准（方差 / KS 分布保留度）+ 决策流程
- **六个门禁 + 独立 Subagent 审计**：门禁 0 文献先行 → 1 建模定稿 → 2 代码可跑 → 3 论文成稿 → 4 论文质量 → 5 过程记录，给成功标准不给步骤
- **两阶段流程**：先完成第一问并交审阅报告，团队明确批准后才推进后续问题
- **五样检验**：网格无关 / 数值收敛 / 灵敏度 / 误差分析 / 对比验证，逐项判断适用性
- **数字冻结**：论文里的结果性数字必须来自 `results/`，改数字必须重跑，校验双向
- **TeX + Word 双渲染**、**过程记录**（13 节，含逐问试错链）
- **数据冻结**（`frozen_data.py`）：第二阶段用类型保真的冻结 JSON，不重新清洗

**v1.0 保留的部分**：4 个算法示例、论文生成框架（3 个模块）、4 篇方法论文档。

想对照两个版本：`git checkout 4366f0b` 是 v1.0，`git checkout main` 是最新的 v2.0。完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## 致谢

本 skill 部分设计**借鉴/改编**自 [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills)（**Apache-2.0 license**，作者袁一哲等）：

- **图契约**：画图前先写"核心结论 + 证据链 + 图类型 + 编号"（`references/图契约.md`、`Visualizer.register_figure`）
- **受控配色**：语义色（蓝=本文方法/红=基线/绿=改进），禁 rainbow/jet（`visualizer.py` PALETTE）
- **出版级样式与多面板布局**：去上右 spine、hero 面板 + 从属面板（`_apply_style`）
- **画图 QA 校验**：`scripts/validate_figures.py`（改编自 nature-figure 的 `validate_figure.py`）
- **允许来源定向检索**：失败标待核验，不自动回退第三方（`references/文献调研报告模板.md`）
- **六维评分粗筛**、**文献卡片模板**、**DOI 可解析性校验**（`validate_references`）、**证据-声明矩阵**（文献借鉴节）

此外借鉴了以下 skill 的**思路**（未复制代码，MIT license）：

- [Lupynow/math-modeling-skills](https://github.com/Lupynow/math-modeling-skills)（MIT）——四轮自审框架（论证→结构→表述→格式）、去 AI 味写作、参考文献红线（禁非学术来源、正文引用一一对应）
- [zhnnky329/MathModeling-skills](https://github.com/zhnnky329/MathModeling-skills)（MIT）——数字冻结语义（verify 即冻结，改数字须重跑）、方法可行性探测（risk probe）、图分类四类（诊断图按验证价值选择用途）

早期（v2.0）调研参考的数模 skill 仓库（思路借鉴，未复制代码）：

- [cha3343954211/math-modeling-skill](https://github.com/cha3343954211/math-modeling-skill)（MIT）——门控工作流（S0+G1-G7）、结果冻结、Figure Contract、支撑材料标准化
- [JJ66-git/MathModeling-Skills_JJ](https://github.com/JJ66-git/MathModeling-Skills_JJ)（MIT）——多 skill 组织与借鉴来源记录（SOURCES.md）
- [wityu666/National-Mathematical-Modeling-Competition](https://github.com/wityu666/National-Mathematical-Modeling-Competition)（MIT）——分角色 skill 套件（问题分析/模型设计/编码/写作/结果验证/布局验证/终审）
- [RDold8/math-modeling-contest](https://github.com/RDold8/math-modeling-contest)（MIT）——七步转化法、三层模型架构、灵敏度分析清单、反模式清单
- [DongZhouGu/MathModel-Pretrain](https://github.com/DongZhouGu/MathModel-Pretrain)——数模资料集（建模算法/论文模板/实用工具）

Apache-2.0 素材的完整使用说明见 [`NOTICE.md`](NOTICE.md)。

## 许可

AGPL-3.0。用可以，改了的版本请公开。

## 作者

AR-26710
