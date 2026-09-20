"""数值校验模块测试：抓捏造 / 放行真实 / 容差 / manifest / 反向检查。"""
import json
from pathlib import Path

from math_modeling.verify import verify_paper_numbers, write_run_manifest


def test_verify_passes_real(tmp_path):
    r = tmp_path / "res.json"
    r.write_text(json.dumps({"a": 3.14, "n": {"b": 2.5}}), encoding="utf-8")
    issues, unmatched = verify_paper_numbers(str(r), "结果是 3.14 和 2.5")
    assert issues == [] and unmatched == []


def test_verify_catches_fabricated(tmp_path):
    r = tmp_path / "res.json"
    r.write_text(json.dumps({"a": 99.9}), encoding="utf-8")
    issues, _ = verify_paper_numbers(str(r), "结果是 1.0")
    assert len(issues) == 1 and "99.9" in issues[0]


def test_verify_tolerance(tmp_path):
    r = tmp_path / "res.json"
    r.write_text(json.dumps({"a": 1.000001}), encoding="utf-8")
    issues, _ = verify_paper_numbers(str(r), "结果是 1.0")
    assert issues == []


def test_manifest_contains_seed_and_sha(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("x\n1\n")
    m = write_run_manifest(str(tmp_path), 42, "cmd", [f])
    assert m["seed"] == 42 and len(m["inputs"][0]["sha256"]) == 64


def test_verify_reverse_catches_fabricated_paper_number(tmp_path):
    """反向检查：论文里编造的大数字（results 无出处）应进 unmatched。"""
    r = tmp_path / "res.json"
    r.write_text(json.dumps({"a": 3.14}), encoding="utf-8")
    issues, unmatched = verify_paper_numbers(str(r), "结果是 3.14，最优成本 8888.0", reverse=True)
    assert issues == []
    assert any("8888" in u for u in unmatched)


def test_verify_reverse_skips_small_numbers(tmp_path):
    """反向检查：小数字（序号）跳过；大数字无出处如实列出（供人工核对，不阻断）。"""
    r = tmp_path / "res.json"
    r.write_text(json.dumps({"a": 3.14}), encoding="utf-8")
    issues, unmatched = verify_paper_numbers(str(r), "结果是 3.14，序号 3，年份 2026", reverse=True)
    assert issues == []
    assert not any(u == "3" for u in unmatched)    # 小序号不报
    assert any("2026" in u for u in unmatched)     # 大数字无出处如实列出（人工核对是否合法）


# ── v2.1：图号引用检查（图契约清单 ↔ 正文引用 ↔ 图文件）──
# v3.0 C5：路径语义写死 —— file 相对 figures/；script/data_entrypoint 相对项目根，
# 分层布局 figures/scripts|data；双布局（分层 → 扁平 → 两处都不存在 = FAIL）。
def _mk_figure_paper(cited="结果见图1和图2。"):
    return {"abstract": [cited],
            "sections": [{"title": "一", "paras": ["图1 收敛曲线"],
                          "images": [{"caption": "图1 收敛曲线"}]}],
            "references": []}


def _mk_entry(no, **overrides):
    """v3.0 契约形状的登记项（分层布局：figures/scripts|data）。"""
    entry = {"no": no, "title": f"t{no}", "conclusion": "c", "data_source": "r",
             "file": f"{no}.png",
             "script": f"figures/scripts/{no}.py",
             "data_entrypoint": f"figures/data/{no}.json"}
    entry.update(overrides)
    return entry


def _mk_manifest(figdir, entries):
    (figdir / "figures_manifest.json").write_text(json.dumps(entries), encoding="utf-8")


def _mk_layered(figdir, *nos):
    """建分层布局（scripts/ + data/）并返回登记项列表。"""
    (figdir / "scripts").mkdir(exist_ok=True)
    (figdir / "data").mkdir(exist_ok=True)
    (figdir / "figures_manifest.json").parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for no in nos:
        (figdir / "scripts" / f"{no}.py").write_text("print(1)", encoding="utf-8")
        (figdir / "data" / f"{no}.json").write_text("{}", encoding="utf-8")
        (figdir / f"{no}.png").write_bytes(b"x")
        entries.append(_mk_entry(no))
    return entries


def test_verify_figure_references_ok(tmp_path):
    """正常：编号连续、正文引用都在清单、图文件齐全 → 零 issues。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    figdir.mkdir()
    _mk_manifest(figdir, _mk_layered(figdir, "fig1", "fig2"))
    assert verify_figure_references(_mk_figure_paper(), figures_dir=str(figdir)) == []


def test_verify_figure_references_flat_layout_compatible(tmp_path):
    """C5 双布局：脚本/数据在扁平位（figures/figN.py|json）也放过——不打断既有 demo。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    figdir.mkdir()
    (figdir / "fig1.png").write_bytes(b"x")
    (figdir / "fig1.py").write_text("print(1)", encoding="utf-8")
    (figdir / "fig1.json").write_text("{}", encoding="utf-8")
    _mk_manifest(figdir, [_mk_entry("fig1", script="figures/fig1.py",
                                    data_entrypoint="figures/fig1.json")])
    assert verify_figure_references(_mk_figure_paper("结果见图1。"), figures_dir=str(figdir)) == []


def test_verify_figure_references_wrong_directory_fails(tmp_path):
    """C5 边界：「放错目录」必须抓到——分层与扁平两处都不存在 → FAIL。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    (figdir / "elsewhere").mkdir(parents=True)
    (figdir / "fig1.png").write_bytes(b"x")
    (figdir / "elsewhere" / "fig1.py").write_text("print(1)", encoding="utf-8")
    (figdir / "elsewhere" / "fig1.json").write_text("{}", encoding="utf-8")
    _mk_manifest(figdir, [_mk_entry("fig1")])
    issues = verify_figure_references(_mk_figure_paper("结果见图1。"), figures_dir=str(figdir))
    assert any("放错目录或缺失" in i for i in issues), issues


def test_verify_figure_references_backslash_normalized(tmp_path):
    """C5：manifest 反斜杠值先归一化，非 Windows 侧不再解析失败（A14）。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    figdir.mkdir()
    entries = _mk_layered(figdir, "fig1")
    entries[0]["script"] = "figures\\scripts\\fig1.py"
    entries[0]["data_entrypoint"] = "figures\\data\\fig1.json"
    _mk_manifest(figdir, entries)
    assert verify_figure_references(_mk_figure_paper("结果见图1。"), figures_dir=str(figdir)) == []


def test_verify_figure_references_missing_manifest(tmp_path):
    """图契约清单缺失 → 提示生成图契约。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    issues = verify_figure_references({}, figures_dir=str(figdir))
    assert issues and "图契约清单缺失" in issues[0]


def test_verify_figure_references_citation_not_registered(tmp_path):
    """正文引用图 2 但清单只有图 1 → 报引用缺图。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    figdir.mkdir()
    _mk_manifest(figdir, _mk_layered(figdir, "fig1"))
    issues = verify_figure_references(_mk_figure_paper(), figures_dir=str(figdir))
    assert any("正文引用图 2" in i for i in issues)


def test_verify_figure_references_file_missing(tmp_path):
    """清单登记了 fig2 但 figures/fig2.png 不存在 → 报文件缺失。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    figdir.mkdir()
    entries = _mk_layered(figdir, "fig1", "fig2")
    (figdir / "fig2.png").unlink()
    _mk_manifest(figdir, entries)
    issues = verify_figure_references(_mk_figure_paper(), figures_dir=str(figdir))
    assert any("fig2.png" in i and "缺失" in i for i in issues)


def test_verify_figure_references_caption_self_proof_blocked(tmp_path):
    """A3 回归：图题 caption 自带'图N'不算正文引用；正文零引用时反向检查报未引用（防恒绿）。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    figdir.mkdir()
    _mk_manifest(figdir, _mk_layered(figdir, "fig1"))
    paper = {"abstract": [],
             "sections": [{"title": "一", "paras": ["正文未提图"],
                           "images": [{"caption": "图1 收敛曲线"}]}],
             "references": []}
    issues = verify_figure_references(paper, figures_dir=str(figdir))
    assert any("未嵌入" in i for i in issues), f"应报图1未嵌入论文（无 path 的 caption 不算嵌入）: {issues}"


def test_verify_figure_references_embedded_in_section_passes(tmp_path):
    """v2.4 A 回归：图嵌入论文某节（images.path 对应契约 file）即"图进了论文"，反向检查通过；
    不要求正文逐字写"图N"（自动灌引用反模式已撤销）。"""
    from math_modeling.verify import verify_figure_references
    figdir = tmp_path / "figures"
    figdir.mkdir()
    _mk_manifest(figdir, _mk_layered(figdir, "fig1"))
    paper = {"abstract": [],
             "sections": [{"title": "一", "paras": ["正文未逐字写图号"],
                           "images": [{"path": "figures/fig1.png", "caption": "图1 关键结果"}]}],
             "references": []}
    assert verify_figure_references(paper, figures_dir=str(figdir)) == []


def test_build_paper_content_nested_results():
    """v2.4 E 回归：嵌套 results {Q1:{...}} 展开路径 Q1.最优值 也能生成逐问求解节。"""
    import json
    import tempfile
    from math_modeling.paper_generator import build_paper_content
    results = {"Q1": {"最优值": 3.2, "迭代次数": 500}, "总耗时秒": 118.7}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(results, f)
        path = f.name
    paper = build_paper_content(path, {"title": "t"})
    q1_sec = next((s for s in paper["sections"] if "问题1" in s["title"]), None)
    assert q1_sec is not None, "嵌套 Q1 应生成逐问求解节"
    assert "3.2" in q1_sec["paras"][0]
    assert not any("总耗时秒" in s["title"] for s in paper["sections"]), "非 Q 字段不占节"


def test_build_paper_content_images_use_qkey():
    """A6 回归：images 用原始问号 key 挂载；非连续问号 / 非 Q 字段不推移错位。"""
    import json
    import tempfile
    from math_modeling.paper_generator import build_paper_content
    results = {"Q2_最优值": 3.0, "总耗时秒": 118.7}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(results, f)
        path = f.name
    paper = build_paper_content(path, {"title": "t"},
                                images={"Q2": [{"path": "figures/fig1.png", "caption": "图1 Q2 关键结果"}]})
    q2_sec = next(s for s in paper["sections"] if "问题2" in s["title"])
    assert len(q2_sec["images"]) == 1, f"Q2 求解节应挂上图（images 用 qkey='Q2'）: {q2_sec['images']}"
    eval_text = "".join(p for s in paper["sections"] if "模型评价" in s["title"]
                        for p in s["paras"])
    assert "118.7" in eval_text, "非 Q 字段值并入模型评价"
    assert not any("总耗时秒" in s["title"] for s in paper["sections"]), "非 Q 字段不独立占节（A6）"


# ── v2.1：参考文献 DOI 可解析性检查（mock 网络，不真发请求）──
def test_validate_references_doi():
    """check_doi=True：404=错号 issue，200仅可解析，网络异常必须标记待核验。"""
    from unittest.mock import patch
    from urllib.error import HTTPError
    from math_modeling.paper_generator import validate_references

    refs = ["Doe A. (2023). Fake. Journal. DOI: 10.9999/fake-123456"]

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        issues = validate_references(refs, check_doi=True)
    assert not any("DOI" in i for i in issues)

    with patch("urllib.request.urlopen",
               side_effect=HTTPError("", 404, "Not Found", {}, None)):
        issues = validate_references(refs, check_doi=True)
    assert any("404" in i for i in issues)

    with patch("urllib.request.urlopen", side_effect=OSError("no net")):
        issues = validate_references(refs, check_doi=True)
    assert any("DOI" in i and "待核验" in i for i in issues)  # 离线不能冒称已核验

    issues = validate_references(refs, check_doi=False)  # 默认不联网
    assert not any("DOI" in i for i in issues)


# ── v2.1.1：引用编号对应检查（正文 [N] ↔ 参考文献列表）──
def test_verify_citations_ok():
    """正文引用 [1][2]，列表 2 条 → 无警告。"""
    from math_modeling.verify import verify_citations
    refs = ["a (2023). j1. DOI: 10.1/x", "b (2024). j2. DOI: 10.1/y"]
    assert verify_citations("结果见文献[1][2]。", refs) == []


def test_verify_citations_cited_out_of_range():
    """正文引用 [1][2][3] 但列表仅 2 条 → 报列表有缺。"""
    from math_modeling.verify import verify_citations
    refs = ["a (2023). j1.", "b (2024). j2."]
    warns = verify_citations("结果见文献[1][2][3]。", refs)
    assert any("超出" in w and "3" in w for w in warns)


def test_verify_citations_listed_not_cited():
    """列表 2 条但正文只引 [1] → 报第 2 条未被引用。"""
    from math_modeling.verify import verify_citations
    refs = ["a (2023). j1.", "b (2024). j2."]
    warns = verify_citations("结果见文献[1]。", refs)
    assert any("未被引用" in w and "2" in w for w in warns)


def test_verify_citations_range_and_no_refs():
    """[1-2] 合并引用不误报；正文无 [N] 引用不强查。"""
    from math_modeling.verify import verify_citations
    refs = ["a (2023). j1.", "b (2024). j2."]
    assert verify_citations("结果见文献[1-2]。", refs) == []
    assert verify_citations("本文未用编号引用，用作者-年。(Smith, 2023)", refs) == []
