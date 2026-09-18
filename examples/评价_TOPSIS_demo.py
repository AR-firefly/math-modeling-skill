"""评价类示例：熵权+TOPSIS 综合排序，五样检验全做

自包含脚本：在 examples/ 目录下 `python 评价_TOPSIS_demo.py` 直接运行。
- 数据：RandomState(42) 合成 60 方案 × 5 指标的决策矩阵（指标 3、5 为负向/成本型，其余正向）
- 方法：熵权法定客观权重 → TOPSIS 综合排序
- 检验：网格无关 / 数值收敛 / 灵敏度 / 误差分析 / 对比验证 五样全做（assert 通过才算完）
- 落盘：examples/results/results_TOPSIS.json
依赖：numpy / scipy（pandas、sklearn 未用到）
"""
import json
import os
import sys

import numpy as np
from scipy.stats import kendalltau

# 保证 Windows 下 stdout 能打印 ✅ 等 UTF-8 字符
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


def topsis(X, w=None, pos=None):
    """X: (m, n) 决策矩阵（m 方案，n 指标）。
    w: 权重向量（默认等权）；pos: 正/负向指标标记，True=正向（越大越好）。
    返回：贴进度 C (m,)，已按从优到劣排序的下标。"""
    X = np.asarray(X, float)
    m, n = X.shape
    if w is None:
        w = np.ones(n) / n
    if pos is None:
        pos = np.ones(n, dtype=bool)
    w = np.asarray(w, float) / w.sum()

    # 1) 向量归一化（消量纲）
    Z = X / np.sqrt((X ** 2).sum(axis=0))
    # 2) 加权
    Z = Z * w
    # 3) 理想解
    zp = np.where(pos, Z.max(axis=0), Z.min(axis=0))
    zm = np.where(pos, Z.min(axis=0), Z.max(axis=0))
    # 4) 距离 + 贴进度
    dp = np.sqrt(((Z - zp) ** 2).sum(axis=1))
    dm = np.sqrt(((Z - zm) ** 2).sum(axis=1))
    C = dm / (dp + dm + 1e-12)
    return C, np.argsort(-C)


def entropy_weight(X, pos=None):
    """熵权法定客观权重：归一化 → 信息熵 → 权重（和=1）。

    正向指标 min-max 归一化，负向指标取反后再归一化；
    权重 w_j = (1-e_j) / sum_j (1-e_j)，信息量越大（熵越小）权重越高。
    """
    X = np.asarray(X, float)
    n, m = X.shape
    if pos is None:
        pos = np.ones(m, dtype=bool)
    pos = np.asarray(pos, bool)

    Z = np.empty_like(X)
    for j in range(m):
        lo, hi = X[:, j].min(), X[:, j].max()
        r = hi - lo
        if r < 1e-12:
            Z[:, j] = 1.0
        elif pos[j]:
            Z[:, j] = (X[:, j] - lo) / r
        else:
            Z[:, j] = (hi - X[:, j]) / r
    Z = Z + 1e-10                      # 避免 log(0)
    P = Z / Z.sum(axis=0)
    e = -(P * np.log(P)).sum(axis=0) / np.log(n)
    d = 1 - e
    w = d / d.sum()
    return w


def generate_data(n, seed=42):
    """合成决策矩阵：一个潜变量 s 同时驱动各指标（带不同强度噪声），
    保证各指标间有公共排序信号，且噪声强弱不同 → 熵权有区分度。
    指标 0,1,3 正向（越大越好），指标 2,4 负向/成本（越小越好）。"""
    rng = np.random.RandomState(seed)
    s = rng.uniform(0.2, 0.9, size=n)          # 潜变量：方案优劣
    X = np.empty((n, 5))
    X[:, 0] = 5.0 + 6.0 * s + 0.3 * rng.randn(n)   # 正向，低噪声（熵权高）
    X[:, 1] = 3.0 + 8.0 * s + 1.2 * rng.randn(n)   # 正向，高噪声（熵权低）
    X[:, 2] = 8.0 - 6.0 * s + 0.7 * rng.randn(n)   # 成本，越小越好
    X[:, 3] = 2.0 + 7.0 * s + 1.0 * rng.randn(n)   # 正向
    X[:, 4] = 10.0 - 9.0 * s + 0.5 * rng.randn(n)  # 成本，低噪声（熵权高）
    return X


def rank_from_order(order):
    """排序序列（从优到劣的下标列表）→ 各方案名次（0 为最优）。"""
    order = np.asarray(order)
    rank = np.empty(order.shape, dtype=int)
    for r, i in enumerate(order):
        rank[i] = r
    return rank


def subset_rank(order_full, subset):
    """order_full 为全样本排序；返回 subset 内各方案在全样本排序中的名次（0 最优）。"""
    return rank_from_order(order_full)[subset]


def concordant_proportion(a, b):
    """两打分序列（越大越好）的同序对比例（一致率），无并列假设。"""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    n = len(a)
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            d1 = a[i] - a[j]
            d2 = b[i] - b[j]
            if d1 * d2 > 0:
                conc += 1
            elif d1 * d2 < 0:
                disc += 1
    return conc / (conc + disc)


def main():
    # ===== 数据与权重 =====
    X_all = generate_data(80, seed=42)          # 生成 80 行，主 demo 用前 60（满足 20/40/60/80 收敛档）
    X_main = X_all[:60]                         # 60 方案 × 5 指标
    pos = np.array([True, True, False, True, False])   # 指标 3、5（1-based）为成本型
    w = entropy_weight(X_main, pos)             # 熵权法客观权重，和=1
    n_ind = X_main.shape[1]

    # ===== 主排序 =====
    C, order = topsis(X_main, w, pos)

    print("=" * 68)
    print("熵权 + TOPSIS 综合评价排序  demo")
    print("=" * 68)
    print("熵权权重:", np.round(w, 4).tolist(), "  权重和 =", round(w.sum(), 6))
    print("前 10 名（方案序号从1起，附贴进度）:")
    for k in range(10):
        i = order[k]
        print(f"  第{k + 1:>2} 名: 方案{i + 1:>2}   贴进度 = {C[i]:.4f}")

    # ===== 五样检验 =====
    checks = {}

    # 1) 网格无关（评价版）：样本量减半（30）vs 全量（60）
    subset = np.arange(30)
    _, order_half = topsis(X_main[:30], w, pos)
    _, order_full = topsis(X_main, w, pos)
    tau_grid, _ = kendalltau(subset_rank(order_half, subset), subset_rank(order_full, subset))
    assert tau_grid > 0.95
    print(f"✅ 网格无关 OK：样本量 30 vs 60 排序 Kendall-τ = {tau_grid:.4f} > 0.95")
    checks["grid_independence"] = {"threshold": "> 0.95", "kendall_tau": round(float(tau_grid), 4),
                                   "n_half": 30, "n_full": 60, "pass": True}

    # 2) 数值收敛（评价版）：样本量 20/40/60/80，相邻档排序 Kendall-τ ≥ 0.95
    sizes = [20, 40, 60, 80]
    tau_conv = []
    for a, b in zip(sizes[:-1], sizes[1:]):
        _, order_a = topsis(X_all[:a], w, pos)
        _, order_b = topsis(X_all[:b], w, pos)
        common = np.arange(a)
        t, _ = kendalltau(subset_rank(order_a, common), subset_rank(order_b, common))
        tau_conv.append(t)
        assert t >= 0.95
    print("✅ 数值收敛 OK：样本量 20/40/60/80 相邻档 Kendall-τ = "
          + ", ".join(f"{t:.4f}" for t in tau_conv) + "，均 ≥ 0.95")
    checks["numerical_convergence"] = {"sizes": sizes,
                                       "kendall_taus": [round(float(t), 4) for t in tau_conv],
                                       "threshold": "each >= 0.95", "pass": True}

    # 3) 灵敏度：权重逐指标 ±20% 扰动（w*(1±0.2) 再归一化），排序 vs 原排序最差 Kendall-τ ≥ 0.85
    tau_sens = []
    for j in range(n_ind):
        for factor in (1.2, 0.8):
            w_pert = w.copy()
            w_pert[j] *= factor
            w_pert = w_pert / w_pert.sum()
            _, order_p = topsis(X_main, w_pert, pos)
            t, _ = kendalltau(rank_from_order(order), rank_from_order(order_p))
            tau_sens.append(t)
    tau_sens_min = min(tau_sens)
    assert tau_sens_min >= 0.85
    print(f"✅ 灵敏度 OK：权重逐指标 ±20% 扰动（10 次）最差 Kendall-τ = {tau_sens_min:.4f} ≥ 0.85")
    checks["sensitivity"] = {"threshold": ">= 0.85", "worst_kendall_tau": round(float(tau_sens_min), 4),
                             "all_kendall_taus": [round(float(t), 4) for t in tau_sens], "pass": True}

    # 4) 误差分析：TOPSIS vs 合成真值基准（0.4*正向和 - 0.2*成本）的一致率 > 0.8
    baseline = 0.4 * (X_main[:, 0] + X_main[:, 1] + X_main[:, 3]) - 0.2 * (X_main[:, 2] + X_main[:, 4])
    conc = concordant_proportion(baseline, C)
    assert conc > 0.8
    print(f"✅ 误差分析 OK：TOPSIS 贴进度 vs 合成真值基准排序一致率 = {conc:.4f} > 0.8")
    checks["error_analysis"] = {"threshold": "> 0.8", "concordant_proportion": round(float(conc), 4),
                                "baseline_formula": "0.4*正向和 - 0.2*成本", "pass": True}

    # 5) 对比验证：熵权 TOPSIS vs 等权（AHP 简化为等权）TOPSIS，量化 Kendall-τ
    w_eq = np.ones(n_ind) / n_ind
    C_eq, order_eq = topsis(X_main, w_eq, pos)
    tau_cmp, _ = kendalltau(rank_from_order(order), rank_from_order(order_eq))
    assert tau_cmp >= 0.7
    print(f"✅ 对比验证 OK：熵权 TOPSIS vs 等权(AHP简化) TOPSIS Kendall-τ = {tau_cmp:.4f}")
    checks["comparison"] = {"method_b": "等权 TOPSIS（AHP 简化）", "kendall_tau": round(float(tau_cmp), 4),
                            "threshold": ">= 0.7", "pass": True}

    # ===== 结果落盘 =====
    results = {
        "method": "熵权法 + TOPSIS",
        "data": {"n_alternatives": 60, "n_indicators": 5, "seed": 42,
                 "positive_indicators_1based": [1, 2, 4], "cost_indicators_1based": [3, 5]},
        "entropy_weights": [round(float(x), 6) for x in w],
        "top10": {
            "position_1based": list(range(1, 11)),
            "alternative_index_1based": [int(i) + 1 for i in order[:10]],
            "closeness": [round(float(C[i]), 6) for i in order[:10]],
        },
        "closeness_all": [round(float(c), 6) for c in C],
        "checks": checks,
    }
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "results_TOPSIS.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("-" * 68)
    print("结果已落盘:", out_path)
    print("五样检验全部 OK，无异常退出。")

    return results


if __name__ == "__main__":
    main()
