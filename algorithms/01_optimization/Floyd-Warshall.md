# Floyd-Warshall

## 1 适用情况

- 数据要求：图邻接矩阵 adj（inf 表示无边，对角线为 0），有向/无向均可，权可为负（无负环）
- 场景：全源最短路径、传递闭包、多源多汇的网络可达性
- 何时用：点少（几百内）、要求所有点对最短路、实现简单
- 何时不用：单源最短路（用 Dijkstra/SPFA 更快）、点极多（O(n³) 不可行）

## 2 可联动算法

- 与 Dijkstra 单源结果交叉校验
- 输出最短路矩阵后，可计算网络连通性、中心性指标
- 测线/巡检路径规划中作"任意两点最短距离"预处理

## 3 完整代码模板

```python
"""Floyd-Warshall 全源最短路：O(n^3) 动态规划。"""
import numpy as np


def floyd_warshall(adj):
    """adj: 邻接矩阵（inf = 无边）。返回最短路距离矩阵。"""
    n = adj.shape[0]
    d = np.asarray(adj, float).copy()
    for k in range(n):                                    # 中转点 k
        d = np.minimum(d, d[:, k][:, None] + d[k, :][None, :])
    return d


if __name__ == "__main__":
    inf = np.inf
    # 4 节点有向图
    adj = np.array([[0, 3, inf, 7],
                    [8, 0, 2, inf],
                    [5, inf, 0, 1],
                    [2, inf, inf, 0]])
    d = floyd_warshall(adj)
    assert d[0, 1] == 3        # 直达
    assert d[0, 2] == 5        # 0->1->2 = 3+2
    assert d[0, 3] == 6        # 0->1->2->3 = 3+2+1 优于直达 7
    assert d[1, 3] == 3        # 1->2->3 = 2+1
    assert d[2, 0] == 3        # 2->3->0 = 1+2
    print("最短路矩阵:\n", d)
```

## 4 真题出处

- 全源最短路：2011B（交巡警平台，十年外早年真题，非近十年实证）、一般网络最短路需求
- 见需求文档 v5.0 第三节"Floyd-Warshall 多源最短路"行（早年级别佐证）
