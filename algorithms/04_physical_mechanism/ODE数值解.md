# ODE数值解

## 1 适用情况

- 数据要求：可写成一阶常微分方程组 dy/dt=f(t,y) 的过程，初值已知
- 场景：化学反应动力学、多物理场耦合、含阻尼/外力/衰减的动力学过程
- 何时用：解析解难求或不存在，需数值积分；刚性不重时 RK4 足够
- 何时不用：极刚性问题（换 scipy.integrate.solve_ivp 带 stiff 方法）

## 2 可联动算法

- 有限差分热传导：同一时间推进思想，空间离散+时间推进
- 运动学动力学：把含阻力的抛体运动写成 ODE 交给本算法
- 最小二乘拟合：由观测数据反推微分方程中的参数（参数估计）

## 3 完整代码模板

```python
"""ODE 数值解：手写四阶 Runge-Kutta（RK4）。"""
import numpy as np


def solve_ode(f, y0, t_span, n=1000):
    """f(t, y): 右端函数；y0: 初值（标量或数组）；t_span: (t0, t1)。
    返回 (t, y)，t 为 (n,) 等距网格，y 为 (n, ...) 逐时刻状态。"""
    t0, t1 = t_span
    t = np.linspace(t0, t1, n)
    dt = t[1] - t[0]
    y = np.empty((n,) + np.shape(y0))
    y[0] = y0
    for i in range(n - 1):
        k1 = f(t[i], y[i])
        k2 = f(t[i] + dt / 2, y[i] + dt / 2 * k1)
        k3 = f(t[i] + dt / 2, y[i] + dt / 2 * k2)
        k4 = f(t[i] + dt, y[i] + dt * k3)
        y[i + 1] = y[i] + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    return t, y


if __name__ == "__main__":
    # demo：解 y' = -y, y(0)=1，解析解 y=e^(-t)，t=1 处为 e^-1
    f = lambda t, y: -y
    t, y = solve_ode(f, 1.0, (0, 1), n=1000)
    assert abs(y[-1] - np.exp(-1)) < 1e-3, f"终值误差 {abs(y[-1]-np.exp(-1))}"
    # 单调衰减校验
    assert (np.diff(y) <= 0).all()
    print(f"y(1)≈{y[-1]:.6f}（解析 e^-1={np.exp(-1):.6f}），误差 {abs(y[-1]-np.exp(-1)):.2e}")
```

## 4 真题出处

- **ODE 降阶 + 龙格-库塔求解（保底层核心真题）**：2022A（波浪能降阶 RK4）、2018A（高温作业）、2019A（高压油管）、2020A（回焊炉温）
- 微分/差分方程建立：2016A（系泊）、2024A（板凳龙运动学）、2021A（FAST 反射面）
- 并入：2021B 化学反应动力学、2022A 多物理场耦合（垂荡+纵摇）
- 见需求文档 v5.0 第三节真题覆盖表"微分方程数值解"与"微分/差分方程建立"行
