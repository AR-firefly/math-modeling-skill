# 数学建模全流程 Skill

> 不是教你数学建模。是教你用 AI 协作做完数学建模。

每年几十万人参赛，很多人都花 3 天在干同一件事：跟队友吵架、跟论文搏斗、跟算法死磕。

这个项目不是给你一段代码跑的——**是给你一套工作流，告诉你每步怎么跟 AI 配合**。从读题到交论文，人做什么、AI 做什么、怎么沟通才不会翻车。

新手 10 分钟上手 → [TUTORIAL.md](TUTORIAL.md)

## 设计理念

大多数数学建模开源项目给你的是代码。这个项目给你的是**人怎么跟 AI 一起工作的方法**：

- **人机分工明确**：8 阶段流程，每步写清楚谁干什么。AI 不替你思考，你也不用硬写代码。
- **方法论 > 代码**：代码只是示例。真正的价值在 methodology/ 里的协作心法、写作心法、算法选型指南——这些东西换个赛题照样用。
- **可落地**：不是空谈理论。每个方法论都绑定了实操步骤，跟着走就能出东西。

## 结构

```
math-modeling-skill/
├── SKILL.md                    ← Claude Code Skill 入口（全流程指南）
├── pyproject.toml              ← pip 安装配置
├── methodology/                ← 方法论文档（真正的价值）
│   ├── AI协作心法.md           ← 人机协作：怎么沟通、怎么校验、Karpathy原则
│   ├── 分步工作流.md           ← 8阶段流程：每步谁做什么、交付什么
│   ├── 写作心法.md             ← 论文写作规范：结构/标题/摘要/格式
│   └── 算法选型指南.md          ← 算法决策树 + 参数设定
├── src/math_modeling/          ← 论文生成框架（可 pip install）
│   ├── paper_generator.py      ← 参数化论文生成器
│   ├── formula_renderer.py     ← LaTeX → PNG 渲染
│   └── table_builder.py        ← 三线表构建器
├── examples/                   ← 示例代码（纯随机数据演示用）
│   ├── config.py
│   ├── tsp_solver.py           ← Phase1: TSP(Held-Karp DP)
│   ├── vrptw_ga.py             ← Phase2: VRPTW(增强GA)
│   ├── nsga2.py                ← Phase3: NSGA-II+VNS
│   ├── layout_optimizer.py     ← Phase4: 两阶段布局优化
│   └── main.py                 ← 全流程串联入口
├── requirements.txt
└── .gitignore
```

## 快速开始

### 一键运行（示例）

```bash
pip install -r requirements.txt
python run_all.py
```

安装依赖 → 模型求解 → 生成论文 → 汇总结果。约 1-2 分钟。

### 接入你自己的题目

1. 改 `examples/config.py`：坐标、参数、任务数据
2. 跑 `python run_all.py`
3. 在 `PaperConfig` 设学校名、标题

> 示例数据全是随机生成的，仅用于演示。你实际比赛时替换成真实数据就行。

### 作为 Claude Code Skill 用

```json
// .claude/settings.json
{
  "skills": {
    "math-modeling": "/path/to/math-modeling-skill"
  }
}
```

然后在对话里输 `/math-modeling` 调用。

## 内含算法

| 阶段   | 算法                        | 适用场景          |
| ------ | --------------------------- | ----------------- |
| Phase1 | Held-Karp DP / 最近邻       | 小规模 TSP 精确解 |
| Phase2 | GA + FFD 装箱 + LPT + 2-opt | VRPTW / 调度问题  |
| Phase3 | NSGA-II + VNS 局部搜索      | 多目标优化        |
| Phase4 | 两阶段（TSP粗搜 + GA精评）  | 布局 / 参数优化   |

## 安全声明

- 本项目**不含**任何竞赛题目数据、学校模板或个人身份信息
- 所有示例数据纯随机生成
- 用户使用时应替换为实际问题数据
- 遵守各竞赛学术诚信规则

## 适用人群

- **数学建模参赛者**：从读题到交论文的全流程指导
- **想学 AI 协作的人**：这套方法论对数学建模之外的工作也有用
- **Claude Code 用户**：直接加载为 skill，比赛时自动触发

## 致谢

Claude Code + GitHub 开源社区

## 许可

AGPL-3.0。用可以，改了的版本请公开。

## 作者

AR-26710
