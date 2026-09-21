# SVM（支持向量机）

## 1 适用情况

- 数据要求：有类别标签的 m 样本 × n 特征；RBF 核可处理非线性
- 场景：小样本高维分类，寻找最大间隔分类超平面
- 何时用：样本量适中、需要较强泛化能力、特征维度高
- 何时不用：超大数据集训练慢时用随机森林/XGBoost；类别极度不平衡需调权重

## 2 可联动算法

- 强机器学习（XGBoost / LightGBM / 神经网络）是国赛加分项：本模板的 SVM 可换用
  `XGBClassifier` / `LGBMClassifier`，接口一致，作为精度对比
- 与 PCA 搭配降维后分类；与网格搜索调参（C、gamma）

## 3 完整代码模板

```python
"""SVM：支持向量机分类，默认 RBF 核处理非线性问题。"""
import numpy as np
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from sklearn.datasets import make_moons


def svm_classify(X, y, C=1.0, gamma="scale"):
    """X: (m, n) 特征；y: (m,) 标签。返回拟合好的 SVC 模型。"""
    return SVC(C=C, gamma=gamma, random_state=42).fit(X, y)


if __name__ == "__main__":
    # demo：make_moons 非线性可分数据，RBF 核可解
    X, y = make_moons(n_samples=100, noise=0.1, random_state=42)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=42)
    acc = svm_classify(Xtr, ytr).score(Xte, yte)
    assert acc > 0.8
    print("SVM 测试准确率:", round(acc, 3))
```

## 4 真题出处

分类（SVM）：2022C、2025C；强机器学习并入（2022C 玻璃/2025C NIPT 分类）
- 见 `algorithms/真题实证表.md` §2.1 保底"支持向量机（SVM）"行

