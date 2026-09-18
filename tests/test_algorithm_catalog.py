"""算法库 .md 代码块全量校验：语法 + demo 可执行（seed=42 自包含）。

用途：算法目录写完后立即跑，不等最后才暴露算法代码 bug。
覆盖：algorithms/ 下所有 .md 的所有 ```python 代码块。
规则：demo 必须自包含（numpy 合成 seed=42）、含 assert、禁止 plt.show()/input()。
"""
import re
import pathlib

import pytest

ALGO_ROOT = pathlib.Path(__file__).resolve().parents[1] / "algorithms"


def _py_blocks():
    """逐个 .md 文件产出 (文件, 块序号, 代码文本)。"""
    for f in sorted(ALGO_ROOT.rglob("*.md")):
        if f.name == "README.md":
            continue
        text = f.read_text(encoding="utf-8")
        for i, block in enumerate(re.findall(r"```python\n(.*?)```", text, re.S)):
            yield f, i, block


def test_all_blocks_parse():
    """每个代码块必须能 compile（无语法错误）。"""
    errs = []
    for f, i, block in _py_blocks():
        try:
            compile(block, str(f), "exec")
        except SyntaxError as e:
            errs.append(f"{f.name} 块{i}: {e}")
    assert not errs, "\n".join(errs)


def test_all_demos_run():
    """含 __main__ 的代码块必须 exec 可运行；重依赖/外部文件显式跳过并计数。"""
    skipped, errs = [], []
    for f, i, block in _py_blocks():
        if 'if __name__ == "__main__"' not in block:
            skipped.append(f"{f.name}:{i}")
            continue
        try:
            exec(compile(block, str(f), "exec"), {"__name__": "__main__"})
        except (ImportError, OSError) as e:   # 重依赖/外部文件 → 显式跳过并计数
            skipped.append(f"{f.name}:{i} ({type(e).__name__})")
        except Exception as e:                 # 真实 bug → 失败
            errs.append(f"{f.name}:{i}: {type(e).__name__}: {e}")
    assert not errs, "\n".join(errs)
    assert len(skipped) <= 5, f"跳过过多（掩盖问题）: {skipped}"
