# AHP（层次分析法）

## 1 适用情况

- 数据要求：指标两两比较判断矩阵（n×n，a_ij 表示指标 i 对 j 的重要程度），指标数 ≥ 2
- 场景：多准则决策定主观权重——拆解目标、指标、方案三层递阶结构
- 何时用：有专家/决策者主观偏好、缺少客观数据时定权重
- 何时不用：指标间可客观度量时优先用熵权法等客观法

## 2 可联动算法

- 熵权法/CRITIC 定客观权重，组合评价法融合主观+客观（`combine_weights`）
- 权重向量喂给 TOPSIS / 模糊综合评价做加权排序

## 3 完整代码模板

```python
"""AHP：层次分析法主观权重，含一致性检验 CR<0.1。"""
import numpy as np


def ahp_weight(pairwise):
    """pairwise: n×n 判断矩阵（a_ij 表示指标 i 相对 j 的重要程度）。
    返回：(权重向量 w, 一致性比例 CR)。CR<0.1 认为判断矩阵可接受。"""
    A = np.asarray(pairwise, float)
    n = A.shape[0]
    # 特征向量法：最大特征值对应特征向量归一化即为权重
    eigval, eigvec = np.linalg.eig(A)
    w = np.abs(eigvec[:, int(np.argmax(eigval.real))].real)
    w = w / w.sum()
    # 一致性检验 CI = (lam-n)/(n-1)，查平均随机一致性指标 RI
    lam = eigval.real.max()
    CI = (lam - n) / (n - 1) if n > 1 else 0.0
    RI = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}
    CR = 0.0 if n <= 2 else CI / RI.get(n, 1.32)  # n≤2 恒一致（RI=0，避免 0/0=NaN 误判）
    return w, CR


if __name__ == "__main__":
    # demo：3 指标（成本、质量、交期）的两两判断矩阵
    A = np.array([[1, 1 / 3, 2], [3, 1, 5], [1 / 2, 1 / 5, 1]])
    w, CR = ahp_weight(A)
    assert CR < 0.1                 # 一致性通过
    assert np.isclose(w.sum(), 1) and w.min() > 0
    print("AHP 权重:", np.round(w, 3), "| CR =", round(CR, 4))
```

## 4 真题出处

综合评价（AHP 定权，CR<0.1 校验）：2016A（系泊系统）、2021C（供应商综合评价）；可联动熵权/组合评价法
