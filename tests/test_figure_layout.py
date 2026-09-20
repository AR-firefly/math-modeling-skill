"""E / 批次 2 —— 图目录**分层布局**与**路径归一化**单测（作图契约 §二；出口条件 6、7）。

出口条件 6「双布局兼容 + 放错目录 FAIL」判定顺序（硬性）：

    分层 `figures/scripts/…`、`figures/data/…`  →  扁平 `figures/…`  →  两处都没有 = FAIL

兼容扁平只为不打断既有 demo；**「放错目录」必须被抓到**，不得因为兼容扁平面放过。
本文件对同一条规则在**两个入口**都验证：

- `visualizer.Visualizer.find_entry` / `figure_paths`（作图侧解析）
- `stage_gate.resolve_script` / `resolve_data_entrypoint` / `resolve_png`（门禁侧解析）

出口条件 7「非 Windows 路径归一化」：manifest 内路径一律正斜杠；反斜杠值仍须解析
（`verify.py` 与 `gate_audit.py` 两侧都归一化），**绝对路径必须被拒**——不能悄悄
lstrip 成看着合法的相对路径，否则「本机绝对路径」这条红线就失去抓手。

诚实边界
--------
本文件只证明「路径解析与判定顺序符合契约」，**不证明图本身正确**；数值一致性归
`check_figure_binding.py`，图好不好看归目视检查（作图契约 §八）。
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from math_modeling.visualizer import Visualizer, normalize_manifest_path  # noqa: E402


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("e_layout_gate", ROOT / "scripts/stage_gate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["e_layout_gate"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verify_module():
    spec = importlib.util.spec_from_file_location("e_layout_verify",
                                                  ROOT / "src/math_modeling/verify.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["e_layout_verify"] = module
    spec.loader.exec_module(module)
    return module


# ── 出口条件 6：分层优先 ──────────────────────────────────────────────
def test_layered_layout_takes_priority(tmp_path):
    """分层与扁平**同时存在**时必须取分层（契约判定顺序：先分层）。"""
    out = tmp_path / "figures"
    (out / "scripts").mkdir(parents=True)
    (out / "data").mkdir(parents=True)
    layered = out / "scripts" / "fig1.py"
    flat = out / "fig1.py"
    layered.write_text("layered", encoding="utf-8")
    flat.write_text("flat", encoding="utf-8")
    viz = Visualizer(output_dir=str(out))
    assert viz.find_entry("figures/scripts/fig1.py", "fig1.py", "scripts") == layered


def test_flat_layout_is_still_accepted(tmp_path):
    """只有扁平布局时兼容通过（不打断既有 demo）。"""
    out = tmp_path / "figures"
    out.mkdir(parents=True)
    flat = out / "fig1.py"
    flat.write_text("flat", encoding="utf-8")
    viz = Visualizer(output_dir=str(out))
    assert viz.find_entry("figures/fig1.py", "fig1.py", "scripts") == flat


def test_misplaced_script_returns_none(tmp_path):
    """**放错目录**（既不在分层也不在扁平）→ None，不得判通过。"""
    out = tmp_path / "figures"
    (out / "elsewhere").mkdir(parents=True)
    (out / "elsewhere" / "fig1.py").write_text("x", encoding="utf-8")
    viz = Visualizer(output_dir=str(out))
    assert viz.find_entry("figures/elsewhere/fig1.py", "fig1.py", "scripts") is None
    assert viz.find_entry("figures/somewhere/fig1.py", "fig1.py", "scripts") is None


def test_figure_paths_resolves_whole_triple(tmp_path):
    """三元组一次解析：脚本（分层）/ 数据入口（分层）/ PNG（相对 figures/）。"""
    out = tmp_path / "figures"
    (out / "scripts").mkdir(parents=True)
    (out / "data").mkdir(parents=True)
    (out / "scripts" / "fig1.py").write_text("x", encoding="utf-8")
    (out / "data" / "fig1.json").write_text("{}", encoding="utf-8")
    (out / "fig1.png").write_bytes(b"\x89PNG")
    viz = Visualizer(output_dir=str(out))
    paths = viz.figure_paths({"no": "fig1", "script": "figures/scripts/fig1.py",
                              "data_entrypoint": "figures/data/fig1.json", "file": "fig1.png"})
    assert paths["script"] == out / "scripts" / "fig1.py"
    assert paths["data_entrypoint"] == out / "data" / "fig1.json"
    assert paths["file"] == out / "fig1.png"


def test_figure_paths_reports_none_for_misplaced_entry(tmp_path):
    out = tmp_path / "figures"
    (out / "scripts").mkdir(parents=True)
    (out / "scripts" / "fig1.py").write_text("x", encoding="utf-8")
    viz = Visualizer(output_dir=str(out))
    paths = viz.figure_paths({"no": "fig1", "script": "figures/scripts/fig1.py",
                              "data_entrypoint": "figures/data/fig1.json", "file": "fig1.png"})
    assert paths["data_entrypoint"] is None, "数据入口放错目录必须解析为 None"
    assert paths["file"] is None, "PNG 缺失必须解析为 None"


def test_png_lookup_confined_to_figures_dir(tmp_path, monkeypatch):
    """`file` 相对 figures/：cwd 下同名文件**不得**被当成本图产物（防放错目录假绿）。"""
    out = tmp_path / "figures"
    out.mkdir()
    (tmp_path / "fig1.png").write_bytes(b"\x89PNG stray")     # 项目根下的同名文件
    monkeypatch.chdir(tmp_path)
    viz = Visualizer(output_dir=str(out))
    assert viz.find_entry("fig1.png", "fig1.png", root_relative=False) is None
    (out / "fig1.png").write_bytes(b"\x89PNG real")
    assert viz.find_entry("fig1.png", "fig1.png", root_relative=False) == out / "fig1.png"


# ── 出口条件 6：门禁侧（stage_gate）用同一条判定顺序 ────────────────────
def _project(tmp_path, *, layered=True, flat=False):
    project = tmp_path / "project"
    (project / "figures").mkdir(parents=True)
    if layered:
        (project / "figures" / "scripts").mkdir()
        (project / "figures" / "data").mkdir()
        (project / "figures" / "scripts" / "fig1.py").write_text("x", encoding="utf-8")
        (project / "figures" / "data" / "fig1.json").write_text("{}", encoding="utf-8")
    if flat:
        (project / "figures" / "fig1.py").write_text("x", encoding="utf-8")
    (project / "figures" / "fig1.png").write_bytes(b"\x89PNG")
    return project


def test_stage_gate_prefers_layered_when_both_exist(gate, tmp_path):
    project = _project(tmp_path, layered=True, flat=True)
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json"}
    path, err = gate.resolve_script(project, figure)
    assert err is None and path == project / "figures" / "scripts" / "fig1.py"


def test_stage_gate_falls_back_to_flat(gate, tmp_path):
    project = _project(tmp_path, layered=False, flat=True)
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/fig1.py",
              "data_entrypoint": "figures/fig1.json"}
    path, err = gate.resolve_script(project, figure)
    assert err is None and path == project / "figures" / "fig1.py"


def test_stage_gate_fails_on_misplaced_script(gate, tmp_path):
    """**出口条件 6 的核心反例**：登记 `figures/scripts/fig1.py`，实际却躺在
    `figures/elsewhere/fig1.py` → 分层/扁平两处都找不到 → FAIL 而非 PASS。

    （注意：`resolve_script` 会把登记值本身当作候选路径，所以"登记值指向哪里、
    文件就在哪里"是自洽的；真正要抓的是**登记位置与实际位置不符**。）
    """
    project = _project(tmp_path, layered=False, flat=False)
    (project / "figures" / "elsewhere").mkdir()
    (project / "figures" / "elsewhere" / "fig1.py").write_text("x", encoding="utf-8")
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json"}
    assert not (project / "figures" / "scripts" / "fig1.py").exists()
    path, err = gate.resolve_script(project, figure)
    assert path is None and "脚本不存在" in err, (path, err)


def test_stage_gate_misplaced_script_turns_into_figure_fail(gate, tmp_path):
    """放错目录 → 该图的 script_path 检查项为 FAIL（并折进总体判定）。"""
    project = _project(tmp_path, layered=False, flat=False)
    (project / "figures" / "elsewhere").mkdir()
    (project / "figures" / "elsewhere" / "fig1.py").write_text("x", encoding="utf-8")
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py"}
    row = gate._check_figure(project, figure, "q1", False, 30, tmp_path / "scratch", False)
    assert row["level"] == "FAIL"
    assert row["checks"]["script_path"]["level"] == "FAIL"


def test_stage_gate_reports_missing_data_entrypoint_as_warn(gate, tmp_path):
    project = _project(tmp_path, layered=True)
    (project / "figures" / "data" / "fig1.json").unlink()
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json"}
    assert gate.resolve_data_entrypoint(project, figure) is None
    row = gate._check_figure(project, figure, "q1", False, 30, tmp_path / "scratch", False)
    assert row["checks"]["data_entrypoint"]["level"] == "WARN"


def test_stage_gate_png_missing_is_fail(gate, tmp_path):
    project = _project(tmp_path, layered=True)
    (project / "figures" / "fig1.png").unlink()
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json"}
    assert gate.resolve_png(project, figure) is None
    row = gate._check_figure(project, figure, "q1", False, 30, tmp_path / "scratch", False)
    assert row["checks"]["png"]["level"] == "FAIL"


def test_stage_gate_png_falls_back_to_figure_number(gate, tmp_path):
    """`file` 缺失时才回落到 `{no}.png`（两者都要求会把 fig01_demo.png 拖成 FAIL）。"""
    project = _project(tmp_path, layered=True)
    (project / "figures" / "fig1.png").unlink()
    (project / "figures" / "fig1.png").write_bytes(b"\x89PNG")
    figure = {"no": "fig1", "file": ""}
    assert gate.resolve_png(project, figure) == project / "figures" / "fig1.png"


# ── 出口条件 7：路径归一化（反斜杠反例 + 绝对路径拒绝） ────────────────
def test_norm_converts_backslash_to_posix(gate):
    assert gate._norm("figures\\scripts\\fig1.py") == "figures/scripts/fig1.py"
    assert gate._norm("figures/scripts/fig1.py") == "figures/scripts/fig1.py"
    assert gate._norm("./figures/fig1.py") == "figures/fig1.py"


@pytest.mark.parametrize("value", ["C:\\contest\\figures\\fig1.py", "C:/contest/figures/fig1.py",
                                   "/etc/passwd", "/home/alice/figures/fig1.py"])
def test_norm_rejects_absolute_paths(gate, value):
    """绝对路径返回空串 → 调用方按「字段无效」处理，**不得 lstrip 洗成相对路径**。"""
    assert gate._norm(value) == "", value


def test_norm_handles_empty_and_none(gate):
    assert gate._norm(None) == "" and gate._norm("") == "" and gate._norm("   ") == ""


def test_backslash_manifest_value_still_resolves(gate, tmp_path):
    """非 Windows 侧：manifest 写反斜杠（不规范）仍须解析，**不得误报为缺件**。"""
    project = _project(tmp_path, layered=True, flat=False)
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures\\scripts\\fig1.py",
              "data_entrypoint": "figures\\data\\fig1.json"}
    path, err = gate.resolve_script(project, figure)
    assert err is None and path == project / "figures" / "scripts" / "fig1.py"
    assert gate.resolve_data_entrypoint(project, figure) == project / "figures" / "data" / "fig1.json"


def test_absolute_manifest_script_is_rejected(gate, tmp_path):
    project = _project(tmp_path, layered=True)
    figure = {"no": "fig1", "file": "fig1.png",
              "script": "C:\\contest\\figures\\scripts\\fig1.py"}
    path, err = gate.resolve_script(project, figure)
    assert path is None and "绝对路径" in err, (path, err)


def test_absolute_manifest_data_entrypoint_is_rejected(gate, tmp_path):
    project = _project(tmp_path, layered=True)
    figure = {"no": "fig1", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "/home/alice/figures/data/fig1.json"}
    assert gate.resolve_data_entrypoint(project, figure) is None


def test_absolute_manifest_file_falls_back_to_figure_number(gate, tmp_path):
    """`file` 字段写绝对路径时的**实际行为**（记录，非理想行为）：

    `_norm` 返回空串 → `resolve_png` 回落到 `{no}.png`。即**绝对路径值被忽略、
    不报错、产物仍按 `fig1.png` 找到**。`script`/`data_entrypoint` 两字段会明确报
    「绝对路径」错误，`file` 字段不会——这条差异已作为发现交回主 Agent。
    """
    project = _project(tmp_path, layered=True)
    resolved = gate.resolve_png(project, {"no": "fig1", "file": "D:/contest/fig1.png"})
    assert resolved == project / "figures" / "fig1.png"
    assert not str(resolved).startswith("D:"), "绝不能解析到项目外的绝对路径"


def test_absolute_manifest_file_absent_png_is_none(gate, tmp_path):
    """绝对路径 + `{no}.png` 也不存在 → None（不得凭空造出路径）。"""
    project = _project(tmp_path, layered=True)
    (project / "figures" / "fig1.png").unlink()
    assert gate.resolve_png(project, {"no": "fig1", "file": "D:/contest/fig1.png"}) is None


def test_png_targets_never_yields_absolute_path(gate, tmp_path):
    """`_png_targets` 供空 cwd 重跑用，绝不能产出项目外路径。"""
    project = _project(tmp_path, layered=True)
    targets = gate._png_targets(project, {"no": "fig1", "file": "C:\\contest\\fig1.png"})
    assert targets == [project / "figures" / "fig1.png"]
    assert all(project in t.parents for t in targets)


def test_absolute_path_does_not_escape_project(gate, tmp_path):
    """绝对路径若被 lstrip 成 `contest/...`，会把项目外文件当成本图产物——必须堵死。"""
    project = _project(tmp_path, layered=True)
    outside = tmp_path / "contest" / "figures" / "scripts"
    outside.mkdir(parents=True)
    (outside / "fig1.py").write_text("x", encoding="utf-8")
    figure = {"no": "fig1", "script": str(outside / "fig1.py")}
    path, err = gate.resolve_script(project, figure)
    assert path is None and err, "绝对路径不得解析到项目外文件"


# ── visualizer 与 verify/gate_audit 两侧归一化口径一致 ──────────────────
def test_two_sided_normalization_agrees(gate, verify_module):
    """`verify.py` 与 `gate_audit.py` 两侧都归一化（契约 §二 要求两侧都做）。"""
    spec = importlib.util.spec_from_file_location("e_layout_audit", ROOT / "scripts/gate_audit.py")
    audit = importlib.util.module_from_spec(spec)
    sys.modules["e_layout_audit"] = audit
    spec.loader.exec_module(audit)
    raw = "figures\\scripts\\fig1.py"
    expected = "figures/scripts/fig1.py"
    assert normalize_manifest_path(raw) == expected
    assert gate._norm(raw) == expected
    assert audit.normalize_manifest_path(raw) == expected
    assert getattr(verify_module, "normalize_manifest_path", normalize_manifest_path)(raw) == expected


def test_visualizer_and_gate_agree_on_layering(tmp_path, gate):
    """作图侧与门禁侧对「同一份 manifest 值解析到同一个文件」必须一致。"""
    project = _project(tmp_path, layered=True, flat=True)
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json"}
    via_gate, _ = gate.resolve_script(project, figure)
    viz = Visualizer(output_dir=str(project / "figures"))
    via_viz = viz.find_entry(figure["script"], "fig1.py", "scripts")
    assert via_gate == via_viz == project / "figures" / "scripts" / "fig1.py"


# ── manifest JSON 落盘形态（分层字段语义写死） ─────────────────────────
def test_manifest_fields_semantics(tmp_path):
    """`file` 相对 figures/；`script`/`data_entrypoint` 相对项目根（登记值原样落盘）。"""
    out = tmp_path / "figures"
    out.mkdir()
    viz = Visualizer(output_dir=str(out))
    viz.register_figure("fig1", "t", "c", "results/q1_results.json:Q1",
                        script="figures/scripts/fig1.py",
                        data_entrypoint="figures/data/fig1.json",
                        run_command="python figures/scripts/fig1.py", dependencies={},
                        official_url="https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.plot.html",
                        official_api="matplotlib.pyplot.plot", adaptation="official_api_composition",
                        changes="c", reason="r",
                        data_binding={"results_path": "results/q1_results.json",
                                      "bindings": {"y": "Q1"}})
    manifest = json.loads(viz.save_manifest().read_text(encoding="utf-8"))
    assert manifest[0]["file"] == "fig1.png"                      # 不带 figures/ 前缀
    assert manifest[0]["script"] == "figures/scripts/fig1.py"     # 相对项目根
    assert manifest[0]["data_entrypoint"] == "figures/data/fig1.json"
