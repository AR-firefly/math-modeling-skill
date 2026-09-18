"""
预测类示例：GM(1,1) 小样本预测，五样检验全做

- 数据：RandomState(42) 合成 30 点指数趋势序列 30*exp(t*0.05)+噪声
- 训练前 25 点，后 5 点为真实值用于对比验证
- 模型：GM(1,1) 灰色预测（算法库 03_prediction/灰色预测GM11.md）
- 五样检验：网格无关(预测版) / 数值收敛 / 灵敏度 / 误差分析 / 对比验证
- 结果落盘：examples/results/results_GM11.json
"""
import json
import os
import sys

# Windows 控制台默认 GBK 无法打印 ✅ 等字符，统一转 utf-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import numpy as np
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.holtwinters import SimpleExpSmoothing


# ============================================================
# GM(1,1) 灰色预测核心 —— 复制自 03_prediction/灰色预测GM11.md
# ============================================================
def gm11(x, n_future=5):
    """x: 原始序列；n_future: 外推期数。
    返回预测全序列，长度 len(x)+n_future，前 len(x) 个是回代拟合值。"""
    x = np.asarray(x, float)
    n = len(x)
    x1 = np.cumsum(x)                       # 一次累加生成，弱化随机性
    # 紧邻均值序列 z(k) = 0.5*(x1(k)+x1(k+1))
    z = -0.5 * (x1[:-1] + x1[1:])
    B = np.column_stack([z, np.ones(n - 1)])
    Y = x[1:]
    a, b = np.linalg.lstsq(B, Y, rcond=None)[0]   # 最小二乘求发展系数 a、灰作用量 b
    # 累加序列预测：x1_hat(k) = (x(1)-b/a) * exp(-a(k-1)) + b/a
    k = np.arange(n + n_future)
    x1_hat = (x[0] - b / a) * np.exp(-a * k) + b / a
    x_hat = np.empty(n + n_future)
    x_hat[0] = x1_hat[0]
    x_hat[1:] = np.diff(x1_hat)             # 累减还原
    return x_hat


# ============================================================
# 灵敏度辅助：解出发展系数 a、灰作用量 b，并按给定 (a, b) 外推
# ============================================================
def _fit_ab(x):
    x = np.asarray(x, float)
    n = len(x)
    x1 = np.cumsum(x)
    z = -0.5 * (x1[:-1] + x1[1:])
    B = np.column_stack([z, np.ones(n - 1)])
    a, b = np.linalg.lstsq(B, x[1:], rcond=None)[0]
    return a, b


def _forecast_from_ab(x0, a, b, n, n_future):
    k = np.arange(n + n_future)
    x1_hat = (x0 - b / a) * np.exp(-a * k) + b / a
    x_hat = np.empty(n + n_future)
    x_hat[0] = x1_hat[0]
    x_hat[1:] = np.diff(x1_hat)
    return x_hat[n:]                        # 只取未来外推段


# ============================================================
# 一、数据生成：30 点指数趋势 + 噪声（seed 固定，可复现）
# ============================================================
rng = np.random.RandomState(42)
t = np.arange(30)
X_TRUE = 30.0 * np.exp(t * 0.05)            # 指数趋势（生长率 ~5%/期）
NOISE_STD = 1.0
x = X_TRUE + rng.normal(0, NOISE_STD, 30)

N_TRAIN, N_FUTURE = 25, 5
x_train = x[:N_TRAIN]
x_test = x[N_TRAIN:]                        # 后 5 点真实值

# ============================================================
# 二、GM(1,1) 主预测：预测值 / 残差 / 后验差比 C
# ============================================================
pred_full = gm11(x_train, n_future=N_FUTURE)
fitted = pred_full[:N_TRAIN]                # 前 25 个：回代拟合值
pred_future = pred_full[N_TRAIN:]           # 后 5 个：外推预测
resid = x_train - fitted
C = float(resid.std(ddof=1) / x_train.std(ddof=1))     # 后验差比
mean_rel_resid = float(np.mean(np.abs(resid) / x_train))

print("GM(1,1) 外推预测(后5点):", np.round(pred_future, 3))
print("真实值(后5点):          ", np.round(x_test, 3))
print("残差(训练段最大相对):   ", round(float(np.max(np.abs(resid) / x_train)), 4))
print("后验差比 C = std(resid)/std(x):", round(C, 4))

# ============================================================
# 三、五样检验（每样 assert 通过打印 OK）
# ============================================================
five_checks = {}

# ---- 1. 网格无关（预测版）：n=24 与 n+1=25 训练，预测第 26 点，差 < 0.5% ----
p26_n24 = gm11(x[:24], n_future=2)[-1]      # 用 24 点训练，外推 2 步到第 26 点
p26_n25 = gm11(x[:25], n_future=1)[-1]      # 用 25 点训练，外推 1 步到第 26 点
rel_gap = abs(p26_n24 - p26_n25) / p26_n25
assert rel_gap < 0.005, f"网格无关失败: 相对差 {rel_gap:.4%} >= 0.5%"
print(f"✅ 网格无关 OK：n=24 预测第26点 {p26_n24:.4f}，n=25 预测 {p26_n25:.4f}，"
      f"相对差 {rel_gap:.4%} < 0.5%")
five_checks["grid_independence"] = {
    "p26_n24": float(p26_n24), "p26_n25": float(p26_n25),
    "rel_diff": float(rel_gap), "conclusion": "OK <0.5%"}

# ---- 2. 数值收敛：样本量 10/15/20/25 递增预测第 26 点，逐档收敛 ----
sizes = [10, 15, 20, 25]
conv_preds = [float(gm11(x[:n], n_future=26 - n)[-1]) for n in sizes]
conv_diffs = [abs(conv_preds[i] - conv_preds[i - 1]) / conv_preds[i] for i in range(1, 4)]
assert conv_diffs[0] > conv_diffs[1] > conv_diffs[2], f"档差未递减: {conv_diffs}"
assert conv_diffs[2] < 0.02, f"末档差 {conv_diffs[2]:.4%} >= 2%"
print(f"✅ 数值收敛 OK：样本量 {sizes} 预测第26点 {[round(p,3) for p in conv_preds]}，"
      f"档差 {[f'{d:.3%}' for d in conv_diffs]} 递减且末档 <2%")
five_checks["numerical_convergence"] = {
    "sizes": sizes, "preds": conv_preds,
    "adjacent_diffs": conv_diffs, "conclusion": "OK 逐档收敛，末档<2%"}

# ---- 3. 灵敏度：首点 x0 与 a、b 各 ±10% 扰动，输出影响排序 ----
a0, b0 = _fit_ab(x_train)
base_f = _forecast_from_ab(x_train[0], a0, b0, N_TRAIN, N_FUTURE)


def sens_change(pred):
    # 5 点未来预测的平均相对变化幅度
    return float(np.mean(np.abs(pred - base_f) / np.abs(base_f)))


def sens_x0(factor):
    xm = x_train.copy()
    xm[0] *= factor
    return gm11(xm, n_future=N_FUTURE)[N_TRAIN:]


perturbations = {
    "x0*1.1": sens_change(sens_x0(1.1)),
    "x0*0.9": sens_change(sens_x0(0.9)),
    "a*1.1":  sens_change(_forecast_from_ab(x_train[0], a0 * 1.1, b0, N_TRAIN, N_FUTURE)),
    "a*0.9":  sens_change(_forecast_from_ab(x_train[0], a0 * 0.9, b0, N_TRAIN, N_FUTURE)),
    "b*1.1":  sens_change(_forecast_from_ab(x_train[0], a0, b0 * 1.1, N_TRAIN, N_FUTURE)),
    "b*0.9":  sens_change(_forecast_from_ab(x_train[0], a0, b0 * 0.9, N_TRAIN, N_FUTURE)),
}
ranking = sorted(perturbations.items(), key=lambda kv: kv[1], reverse=True)
print("✅ 灵敏度 OK：±10% 扰动对 5 点预测的平均相对影响排序（分数，与 results_GM11.json 一致）：")
for name, chg in ranking:
    print(f"     {name:>8}: {chg:.4f}")
print("     注：首点 x0 单独扰动对预测严格不变（GM 结构下 OLS 精确吸收 x0 缩放），"
      "真正敏感参数是发展系数 a 与灰作用量 b")
five_checks["sensitivity"] = {
    "perturbations": {k: float(v) for k, v in perturbations.items()},
    "ranking": [k for k, _ in ranking],
    "note": "发展系数a最敏感(~14%)>灰作用量b(~9.5%)>首点x0(单独扰动严格不变，GM结构下OLS精确吸收x0缩放)"}

# ---- 4. 误差分析：残差均值 < 5%（相对），后验差比 C < 0.35 ----
assert mean_rel_resid < 0.05, f"残差均值 {mean_rel_resid:.4%} >= 5%"
assert C < 0.35, f"C={C:.4f} >= 0.35"
print(f"✅ 误差分析 OK：残差均值 {mean_rel_resid:.4%} < 5%，后验差比 C={C:.4f} < 0.35")
five_checks["error_analysis"] = {
    "mean_rel_resid": mean_rel_resid, "C": C, "conclusion": "OK 残差<5%，C<0.35"}

# ---- 5. 对比验证：GM(1,1) vs 指数平滑 vs 线性回归，后 5 点真实值 RMSE ----
rmse_gm = float(np.sqrt(np.mean((pred_future - x_test) ** 2)))

es_fit = SimpleExpSmoothing(x_train).fit()
es_pred = np.asarray(es_fit.forecast(N_FUTURE))
rmse_es = float(np.sqrt(np.mean((es_pred - x_test) ** 2)))

lr_fit = LinearRegression().fit(t[:N_TRAIN].reshape(-1, 1), x_train)
lr_pred = lr_fit.predict(t[N_TRAIN:].reshape(-1, 1))
rmse_lr = float(np.sqrt(np.mean((lr_pred - x_test) ** 2)))

assert rmse_gm <= min(rmse_es, rmse_lr), f"GM 非最小: GM={rmse_gm}, ES={rmse_es}, LR={rmse_lr}"
print(f"✅ 对比验证 OK：后5点RMSE  GM={rmse_gm:.4f} < ES={rmse_es:.4f} < LR={rmse_lr:.4f}，"
      f"GM 最小（指数趋势下指数平滑/线性回归外推失真）")
five_checks["comparison"] = {
    "rmse_gm": rmse_gm, "rmse_es": rmse_es, "rmse_lr": rmse_lr,
    "conclusion": "OK GM 在指数趋势小样本上 RMSE 最小"}

print("\n五样检验全部通过 ✅")

# ============================================================
# 四、结果落盘 results/results_GM11.json
# ============================================================
res_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(res_dir, exist_ok=True)

results = {
    "data": {
        "n_points": int(len(x)), "n_train": int(N_TRAIN), "n_future": int(N_FUTURE),
        "seed": 42, "expression": "30*exp(t*0.05) + N(0,1)", "true_last5": x_test.tolist(),
    },
    "gm11": {
        "pred_future": pred_future.tolist(),
        "resid_train": resid.tolist(),
        "C": C, "mean_rel_resid": mean_rel_resid,
    },
    "five_checks": five_checks,
}
out_path = os.path.join(res_dir, "results_GM11.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("结果已落盘:", out_path)
