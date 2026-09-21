# FFT周期提取

## 1 适用情况

- 数据要求：等间隔采样的时间序列（带固定采样间隔 dt）
- 场景：信号主频/主周期提取、频谱分析、周期性数据（振动/波浪/光谱）
- 何时用：数据大致周期、采样点数足够（频率分辨率 Δf=1/T）
- 何时不用：数据严重非平稳（用短时 FFT）；只想要趋势（去周期再看）

## 2 可联动算法

- 光学干涉太阳几何：太阳光谱/干涉条纹做 FFT 频谱提取（联动）
- 最小二乘拟合：FFT 给出初频，再用非线性拟合精调幅相
- 数值积分：频域能量与总功率校验（Parseval）

## 3 完整代码模板

```python
"""FFT 周期提取：求序列主频与主周期。"""
import numpy as np


def fft_period(x, dt):
    """x: 等间隔采样序列；dt: 采样间隔(秒)。
    返回 (主频 Hz, 主周期 s)，跳过直流分量。"""
    x = np.asarray(x, float)
    N = len(x)
    freq = np.fft.rfftfreq(N, dt)              # 单边频率轴
    mag = np.abs(np.fft.rfft(x - x.mean()))    # 去直流后幅值谱
    k = np.argmax(mag[1:]) + 1                 # 跳过直流找主峰
    f0 = freq[k]
    return f0, 1.0 / f0


if __name__ == "__main__":
    # demo：50Hz 正弦 + 噪声，应提取出 50Hz
    rng = np.random.RandomState(42)
    dt = 0.001                                  # 采样率 1000Hz
    t = np.arange(0, 1, dt)
    x = np.sin(2 * np.pi * 50 * t) + 0.2 * rng.randn(len(t))
    f0, T0 = fft_period(x, dt)
    assert abs(f0 - 50) < 1.0, f"主频 {f0:.2f} 偏离 50Hz"
    assert abs(1.0 / T0 - 50) < 1.0             # 周期倒数即频率
    print(f"主频={f0:.2f}Hz，主周期={T0:.4f}s（真值 50Hz / 0.02s）")
```

## 4 真题出处

- 并入：2025B 太阳光谱/频率分析（含 FFT 频谱提取联动）
- 保底：含振动、波浪、周期性数据提取主周期的赛题（并入）
- 见 `algorithms/真题实证表.md` §2.1 保底"FFT/频谱周期提取"行
