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
    """v2.0 新图类型 errorbar/contour/contourf/radar/fill_between 全部出图落盘。"""
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
    v.register_figure("fig1", "收敛曲线", "迭代收敛到最优", "results.json:Q1_最优值")
    v.save_manifest()
    m = json.loads((tmp_path / "figures_manifest.json").read_text(encoding="utf-8"))
    assert m[0]["title"] == "收敛曲线"
    assert m[0]["data_source"] == "results.json:Q1_最优值"


def test_radar_uses_polar_projection(tmp_path, monkeypatch):
    """回归：雷达图必须用极坐标投影，否则 angles 是弧度却被当直角 X 轴，画成折线图。"""
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
    """回归：plot 的 ylim 参数做 y 轴动态缩放（值在 80-95 不画 0-100）。"""
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
