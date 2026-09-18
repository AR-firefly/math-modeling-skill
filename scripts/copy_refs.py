# -*- coding: utf-8 -*-
"""复制三个规则 PDF 到 references/。

用法：
    python scripts/copy_refs.py --src "<存放这三个 PDF 的目录>"
"""
import argparse
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]  # 由脚本位置推断仓库根，不硬编码路径
DST = ROOT / "references"

targets = [
    "国赛参赛规则2026.pdf",
    "国赛论文规范2026.pdf",
    "近5年数模国赛A-E赛题规律与2026命题趋势解读.pdf",
]

parser = argparse.ArgumentParser(description="复制规则 PDF 到 references/")
parser.add_argument("--src", required=True, help="存放上述三个 PDF 的目录")
args = parser.parse_args()
SRC = pathlib.Path(args.src)

for name in targets:
    s = SRC / name
    if s.exists():
        shutil.copy2(s, DST / name)
        print(f"复制 OK: {name} ({s.stat().st_size} bytes)")
    else:
        print(f"!! 未找到: {name}")

print("\n=== references 全貌 ===")
for f in sorted(DST.iterdir()):
    tag = "dir" if f.is_dir() else "file"
    print(f"  [{tag}] {f.name}")
