# NOTICE

本仓库（math-modeling-skill）部分内容**借鉴/改编**自
[Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills)
（**Apache-2.0 license**，作者：袁一哲 Yuan1z0825、马昕瑞、胡彬 等）。

## 借鉴/改编的内容（Apache-2.0 素材，保留原版权声明并注明改编）

| 本仓库文件                             | 借鉴自                                              | 借鉴/改编内容                                                                                                                                                                                                   |
| -------------------------------------- | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/math_modeling/visualizer.py`      | nature-figure                                       | 图契约（register_figure）、受控配色 PALETTE（语义色：蓝=方法/红=基线/绿=改进）、出版级样式 `_apply_style`（去上右 spine/无边框 legend）、errorbar/contour/radar/fill_between 图表模式、design-theory 的布局规范 |
| `scripts/validate_figures.py`          | nature-figure `validate_figure.py`                  | 无依赖静态预检框架（语法/字体/配色/DPI/采样/数据排除检查，PASS/WARN/FAIL），按国赛口径改编                                                                                                                      |
| `references/图契约.md`                 | nature-figure `figure-contract.md`                  | 画图前五问、hero 面板 + 从属面板、反冗余检查、QA 校验                                                                                                                                                           |
| `references/图表规范.md`               | nature-figure `design-theory.md` / `chart-types.md` | 受控配色、图表类型决策表、导出规范                                                                                                                                                                              |
| `references/文献调研报告模板.md`       | nature-academic-search + nature-literature-pipeline | T1→T2→T3 多源检索回退、六维评分粗筛（题型匹配 gate）、文献卡片（note-template）                                                                                                                                 |
| `src/math_modeling/paper_generator.py` | nature-ref-verifier                                 | `validate_references` 的 DOI 可解析性检查（Crossref `works/<DOI>`，404=错号）                                                                                                                                   |
| `methodology/process_record规格.md`    | nature-paper-card                                   | 文献借鉴节的证据-声明矩阵写法                                                                                                                                                                                   |

## Apache-2.0 许可

以上素材按 Apache License 2.0 使用（保留原始版权声明、注明改编、附带许可文本）。
完整许可文本见 <https://www.apache.org/licenses/LICENSE-2.0>。

本项目自身代码采用 **AGPL-3.0** license（见 `LICENSE`），Apache-2.0 / MIT 素材并入本项目时保持其各自许可约束。
