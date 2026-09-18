"""过程记录（ProcessRecorder）：可核验的决策与实验记录 + 断点恢复。

核心：**完整工作记录**——AI 透明工作，人对照着去优化。
process_record 是核心产出物，必须记录：决策依据与实验过程、为什么这么做、
结果如何、在哪撞墙了、后来怎么改进、最终效果、算法取舍（多种算法怎么选）、
AI 的风险点、需要人审查的点、优化方向、之后的行动建议。不是填空。

职责：
- log(section, text)      —— 追加一条到指定节（同节可多次）
- log_trace(qid, stage, thought) —— 逐问思考轨迹，stage 用标准阶段（六步试错链）：
    怎么想 / 试了什么 / 结果如何 / 在哪撞墙 / 怎么改进 / 最终效果
    （兼容旧阶段：题型判断 / 算法尝试 / 撞墙 / 改进 / 算法取舍 / 验证）
- checkpoint(stage, next_step)   —— 断点：记录当前阶段+下一步
- resume()                —— 断点恢复：读上次阶段，续跑不重头
- save(path)              —— 生成 process_record.md（思考轨迹节按 Q 分子标题渲染）

各节填充责任（run_pipeline 与 solve_question 逐项负责，见 run_all.py）：
- 赛题判断 → solve_question 内部确认题型后 log（不在求解前占位）
- 数据清洗 → run_pipeline 清洗阶段；灵敏度 → 全局扫描后
- 算法取舍 / 思考轨迹（含撞墙·改进链） → solve_question 内部逐问
- 风险点与不确定点 / 可优化方向 / 人工审核方向 / 复现 → run_pipeline 逐问循环显式 log
- 数值归因 → build_provenance 后；断点 → checkpoint；行动建议 → run_pipeline 逐问 + 全局
"""
from __future__ import annotations

import re
from pathlib import Path


class ProcessRecorder:
    """13 节过程记录（AI 工作记录）+ 逐问思考轨迹 + 断点恢复。"""

    # 13 节："文献借鉴"= 解题阶段参考了什么文献、怎么用到本赛题（写透级）；
    # "论文参考与风险点"= 写作阶段的论文参考 + 查重，两者语义区分。
    SECTIONS = ["赛题判断", "数据清洗", "算法取舍", "文献借鉴", "思考轨迹", "灵敏度",
                "不确定点", "可优化方向", "人工审核方向", "数值归因",
                "论文参考与风险点", "复现", "断点"]

    # 试错链六步标准 stage（log_trace 用）；兼容旧 stage 名
    TRACE_STAGES = ["怎么想", "试了什么", "结果如何", "在哪撞墙", "怎么改进", "最终效果"]
    LEGACY_STAGES = ["题型判断", "算法尝试", "撞墙", "改进", "算法取舍", "验证"]

    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._entries = {s: [] for s in self.SECTIONS}
        self._traces = {}        # {qid: [(stage, thought), ...]}
        self._checkpoint = None  # (stage, next_step)
        path = self.output_dir / "process_record.md"
        self._history = path.read_bytes() if path.exists() else b""
        self._last_saved = self._history
        self._destinations = {path.resolve(): (self._history, self._history)}

    # ── 记录 ──
    def log(self, section, text):
        """追加一条记录到指定节（同节可多次）。"""
        if section not in self._entries:
            self._entries[section] = []
        self._entries[section].append(str(text))
        return self

    def log_trace(self, qid, stage, thought):
        """逐问思考轨迹：qid=问题号, stage=六步试错链阶段
        (怎么想/试了什么/结果如何/在哪撞墙/怎么改进/最终效果；
        兼容旧: 题型判断/算法尝试/撞墙/改进/算法取舍/验证), thought=决策摘要或实验事实。"""
        self._traces.setdefault(qid, []).append((stage, str(thought)))
        return self

    def checkpoint(self, stage, next_step):
        """断点：当前阶段 + 下一步。"""
        self._checkpoint = (stage, next_step)
        self._entries["断点"].append(f"当前阶段：{stage} / 下一步：{next_step}  # 人工可接着 AI 思路继续")
        self.save()
        return self

    def resume(self):
        """断点恢复：读已存在的 process_record.md 的"断点"节，返回上次阶段。"""
        path = self.output_dir / "process_record.md"
        if not path.exists():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
        matches = re.findall(r"(?:^|\n)(?:- )?当前阶段：(.+?) / 下一步：", text)
        return matches[-1].strip() if matches else ""

    # ── 落盘 ──
    def save(self, path=None):
        """生成 process_record.md；思考轨迹节按 Q 子标题渲染完整工作记录。"""
        path = Path(path) if path else self.output_dir / "process_record.md"
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["# 过程记录", "",
                 "> **核心产出物**：AI 透明工作，人主导优化。本文档是 AI 的完整工作记录——",
                 "> 每问怎么想、试了什么、结果如何、在哪撞墙、怎么改进、最终效果、",
                 "> 多种算法怎么取舍、AI 的风险点、需要人审查的点、优化方向、之后的行动建议。",
                 "> 人拿着它复核工作过程、逐段对照优化，与论文并列，不是附属品。", ""]

        for section in self._entries:
            lines.append(f"## {section}")
            if section == "思考轨迹":
                # 逐问轨迹：每个 Q 一个子标题，按阶段顺序列出；顶部提示六步试错链
                lines.append("> 逐问完整试错链：怎么想→试了什么→结果如何→在哪撞墙→怎么改进→最终效果。如实记录；未发生的失败标记未发生，不编造试错。")
                lines.append("")
                for qid in sorted(self._traces.keys()):
                    lines.append(f"### 问题{qid}")
                    for stage, thought in self._traces[qid]:
                        lines.append(f"- **[{stage}]** {thought}")
                if not self._traces:
                    lines.append("- （无逐问轨迹）")
            elif section == "人工审核方向":
                # 需求原话"逐条 [ ]"：人工审核项渲染成勾选清单，人可逐条打勾
                for item in self._entries.get(section, []):
                    lines.append(f"- [ ] {item}")
                if not self._entries.get(section):
                    lines.append("- [ ] （无）")
            else:
                for item in self._entries.get(section, []):
                    lines.append(f"- {item}")
                if not self._entries.get(section):
                    lines.append("- （无内容）")
            lines.append("")

        current = path.read_bytes() if path.exists() else b""
        key = path.resolve()
        history, last_saved = self._destinations.get(key, (current or self._history, current))
        if current != last_saved:
            raise RuntimeError("过程记录被其他写入者修改，请重新加载后再追加，禁止覆盖历史")
        payload = history + (b"\n\n" if history else b"") + "\n".join(lines).encode("utf-8")
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
        self._destinations[key] = (history, payload)
        return path
