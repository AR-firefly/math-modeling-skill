"""数据清洗模块测试：策略全集、对比报告四列、best 合法、reason 含理由。"""
import numpy as np
import pandas as pd
from math_modeling.data_cleaner import DataCleaner


def make_df():
    rng = np.random.RandomState(0)
    df = pd.DataFrame({"x": rng.randn(50), "y": rng.randn(50)})
    df.loc[::7, "x"] = np.nan  # 制造缺失
    return df


def test_apply_all_returns_all_strategies():
    d = DataCleaner(make_df())
    assert set(d.apply_all()) == set(DataCleaner.STRATEGIES)


def test_compare_columns():
    rep = DataCleaner(make_df()).compare()
    assert {"strategy", "var_change", "ks_stat", "filled"} <= set(rep.columns)


def test_best_is_valid():
    b = DataCleaner(make_df()).best()
    assert b in DataCleaner.STRATEGIES


def test_reason_mentions_rationale():
    assert "选择理由" in DataCleaner(make_df()).reason()


def test_best_not_noop_or_heavy_drop():
    # 回归：无 group_cols 时 group_median 是 no-op 不选；缺失 >5% 时 drop 删行多不选
    rng = np.random.RandomState(0)
    df = pd.DataFrame({"x": rng.randn(50), "y": rng.randn(50), "z": rng.randn(50)})
    df.loc[::3, ["x", "y", "z"]] = np.nan  # ~33% 缺失
    b = DataCleaner(df).best()
    assert b != "group_median", "无分组时 group_median no-op，不应被选"
    assert b != "drop", "33% 缺失时 drop 删行损失大，不应被选"
    assert b in ("mean", "median", "knn", "zero")


def test_compare_no_crash_on_all_nan_column():
    # 回归：KNN 遇全 NaN 列不再崩溃（过滤全 NaN 列后由其它策略处理）
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [np.nan, np.nan, np.nan]})
    rep = DataCleaner(df, target_cols=["a", "b"]).compare()
    assert {"strategy", "var_change", "ks_stat", "filled"} <= set(rep.columns)
