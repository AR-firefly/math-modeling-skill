# -*- coding: utf-8 -*-
"""
优秀论文预处理：近五年（2021-2025）国赛优秀论文 → references/优秀论文/{题号}/{四类}/
- 无损：只做格式整理（PDF 提取 .txt、扫描 JPG 按页重命名），不做内容精简
- 去姓名：文件名剔除队员真实姓名（保留题号/年份/编号）
- 分类映射：按题型表 + 命题趋势解读（D 专科优化→优化类，E 专科分类研判→评价类）

用法（路径全部参数化，不硬编码本机路径）：
    python scripts/preprocess_papers.py --big "<大汇总目录>" [--b030 "<B030目录>"] [--learn2025 "<2025学习资料目录>"] [--pdf-only] [--scanned-only]
"""
from __future__ import annotations
import argparse
import os
import re
import shutil
import tempfile
import zipfile
import pathlib

# ── 配置（路径由命令行参数传入，默认目标 = 脚本位置推断的 v2.0 仓库）──
V2 = pathlib.Path(__file__).resolve().parents[1]  # 脚本位置推断 v2.0 仓库（不硬编码绝对路径）
TARGET = V2 / "references" / "优秀论文"
BIG = None          # --big 传入（大汇总目录）
B030 = None         # --b030 传入
LEARN2025 = None    # --learn2025 传入

# 分类映射：{年份: {题号: 四类}}，基于题型表（本科 ABC）+ 命题趋势（专科 DE）
# 主类优先；D 专科→优化类，E 专科→评价类
TYPE_MAP = {
    2021: {"A": "机理", "B": "机理", "C": "优化", "D": "优化", "E": "评价"},
    2022: {"A": "机理", "B": "机理", "C": "评价", "D": "优化", "E": "评价"},
    2023: {"A": "机理", "B": "优化", "C": "预测", "D": "优化", "E": "评价"},
    2024: {"A": "机理", "B": "优化", "C": "优化", "D": "优化", "E": "评价"},
    2025: {"A": "机理", "B": "机理", "C": "预测", "D": "优化", "E": "评价"},
}


def clean_name(name: str) -> str:
    """去姓名：剔除文件名里的中文姓名，保留题号+学校；避免双 .pdf。"""
    # 2025 学习资料格式: "A（学校名）姓名1_姓名2_姓名3.pdf" → "A_学校名.pdf"
    m = re.match(r"^([A-E])（([^）]+)）.*\.pdf$", name)
    if m:
        return f"{m.group(1)}_{m.group(2)}.pdf"
    # 大汇总格式: "A066.pdf" / "2025A..." → 去重 .pdf（防 .pdf.pdf 双后缀）
    base = name[:-4] if name.lower().endswith(".pdf") else name
    return base + ".pdf"


def classify(year: int, problem: str) -> str:
    return TYPE_MAP.get(year, {}).get(problem.upper(), "评价")


def ensure_dirs(year, problem, category):
    d = TARGET / problem.upper() / category
    d.mkdir(parents=True, exist_ok=True)
    return d


def extract_pdf_text(src: pathlib.Path, dest_dir: pathlib.Path, stem: str):
    """PDF 有文字层 → 提取 .txt（无损），保留原 PDF。"""
    dest_pdf = dest_dir / f"{stem}.pdf"
    shutil.copy2(src, dest_pdf)
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(src))
        txt = "\n\n".join(page.get_text() for page in doc)
        doc.close()
        (dest_dir / f"{stem}.txt").write_text(txt, encoding="utf-8")
        has_text = bool(txt.strip())
        if not has_text:  # 无文字层（扫描 PDF）→ 转逐页图
            (dest_dir / f"{stem}.txt").write_text("（扫描版 PDF，无文字层，按页图读取）\n", encoding="utf-8")
            _pdf_to_images(src, dest_dir, stem)
        return "text" if has_text else "scanned"
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] PDF 提取失败 {src.name}: {e}")
        return "error"


def _pdf_to_images(src, dest_dir, stem):
    import fitz
    doc = fitz.open(str(src))
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(dpi=150)
        img = dest_dir / f"{stem}_page{i:03d}.png"
        pix.save(str(img))
    doc.close()


def copy_scanned_jpgs(src_dir: pathlib.Path, dest_dir: pathlib.Path, stem: str, page_sort_key):
    """扫描 JPG → 按页重命名（001.jpg, 002.jpg...），保读取顺序。"""
    jpgs = sorted([f for f in src_dir.iterdir() if f.suffix.lower() == ".jpg"], key=page_sort_key)
    # 去掉重复（微信图片 (1).jpg 与 .jpg 是同一张）
    seen = set()
    keep = []
    for f in jpgs:
        base = re.sub(r"\(\d+\)", "", f.name)
        if base not in seen:
            seen.add(base)
            keep.append(f)
    for i, f in enumerate(keep, 1):
        dest = dest_dir / f"{stem}_page{i:03d}.jpg"
        shutil.copy2(f, dest)
    return len(keep)


def page_key(f: pathlib.Path):
    """扫描图页序近似键：优先数字部分，否则按文件名。"""
    m = re.search(r"(\d+)", f.stem)
    return (0, int(m.group(1))) if m else (1, f.name)


def process_pdf_batch():
    """2023 / 2025 PDF 优秀论文（含大汇总 2025 + 学习资料 2025 去姓名）。"""
    count = 0
    p23 = BIG / "2023年数学建模国赛真题+优秀论文" / "2023数学建模竞赛展示论文" / "2023年展示论文" if BIG else None
    if p23 and p23.exists():
        for f in sorted(p23.glob("*.pdf")):
            m = re.match(r"^([A-E])", f.name)
            if not m:
                continue
            prob, year = m.group(1), 2023
            cat = classify(year, prob)
            d = ensure_dirs(year, prob, cat)
            stem = f"{year}{prob}_{f.stem}"  # 2023A_A092
            res = extract_pdf_text(f, d, stem)
            print(f"  [2023] {f.name} → {cat}/{stem} ({res})")
            count += 1
    p25 = BIG / "2025年数学建模国赛真题+优秀论文" / "2025数学建模国赛优秀论文" if BIG else None
    if p25 and p25.exists():
        for f in sorted(p25.glob("*.pdf")):
            m = re.match(r"^([A-E])", f.name)
            if not m:
                continue
            prob = m.group(1)
            cat = classify(2025, prob)
            d = ensure_dirs(2025, prob, cat)
            stem = f"2025{prob}_{f.stem}"
            res = extract_pdf_text(f, d, stem)
            print(f"  [2025汇总] {f.name} → {cat}/{stem} ({res})")
            count += 1
    if LEARN2025 and LEARN2025.exists():
        for f in sorted(LEARN2025.glob("*.pdf")):
            m = re.match(r"^([A-E])", f.name)
            if not m:
                continue
            prob = m.group(1)
            cat = classify(2025, prob)
            d = ensure_dirs(2025, prob, cat)
            stem = f"2025{prob}_{clean_name(f.name)}"  # 去姓名（含去重 .pdf）
            res = extract_pdf_text(f, d, stem)
            print(f"  [2025学习] {f.name} → {cat}/{stem} ({res})")
            count += 1
    return count


def process_scanned_batch():
    """2021 / 2022 扫描 JPG（含 2024 zip 解压处理，解压到临时目录不写 SKILL_ROOT）。"""
    count = 0
    p21 = BIG / "2021年数学建模国赛真题+优秀论文" / "2021年优秀论文" if BIG else None
    if p21 and p21.exists():
        for sub in sorted(p21.iterdir()):
            if not sub.is_dir():
                continue
            m = re.match(r"2021年国赛优秀论文([A-E])题-([A-E0-9]+)", sub.name)
            if not m:
                continue
            prob, num = m.group(1), m.group(2)
            cat = classify(2021, prob)
            d = ensure_dirs(2021, prob, cat)
            stem = f"2021{prob}_{num}"
            n = copy_scanned_jpgs(sub, d, stem, page_key)
            print(f"  [2021] {sub.name} → {cat}/{stem} ({n}页)")
            count += 1
    if BIG:
        for sub in sorted(BIG.glob("2022年国赛优秀论文*")):
            if not sub.is_dir():
                continue
            m = re.match(r"2022年国赛优秀论文([A-E])(?:题)?([A-E0-9]+)", sub.name)
            if not m:
                continue
            prob, num = m.group(1), m.group(2)
            cat = classify(2022, prob)
            d = ensure_dirs(2022, prob, cat)
            stem = f"2022{prob}_{num}"
            n = copy_scanned_jpgs(sub, d, stem, page_key)
            print(f"  [2022] {sub.name} → {cat}/{stem} ({n}页)")
            count += 1
    if B030 and B030.exists():
        cat = classify(2022, "B")
        d = ensure_dirs(2022, "B", cat)
        stem = "2022B_B030"
        n = copy_scanned_jpgs(B030, d, stem, page_key)
        print(f"  [2022B030] → {cat}/{stem} ({n}页)")
        count += 1
    z24 = BIG / "2024年数学建模国赛真题+优秀论文" / "2024国赛优秀论文" / "2024国赛优秀论文.zip" if BIG else None
    if z24 and z24.exists():
        # 解压到临时目录（不写 SKILL_ROOT 仓库），处理完即弃
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="zip2024_"))
        try:
            with zipfile.ZipFile(z24) as zf:
                zf.extractall(str(tmp))
            base = tmp / "2024国赛优秀论文"
            for prob_dir in sorted(base.iterdir()) if base.exists() else []:
                if not prob_dir.is_dir():
                    continue
                m = re.match(r"([A-E])题", prob_dir.name)
                if not m:
                    continue
                prob = m.group(1)
                cat = classify(2024, prob)
                for team in sorted(prob_dir.iterdir()):
                    if not team.is_dir():
                        continue
                    stem = f"2024{prob}_{team.name}"
                    d = ensure_dirs(2024, prob, cat)
                    n = copy_scanned_jpgs(team, d, stem, page_key)
                    print(f"  [2024] {prob}/{team.name} → {cat}/{stem} ({n}页)")
                    count += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return count


def write_readme():
    d = TARGET
    d.mkdir(parents=True, exist_ok=True)
    readme = d / "README.md"
    lines = [
        "# 优秀论文库（近五年 2021-2025，全量无损）",
        "",
        "## 组织方式",
        "- 第一层：题号 A/B/C/D/E；第二层：四类（优化/评价/预测/机理）",
        "- 例：`references/优秀论文/A/机理/2021A_A028_page001.jpg`（2021A 题 A028 扫描第 1 页）",
        "",
        "## 分类映射（题型表 + 命题趋势）",
        "- A 题（工程物理类）→ 机理；B 题（开放综合）→ 视题（优化/机理）；C 题（数据分析）→ 评价/预测/优化",
        "- D 题（专科轻量化优化）→ 优化；E 题（专科分类研判）→ 评价",
        "",
        "## AI 读取方法",
        "- PDF 有文字层：读同名 `.txt`（纯文本，AI 直接读）",
        "- 扫描版：读 `*_pageNNN.jpg/png` 逐页视觉读（按页号顺序）",
        "- 读取策略：先首页/摘要定结构结论，再按需深入模型建立/求解/结果页",
        "- **全量无损**：只做格式整理，未做内容精简",
        "",
        "## 格式说明",
        "- PDF：原 PDF + 同名 .txt（pymupdf 提取）；扫描 PDF 转逐页 png",
        "- 扫描 JPG：按页重命名 `_page001.jpg, _page002.jpg...`（保顺序）",
        "- 已去姓名：文件名不含队员真实姓名（2025 学习资料已重命名）",
        "",
        "## 收录范围",
        "年份、篇数与题号分布以本次运行的实际处理结果为准。",
    ]
    readme.write_text("\n".join(lines), encoding="utf-8")
    print("README 已写:", readme)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="优秀论文预处理（路径参数化，不硬编码本机路径）")
    ap.add_argument("--target", default=None, help="目标目录（默认 <仓库>/references/优秀论文）")
    ap.add_argument("--big", default=None, help="大汇总目录（1992-2025...）")
    ap.add_argument("--b030", default=None, help="B030 目录")
    ap.add_argument("--learn2025", default=None, help="2025 学习资料目录")
    ap.add_argument("--pdf-only", action="store_true", help="只处理 PDF 论文")
    ap.add_argument("--scanned-only", action="store_true", help="只处理扫描版论文")
    args = ap.parse_args()

    if args.target:
        TARGET = pathlib.Path(args.target)
    # 模块级变量默认全局，函数内可直接读到（无需 global 声明）
    BIG = pathlib.Path(args.big) if args.big else None
    B030 = pathlib.Path(args.b030) if args.b030 else None
    LEARN2025 = pathlib.Path(args.learn2025) if args.learn2025 else None

    if not args.scanned_only:
        print("=== PDF 优秀论文 ===")
        n = process_pdf_batch()
        print(f"PDF 论文处理 {n} 篇")
    if not args.pdf_only:
        print("=== 扫描版优秀论文 ===")
        n = process_scanned_batch()
        print(f"扫描论文处理 {n} 篇")
    write_readme()
    print("完成")
