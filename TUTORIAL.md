# 使用教程（TUTORIAL）

> 现行阶段、来源、创新、人工声明及交付边界见 `references/执行与交付契约.md`；原细则在当前阶段范围内执行，不代替团队第一问批准或全文独立终审。

> math-modeling-skill v3.0 从安装到接入真实赛题的完整走法。

## 1. 安装

```bash
pip install -r "<SKILL_ROOT绝对路径>/requirements.txt"     # 运行依赖
pip install -e "<SKILL_ROOT绝对路径>"            # 安装当前仓库（或 pip install -e <仓库路径>）
python -c "import math_modeling; print('ok')"   # 验证
pip install -r "<SKILL_ROOT绝对路径>/requirements-dev.txt" # 仅跑测试需要（pytest）
```

依赖：numpy、pandas、scipy、matplotlib、scikit-learn、statsmodels、pymupdf（运行）；pytest 在 requirements-dev.txt（测试）。

## 2. 跑内置 demo（全流程）

```bash
cd "<新建的空演示项目绝对路径>"  # 不能在Skill根或覆盖已有产物
python "<SKILL_ROOT绝对路径>/run_all.py" --demo    # 内置 demo 合成数据跑通全流程
```

自动完成：读题（内置 2 个子问题）→ 生成 demo 数据 → 数据清洗六策略择优 →
逐问求解（通用占位实现）→ 五样检验诊断 → 灵敏度扫描 →
论文生成 → verify 双向校验 → TeX 单渲染。

> demo 产物写到当前工作目录（`output/`、`results/`、`figures/`，git 忽略）：
>
> - `results/results.json` + `results/run_manifest.json` —— 结果与复现清单
> - `output/paper.tex` —— 论文源码（v3.0 唯一交付格式，可在线 LaTeX 编译）
> - `output/process_record.md` —— **核心产出物**：完整可核验决策摘要与实验记录（13 节 + 逐问思考轨迹 + 文献借鉴）
> - `output/risk_points.md` —— 查重风险点清单（人工按清单改写规避）

> **通用占位说明**：run_all 的内置求解是"数据洞察占位"（结果无真实建模意义，论文会标注）。
> 通用五样检验是**真实重算诊断**（不达标标 WARN 进 process_record，不假装通过）；
> 真实赛题由编程手按题型替换为 algorithms/ 对应算法，并换成硬断言五样检验。

## 3. 跑四类示例（Task 9，含五样检验）

```bash
cd examples
python main.py                # 优化类（AGV 全流程）
python 评价_TOPSIS_demo.py    # 评价类
python 预测_GM11_demo.py      # 预测类
python 机理_ODE_demo.py       # 机理类
```

每个示例打印五样检验结论（网格无关/数值收敛/灵敏度/误差分析/对比验证），产物落 `examples/results/`。

## 4. 接入真实赛题

**SKILL_ROOT 只读规则**：本仓库是 Skill 库，不写产物。真实赛题这样用：

```bash
# ① 切换独立赛题工作目录，使用SKILL_ROOT中入口的绝对路径，不复制孤立入口

# ② 在赛题目录放好：
#    - 问题.txt （赛题文本，含"问题N/第N问"标题）
#    - 数据.csv （附件数据）
#    - meta.json （{"title": "赛题名称"}）
cd 赛题目录
python "<SKILL_ROOT绝对路径>/run_all.py" 问题.txt 数据.csv meta.json --solver-module project_solver.py --stage stage1
```

产物（results/、figures/、output/）全写在赛题工作目录，不污染 skill 仓库。

> **真实赛题 = 第一问实际完整材料先审，批准后完成后续全文**（不是 run_all 开箱出论文）：
>
> 1. **编程手 AI 真解**：按题型检索 `algorithms/0X_*/`，把对应算法代码模板替换
>    项目solve_question/prepare_data回调，套赛题数据**真解**，不修改Skill中的演示函数（结果才有建模意义），并深化五样检验到赛题口径。
> 2. **AI完成论文内容并显式传入**：真实run_pipeline读取meta.paper完整结构，不会把meta.analysis/assumptions/evaluation自动接线为真实论文。论文各节、模型检验和评价由AI依据实际题目与实验材料撰写。
>    如需骨架，可单独显式调用 `build_paper_content(results_json, context_meta)` 辅助组织材料；它仅是骨架，须补齐实际全文、删去占位、核验各节，再将完整结构赋给 `meta["paper"]`，同时提供claims和来源证据。不能宣称工具自动生成真实检验结论或模型评价。完整接口见§9。
> 3. **人审查**：拿 `process_record.md` 回放 AI 思路，对照检查求解、检验、论文数字，可要求模型/计算/假设修改，不能限于润色。
> 4. **数字冻结**：论文结果性数字按指标/单位/条件对应 `results/`；年份/编号/常量分类核验。改数字**必须重跑更新 results/**，禁止手改论文数字——再做机器映射核验与独立语义审查，不能假定verify能捕获所有解释错误。

> **run_all 内置 demo 是流程演示**：通用求解是占位（物理上无法对任意赛题自动建模），
> 产物与论文仅演示全流程跑通，**不代表开箱出可用论文**——真实赛题走上面三步。

## 5. 断点恢复（E3）

中断后从独立赛题cwd使用入口绝对路径恢复，保留旧过程原文并核对实际阶段/批准/输入版本；Markdown断点文字不代替批准。
只复用仍有效的阶段证据与冻结输入，缺状态标未知；基础变化后重新审阅，不能从旧日志猜测已通过。

## 6. 读 process_record 定位优化方向（核心产出物）

`output/process_record.md` 13 节——它是"AI 透明工作"的载体：人拿它回放 AI 思路、逐段对照优化。

| 节               | 干什么用                                                                        |
| ---------------- | ------------------------------------------------------------------------------- |
| 赛题判断         | 每问题型依据，供核对建模方向                                                    |
| 数据清洗         | DataCleaner 六策略对比 + 择优理由                                               |
| 算法取舍         | 对比→选择→验证逻辑链（选了什么、弃了什么、为什么）                              |
| 文献借鉴         | 逐篇文献：来源 + 参考了它的什么 + 怎么用到本赛题 + 效果（写透级）               |
| 思考轨迹         | 逐问完整试错链：**怎么想→试了什么→结果如何→在哪撞墙→怎么改进→最终效果**（核心） |
| 灵敏度           | 参数扰动变化幅度排序                                                            |
| 不确定点         | 存疑假设/待定参数/影响多大                                                      |
| 可优化方向       | 换算法/加数据/深化论证                                                          |
| 人工审核方向     | **必须人才能审查的点**（[ ] 清单）                                              |
| 数值归因         | 论文数字 ↔ results 字段 ↔ 代码出处                                              |
| 论文参考与风险点 | 参考了哪些优秀论文、为什么这么写、查重风险点清单摘要、参考文献来源              |
| 复现             | run_manifest.json 路径（seed + SHA-256）                                        |
| 断点             | 当前阶段 / 下一步（断点恢复用）                                                 |

**优化论文的关键动作**：对照"思考轨迹（撞墙→改进） + 风险点 + 可优化方向 + 行动建议 + 人工审核方向"，
逐项解决 AI 自己指出的风险与待确认点，深化论证，然后重跑更新结果与论文。

## 7. 测试

```bash
python -m pytest tests/ -v
```

覆盖：数据清洗、可视化、数值校验、灵敏度、算法库全量（compile + demo exec）。

## 8. 真实两阶段调用补充

在独立项目cwd提供项目solver模块。模块导出 solve_question(question, df, seed, qi, rec) 和 prepare_data(df, rec)，按实际题目实现，不以演示替代。第一阶段只计算Q1并交第一问审阅报告；真实团队批准及独立审查记录完成后，才使用相同入口 --stage stage2 运行依赖后续求解。精确报告/批准字段按当前workflow接口填写真实证据，不能伪造通过。

读取、数据清洗、求解、验证、绘图、论文与自审职责保留，实际赛题由AI实现完整模型与章节，不靠通用骨架自动解决。需要修改基础决策时重新提交团队。所有run_all调用（包括demo）必须独立cwd，demo不能覆盖已有output/results/figures，工具self-test只在独立临时副本运行。

完成判定要有最终可编辑论文、实际渲染检查、代码/数据/图复现证据、真实引用、13节500行过程记录、风险清单、双方终审记录及独立人工待办；运行命令成功不等于AI终审通过或团队可提交。

## 9. 项目模块、meta与批准接口

以下描述实际接口；计算与报告必须来自当前赛题，不能把说明文字或示例值当作完成证据。

### 项目模块

`project_solver.py` 导出：

| 接口                                        | 必须返回/完成                                            |
| ------------------------------------------- | -------------------------------------------------------- |
| prepare_data(df, rec)                       | 按实际题目清洗后的pandas.DataFrame，真实决策写rec        |
| solve_question(question, df, seed, qi, rec) | dict，公开结果键以对应Qn\_或Qn.开头，数值/数组为实际结果 |

第一问返回dict另含 `_basis`（非空的实质模型/假设/算法依据）、`_basis_files`（第一问实际代码/数据依赖路径列表）、`_review`（下列12字段）和可选 `_code_map`（结果字段到代码位置）。别把会独立变化的Q2文件捆绑进第一问依据。

`_review` 必须有 whole_problem、dependencies、assumptions、model、algorithm、results、interpretation、validation、sensitivity、alternatives、uncertainties、downstream，各字段写真实说明并链接实际验证/论文/图表资料。缺项会标待补，不算第一问完成。

### 第一阶段meta.json

```json
{
  "title": "赛题名称",
  "read_csv_options": { "dtype": { "编号": "string" } }
}
```

dtype字段仅在题目确实有该列时保留或按实际列名修改。原CSV可显式指定类型；prepare返回数据冻结到results/df_clean.json（类型保真的权威输入）并导出CSV供阅读，两者哈希均检查。第二阶段从冻结JSON读数据，不重新运行prepare。

### 独立审查与真实批准

独立Agent产生项目内 `output/q1_review.json`，接口如下（待审格式不能取得批准；只有实际独审通过后才填写passed、空问题列表及真实证据）：

```json
{
  "decision": "pending",
  "open_issues": ["由独立审查者记录实际问题"],
  "reviewer": "独立审查者标识",
  "evidence": ["docs/q1_review_evidence.md"],
  "q1_fingerprint": "当前状态的q1_fingerprint值"
}
```

指纹通过 `q1_fingerprint(state)` 取得，state读取当前output/workflow_state.json。审查证据须真实存在且匹配版本。团队明确批准后主Agent才记录真实原文与消息出处；以下代码读取团队已提供的文件，不生成批准：

```python
import json
from pathlib import Path
from math_modeling.workflow import record_team_approval
project = Path.cwd()
record_team_approval(
    project,
    (project / "docs/team_approval.txt").read_text(encoding="utf-8"),
    (project / "docs/team_message_reference.txt").read_text(encoding="utf-8"),
    project / "output/q1_review.json",
)
```

该函数是记录与一致性守卫，不认证用户身份，不能由AI自行编造文本或文件。基础变化重新审阅；标题样式等明确排版变化可保留，内容含义不明则复核。团队批准后命令将 `--stage stage1` 改为 `--stage stage2`。

### 第二阶段meta及完整论文

meta保留title，增加 `q1_basis`（与第一问返回\_basis完全一致）。论文手将实际完整PAPER_STRUCT写入meta.paper：meta.title、abstract字符串列表、sections列表（每节title、paras、formulas、tables、images）、references字符串列表、ai_declaration空字符串。表含caption/headers/rows/notes，图含path/caption/notes；必要符号、单位和条件写入内容，不以占位说明冒充正文。

meta同时提供：

- `claims`：实际结果声明列表，含path、text、label、value、unit、expected_unit；派生量按实际计算给scale/offset和derivation。标签、单位及数字必须对应实际论文。
- `non_result_numbers`：每项text、kind（year/index/constant/citation/unit/input）、reason，解释非结果数字，不用它掩盖未映射的实验结果。
- `source_evidence`：与参考文献同序，每项status、publisher、original_url、purpose、original_source、verification_note；真实核验后才能填verified与true。
- `selected_papers`：相对**共享语料目录**（`SHARED_PAPERS_DIR`，可用环境变量 `MM_SHARED_PAPERS` 覆盖；语料保留在 v2.0 目录、不在本仓库）的已选UTF-8文本文件路径列表，不允许越界或扫描占位文本；实际阅读全文及页码证据另记，文本相似检查不等于全文质量审查。

没有meta.paper只保存计算待审状态，不能声称全文完成。pipeline最多生成final_awaiting_review；完成全部质量改进、渲染、复现和固定双审后再交付。AI声明/详情正文保持空白，人工事项不由AI伪造完成。

## 10. 全文final_review.json与最终审计

只有完成真实全文、渲染、复现和主Agent/独立Agent审查后才形成最终结论。先以待审状态建立 `output/final_review.json`，各项字段如下；不要复制“passed”模板冒充已经审过。

| 字段               | 内容                                                                  |
| ------------------ | --------------------------------------------------------------------- |
| schema_version     | 整数1                                                                 |
| criteria_file      | 固定为references/终审运行检查表.md（项目相对路径）                    |
| criteria_sha256    | 项目内该标准文件的实际SHA-256，必须与第一问首次冻结的workflow状态一致 |
| self_review        | reviewer、decision、open_issues、evidence四字段；主Agent实际自审记录  |
| independent_review | 同上，由另一位独立审查者提供，reviewer必须与主Agent不同               |
| artifact_hashes    | 项目相对文件路径到实际SHA-256的映射                                   |

两份review中的decision未审或未通过时保持pending/failed，并记录真实open_issues；只有实际审查全部通过才记passed及空问题列表。evidence为非空项目相对路径列表，指向实际审查证据文件；不能只写“已通过”而无逐项事实。

artifact_hashes必须包括：output/paper.json、paper.tex、claims.json、source_evidence.json、process_record.md、workflow_state.json，results/results.json，figures/figures_manifest.json；若存在output/non_result_numbers.json也纳入。逐图图片、绘图脚本、数据入口，以及self_review和independent_review两方列出的所有证据文件，同样必须纳入真实哈希。所有路径须在项目内且文件存在。final_review.json自身不作自哈希；criteria由criteria_sha256及首次冻结基线双重核对。哈希只证明文件版本一致，不能证明内容正确。

在完整产物准备好后，从独立赛题cwd执行：

```bash
python "<SKILL_ROOT绝对路径>/scripts/gate_audit.py" --project "<赛题项目绝对路径>"
```

这是全文可机检审计，不能作为第一问阶段前置条件。它要求真实第二阶段和有效第一问批准，核对实际交付物、两方审查证据及冻结标准。任何被审文件改变，都必须按实际影响重新审查并更新真实哈希；不能仅重算哈希消除问题。审计返回machine_checks_only，即使机器通过仍不代表评委必给国奖或团队人工事项完成。

## 11. 七份编排任务书怎么用

`references/任务书/` 里是七份文档：一份 **需求文档（主agent）.md** + 六份角色任务书（建模手 / 编程手 / 作图手 / 论文手 / 信息检索手 / 审查手）。

它们把 SKILL.md 的六角色表落成可执行剧本——每个角色具体加载哪些文档、产出什么、按什么格式写日志、在哪个门禁交审。跑真实赛题时，主 Agent 按需求文档派活，各角色按各自的任务书干活。

**这七份文档是按一套具体工作环境写的，你可以改：**

- 需求文档 §0 有任务参数表（赛题文件、Skill 路径、工作目录）——**开跑前先填**
- 文中 `SKILL_ROOT` 指你的 skill 仓库根目录，按实际路径替换；`<SKILL_ROOT>` 是待填占位符
- 角色划分、加载清单、日志格式都可以按自己的习惯调整；建议先完整跑一遍，知道每条在防什么问题再动
