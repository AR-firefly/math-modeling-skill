"""
优秀论文共享语料：唯一定位点 + 启动自检（v3.0 计划 C7）

设计约束（三条，缺一不可）：

1. **不随仓库分发**：优秀论文语料需自行准备，仓库内不复制、不缓存。
   **语料目录不可删、不可移**。
2. **禁硬编码**：全库只有本模块定义语料路径常量 `SHARED_PAPERS_DIR`；调用方（run_all / 各脚本）
   一律引用它，不得再写死 `"references/优秀论文"` 之类的字面路径。
   环境变量 `MM_SHARED_PAPERS` 可覆盖默认值——换机器、换目录无需改代码。
3. **可选自检**：`require_shared_papers()` 在语料缺失时抛 `SharedCorpusMissing`，供需要强校验的
   调用方使用。入口 `run_all` 不强制调用——缺失时降级：参考文献比对跳过，并在
   `output/risk_points.md` 写明「未进行参考论文文本比对，此状态不代表零风险」。

为什么代码读不了语料正文（必须写进契约，避免误判"读了个空"）：
语料主体是扫描页——2226 个文件中 2157 张是 jpg/png、仅 37 个 txt。无文字层的扫描 PDF/图片
**只能由 Agent 视觉读取**，`load_ref_papers` 会主动拒绝占位文本与 <100 字符文件。
"""

from __future__ import annotations

import os
from pathlib import Path

# 环境变量名：覆盖语料目录（相对或绝对路径均可）
ENV_VAR = "MM_SHARED_PAPERS"

# v3.0 仓库根 = <SKILL_ROOT>/src/math_modeling/shared_corpus.py 的上两级
SKILL_ROOT = Path(__file__).resolve().parents[2]

# 默认值由 SKILL_ROOT 推导（不是本机绝对路径字面量）：
# v2.0 与 v3.0 同属 “数学建模skill升级/” 目录。
_DEFAULT_SHARED_PAPERS = (SKILL_ROOT.parent / "math-modeling-skill-v2.0"
                          / "references" / "优秀论文")

#: 语料目录常量（导入时的解析结果）。需要感知运行时环境变量时用
#: `resolve_shared_papers_dir()`。
SHARED_PAPERS_DIR = Path(os.environ.get(ENV_VAR) or _DEFAULT_SHARED_PAPERS)


class SharedCorpusMissing(RuntimeError):
    """共享语料目录缺失（或不可用）——入口应据此报错退出，不得降级静默继续。"""


def resolve_shared_papers_dir(env: dict | None = None) -> Path:
    """解析语料目录：环境变量 `MM_SHARED_PAPERS` 优先，否则用默认推导值。"""
    source = os.environ if env is None else env
    override = source.get(ENV_VAR)
    return Path(override).expanduser() if override else _DEFAULT_SHARED_PAPERS


def require_shared_papers(env: dict | None = None) -> Path:
    """启动自检：语料目录必须存在且非空，否则抛 `SharedCorpusMissing`。

    返回解析后的目录（供调用方直接使用，避免二次硬编码）。
    """
    target = resolve_shared_papers_dir(env)
    if not target.is_dir():
        raise SharedCorpusMissing(
            f"共享语料目录不存在：{target}\n"
            f"该目录保存优秀论文语料，v3.0 不复制、不可删移。\n"
            f"若目录已移动，请设置环境变量 {ENV_VAR} 指向实际位置后重试。")
    try:
        has_entry = any(target.iterdir())
    except OSError as exc:  # 权限等原因无法读取
        raise SharedCorpusMissing(f"共享语料目录不可读：{target}（{exc}）") from exc
    if not has_entry:
        raise SharedCorpusMissing(
            f"共享语料目录为空：{target}\n"
            f"语料缺失会导致「文献先行」门禁无据可查，请恢复语料或修正 {ENV_VAR}。")
    return target
