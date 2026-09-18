# RFM 客户价值分析

## 1 适用情况

- 数据要求：交易明细表，含 客户ID、交易日期、交易金额 三列
- 场景：客户价值分层——按 最近购买（Recency）/ 购买频率（Frequency）/ 累计金额（Monetary）打分
- 何时用：有客户交易流水，需区分高价值/中/低价值客户群体
- 何时不用：无时间与金额字段、或分析对象非"客户行为"时

## 2 可联动算法

- 分层结果作为标签进聚类/判别分析（对应 02 类聚类.md、判别分析.md）
- 各层客户画像结合相关性分析找影响因素

## 3 完整代码模板

```python
"""RFM 客户价值分析：最近/频率/金额三维打分并分层。"""
import numpy as np
import pandas as pd


def rfm_score(df):
    """df: 交易记录表，需含列 客户ID/日期/金额（日期为 datetime）。
    返回：客户级 RFM 表，含 综合得分 rfm 与 分层列 level（高/中/低）。"""
    g = df.groupby("客户ID").agg(
        最近天数=("日期", lambda s: (df["日期"].max() - s.max()).days),
        频率=("日期", "count"),
        金额=("金额", "sum"))
    # 百分位打分：最近天数小更好（反向），频率/金额大更好
    r = g["最近天数"].rank(pct=True, ascending=False)
    f = g["频率"].rank(pct=True)
    m = g["金额"].rank(pct=True)
    g["rfm"] = (r + f + m) / 3 * 100                 # 综合得分 0-100
    g["level"] = pd.cut(g["rfm"], [0, 33, 66, 101], labels=["低", "中", "高"])
    return g


if __name__ == "__main__":
    # demo：5 位客户近 60 天的随机交易流水
    rng = np.random.RandomState(42)
    days = pd.date_range("2026-01-01", periods=60, freq="D")
    rows = []
    for cid in range(5):                              # 每位客户随机 3-6 笔
        for _ in range(int(rng.randint(3, 7))):
            rows.append([cid, rng.choice(days), float(rng.randint(50, 500))])
    df = pd.DataFrame(rows, columns=["客户ID", "日期", "金额"])
    rfm = rfm_score(df)
    assert "level" in rfm.columns and "rfm" in rfm.columns   # 分层列存在
    assert set(rfm["level"].unique()) <= {"低", "中", "高"}
    print(rfm[["频率", "金额", "rfm", "level"]])
```

## 4 真题出处

RFM/数据挖掘：2018C（会员画像）

