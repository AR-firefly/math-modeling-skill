# TOPSIS（优劣解距离法）

## 1 适用情况

- 数据要求：多方案 × 多指标的决策矩阵（数值型，可含正负向指标），方案数 ≥ 2
- 场景：综合评价排序——选择"贴近理想解"（正理想解最优、负理想解最劣）的方案
- 何时用：指标量纲不同、无标准权重、需要客观排序
- 何时不用：指标语义无法量化、方案间无可比性

## 2 可联动算法

- 熵权法定客观权重（`entropy_weight` → 权重向量喂给 TOPSIS）
- AHP 定主观权重；组合评价法（AHP+熵权+CRITIC 融合）
- 与灰色关联分析对比：TOPSIS 看距离、灰关联看相似度

## 3 完整代码模板

```python
"""TOPSIS：多方案多指标综合排序，贴近理想解。"""
import numpy as np


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

    # 1) 向量归一化（消量纲）；分母加小量防全零列除零（全零列 Z=0，对距离无贡献）
    Z = X / (np.sqrt((X ** 2).sum(axis=0)) + 1e-12)
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


if __name__ == "__main__":
    # demo：3 个方案 × 3 个指标（2 正向 1 负向），熵权法权重
    rng = np.random.RandomState(42)
    X = rng.rand(3, 3) * 10
    pos = np.array([True, True, False])   # 指标3 越小越好（成本）
    w = np.array([0.4, 0.35, 0.25])       # 熵权/专家给出
    C, order = topsis(X, w, pos)
    assert C.shape == (3,) and len(order) == 3
    assert (C >= 0).all() and (C <= 1).all()      # 贴进度合法 0-1
    assert C[order[0]] == C.max()                 # 排序第一 = 贴进度最高（排序正确性）
    print("TOPSIS 排序:", order, "贴进度:", np.round(C[order], 3))
    # 验证单调性：全优方案贴进度应 > 全劣方案
    Xb = np.array([[9, 9, 1], [1, 1, 9]])   # 前优后劣
    Cb, _ = topsis(Xb, w, pos)
    assert Cb[0] > Cb[1]
    print("TOPSIS 基准校验通过")
```

## 4 真题出处

综合评价（TOPSIS）：2016A（系泊系统）、2021C（供应商综合排序）
