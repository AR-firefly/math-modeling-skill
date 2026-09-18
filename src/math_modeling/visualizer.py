"""可视化：六种选图 + 四个科研图类型 + 300dpi PNG + 中文字体 + 图契约登记。

职责：按数据形态自动选图（line/bar/box/hist），散点/热力图显式指定；
出图统一 300dpi PNG 落盘到输出目录，中文字体 SimHei/微软雅黑 自动探测，
保证论文图表清晰、中文不乱码。

v2.0 增强（借鉴 nature-figure，Apache-2.0，见仓库 NOTICE.md）：
- PALETTE 受控配色：数模语义色（蓝=本文方法 / 红=基线 / 绿=改进）+ Okabe-Ito 色盲友好扩展
- _apply_style()：出版级 rcParams（去上右 spine/无边框 legend/字号规范），style.use 后调用
- 新增图类型：errorbar（误差棒）/ contour·contourf（等高线）/ radar（雷达）/ fill_between（区间）
- register_figure()：图契约登记（编号/图题/核心结论/数据出处）→ figures/figures_manifest.json

用法：
    viz = Visualizer(output_dir="figures", dpi=300)
    kind = viz.decide_kind(x, y, n_cat=3)     # 自动选图
    p = viz.plot("line", {"x": xs, "y": ys}, title="...", save_name="fig1")
    viz.register_figure("fig1", "收敛曲线", "迭代 500 步收敛到最优解", "results.json:Q1_最优值")
    viz.save_manifest()
"""
import json
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")  # 无界面后端，供脚本/服务器出图
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# --- 中文字体探测：SimHei > 微软雅黑 > SimSun，找不到则回退默认并告警 ---
_FONTS = [f.name for f in fm.fontManager.ttflist]
_CN_FONT = next((f for f in ("SimHei", "Microsoft YaHei", "SimSun") if f in _FONTS), None)


def _apply_cn_font():
    """应用中文字体到 rcParams（plt.style.use 会重置字体，必须在 style 之后调用）。"""
    if _CN_FONT:
        matplotlib.rcParams["font.sans-serif"] = [_CN_FONT]
        matplotlib.rcParams["font.family"] = "sans-serif"
    else:
        import warnings

        warnings.warn("未找到中文字体，图表中文可能乱码；请安装 SimHei/微软雅黑")
    matplotlib.rcParams["axes.unicode_minus"] = False  # 负号正常显示


# --- 受控配色（借鉴 nature-figure design-theory/api.md，Apache-2.0，见 NOTICE.md）---
# 数模语义色：蓝=本文方法 / 红=基线 / 绿=改进，正好配"基线对比"；禁 rainbow/jet。
PALETTE = {
    "method": "#0F4D92",        # 深蓝 —— 本文方法（hero）
    "method_2": "#3775BA",      # 中蓝 —— 第二方法
    "baseline": "#B64342",      # 红 —— 基线 / 对比
    "improve": "#2E9E44",       # 绿 —— 改进 / 提升
    "neutral_light": "#CFCECE",
    "neutral_mid": "#767676",
    "neutral_dark": "#4D4D4D",
    "accent_teal": "#42949E",
    "accent_violet": "#9A4D8E",
}
DEFAULT_COLOR_ORDER = [
    PALETTE["method"], PALETTE["method_2"], PALETTE["baseline"], PALETTE["improve"],
    PALETTE["accent_teal"], PALETTE["accent_violet"], PALETTE["neutral_light"], PALETTE["neutral_mid"],
]
# Okabe-Ito 色盲友好 8 色（需要更多类别时按序扩展，避免彩虹渐变）
OKABE_ITO = ["#0072B2", "#D55E00", "#009E73", "#CC79A7",
             "#56B4E9", "#E69F00", "#F0E442", "#000000"]


def _apply_style():
    """统一出版级 rcParams（借鉴 nature-figure design-theory，适配国赛 300dpi PNG）。

    必须在 plt.style.use 之后调用（style 会重置 rcParams，与 _apply_cn_font 同理）。
    """
    matplotlib.rcParams.update({
        "axes.spines.right": False,       # 去上右 spine，极简
        "axes.spines.top": False,
        "axes.linewidth": 0.8,
        "font.size": 10.5,                # 300dpi 下正文可读
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.frameon": False,          # 无边框 legend
        "axes.grid": False,               # 默认无网格，稀疏刻度引导
        "grid.linewidth": 0.6,
        "grid.alpha": 0.4,
        "lines.linewidth": 2.0,
        "lines.markersize": 7,
        "errorbar.capsize": 4,
        "xtick.direction": "out",
        "ytick.direction": "out",
    })


_apply_cn_font()
_apply_style()


class Visualizer:
    """六种基础图表 + 四个科研图类型（errorbar/contour/radar/fill_between）的统一出图器。

    图契约登记：register_figure() 把每张图的核心结论与数据出处写入 figures_manifest.json，
    供 verify_figure_references 检查（图号连续/正文引用对应/文件存在）。
    """

    def __init__(self, dpi=300, output_dir="figures", style="seaborn-v0_8-whitegrid"):
        self.dpi, self.out = dpi, Path(output_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self._figures = []  # 图契约登记（register_figure 追加，save_manifest 落盘）
        try:
            plt.style.use(style)
        except OSError:
            plt.style.use("ggplot")  # 老版本 matplotlib 无 seaborn 风格时回退
        _apply_cn_font()   # style 重置字体后重新应用中文字体
        _apply_style()     # style 重置样式后重新应用出版级样式

    def decide_kind(self, x, y, n_cat=None):
        """自动选图类型（覆盖 line/bar/box/hist；scatter/heatmap 需显式指定）。"""
        if x is None and y is None:
            return "hist"
        if n_cat and y is not None:
            return "box"                       # 分类×连续 → 箱线图
        if x is not None and y is not None:
            return "line" if len(np.unique(x)) > 8 else "bar"  # 连续时序→折线；分类对比→柱状
        return "hist"

    def register_figure(self, no, title, conclusion, data_source, *, script=None,
                        data_entrypoint=None, run_command=None, dependencies=None,
                        official_url=None, official_api=None, adaptation=None,
                        changes=None, reason=None, seed=None, source_evidence=None):
        """登记复现与来源线索。字段齐全只表示待核验，不能证明实际复现或来源可靠。"""
        record = dict(no=no, title=title, conclusion=conclusion, data_source=data_source,
                      file=f"{no}.png", script=script, data_entrypoint=data_entrypoint,
                      run_command=run_command, dependencies=dependencies or {},
                      official_url=official_url, official_api=official_api,
                      adaptation=adaptation, changes=changes, reason=reason, seed=seed,
                      source_evidence=source_evidence or {})
        required = ("script", "data_entrypoint", "run_command", "dependencies",
                    "official_url", "official_api", "adaptation", "changes", "reason")
        record["missing_evidence"] = [key for key in required if not record[key]]
        record["evidence_status"] = "incomplete" if record["missing_evidence"] else "pending_verification"
        self._figures.append(record)
        return self

    def save_manifest(self, manifest_name="figures_manifest.json"):
        """把图契约登记落盘到 {output_dir}/{manifest_name}，返回 Path。"""
        path = self.out / manifest_name
        path.write_text(json.dumps(self._figures, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def plot(self, kind, data, title, xlabel=None, ylabel=None, save_name="fig", ylim=None):
        """按 kind 画图并落盘 {output_dir}/{save_name}.png，返回 Path。

        radar 用极坐标投影（angles 是弧度、fill 成扇形），否则是直角坐标系；
        ylim=(y0, y1) 可选：y 轴动态缩放（值在 80-95 不画 0-100），防误导。
        """
        subplot_kw = {"projection": "polar"} if kind == "radar" else {}
        fig, ax = plt.subplots(figsize=(8, 5), subplot_kw=subplot_kw)
        getattr(self, f"_{kind}")(ax, data)
        ax.set_title(title)
        if kind != "radar":  # 极坐标轴无 x/y 标签语义
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
        if ylim:
            ax.set_ylim(ylim)
        fig.tight_layout()
        if ylim:
            ax.set_ylim(ylim)  # tight_layout 可能触发 autoscale 覆盖 y 限界，savefig 前强制恢复
        path = self.out / f"{save_name}.png"
        fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        return path

    # --- 基础六图 ---
    def _line(self, ax, d):
        ax.plot(d["x"], d["y"], marker="o", color=d.get("color", PALETTE["method"]))
        ax.grid(True, ls="--", alpha=.4)

    def _bar(self, ax, d):
        ax.bar(d["x"], d["y"], color=d.get("color", PALETTE["method"]),
               edgecolor="black", linewidth=0.6)
        ax.grid(axis="y", ls="--", alpha=.4)

    def _scatter(self, ax, d):
        ax.scatter(d["x"], d["y"], s=18, alpha=.7,
                   color=d.get("color", PALETTE["method"]))

    def _box(self, ax, d):
        # 注意：matplotlib>=3.11 boxplot 无 labels 参数（会 TypeError），改 xticklabels 设置
        labels = d.get("labels") or [f"G{i + 1}" for i in range(len(d["y"]))]
        ax.boxplot(d["y"])
        ax.set_xticks(range(1, len(labels) + 1))
        ax.set_xticklabels(labels)

    def _heatmap(self, ax, d):
        im = ax.imshow(d["z"], cmap=d.get("cmap", "YlGnBu"), aspect="auto")
        ax.figure.colorbar(im, ax=ax)
        ax.set_xticks(range(d["z"].shape[1]))
        ax.set_yticks(range(d["z"].shape[0]))
        ax.set_xticklabels(d.get("xlabels") or [])
        ax.set_yticklabels(d.get("ylabels") or [])

    def _hist(self, ax, d):
        ax.hist(d["y"] if "y" in d else d["x"], bins=d.get("bins", 20),
                edgecolor="white", color=d.get("color", PALETTE["method"]))

    # --- 科研图类型（v2.0，借鉴 nature-figure chart-types/design-theory）---
    def _errorbar(self, ax, d):
        """误差棒柱状（灵敏度/元启发式 3 次均值±方差）；hatch 保证灰度打印可区分。"""
        x = np.asarray(d["x"])
        y = np.asarray(d["y"])
        err = np.asarray(d.get("err", np.zeros_like(y)))
        bars = ax.bar(x, y, yerr=err, capsize=4, color=d.get("color", PALETTE["method"]),
                      edgecolor="black", linewidth=0.8, hatch=d.get("hatch"))
        if d.get("annotate"):
            for b, v in zip(bars, y):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + err.max() * 0.05,
                        f"{v:.3g}", ha="center", va="bottom", fontsize=9)
        if d.get("baseline") is not None:
            ax.axhline(d["baseline"], color=PALETTE["baseline"], ls="--", lw=1.5, alpha=0.6,
                       label="基线")

    def _contour(self, ax, d):
        """等高线（机理题参数响应/目标函数曲面），带等值线标注。"""
        X, Y = np.meshgrid(np.asarray(d["x"]), np.asarray(d["y"]))
        Z = np.asarray(d["z"])
        cf = ax.contour(X, Y, Z, levels=d.get("levels", 15))
        ax.clabel(cf, inline=True, fontsize=8, fmt=d.get("fmt", "%.2f"))
        if d.get("colorbar"):
            ax.figure.colorbar(cf, ax=ax)

    def _contourf(self, ax, d):
        """填充等高线（参数响应曲面），加黑色等值线提升对比度。"""
        X, Y = np.meshgrid(np.asarray(d["x"]), np.asarray(d["y"]))
        Z = np.asarray(d["z"])
        cf = ax.contourf(X, Y, Z, levels=d.get("levels", 30),
                         cmap=d.get("cmap", "YlGnBu"))
        ax.figure.colorbar(cf, ax=ax)
        if d.get("contour_lines", True):
            ax.contour(X, Y, Z, levels=15, colors="k", linewidths=0.4, alpha=0.5)

    def _radar(self, ax, d):
        """雷达图（评价类多指标对比）；默认去极坐标网格，只留刻度。"""
        categories = list(d["categories"])
        n = len(categories)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles += angles[:1]
        for i, s in enumerate(d["series"]):
            vals = list(s["values"]) + [s["values"][0]]
            color = s.get("color") or DEFAULT_COLOR_ORDER[i % len(DEFAULT_COLOR_ORDER)]
            ax.plot(angles, vals, color=color, lw=2, label=s.get("label"))
            ax.fill(angles, vals, color=color, alpha=0.08)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=9)
        ax.set_ylim(d.get("ylim", (0, 1)))
        ax.grid(True, ls="--", alpha=0.4)
        if len(d["series"]) > 1:
            ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.0), frameon=False)

    def _fill_between(self, ax, d):
        """区间填充（预测区间/置信带/不确定度带），可选基线参考线。"""
        x = np.asarray(d["x"])
        mean, lo, hi = np.asarray(d["mean"]), np.asarray(d["lo"]), np.asarray(d["hi"])
        color = d.get("color", PALETTE["method"])
        ax.plot(x, mean, color=color, lw=2, label=d.get("label", "均值"))
        ax.fill_between(x, lo, hi, color=color, alpha=0.15, label=d.get("band_label", "区间"))
        if d.get("baseline") is not None:
            ax.axhline(d["baseline"], color=PALETTE["baseline"], ls="--", lw=1.5, alpha=0.6,
                       label="基线")
        if d.get("xlabel"):
            ax.set_xlabel(d["xlabel"])
        if d.get("ylabel"):
            ax.set_ylabel(d["ylabel"])
        ax.legend(frameon=False)
