"""机理类示例：RK4 解阻尼振动 ODE，五样检验全做。"""
import os
import io
import sys
import json
import numpy as np


def _force_utf8():
    """Windows 控制台默认 GBK 编码，打印 ✅/中文 会 UnicodeEncodeError，强制 UTF-8 输出。"""
    try:
        enc = getattr(sys.stdout, "encoding", None)
        if enc and enc.lower().replace("-", "") not in ("utf8", "cp65001"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8()


# =====================================================================
# RK4 求解器（复制自 algorithms/04_physical_mechanism/ODE数值解.md）
# =====================================================================
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


def euler_ode(f, y0, t_span, n=1000):
    """手写前向欧拉，仅用于对比验证（对照 RK4）。"""
    t0, t1 = t_span
    t = np.linspace(t0, t1, n)
    dt = t[1] - t[0]
    y = np.empty((n,) + np.shape(y0))
    y[0] = y0
    for i in range(n - 1):
        y[i + 1] = y[i] + dt * f(t[i], y[i])
    return t, y


# =====================================================================
# 模型：阻尼振动  dx/dt=v, dv/dt=-k*x-c*v
# =====================================================================
K, C = 10.0, 0.5
X0, V0 = 1.0, 0.0
T0, T1 = 0.0, 10.0

# 欠阻尼解析解 x(t)=A*exp(-beta*t)*cos(omega_d*t+phi)
BETA = C / 2.0
OMEGA0 = np.sqrt(K)
OMEGA_D = np.sqrt(OMEGA0 ** 2 - BETA ** 2)
A_AMP = np.sqrt(1.0 + (BETA / OMEGA_D) ** 2)
PHI = -np.arctan(BETA / OMEGA_D)


def make_rhs(c):
    def rhs(t, y):
        x, v = y
        return np.array([v, -K * x - c * v])
    return rhs


rhs = make_rhs(C)  # 默认 c=C=0.5 的右端函数


def analytic(t):
    """欠阻尼解析解，返回 (x, v)。x(t)=A*exp(-beta*t)*cos(omega_d*t+phi)"""
    x = A_AMP * np.exp(-BETA * t) * np.cos(OMEGA_D * t + PHI)
    v = -BETA * x - A_AMP * np.exp(-BETA * t) * OMEGA_D * np.sin(OMEGA_D * t + PHI)
    return x, v


def run_rk4(dt, c=C):
    n = int(round((T1 - T0) / dt)) + 1
    t, y = solve_ode(make_rhs(c), np.array([X0, V0]), (T0, T1), n)
    return t, y[:, 0], y[:, 1]


def terminal_amplitude(t, x, c):
    """终态振幅：最后一个振荡周期（窗口长 1.5*T_d）内 |x| 的峰值。"""
    T_d = 2.0 * np.pi / np.sqrt(OMEGA0 ** 2 - (c / 2.0) ** 2)
    mask = t >= t[-1] - 1.5 * T_d
    return float(np.max(np.abs(x[mask])))


def main():
    RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(RESULT_DIR, exist_ok=True)
    out = {
        "model": "阻尼振动 ODE: dx/dt=v, dv/dt=-k*x-c*v",
        "params": {"k": K, "c": C, "x0": X0, "v0": V0, "t_span": [T0, T1], "dt_default": 0.01},
    }

    print(f"阻尼振动 ODE: k={K}, c={C}, x0={X0}, v0={V0}, t∈[{T0},{T1}]")
    print(f"欠阻尼参数: omega0={OMEGA0:.4f}, beta={BETA:.4f}, omega_d={OMEGA_D:.4f}, "
          f"A={A_AMP:.4f}, phi={PHI:.4f}")

    # ---------------- 主求解 ----------------
    t, x, v = run_rk4(0.01)
    max_amp = float(np.max(np.abs(x)))
    t_amp = terminal_amplitude(t, x, C)
    print(f"\nRK4(dt=0.01): 终态位置 x(10)={x[-1]:.8f}, 终态速度 v(10)={v[-1]:.8f}")
    print(f"最大振幅 max|x|={max_amp:.6f}, 终态振幅(末周期峰值)={t_amp:.6f}")
    out["solution"] = {
        "x_end": float(x[-1]), "v_end": float(v[-1]),
        "max_amplitude": max_amp, "terminal_amplitude": t_amp,
    }

    # ---------------- 检验1 网格无关 ----------------
    t_c, x_c, _ = run_rk4(0.01)
    t_f, x_f, _ = run_rk4(0.005)
    diff = abs(x_f[-1] - x_c[-1])
    rel = diff / max(abs(x_c[-1]), 1e-9) * 100.0
    assert rel < 0.1, f"网格无关失败: 相对差 {rel:.4f}% >= 0.1%"
    print(f"✅ 网格无关 OK：dt=0.01 与 dt=0.005 终态位置差 {diff:.3e}"
          f"（相对 {rel:.5f}% < 0.1%）")
    out["checks"] = {
        "grid_independence": {
            "dt1": 0.01, "dt2": 0.005,
            "x_end_coarse": float(x_c[-1]), "x_end_fine": float(x_f[-1]),
            "abs_diff": diff, "rel_diff_pct": rel, "pass": True,
        }
    }

    # ---------------- 检验2 数值收敛 ----------------
    dts = [0.05, 0.02, 0.01]
    ends = []
    for d in dts:
        _, xx, _ = run_rk4(d)
        ends.append(float(xx[-1]))
    diffs = [abs(ends[i] - ends[i + 1]) for i in range(len(ends) - 1)]
    assert diffs[1] < diffs[0], f"数值收敛失败: 相邻档差 {diffs} 未递减"
    print(f"✅ 数值收敛 OK：dt 取 {dts} → 终态位置 {[f'{e:.8f}' for e in ends]}")
    print(f"   相邻档差 {[f'{d:.3e}' for d in diffs]}，逐档递减")
    out["checks"]["convergence"] = {
        "dts": dts, "x_end": ends,
        "diff_adjacent": diffs, "monotone_decreasing": True, "pass": True,
    }

    # ---------------- 检验3 灵敏度（阻尼系数 c） ----------------
    c_scan = [0.3, 0.5, 0.7]
    amps = []
    for cc in c_scan:
        tt, xx, _ = run_rk4(0.01, c=cc)
        amps.append(terminal_amplitude(tt, xx, cc))
    # 阻尼越大，终态振幅越小（按振幅升序 = 阻尼降序）
    assert amps[0] > amps[1] > amps[2], f"灵敏度排序异常: {amps}"
    variation = (max(amps) - min(amps)) / np.mean(amps) * 100.0
    order_str = " > ".join(f"c={c}" for c, a in
                           sorted(zip(c_scan, amps), key=lambda p: -p[1]))
    print(f"✅ 灵敏度 OK：c=±40% 扫描 ({c_scan}) → 终态振幅 "
          f"{[f'{a:.6f}' for a in amps]}")
    print(f"   排序 {order_str}（阻尼越大终态振幅越小），变化幅度 {variation:.1f}%")
    out["checks"]["sensitivity"] = {
        "c_scan": c_scan, "terminal_amplitude": amps,
        "ordering": "阻尼越大终态振幅越小", "variation_pct": variation, "pass": True,
    }

    # ---------------- 检验4 误差分析（vs 解析解） ----------------
    t, x, v = run_rk4(0.01)
    xa, va = analytic(t)
    err_x = float(np.max(np.abs(x - xa)))
    err_v = float(np.max(np.abs(v - va)))
    err_max = max(err_x, err_v)
    assert err_max < 1e-3, f"误差分析失败: 最大误差 {err_max:.3e} >= 1e-3"
    print(f"✅ 误差分析 OK：RK4(dt=0.01) vs 解析解 最大误差 "
          f"x={err_x:.3e}, v={err_v:.3e}（< 1e-3）")
    out["checks"]["error_analysis"] = {
        "dt": 0.01, "max_err_x": err_x, "max_err_v": err_v,
        "max_err": err_max, "threshold": 1e-3, "pass": True,
    }

    # ---------------- 检验5 对比验证（RK4 vs 欧拉） ----------------
    n = int(round((T1 - T0) / 0.01)) + 1
    _, y_e = euler_ode(rhs, np.array([X0, V0]), (T0, T1), n)
    err_e_x = float(np.max(np.abs(y_e[:, 0] - xa)))
    err_e_v = float(np.max(np.abs(y_e[:, 1] - va)))
    err_e = max(err_e_x, err_e_v)
    ratio = err_e / err_max
    assert ratio > 10.0, f"对比验证失败: RK4 误差仅比欧拉小 {ratio:.1f} 倍"
    print(f"✅ 对比验证 OK：同 dt=0.01，欧拉最大误差 {err_e:.3e}，"
          f"RK4 最大误差 {err_max:.3e}，RK4 小 {ratio:.1f} 倍（>10 倍）")
    out["checks"]["comparison"] = {
        "dt": 0.01, "euler_max_err": err_e, "rk4_max_err": err_max,
        "improve_ratio": ratio, "pass": True,
    }

    # ---------------- 落盘 ----------------
    path = os.path.join(RESULT_DIR, "results_ODE.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[save] {path}")
    print("全部五样检验通过 ✓")


if __name__ == "__main__":
    main()
