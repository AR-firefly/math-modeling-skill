# DEA（数据包络分析）

## 1 适用情况

- 数据要求：多个决策单元（DMU）的投入指标 + 产出指标（数值型，均非负）
- 场景：相对效率评价——不预设生产函数，用线性规划包络前沿度量效率
- 何时用：多投入多产出、难以统一量纲归一化、要识别低效单元与改进方向
- 何时不用：决策单元间无可比性、投入产出指标选择不当

## 2 可联动算法

- 与 AHP/TOPSIS 结合做综合绩效评价
- 效率值为 0-1 的连续性指标，可进聚类/回归分析找影响因素

## 3 完整代码模板

```python
"""DEA-CCR：投入导向数据包络分析，测度决策单元相对效率。"""
import numpy as np
from scipy.optimize import linprog


def dea_ccr(X, Y):
    """X: (n, p) 投入矩阵；Y: (n, q) 产出矩阵（n 个决策单元）。
    返回效率向量 (n,)，取值 0-1，等于 1 表示 DEA 有效。"""
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    n = X.shape[0]
    eff = []
    for j in range(n):
        # 变量 [theta, lambda_0..lambda_{n-1}]，目标极小化 theta
        c = np.r_[1.0, np.zeros(n)]
        A_ub, b_ub = [], []
        for i in range(X.shape[1]):                  # 投入约束：组合投入 <= theta*当前
            A_ub.append(np.r_[-X[j, i], X[:, i]])
            b_ub.append(0.0)
        for r in range(Y.shape[1]):                  # 产出约束：组合产出 >= 当前产出
            A_ub.append(np.r_[0.0, -Y[:, r]])
            b_ub.append(-Y[j, r])
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=[(0, None)] * (n + 1))
        eff.append(res.fun if res.success else np.nan)
    return np.array(eff)


if __name__ == "__main__":
    # demo：4 个决策单元，投入（人力, 资金）、产出（产值）
    X = np.array([[2.0, 3.0], [3.0, 1.0], [5.0, 4.0], [8.0, 6.0]])
    Y = np.array([[3.0], [2.0], [5.0], [4.0]])
    eff = dea_ccr(X, Y)
    assert (eff >= 0).all() and (eff <= 1 + 1e-6).all()   # 效率在 0-1
    assert (eff > 1 - 1e-6).sum() >= 1                     # 至少一个 DMU 有效
    print("DEA 效率:", np.round(eff, 3))
```

## 4 真题出处

DEA（数据包络，LP 求效率）：2021C（供应商效率）、2020C（信贷）——加分项

