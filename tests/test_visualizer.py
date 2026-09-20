"""可视化模块测试：decide_kind 四类自动选图 + plot 落盘 300dpi PNG。"""
import numpy as np
from math_modeling.visualizer import Visualizer


def test_decide_kind_hist():
    assert Visualizer().decide_kind(None, None) == "hist"


def test_decide_kind_box():
    assert Visualizer().decide_kind("cat", "y", n_cat=3) == "box"


def test_decide_kind_line_vs_bar():
    x_long = np.arange(20)
    x_short = np.arange(3)
    assert Visualizer().decide_kind(x_long, "y") == "line"
    assert Visualizer().decide_kind(x_short, "y") == "bar"


def test_plot_saves_png(tmp_path):
    v = Visualizer(output_dir=str(tmp_path), dpi=300)
    p = v.plot("line", {"x": [1, 2, 3], "y": [1, 4, 9]}, title="t", save_name="demo")
    assert p.exists() and p.stat().st_size > 1000


def test_plot_box_saves_png(tmp_path):
    # 回归：box 图（matplotlib>=3.11 无 labels 参数，应改用 xticklabels）可正常落盘
    v = Visualizer(output_dir=str(tmp_path), dpi=300)
    p = v.plot("box", {"y": [[1, 2, 3], [4, 5, 6]], "labels": ["A", "B"]},
               title="box", save_name="box")
    assert p.exists() and p.stat().st_size > 1000


def test_new_kinds_save_png(tmp_path):
    """v2.1 新图类型 errorbar/contour/contourf/radar/fill_between 全部出图落盘。"""
    v = Visualizer(output_dir=str(tmp_path), dpi=300)
    xs = np.linspace(-2, 2, 20)
    X, Y = np.meshgrid(xs, xs)
    v.plot("errorbar", {"x": [1, 2], "y": [2, 3], "err": [0.2, 0.1]}, "e", save_name="f1")
    v.plot("contour", {"x": xs, "y": xs, "z": X ** 2 + Y ** 2}, "c", save_name="f2")
    v.plot("contourf", {"x": xs, "y": xs, "z": X ** 2 + Y ** 2}, "cf", save_name="f3")
    v.plot("radar", {"categories": ["a", "b", "c"],
                     "series": [{"label": "s", "values": [0.8, 0.6, 0.7]}]}, "r", save_name="f4")
    v.plot("fill_between", {"x": [1, 2, 3], "mean": [2, 3, 2],
                            "lo": [1, 2, 1], "hi": [3, 4, 3]}, "fb", save_name="f5")
    pngs = list(tmp_path.glob("*.png"))
    assert len(pngs) == 5
    assert all(p.stat().st_size > 1000 for p in pngs), "新图类型 PNG 应非空"


def test_register_figure_manifest(tmp_path):
    """图契约登记 → figures_manifest.json UTF-8 内容正确（防 GBK 乱码）。"""
    import json
    v = Visualizer(output_dir=str(tmp_path))
    v.register_figure("fig1", "收敛曲线", "迭代收敛到最优", "results.json:Q1_最优值",
                      data_binding={"results_path": "results/q1_results.json",
                                    "bindings": {"y": "Q1_最优值"}})
    v.save_manifest()
    m = json.loads((tmp_path / "figures_manifest.json").read_text(encoding="utf-8"))
    assert m[0]["title"] == "收敛曲线"
    assert m[0]["data_source"] == "results.json:Q1_最优值"
    # 自由字符串 data_source（人读）保留；结构化 data_binding（机检）并存
    assert m[0]["data_binding"]["results_path"] == "results/q1_results.json"


# ── v3.0 C5：目录分层（先分层 → 再扁平 → 两处都不存在 = None）──
def test_find_entry_layered_then_flat(tmp_path):
    v = Visualizer(output_dir=str(tmp_path))
    (tmp_path / "scripts").mkdir()
    layered = tmp_path / "scripts" / "fig1.py"
    layered.write_text("x = 1", encoding="utf-8")
    assert v.find_entry("figures/scripts/fig1.py", "fig1.py", "scripts") == layered
    # 扁平布局兼容
    (tmp_path / "fig2.py").write_text("x = 1", encoding="utf-8")
    assert v.find_entry("figures/fig2.py", "fig2.py", "scripts") == tmp_path / "fig2.py"
    # 两处都不存在 → None（「放错目录」必须抓到）
    assert v.find_entry("figures/elsewhere/fig9.py", "fig9.py", "scripts") is None


def test_png_lookup_is_confined_to_figures_dir(tmp_path, monkeypatch):
    """回归：`file` 相对 figures/，不得把 cwd 下偶然同名的文件当成本图产物（假绿）。"""
    out = tmp_path / "figures"
    out.mkdir()
    stray = tmp_path / "fig1.png"          # 项目根下的同名文件，不是本图产物
    stray.write_bytes(b"\x89PNG stray")
    monkeypatch.chdir(tmp_path)
    v = Visualizer(output_dir=str(out))
    assert v.find_entry("fig1.png", "fig1.png", root_relative=False) is None
    assert v.find_entry("ignored.png", "fig1.png", root_relative=False) is None
    (out / "fig1.png").write_bytes(b"\x89PNG real")
    assert v.find_entry("fig1.png", "fig1.png", root_relative=False) == out / "fig1.png"


def test_register_missing_data_binding_is_incomplete(tmp_path):
    """v3.0：data_binding 是机检新增必填（gate_audit 必填键 11 → 12）。"""
    v = Visualizer(output_dir=str(tmp_path))
    v.register_figure("fig1", "t", "c", "results.json:Q1",
                      script="figures/scripts/fig1.py", data_entrypoint="figures/data/fig1.json",
                      run_command="python figures/scripts/fig1.py", dependencies={},
                      official_url="https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.plot.html",
                      official_api="matplotlib.pyplot.plot", adaptation="official_api_composition",
                      changes="c", reason="r")
    assert "data_binding" in v._figures[0]["missing_evidence"]
    assert v._figures[0]["evidence_status"] == "incomplete"


# ── v3.0 C3：manifest 状态机（reproduced 自写 + 三元组失效退回）──
def _ready_visualizer(tmp_path):
    """构造一张字段齐全、脚本/数据/PNG 都已落盘的图，返回 (viz, script, data, png)。"""
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    script = tmp_path / "scripts" / "fig1.py"
    data = tmp_path / "data" / "fig1.json"
    png = tmp_path / "fig1.png"
    script.write_text("print(1)\n", encoding="utf-8")
    data.write_text('{"y": 1}', encoding="utf-8")
    png.write_bytes(b"\x89PNG demo" * 50)
    v = Visualizer(output_dir=str(tmp_path))
    v.register_figure("fig1", "t", "c", "results.json:Q1",
                      script="figures/scripts/fig1.py", data_entrypoint="figures/data/fig1.json",
                      run_command="python figures/scripts/fig1.py", dependencies={"matplotlib": "3.10"},
                      official_url="https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.plot.html",
                      official_api="matplotlib.pyplot.plot", adaptation="official_api_composition",
                      changes="c", reason="r",
                      data_binding={"results_path": "results/q1_results.json", "bindings": {"y": "Q1"}})
    return v, script, data, png


def test_mark_reproduced_sets_artifact_hash(tmp_path):
    v, _, _, _ = _ready_visualizer(tmp_path)
    record = v.mark_reproduced("fig1")
    assert record["evidence_status"] == "reproduced"
    assert len(record["artifact_hash"]) == 64


def test_artifact_change_demotes_to_pending_verification(tmp_path):
    """状态不脱钩：改脚本 / 改数据 / 重跑生成不同 PNG → 自动退回 pending_verification。"""
    for name in ("script", "data", "png"):
        root = tmp_path / name
        root.mkdir()
        v, script, data, png = _ready_visualizer(root)
        v.mark_reproduced("fig1")
        assert v._figures[0]["evidence_status"] == "reproduced"
        if name == "script":
            script.write_text("print(2)\n", encoding="utf-8")
        elif name == "data":
            data.write_text('{"y": 2}', encoding="utf-8")
        else:
            png.write_bytes(b"\x89PNG other" * 50)
        assert v.refresh_statuses() == ["fig1"], name
        assert v._figures[0]["evidence_status"] == "pending_verification", name
        assert "artifact_hash" not in v._figures[0], name


def test_visualizer_has_no_verified_writer(tmp_path):
    """verified 只由审查 Agent 写：本模块不得提供置 verified 的接口（防自证）。"""
    v, _, _, _ = _ready_visualizer(tmp_path)
    assert not hasattr(v, "mark_verified")
    assert "verified" not in [name for name in dir(v) if not name.startswith("__")]
    v.mark_reproduced("fig1")
    assert v._figures[0]["evidence_status"] != "verified"


def test_mark_reproduced_rejects_missing_files(tmp_path):
    """脚本/PNG 未按契约落盘（含放错目录）不得标记 reproduced。"""
    import pytest
    v, script, _, _ = _ready_visualizer(tmp_path)
    script.unlink()
    with pytest.raises(ValueError, match="落盘"):
        v.mark_reproduced("fig1")


def test_radar_uses_polar_projection(tmp_path, monkeypatch):
    """回归（E1-01）：雷达图必须用极坐标投影，否则 angles 是弧度却被当直角 X 轴，画成折线图。"""
    import matplotlib.pyplot as plt

    real_subplots = plt.subplots
    captured = {}

    def spy_subplots(*a, **kw):
        captured.update(kw)
        return real_subplots(*a, **kw)

    monkeypatch.setattr(plt, "subplots", spy_subplots)
    v = Visualizer(output_dir=str(tmp_path), dpi=300)
    v.plot("radar",
           {"categories": ["a", "b", "c"],
            "series": [{"label": "s", "values": [0.8, 0.6, 0.7]}]},
           "radar", save_name="radar")
    assert captured.get("subplot_kw") == {"projection": "polar"}


def test_plot_ylim_applies(tmp_path, monkeypatch):
    """回归（E3-04）：plot 的 ylim 参数做 y 轴动态缩放（值在 80-95 不画 0-100）。"""
    import matplotlib.pyplot as plt

    real_ylim = plt.Axes.set_ylim
    calls = []

    def spy_ylim(self, *a, **kw):
        calls.append(a)
        return real_ylim(self, *a, **kw)

    monkeypatch.setattr(plt.Axes, "set_ylim", spy_ylim)
    v = Visualizer(output_dir=str(tmp_path), dpi=300)
    v.plot("line", {"x": [1, 2, 3], "y": [80, 90, 95]}, "t", save_name="ylim", ylim=(70, 100))
    assert calls and calls[-1] == ((70, 100),), \
        f"ylim 未在 savefig 前锁定（autoscale 覆盖了）: {calls}"
