# Radon变换

## 1 适用情况

- 数据要求：二维断层/图像（方形数组）+ 一组投影角度
- 场景：CT 断层扫描重建、图像反投影、由投影恢复截面密度
- 何时用：多角度平行束投影已知、需要重建二维截面
- 何时不用：只需边缘/特征提取（走常规图像处理）；角度太少（伪影严重）

## 2 可联动算法

- 数值积分：投影即沿线的线积分，可用积分思想解释
- 坐标变换：旋转图像对应坐标旋转变换
- 滤波反投影（加分项）：重建前对投影加斜坡滤波，伪影更少

## 3 完整代码模板

```python
"""Radon 变换（平行束投影）与简单反投影重建。"""
import numpy as np
from scipy.ndimage import rotate


def radon_transform(img, angles):
    """img: (n,n) 灰度图；angles: 角度数组(度)。
    返回投影矩阵 P，形状 (len(angles), n)，每行=旋转该角后沿轴求和。"""
    img = np.asarray(img, float)
    n = img.shape[0]
    P = np.zeros((len(angles), n))
    for i, a in enumerate(angles):
        rot = rotate(img, -a, reshape=False, order=1, mode="constant")
        P[i] = rot.sum(axis=1)          # 沿 x 方向投影，得沿 y 的剖面
    return P


def iradon_simple(P, angles):
    """简单反投影：把每条投影沿原方向抹回，叠加后归一化重建。"""
    n = P.shape[1]
    reco = np.zeros((n, n))
    for i, a in enumerate(angles):
        back = np.broadcast_to(P[i], (n, n))
        reco += rotate(back, a, reshape=False, order=1, mode="constant")
    return reco / len(angles)


if __name__ == "__main__":
    # demo：32×32 中心圆盘，180° 内均匀取 60 个角度投影并重建
    n = 32
    yy, xx = np.mgrid[:n, :n]
    img = (np.hypot(xx - n / 2, yy - n / 2) < 6).astype(float)   # 半径6圆盘
    angles = np.arange(0, 180, 3)
    P = radon_transform(img, angles)
    assert P.shape == (len(angles), n) and P.min() >= -1e-9      # 投影形状正确
    M = img.sum()
    assert abs(P.sum() - M * len(angles)) < 0.05 * M * len(angles)  # 质量守恒
    reco = iradon_simple(P, angles)
    assert reco.shape == (n, n) and np.isfinite(reco).all()      # 重建有限
    corr = np.corrcoef(img.ravel(), reco.ravel())[0, 1]
    assert corr > 0.3, f"重建相关 {corr:.3f} 过低"
    print(f"投影形状{P.shape}，重建误差RMSE={np.sqrt(np.mean((reco-img)**2)):.3f}，相关={corr:.3f}")
```

## 4 真题出处

- 并入：2017A CT 图像重建（并入）
- 加分项：重建前做滤波反投影（斜坡滤波）可显著降伪影
