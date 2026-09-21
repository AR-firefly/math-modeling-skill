# Logistic增长模型

## 1 适用情况

- 数据要求：随时间的增长数据（y 单调递增且有上限），S 型（先快后慢）曲线
- 场景：人口增长、技术扩散、传播数量、含饱和容量的增长过程
- 何时用：数据呈明显 S 型、存在容量上限 K、需外推未来水平
- 何时不用：数据线性增长无饱和（用线性回归）、有下降段（Logistic 只增）

## 2 可联动算法

- 参数估计.md：curve_fit 即最小二乘参数反演，可与 MLE 对比
- 时间序列分解：分解出趋势后再用 Logistic 拟合趋势段
- 微分方程建模：Logistic 是 dP/dt=rP(1-P/K) 的解析解，可用于机理类题

## 3 完整代码模板

```python
"""Logistic 增长模型：S 型曲线拟合（人口/技术扩散）。"""
import numpy as np
from scipy.optimize import curve_fit


def logistic_growth(t, K, r, t0):
    """S 型曲线：K 容量上限、r 增长率、t0 拐点（中点）时刻。"""
    return K / (1.0 + np.exp(-r * (t - t0)))


if __name__ == "__main__":
    rng = np.random.RandomState(42)
    t = np.arange(20, dtype=float)          # 时间 0~19
    K_true, r_true, t0_true = 100.0, 0.5, 10.0
    y = logistic_growth(t, K_true, r_true, t0_true) + rng.randn(20) * 0.5
    # 初值猜测：K≈最大值、r 取正、t0≈中点
    p0 = [y.max() * 1.1, 0.3, t[10]]
    popt, _ = curve_fit(logistic_growth, t, y, p0=p0)
    K, r, t0 = popt
    # 相对误差 < 10%
    assert abs(K - K_true) / K_true < 0.1
    assert abs(r - r_true) / r_true < 0.1
    print(f"拟合参数 K={K:.2f}, r={r:.3f}, t0={t0:.2f}")
```

## 4 真题出处

- 保底层：Logistic 增长模型 2017C、2016C（题名佐证，增长/扩散类）
- 曲线拟合类：2021B（化学反应/浓度变化趋势拟合）
- 见 `algorithms/真题实证表.md` §2.1 保底"Logistic 增长模型"行
