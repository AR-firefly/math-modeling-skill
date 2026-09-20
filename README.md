# 🏆 数学建模国赛全流程 Skill v3.0

> 现行阶段、来源、创新、人工声明及交付边界见 `references/执行与交付契约.md`；原细则在当前阶段范围内执行，不代替团队第一问批准或全文独立终审。

> 从问题分析到论文生成的一站式数学建模竞赛工具箱（v3.0，基于需求文档 v5.0 + 近十年真题实证）

> ⚠️ **本仓库不含优秀论文库**。下文提到的「深度参考优秀论文」指的是历年国赛优秀论文资料（约 516 MB），需要你自己准备，原因见[「为什么本仓库不含优秀论文库」](#为什么本仓库不含优秀论文库)。没有它工作流不会中断。

> **版本**：v3.0（当前） · [v2.0](https://github.com/AR-firefly/math-modeling-skill/blob/v2.0/README.md) · [v1.0](https://github.com/AR-firefly/math-modeling-skill/blob/v1.0/README.md) —— 三版有什么区别、怎么切换，见文末[「版本」](#版本)

## 设计理念

数学建模竞赛里，AI 能写代码、能算、能写论文，但方向判断得人来做。这套 skill 把流程拆成可审查的环节，每个环节有明确的依据要求和验收标准：

- **一切基于运行结果**——论文里的结果性数字必须来自求解产物，改数字必须重跑，校验双向（结果 → 论文、论文 → 结果）。
- **质量靠独立审查**——门禁由独立 Subagent 审计，给成功标准不给步骤；自审与独审分开，不以自评分通关。
- **过程可核验**——AI 的决策、试错、取舍全部落到过程记录，人能对照着优化，也能复现。
- **分工明确到角色**——六个角色各自加载对应文档、各自按门禁交付，不一次性把上下文灌满。
- **可复现不是口号**——作图脚本能在空 cwd 独立跑通，随机算法 seed=42 固定，元启发式跑 3 次报均值±标准差。

## 这是什么？

一套面向**全国大学生数学建模竞赛**的完整人机协作工作流：**读题 → 信息检索（证据轨/情报轨隔离）→ 数据清洗（多方案对比）→ 算法索引检索 → 逐问求解 → 五样检验 → 灵敏度 → 作图（可独立复现 + 多模态目视）→ 基于事实写论文（深度参考优秀论文）→ 查重风险点清单 → TeX 单渲染 → 三层自评 → 过程记录**。

定位：**AI 透明工作、人主导优化**。AI 完成建模求解与完整论文，并按固定标准自审/独审返工（基于赛题/参考论文/求解结果生成），团队决定审阅和提交，AI 仍需完成全部质量改进（润色措辞、深化论证、改写规避查重）。

## 文件结构

```
math-modeling-skill/
│
├── SKILL.md                       ← 入口：六角色渐进加载 + 七门禁 + AI 行为边界
├── README.md                      ← 本文件（结构导航）
├── TUTORIAL.md                    ← 使用教程：安装/跑管线/接入赛题/断点恢复/读过程记录
├── CHANGELOG.md                   ← 版本更新说明（v1.0 → v2.0 → v3.0）
├── LICENSE                        ← AGPL-3.0
├── NOTICE.md                      ← 第三方素材署名与许可说明
├── pyproject.toml                 ← 包配置（v3.0.0，7 依赖）
├── requirements.txt               ← 依赖清单（运行）
├── requirements-dev.txt           ← 开发依赖（测试）
├── results_demo_data.csv          ← 示例数据
├── .gitignore                     ← 忽略产物（output/results/figures）
├── .gitattributes                 ← 换行符规则
├── run_all.py                     ← 两阶段编排：run_pipeline（Q1真实交付→团队批准→后续与全文）
│
├── methodology/                   ← 方法论（5 篇心法）
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
│   ├── visualizer.py              ← 可视化：基于数据特征自主选图，300dpi（分层目录 + manifest 状态机）
│   ├── data_cleaner.py            ← 数据清洗：多方案自动对比 + 选择理由
│   ├── verify.py                  ← 三层数值校验 + 数值归因 + run_manifest
│   ├── sensitivity.py             ← 灵敏度分析：单参数/多参数联合
│   ├── process_recorder.py        ← process_record 心路历程生成 + 断点恢复
│   ├── frozen_data.py             ← 冻结输入校验（哈希一致性）
│   ├── shared_corpus.py           ← 共享语料唯一定位点（SHARED_PAPERS_DIR / MM_SHARED_PAPERS）
│   ├── workflow.py                ← 两阶段状态机 + 团队批准记录 + q1 指纹
│   └── tex_renderer.py            ← .tex 渲染（可编辑源码，对齐国赛规范；v3.0 唯一渲染路径）
│
├── references/                    ← 参考文档（13 份）
│   ├── 执行与交付契约.md          ← 统一约束：两阶段/受控来源/双轨隔离/交付物/目视检查
│   ├── Subagent质检.md            ← 门禁 2a/2b（共七节点）独立审计成功标准
│   ├── 终审运行检查表.md          ← 全文终审固定标准（含绘图复现行）
│   ├── 作图契约.md                ← 数据图/示意图分类 + 脚本硬规范 + 统计禁令 + manifest 状态机
│   ├── 图契约.md                  ← 画图前五问（指向 作图契约.md 的简版）
│   ├── 图表规范.md                ← 选图决策表 + 图题下/表题上/300dpi + 配色/线宽/字号/网格
│   ├── 改图指南.md                ← 图号→脚本→数据字段→重跑命令 的可复现改图模板
│   ├── 论文自评表.md              ← 门禁4 三层自评（硬门槛 + 官方四维度 + 检查项）
│   ├── 去AI味写作.md              ← 八类 AI 痕迹识别与改法（四轮自审第三轮用）
│   ├── 文献调研报告模板.md        ← 多源检索 + 六维评分粗筛 + 文献卡片 + 核心建模选择预登记
│   ├── 数学建模国赛评价表.md      ← 官方评价维度与硬门槛（A/B/C/D 可信度分级）
│   ├── 国赛参赛规则2026.pdf       ← 参赛纪律（AI 辅助但人负全责、引用规范列文献）
│   ├── 国赛论文规范2026.pdf       ← 论文格式规范（摘要一页/正文≤30页/附录程序清单/无身份信息）
│   └── 任务书/                    ← 七份编排任务书（可按自己情况修改）
│       ├── 需求文档（主agent）.md  ← 六角色分工/硬约束/并行协调/审查协议/提交前检查
│       └── 建模手/编程手/作图/论文手/信息检索/审查 Agent 任务书.md
│
├── examples/                      ← 可运行示例（四类题型，五类检验逐项审适用性）
│   ├── main.py                    ← 优化类示例（AGV 协同调度）
│   ├── 评价_TOPSIS_demo.py        ← 评价类
│   ├── 预测_GM11_demo.py          ← 预测类
│   └── 机理_ODE_demo.py           ← 机理类
│
├── tests/                         ← 单元测试（27 个文件，350 个用例）
│   ├── test_data_cleaner.py / test_visualizer.py / test_verify.py / test_sensitivity.py
│   ├── test_algorithm_catalog.py / test_risk_review.py / test_frozen_data.py
│   ├── test_stage_gate.py / test_execution_boundary.py / test_selftest_isolation.py
│   └── test_figure_*.py / test_upgrade_*.py / test_redo_*.py …
│
├── scripts/                       ← 辅助脚本
│   ├── stage_gate.py              ← 阶段门禁检查器（第一问即可跑，不依赖全文产物）
│   ├── gate_audit.py              ← 全文门禁审计脚本（含 --self-test）
│   ├── validate_figures.py        ← 绘图脚本静态预检（字体/配色/DPI/脚本可运行/契约/AST）
│   ├── figure_runtime_guard.py    ← 作图运行时统计守卫（monkeypatch 统计函数为抛异常）
│   ├── check_figure_binding.py    ← 插桩比对：实际绘图入参 ↔ results 键值
│   └── build_submission_zip.py    ← 独立编译 ZIP（包内统一相对路径，无本机绝对路径）
│
└── output/                        ← 产出物（每次运行生成，git 忽略）
    ├── paper.tex                  ← 论文源码（人深度编辑、润色微调；v3.0 唯一论文交付格式）
    ├── process_record.md          ← AI 完整可核验决策摘要与实验记录——核心产出物
    └── risk_points.md             ← 查重风险点清单（人工按清单改写规避）
```

## 核心原则

1. **事实铁律**：一切基于代码运行结果，论文结果性数字按指标/单位/条件与 results/ 对应，技术强制校验（verify 不一致阻断）
2. **seed=42 固定**：所有随机算法可复现；元启发式跑 3 次报均值±标准差（标明误差定义）
3. **深度参考优秀论文**（库需自备）：AI 写论文时读共享语料中对应题型论文全文借鉴（结构/论证/表述）；`build_paper_content` 提供骨架，**不自动写完整初稿**。写后自审产出查重风险点清单，人工按清单改写规避；AI 不编造参考文献
4. **文献标准**（skill 自定）：绝大部分近五年（2021-2026）、经典著作可例外；总数 ≤ 10 篇（上限非固定）；标准格式 + DOI/URL；文献必须真实
5. **SKILL_ROOT 只读 + 共享语料只读**：skill 仓库只读，产物写用户赛题工作目录；共享语料目录不可删、不可移
6. **作图可独立复现 + 必须目视**：图脚本 `__file__` 相对定位、空 cwd 独立跑通；禁统计推断；每张图实际打开看过
7. **检索双轨隔离**：证据轨（可核验）喂门禁0；情报轨（不可核验）落 `docs/情报/`，任何执行 Agent 不得读取
8. **禁止将赛题产物 push 到 GitHub**

## 运行方式

**前置（必做，否则 import 报模块找不到）**：

```bash
pip install -e "<SKILL_ROOT绝对路径>"          # 安装包 + 依赖（含 pymupdf）；或 export PYTHONPATH=<仓库>/src
```

- **SKILL_ROOT（skill 仓库）只读**；四类示例仅在独立临时副本运行并落盘，不能在 Skill 源目录产生结果
- **跑内置 demo**：切到一个**新建的空目录**，用绝对路径调用（不能在 Skill 根或覆盖已有产物）：

```bash
cd "<新建的空演示项目绝对路径>"
python "<SKILL_ROOT绝对路径>/run_all.py" --demo
```

- **真实赛题**：从独立赛题 cwd 用 Skill 入口绝对路径运行，不复制孤立脚本，产物（results/figures/output）写在工作目录，不污染 skill 仓库
- **第一问阶段产物检查**（可机检）：`python "<SKILL_ROOT绝对路径>/scripts/stage_gate.py" --project "<赛题目录绝对路径>" --stage q1`
- 测试：`python -m pytest tests/ -v`；仅全文终审可机检项（第一问不可用作前置）：`python "<SKILL_ROOT绝对路径>/scripts/gate_audit.py" --project "<赛题目录绝对路径>"`

## 为什么本仓库不含优秀论文库

工作流里「深度参考优秀论文」用到的那套历年国赛优秀论文库（约 516 MB）**不随仓库分发**，需要你自备。三个原因：

1. **含个人信息**——库里相当一部分是扫描件（无文字层），封面/内页可能带学校名和队员姓名，整库公开等于公开他人身份信息
2. **版权**——论文著作权属于参赛者，整库转载未获授权
3. **体积**——516 MB 会让 clone 变得很慢

**没有它工作流不会中断**：查重比对会自动跳过，并在 `output/risk_points.md` 里写明「未进行参考论文文本比对，此状态不代表零风险」。

自备时请注意：

- 先**去姓名重命名**、屏蔽手机号等个人信息再入库
- 用环境变量 `MM_SHARED_PAPERS` 指向实际位置即可，不必和仓库放同级

## 安全声明

- 优秀论文库需**自备**（本仓库不含）。准备时请先**去姓名重命名**、屏蔽手机号等 PII 再入库
- **⚠️ 扫描版论文风险**：2021/2022/2024 部分论文为扫描图（无文字层），AI 视觉读图时**封面/内页可能含学校名或队员姓名**——交前须人工复核删除身份信息（国赛规范：所有文件不能有身份和学校信息）
- 遵守各竞赛学术诚信规则；查重责任在参赛队（AI 只列风险点，不替人决策）

## 适用人群

- **数学建模参赛者**——国赛 / 美赛 / 各类校赛，从读题到交论文的全流程
- **带队老师**——需要可核验的建模过程与质量把关机制
- **想学 AI 协作的人**——这套分工与门禁对数学建模之外的工作同样可用

## 版本

三个版本都保留在 git 历史里，随时可取。

### 怎么用某一个版本

**只要某一版**（不拉全部历史，体积最小）：

```bash
git clone -b v2.0 --depth 1 https://github.com/AR-firefly/math-modeling-skill.git
```

**克隆后切换**（切换完想回最新版用 `git checkout main`）：

```bash
git clone https://github.com/AR-firefly/math-modeling-skill.git
cd math-modeling-skill
git checkout v1.0        # 或 v2.0 / v3.0
```

**不装 git，直接下 ZIP**：

```
https://github.com/AR-firefly/math-modeling-skill/archive/refs/tags/v2.0.zip
```

各版本的 README：**[v1.0](https://github.com/AR-firefly/math-modeling-skill/blob/v1.0/README.md)** · **[v2.0](https://github.com/AR-firefly/math-modeling-skill/blob/v2.0/README.md)** · **v3.0（本页）**

### 三版变化

| 项目     | v1.0                        | v2.0                       | v3.0                                                       |
| -------- | --------------------------- | -------------------------- | ---------------------------------------------------------- |
| 定位     | 论文生成框架 + 4 个算法示例 | 全流程工作流               | 全流程工作流 + 六角色分工                                  |
| 文件数   | 23                          | 147                        | 163                                                        |
| 算法     | 4 个示例                    | 四大类 65 个（带真题出处） | 四大类 65 个（带真题出处）                                 |
| 核心模块 | 3 个                        | 13 个                      | 11 个                                                      |
| 测试文件 | 无                          | 20 个                      | 27 个（350 个用例）                                        |
| 角色     | —                           | 3 角色                     | 6 角色（+ 主 Agent 编排）                                  |
| 门禁     | —                           | 6 门禁                     | 7 门禁（2 拆 2a/2b）                                       |
| 论文输出 | Word                        | TeX + Word 双渲染          | LaTeX 单渲染                                               |
| 规范文档 | 无                          | 11 份                      | 13 份 + 7 份编排任务书                                     |
| 检索     | 无                          | 文献调研报告               | 证据轨 / 情报轨物理隔离                                    |
| 作图     | 无                          | 图契约 + 静态预检          | 作图契约 + manifest 状态机 + AST/运行时双守卫 + 多模态目视 |

**v3.0 新增的能力**

- **六角色分工**：主 Agent（编排/插审/终审整合，不亲自跑题）+ 建模手 / 编程手 / 作图手 / 论文手 / 信息检索手 / 审查手，各自加载对应文档，渐进式推进
- **七门禁**：0 文献先行 → 1 建模定稿 → 2a 代码可跑 → 2b 图可复现 → 3 论文成稿 → 4 论文质量 → 5 过程记录
- **检索双轨隔离**：证据轨（可核验）喂门禁0；情报轨（第三方解析、他人思路）落 `docs/情报/`，执行 Agent 不得读取——不可验证的信息进上下文后会伪装成证据
- **作图层重做**：作图契约 + 改图指南 + manifest 状态机；统计量由编程手算好落盘，作图脚本内的统计调用被 AST 静态检查 + 运行时守卫双拦；每张图必须实际打开看过，门禁2b 审查 Agent 独立看图
- **交付链脚本**：`stage_gate.py`（第一问即可跑的阶段门禁）、`build_submission_zip.py`（独立编译 ZIP，包内无本机路径）、`check_figure_binding.py`（插桩比对绘图入参与 results）、`figure_runtime_guard.py`（统计调用运行时守卫）
- **三层自评**（`references/论文自评表.md`）：硬门槛 + 官方四维度 + 检查项，均不含分值、不作获奖等级预测
- **编排任务书 7 份**（`references/任务书/`）：把六角色和七门禁落成可执行的剧本，**可按自己的情况修改**
- **共享语料唯一定位点**（`shared_corpus.py`）：全库只有一处定义语料路径，禁硬编码

**v3.0 移除的部分**：Word 渲染链（`docx_renderer` / `formula_renderer` / `table_builder`）与两个维护脚本（`copy_refs` / `preprocess_papers`）——论文统一走 LaTeX，Word 不再产出。

## 致谢

感谢**我的老师**为我们培训，给了我很多思路上的启发，同时也感谢**与我并肩作战的队友**，感谢他们的努力付出。

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
