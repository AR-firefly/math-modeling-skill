# PCA 主成分/因子分析

## 1 适用情况

- 数据要求：m 样本 × n 维数值数据（建议先标准化）
- 场景：无监督降维——把相关指标压缩成少数主成分，消除共线性
- 何时用：指标多且相关性强、需要降维可视化或作后续建模输入
- 何时不用：指标语义需完整保留（解释性优先）时用因子分析做旋转解释

## 2 可联动算法

- 降维后的主成分作聚类/回归/分类输入（对应 02 类聚类.md 等）
- 与 LDA 对比：PCA 无监督、LDA 有监督

## 3 完整代码模板

```python
"""PCA 主成分分析/因子分析降维，自动选主成分数使累计贡献达标。"""
import numpy as np
from sklearn.decomposition import PCA


def pca_components(X, n=None, var_ratio=0.85):
    """X: (m, n) 数据；n: 指定主成分数；否则自动取使累计贡献 > var_ratio 的个数。
    返回：(降维特征矩阵 (m, k), 主成分模型)。"""
    X = np.asarray(X, float)
    model = PCA(n_components=None).fit(X)            # 先求全部主成分
    cum = np.cumsum(model.explained_variance_ratio_)
    if n is None:
        n = int(np.searchsorted(cum, var_ratio) + 1)
    model = PCA(n_components=n, random_state=42).fit(X)
    return model.transform(X), model


if __name__ == "__main__":
    rng = np.random.RandomState(42)
    X = rng.randn(100, 8) @ rng.rand(8, 8)           # 8 维含相关性的合成数据
    Z, model = pca_components(X)
    ratio = model.explained_variance_ratio_.sum()
    assert ratio > 0.85                              # 降维后累计方差比达标
    assert Z.shape[0] == 100                         # 样本数不变
    print("保留主成分数:", Z.shape[1], "| 累计方差比:", round(ratio, 3))
```

## 4 真题出处

PCA/因子分析（降维，累计贡献>85%）：2022C（玻璃多指标）

