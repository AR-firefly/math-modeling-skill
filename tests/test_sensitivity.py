"""灵敏度分析模块测试：扫描行数、联合网格大小、reason 含排序。"""
import numpy as np
from math_modeling.sensitivity import sensitivity_scan, joint_sensitivity, strategy_reason


def f(a=1, b=1):
    return a * b


def test_scan_rows():
    s = sensitivity_scan(f, {"a": [0.5, 1.0, 2.0], "b": [1.0, 2.0]})
    assert len(s) == 3 + 2  # 每个参数各扫其取值数


def test_joint_grid_size():
    j = joint_sensitivity(f, {"a": [0, 1], "b": [0, 1]}, n=3)
    assert len(j) == 3 * 3


def test_reason_sorts():
    r = strategy_reason(sensitivity_scan(f, {"a": [1, 10], "b": [1, 1.1]}))
    assert "排序" in r or "幅度" in r
