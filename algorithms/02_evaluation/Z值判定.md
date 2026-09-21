# Z 值判定（Z 检验）

## 1 适用情况

- 数据要求：一组数值样本，总体标准差已知或样本量足够大（大样本近似）
- 场景：单/双样本均值假设检验——判断样本均值是否显著异于给定值
- 何时用：总体方差已知、样本量大（n≥30）时用 z 检验
- 何时不用：总体方差未知且样本小时用 t 检验（scipy.stats.ttest_1samp）

## 2 可联动算法

- 与 t 检验/方差分析/卡方检验构成统计显著性工具箱（对应 02 类方差分析.md、卡方检验.md）
- 检验结论支撑灵敏度分析与误差分析

## 3 完整代码模板

```python
"""Z 检验：总体方差已知（或大样本近似）时的均值假设检验。"""
import numpy as np
from scipy import stats


def z_test(x, mu, sigma):
    """x: (n,) 样本；mu: 原假设均值；sigma: 总体标准差（已知）。
    返回：(z 统计量, 双侧 p 值)。"""
    x = np.asarray(x, float)
    n = len(x)
    z = (x.mean() - mu) / (sigma / np.sqrt(n))      # z 统计量
    p = 2 * (1 - stats.norm.cdf(abs(z)))            # 双侧 p 值
    return z, p


if __name__ == "__main__":
    # demo：单样本，H0: 均值=100，实际总体均值 103（差异足够显著）
    rng = np.random.RandomState(42)
    x = rng.normal(103, 4, 50)
    z, p = z_test(x, mu=100, sigma=4)
    assert 0 <= p <= 1
    assert z > 0 and p < 0.05                        # 显著高于 100，拒绝 H0
    print("z =", round(z, 3), "| p =", round(p, 4))
```

## 4 真题出处

Z 值统计判定：2025C（NIPT 时点与胎儿判定）
- 见 `algorithms/真题实证表.md` §2.1 保底"Z 值统计判定"行

