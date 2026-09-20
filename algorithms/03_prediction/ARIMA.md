# ARIMA

## 1 适用情况

- 数据要求：样本 ≥ 30 的单变量时间序列，先做平稳化（差分/对数）
- 场景：基于自身历史相关性的中期预测，不考虑外生变量
- 何时用：序列有一定自相关性、样本量足、需定量外推
- 何时不用：样本过小（改用灰色预测GM11.md）、有强外生驱动（改用回归）、强季节（配合差分季节项）

## 2 可联动算法

- 时间序列分解：先分解出趋势/季节再对残差建 ARIMA
- 指数平滑：同为平滑预测，样本趋势稳定时更快，两者对比择优
- 平稳性检验（ADF）：确定差分阶数 d，决定是否用 ARIMA 或 ARMA

## 3 完整代码模板

```python
"""ARIMA：平稳化后的自回归滑动平均预测。"""
import numpy as np
from statsmodels.tsa.arima.model import ARIMA


def arima_fit(series, order=(1, 1, 1)):
    """series: 一维时间序列；order: (p, d, q)。返回拟合对象与未来 10 期预测。"""
    series = np.asarray(series, float)
    model = ARIMA(series, order=order)
    fit = model.fit()                       # 极大似然估计参数
    pred = fit.forecast(10)                 # 预测未来 10 期
    return fit, np.asarray(pred)


if __name__ == "__main__":
    rng = np.random.RandomState(42)
    x = np.zeros(60)
    for i in range(1, 60):                  # 合成 AR(1) 序列
        x[i] = 0.7 * x[i - 1] + rng.randn()
    fit, pred = arima_fit(x, order=(1, 1, 1))
    assert len(pred) == 10, "预测长度应为 10"
    assert np.all(np.isfinite(pred)), "预测值必须有限"
    print("ARIMA 预测前 3 期:", np.round(pred[:3], 3))
```

## 4 真题出处

- 保底层：时间序列预测 2016C、2023C、2024C（蔬菜/种植/补货类中期预测）
- 见需求文档 v5.0 第三节真题覆盖表"预测"行
