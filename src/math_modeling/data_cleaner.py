"""数据清洗：AI 主动尝试多方案，给出严谨选择理由。

职责：对含缺失值的 DataFrame 同时尝试 mean/median/group_median/knn/zero/drop
六种清洗策略，用"方差变化 + KS 分布保留度 + 填充数"量化对比，自动选出分布
保留最完整的策略，并输出可写进 process_record 与论文"数据处理"小节的选择理由。

用法：
    dc = DataCleaner(df, group_cols=["区域"], target_cols=["销量"])
    best_df = dc.apply_all()[dc.best()]   # 取最优清洗后的数据
    reason = dc.reason()                   # 写入过程记录与论文
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


class DataCleaner:
    """六策略数据清洗：探索所有方案，按分布保留度择优，并给出选择理由。"""

    STRATEGIES = ["mean", "median", "group_median", "knn", "zero", "drop"]

    def __init__(self, df, group_cols=None, target_cols=None):
        self.raw = df.copy()
        self.group_cols = group_cols or []
        self.target_cols = target_cols or [c for c in df.columns if df[c].isna().any()]
        self._cached = {}

    def apply_all(self):
        """返回 {策略名: 清洗后 df}。"""
        for s in self.STRATEGIES:
            self._cached[s] = getattr(self, f"_fill_{s}")()
        return self._cached

    # --- 单策略实现 ---
    def _fill_mean(self):
        """均值填充：缺失列全局均值，最简单，但会压缩方差。"""
        return self.raw.fillna(self.raw[self.target_cols].mean())

    def _fill_median(self):
        """中位数填充：对偏态分布比均值稳健。"""
        return self.raw.fillna(self.raw[self.target_cols].median())

    def _fill_zero(self):
        """零填充：仅当缺失本身有业务含义（如"无记录=0"）时使用。"""
        return self.raw.fillna(0)

    def _fill_group_median(self):
        """分组中位数填充：按 group_cols 分组取中位数，保留组间差异。"""
        out = self.raw.copy()
        if not self.group_cols:
            return out
        g = out.groupby(self.group_cols)[self.target_cols].transform("median")
        return out.fillna(g)

    def _fill_knn(self, k=5):
        """KNN 填充：用最相似样本均值，保留多维结构，代价是依赖其他列。"""
        if not self.target_cols:
            return self.raw.copy()  # 无缺失列：KNN 无可填充目标，原样返回
        num = self.raw[self.target_cols].apply(pd.to_numeric, errors="coerce")
        # 过滤全 NaN 列（KNN 无邻居可参考，交由其它策略；否则 KNNImputer 丢列导致列数不匹配崩溃）
        valid_cols = [c for c in num.columns if num[c].notna().any()]
        if not valid_cols:
            return self.raw.copy()
        from sklearn.impute import KNNImputer
        im = KNNImputer(n_neighbors=min(k, max(2, len(self.raw) - 1)))
        imp = pd.DataFrame(im.fit_transform(num[valid_cols]), columns=valid_cols, index=self.raw.index)
        out = self.raw.copy()
        out[valid_cols] = imp
        return out

    def _fill_drop(self):
        """删行：缺失极少时删除，否则信息损失大。"""
        return self.raw.dropna(subset=self.target_cols).reset_index(drop=True)

    # --- 对比与择优 ---
    def compare(self):
        """对比报告：每策略一行 {strategy, var_change(方差变化), ks_stat(KS 统计量), filled(填充数)}。

        - var_change：填充前后方差的相对变化，越小越好（不扭曲分布）
        - ks_stat：填充后与原始非缺失值的 KS 统计量，越小=分布保留越完整
        - filled：实际填充了多少个缺失值
        """
        if not self.target_cols:
            # 数据无缺失列：六策略等价，全部标记为"无变化/完全保留"
            rows = [{"strategy": s, "var_change": 0.0, "ks_stat": 0.0, "filled": 0}
                    for s in self.STRATEGIES]
            return pd.DataFrame(rows).sort_values("strategy")
        rows = []
        for s, df_ in self.apply_all().items():
            var_change, ks, filled = np.nan, np.nan, 0
            for col in self.target_cols:
                r, c = self.raw[col].dropna(), df_[col].dropna()
                if c.empty or r.empty:
                    continue
                # NaN 安全：第一次迭代 var_change 是 NaN，用 var_change != var_change 判断后取 0
                var_change = max(var_change if var_change == var_change else 0,
                                 abs(c.var() - r.var()) / (r.var() + 1e-12))
                ks = max(ks if ks == ks else 0, stats.ks_2samp(r, c).statistic)
                filled += int(self.raw[col].isna().sum() - df_[col].isna().sum())
            rows.append({"strategy": s, "var_change": var_change, "ks_stat": ks, "filled": filled})
        return pd.DataFrame(rows).sort_values("strategy")

    def best(self):
        """最优策略：剔除 no-op 与删行过多策略后，KS 分布保留度最优先。

        - 无 group_cols 时 group_median 不填充（no-op），剔除；
        - drop 删行占比 >5% 时信息损失大，剔除（与 DATA_CLEANING_GUIDE 一致：drop 仅缺失极低时用）。
        """
        if not self.target_cols:
            return "mean"
        rep = self.compare()
        cand = rep.copy()
        if not self.group_cols:
            cand = cand[cand["strategy"] != "group_median"]
        n = len(self.raw)
        if n > 0:
            drop_rows = n - len(self.raw.dropna(subset=self.target_cols))
            if drop_rows / n > 0.05:
                cand = cand[cand["strategy"] != "drop"]
        if cand.empty:
            cand = rep
        return cand.sort_values(["ks_stat", "var_change"]).iloc[0]["strategy"]

    def reason(self):
        """选择理由（写 process_record / 论文数据处理小节）。"""
        if not self.target_cols:
            return "数据清洗对比：数据无缺失列，无需清洗（六策略等价，保留原数据）。"
        rep = self.compare()
        b = rep.loc[rep["strategy"] == self.best()].iloc[0]
        return (f"数据清洗对比：缺失列{self.target_cols}；最佳[{b['strategy']}]"
                f"（KS={b['ks_stat']:.3f}，方差变化{b['var_change']:.2%}，填充{int(b['filled'])}个）。"
                f"选择理由：KS 最低=分布保留最完整。")
