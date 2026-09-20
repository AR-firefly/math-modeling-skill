"""E / 批次 2 —— 参赛提交 ZIP 打包单测（C9；升级计划 §4.1）。

被测对象：`scripts/build_submission_zip.py`。

断言的核心三件事：
1. **ZIP 内无本机绝对路径**（弧名相对 + 包内文本无盘符/UNC/家目录/临时目录）
2. **含 `output/paper.tex`、图片、编译说明**
3. **不伪造编译成功**：`compiled` 恒为 False，README 明写「待编译验证」

路径判定用**环境无关**写法构造（不依赖运行机器是不是 Windows）：
- 驱动器号用 `"C" + ":" + chr(92)` 之类拼接，避免源码里出现真实盘符字面量
- UNC 与 POSIX 家目录同理

诚实边界
--------
本脚本**只打包、不编译**。包内路径相对 ≠ 能编译通过 ≠ 论文合格；编译结果以实际
`xelatex` 日志为准。本文件不断言任何「论文内容正确」。
"""
import importlib.util
import re
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BSZ = ROOT / "scripts/build_submission_zip.py"

BACKSLASH = chr(92)
DRIVE = "C" + ":" + BACKSLASH          # "C:\"（拼接构造，避免源码里出现盘符字面量）


@pytest.fixture(scope="module")
def bsz():
    spec = importlib.util.spec_from_file_location("e_zip", BSZ)
    module = importlib.util.module_from_spec(spec)
    sys.modules["e_zip"] = module
    spec.loader.exec_module(module)
    return module


TEX_OK = (
    "\\documentclass{article}\n"
    "\\usepackage{graphicx}\n"
    "\\usepackage{ctex}\n"
    "\\begin{document}\n"
    "\\section{模型建立}\n"
    "见图 \\ref{fig:demo}。\n"
    "\\includegraphics[width=0.6\\textwidth]{figures/fig1.png}\n"
    "\\end{document}\n"
)

MINIMAL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082")


def seed(tmp_path, *, tex=TEX_OK, with_png=True, with_bib=True, name="project"):
    project = tmp_path / name
    (project / "output").mkdir(parents=True)
    (project / "output" / "paper.tex").write_text(tex, encoding="utf-8")
    if with_bib:
        (project / "output" / "refs.bib").write_text("@article{k, title={T}}\n", encoding="utf-8")
    if with_png:
        (project / "figures").mkdir(parents=True)
        (project / "figures" / "fig1.png").write_bytes(MINIMAL_PNG)
    return project


# ── 正例：打包成功且内容齐全 ──────────────────────────────────────────
def test_clean_project_packs_with_expected_members(bsz, tmp_path):
    project = seed(tmp_path)
    report = bsz.build(project, tmp_path / "submission.zip")
    assert report["level"] == "PASS", report["problems"]
    with zipfile.ZipFile(tmp_path / "submission.zip") as archive:
        names = archive.namelist()
    assert "output/paper.tex" in names, names
    assert any(n.startswith("figures/") and n.endswith(".png") for n in names), names
    assert bsz.README_NAME in names, "必须含编译说明"
    assert any(n.endswith(".bib") for n in names), names


def test_zip_arcnames_are_relative(bsz, tmp_path):
    """弧名不得是绝对路径、不得含 `..`（zip slip）。"""
    project = seed(tmp_path)
    bsz.build(project, tmp_path / "submission.zip")
    with zipfile.ZipFile(tmp_path / "submission.zip") as archive:
        names = archive.namelist()
    bad = [n for n in names
           if n.startswith("/") or re.match(r"^[A-Za-z]:", n) or ".." in n.split("/")]
    assert bad == [], bad


def test_zip_is_readable_and_not_corrupt(bsz, tmp_path):
    project = seed(tmp_path)
    bsz.build(project, tmp_path / "submission.zip")
    with zipfile.ZipFile(tmp_path / "submission.zip") as archive:
        assert archive.testzip() is None


def test_no_absolute_path_leaks_inside_zip_text(bsz, tmp_path):
    """包内**文本**（tex/bib/md）不得含本机绝对路径——这是最容易被 `\\input{...}` 带进来的。"""
    project = seed(tmp_path)
    bsz.build(project, tmp_path / "submission.zip")
    with zipfile.ZipFile(tmp_path / "submission.zip") as archive:
        body = "".join(archive.read(n).decode("utf-8", "replace") for n in archive.namelist()
                       if n.endswith((".tex", ".bib", ".md", ".cls", ".sty")))
    assert bsz.ABSOLUTE_PATTERNS
    leaked = [p.pattern for p in bsz.ABSOLUTE_PATTERNS if p.search(body)]
    assert leaked == [], leaked


def test_report_is_honest_about_not_compiling(bsz, tmp_path):
    """`compiled` 恒为 False；报告 note 明说不证明可编译通过。"""
    project = seed(tmp_path)
    report = bsz.build(project, tmp_path / "submission.zip")
    assert report["compiled"] is False
    assert "不编译" in report["note"]
    with zipfile.ZipFile(tmp_path / "submission.zip") as archive:
        readme = archive.read(bsz.README_NAME).decode("utf-8")
    assert "待编译验证" in readme
    assert "不得在未编译成功时声称已编译通过" in readme
    assert "xelatex" in readme.lower(), "必须给出编译器与版本留存指引"
    assert "XeLaTeX" in readme, "必须写明首选/兜底编译路径"


def test_readme_lists_package_manifest(bsz, tmp_path):
    project = seed(tmp_path)
    bsz.build(project, tmp_path / "submission.zip")
    with zipfile.ZipFile(tmp_path / "submission.zip") as archive:
        readme = archive.read(bsz.README_NAME).decode("utf-8")
    assert "`output/paper.tex`" in readme
    assert "包内清单" in readme


# ── 反例①：tex 内写死本机绝对路径 → FAIL ─────────────────────────────
def test_absolute_path_in_tex_fails(bsz, tmp_path):
    absolute_line = "\\includegraphics[width=0.6\\textwidth]{" + DRIVE + "contest" + BACKSLASH + "fig1.png}\n"
    project = seed(tmp_path, tex=TEX_OK + absolute_line)
    report = bsz.build(project, tmp_path / "s.zip")
    assert report["level"] == "FAIL", report
    assert report["absolute_path_hits"], "必须列出命中位置"
    hit = report["absolute_path_hits"][0]
    assert hit["file"].endswith("paper.tex") and hit["line"] > 0
    assert not (tmp_path / "s.zip").exists(), "FAIL 时不得留下半成品 ZIP"


def test_absolute_path_in_bib_fails(bsz, tmp_path):
    project = seed(tmp_path)
    (project / "output" / "refs.bib").write_text(
        "@misc{x, file = {" + DRIVE + "refs" + BACKSLASH + "a.pdf}}\n", encoding="utf-8")
    report = bsz.build(project, tmp_path / "s.zip")
    assert report["level"] == "FAIL" and report["absolute_path_hits"]


# ── 反例②：缺主文件 → FAIL（不伪造空的"成功"包） ──────────────────────
def test_missing_main_tex_fails(bsz, tmp_path):
    project = seed(tmp_path)
    (project / "output" / "paper.tex").unlink()
    report = bsz.build(project, tmp_path / "s.zip")
    assert report["level"] == "FAIL"
    assert any("paper.tex" in problem for problem in report["problems"])
    assert not (tmp_path / "s.zip").exists()


# ── 反例③：项目外文件 → 平铺进包，绝不带绝对路径 ──────────────────────
def test_outside_extra_is_flattened_without_absolute_path(bsz, tmp_path):
    project = seed(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("外部补充材料\n", encoding="utf-8")
    report = bsz.build(project, tmp_path / "extra.zip", extra=[str(outside)])
    assert report["level"] == "PASS", report["problems"]
    with zipfile.ZipFile(tmp_path / "extra.zip") as archive:
        names = archive.namelist()
    assert "outside.txt" in names
    assert not any(re.match(r"^[A-Za-z]:", n) for n in names), names


def test_missing_extra_file_is_reported(bsz, tmp_path):
    project = seed(tmp_path)
    report = bsz.build(project, tmp_path / "s.zip", extra=[str(tmp_path / "nope.bin")])
    assert report["level"] == "FAIL"
    assert any("include-extra" in problem for problem in report["problems"])


# ── 反例④：路径回溯 / 绝对弧名被拒（zip slip 防护） ───────────────────
@pytest.mark.parametrize("name", ["../../etc/passwd", DRIVE + "x" + BACKSLASH + "y.png",
                                  "/etc/passwd", "../a.png"])
def test_zip_slip_arcname_is_rejected(bsz, name):
    assert bsz._safe_arcname(name) is None, name


@pytest.mark.parametrize("name", ["figures/a.png", "output/paper.tex", "a.txt"])
def test_legit_arcname_is_preserved(bsz, name):
    assert bsz._safe_arcname(name) == name


def test_arcname_backslash_is_normalized(bsz):
    assert bsz._safe_arcname("figures" + BACKSLASH + "a.png") == "figures/a.png"


# ── 反例⑤：各类本机绝对路径写法必须被抓，相对路径与官方 URL 必须放过 ──
def test_absolute_path_matrix(bsz):
    """环境无关地构造各类绝对路径写法（不依赖运行机器是哪种系统）。"""
    posix_home = "/" + "home/alice/contest/f.png"
    mac_home = "/" + "Users/alice/contest/f.png"
    tmp_path_like = "/" + "tmp/abc12345/f.png"
    unc = BACKSLASH * 2 + "server" + BACKSLASH + "share" + BACKSLASH + "f.png"
    unc_posix = "//server/share/f.png"
    matrix = [
        ("Windows 盘符", DRIVE + "contest" + BACKSLASH + "f.png", True),
        ("Windows 正斜杠盘符", DRIVE + "contest/f.png", True),
        ("真 UNC", unc, True),
        ("正斜杠 UNC", unc_posix, True),
        ("POSIX 家目录", posix_home, True),
        ("macOS 家目录", mac_home, True),
        ("临时目录", tmp_path_like, True),
        ("相对路径 figures/fig1.png", "figures/fig1.png", False),
        ("相对路径 output/paper.tex", "output/paper.tex", False),
        ("官方 URL", "https://matplotlib.org/stable/api/_as_gen/axes.html", False),
        ("LaTeX 命令（单反斜杠）", BACKSLASH + "includegraphics{figures/fig1.png}", False),
        ("LaTeX 命令（\\textbackslash）", BACKSLASH + "textbackslash{}data", False),
    ]
    wrong = [(label, bool(bsz.absolute_hits(line))) for label, line, expect in matrix
             if bool(bsz.absolute_hits(line)) != expect]
    assert wrong == [], "判定不符预期的写法：%s" % wrong


def test_absolute_hits_returns_the_matched_token(bsz):
    hits = bsz.absolute_hits("\\input{" + DRIVE + "contest\\x.tex}")
    assert hits and DRIVE in hits[0]


def test_absolute_hits_is_empty_for_clean_line(bsz):
    assert bsz.absolute_hits("\\includegraphics{figures/fig1.png}") == []


# ── 二进制文件不做文本扫描（避免把 PNG 字节当路径） ────────────────────
def test_binary_members_are_skipped_by_text_scanner(bsz, tmp_path):
    project = seed(tmp_path)
    entries, problems = bsz.collect(project)
    assert problems == []
    hits = bsz.scan_absolute_paths(entries, project)
    assert hits == [], "PNG 字节不得被当成绝对路径命中"


# ── paper.tex 之外的 output/*.tex 也要进包（如 \input 的子文件） ───────
def test_extra_output_tex_is_packed(bsz, tmp_path):
    project = seed(tmp_path)
    (project / "output" / "appendix.tex").write_text("\\section{附录}\n", encoding="utf-8")
    bsz.build(project, tmp_path / "s.zip")
    with zipfile.ZipFile(tmp_path / "s.zip") as archive:
        assert "output/appendix.tex" in archive.namelist()


def test_cli_project_required(bsz, tmp_path, capsys):
    """无 `--project` 且无 `--self-test` → 用法错误（退出码 2，不静默成功）。"""
    with pytest.raises(SystemExit) as excinfo:
        bsz.main([])
    assert excinfo.value.code == 2


def test_docstring_declares_limits():
    """诚实性回归：脚本必须写明「只打包、不编译、不保证编译通过」。"""
    doc = BSZ.read_text(encoding="utf-8").split('"""')[1]
    assert "不编译" in doc
    assert "不保证 ZIP 能编译通过" in doc or "不保证能编译通过" in doc
