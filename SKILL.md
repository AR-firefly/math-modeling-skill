---
name: math-modeling
description: 数学建模全流程：人机协作完成问题分析→算法求解→论文生成。含AI协作心法、分步工作流、标准算法库、论文生成框架。
model: opus
when: 用户需要完成数学建模竞赛题目的建模、求解和论文撰写
---

# 🏆 数学建模全流程 Skill

## 这是什么

一个**完整的人机协作方法论 + 工具链**，覆盖数学建模竞赛全流程：

```
问题理解 → 头脑风暴 → 制定计划 → 资源调查
→ 实现求解 → 简化优化 → 验证确认 → 论文生成 → 自评验收
```

不是上来就写代码。先想清楚、再计划、再执行、再验证。

---

## 工作流程

### Phase 0: 问题理解

理解题目类型、规模、约束。确保人有数、AI 没跑偏。

### Phase 1: 头脑风暴 (Brainstorming)

AI 给出 2-3 种技术路线。不写代码，只聊天。
参考：`methodology/分步工作流.md` Phase 1

### Phase 2: 制定计划 (Plan)

选方向 → 出详细计划 → 你来审核。
计划包含：做什么、涉及文件、实现步骤、验证方法。
参考：`methodology/算法选型指南.md`

### Phase 3: 资源调查

检查已有 skill / 已有代码，不造轮子。

### Phase 4: 实现求解

按 `examples/` 模板写代码，分步跑通，结果存 `results/`。
参考：`examples/main.py`

### Phase 5: 简化优化 (Simplify)

从复用、简化、效率、深度 4 个维度审查代码。
参考：`methodology/AI协作心法.md` — 最小更改检查

### Phase 6: 验证确认 (Verify)

跑真场景，看实际输出，不只看代码。
参考：`methodology/AI协作心法.md` — 验证闭环

### Phase 7: 论文生成

配置 `PaperConfig` → 注入 `results.json` → 生成 .docx。
参考：`src/math_modeling/paper_generator.py`

### Phase 8: 自评验收

对照 `methodology/写作心法.md` 逐项检查。安全扫描。

---

## 方法论文档

| 文档                          | 内容                                                         |
| ----------------------------- | ------------------------------------------------------------ |
| `methodology/AI协作心法.md`   | 人与AI配合的哲学：沟通规则、安全边界、自检机制、Karpathy原则 |
| `methodology/分步工作流.md`   | 8阶段详细流程：每步谁做什么、输入输出、关键点                |
| `methodology/写作心法.md`     | 论文写作规范：标题规则、摘要总分总、模型格式、13节结构       |
| `methodology/算法选型指南.md` | 算法选择决策树、参数设定参考                                 |

## 代码工具

| 模块                 | 作用                                   |
| -------------------- | -------------------------------------- |
| `examples/`          | 示例代码（纯随机数据，与任何竞赛无关） |
| `src/math_modeling/` | 论文生成框架（`pip install` 后可导入） |
| `pyproject.toml`     | pip 安装配置                           |

## 快速使用

```bash
# 1. 安装
pip install -r requirements.txt

# 2. 跑示例（纯随机数据，仅演示框架）
cd examples && python main.py

# 3. 生成示例论文（自动填入结果）
python ../src/math_modeling/paper_generator.py
```

## 核心原则（来自 AI 协作心法）

1. **先计划再动手** — 不盲目编码
2. **验证才算完** — 跑通才是证据
3. **最小更改** — 只改需要改的
4. **安全红线** — 敏感信息不泄露
5. **双向反驳** — AI 和人都可以说"不对"
6. **自评闭环** — 每个阶段自我检查

详情见 `methodology/AI协作心法.md`。
