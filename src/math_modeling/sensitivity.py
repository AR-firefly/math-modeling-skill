"""灵敏度分析：参数扰动对结果影响的量化与排序。

职责：
1. sensitivity_scan —— 单参数扫描（每次只动一个参数，其余取基准值）
2. joint_sensitivity —— 多参数联合扫描（n 点网格全组合，检验交互）
3. strategy_reason —— 输出灵敏度策略结论（写 process_record）

用法：
    scan = sensitivity_scan(solver, {"Q": [0.8, 1.0, 1.2], "δ": [0.9, 1.0, 1.1]})
    reason = strategy_reason(scan)
"""
from itertools import product

import numpy as np
import pandas as pd


def sensitivity_scan(func, param_ranges, base=None):
    """单参数扫描：每个参数各扫其取值列表，其余取基准（默认取值中值）。

    返回 DataFrame：{param, value, output}，共 sum(len(v) for v in ranges) 行。
    """
    base = base or {k: float(np.mean(v)) for k, v in param_ranges.items()}
    rows = []
    for k, vals in param_ranges.items():
        for v in vals:
            kw = dict(base)
            kw[k] = v
            rows.append({"param": k, "value": v, "output": func(**kw)})
    return pd.DataFrame(rows)


def joint_sensitivity(func, param_ranges, n=3):
    """多参数联合扫描：每参数在[min, max] 取 n 点，全组合。

    返回 DataFrame：各参数列 + output 列，共 n ** len(param_ranges) 行。
    """
    grids = {k: np.linspace(min(v), max(v), n) for k, v in param_ranges.items()}
    rows = []
    for combo in product(*grids.values()):
        kw = dict(zip(grids.keys(), combo))
        rows.append({**kw, "output": func(**kw)})
    return pd.DataFrame(rows)


def strategy_reason(scan, joint=None):
    """灵敏度策略结论：按各参数输出变化幅度降序，写 process_record。"""
    span = scan.groupby("param")["output"].agg(lambda s: s.max() - s.min())
    order = span.sort_values(ascending=False)
    txt = "灵敏度策略：先单参数扫描，再按需联合网格。各参数变化幅度：" + str(list(order.items()))
    if joint is not None:
        txt += f"；联合网格 {len(joint)} 组，检验参数交互。"
    return txt
