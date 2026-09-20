# 主成分回归PLS

## 1 适用情况

- 数据要求：样本 × 特征的数值矩阵（特征间高度相关、存在多重共线性），连续因变量 y
- 场景：自变量共线时无法直接用最小二乘，需提取主成分/潜变量后再回归
- 何时用：特征数多、强相关、或比样本量还多，OLS 不稳定
- 何时不用：特征近似正交、普通回归已稳定（直接线性多元回归.md）

## 2 可联动算法

- 线性多元回归：无共线时直接 OLS；有共线转 PLS
- 灰色关联分析/相关性分析：先筛共线特征再决定是否降维
- 交叉验证：确定最优潜变量个数 n（防止过拟合）

## 3 完整代码模板

```python
"""主成分回归/偏最小二乘：多重共线性下的回归预测。"""
import numpy as np
from sklearn.cross_decomposition import PLSRegression


def pls_reg(X, y, n=2):
    """X: (m, p) 自变量（特征高度相关）；y: (m,) 因变量；n: 潜变量个数。
    返回：训练好的 PLS 模型。"""
    X = np.asarray(X, float)
    y = np.asarray(y, float).reshape(-1, 1)
    pls = PLSRegression(n_components=n)   # 提取 n 个主成分（潜变量）
    pls.fit(X, y)
    return pls


if __name__ == "__main__":
    rng = np.random.RandomState(42)
    t = rng.randn(60)                     # 共同潜变量
    X = np.column_stack([t + rng.randn(60) * 0.1,      # 3 个高度相关特征
                         2 * t + rng.randn(60) * 0.1,
                         -1.5 * t + rng.randn(60) * 0.1])
    y = 2.0 * t + rng.randn(60) * 0.2     # 因变量由潜变量决定
    pls = pls_reg(X, y, n=2)
    err = np.abs(y - pls.predict(X).ravel()).mean()
    assert err < 0.5, "预测平均绝对误差应 < 0.5"
    print(f"PLS 预测平均绝对误差 = {err:.4f}")
```

## 4 真题出处

- 保底层：主成分回归/偏最小二乘（PLS）2022C（玻璃成分与多指标回归场景）
- 可联动线性多元回归解决共线问题（对应 03 类线性多元回归.md）
- 见需求文档 v5.0 第三节真题覆盖表"预测"行
