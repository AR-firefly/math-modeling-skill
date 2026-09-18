"""
通用工具函数：距离矩阵、能耗、惩罚、可视化、指标汇总
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import config as cfg

# ===== 预计算距离矩阵 (一次算完，全局复用) =====
_DM = None


def _init_dm():
    global _DM
    if _DM is None:
        c = cfg.COORDS
        diff = c[:, np.newaxis, :] - c[np.newaxis, :, :]
        _DM = np.sqrt((diff ** 2).sum(axis=2))


def invalidate_dm():
    """强制重建距离矩阵 (坐标修改后调用)"""
    global _DM
    _DM = None


def dist(i, j):
    """两点欧式距离，O(1)查表"""
    _init_dm()
    return _DM[i, j]


def route_distance(route):
    """完整路线总距离"""
    _init_dm()
    d = 0.0
    for a, b in zip(route[:-1], route[1:]):
        d += _DM[a, b]
    return d


# ===== 数据生成 =====

def generate_tasks(seed=cfg.SEED):
    """生成示例配送任务。固定种子保证可复现。"""
    rng = np.random.default_rng(seed)
    stations = rng.choice(range(1, cfg.N_STATIONS + 1), size=cfg.N_TASKS,
                          p=cfg.STATION_WEIGHTS)
    weights = rng.uniform(cfg.W_MIN, cfg.W_MAX, size=cfg.N_TASKS).round(1)

    c = cfg.COORDS
    deadlines = np.zeros(cfg.N_TASKS)
    for i in range(cfg.N_TASKS):
        dx, dy = c[stations[i], 0] - c[0, 0], c[stations[i], 1] - c[0, 1]
        round_trip = 2 * np.sqrt(dx * dx + dy * dy)
        deadlines[i] = round_trip / cfg.V + cfg.T0 + rng.uniform(0, 600)

    order = np.argsort(deadlines)
    return stations[order], weights[order], deadlines[order]


# ===== 能耗计算 =====

def energy_per_segment(load, seg_dist):
    """单段能耗: E = (alpha + beta * m) * d"""
    return (cfg.ALPHA + cfg.BETA * load) * seg_dist


def compute_trip_time(trip, stations):
    """一趟配送的总行驶时间 (含装卸)"""
    t = 0.0
    curr = 0
    for tid in trip:
        t += dist(curr, stations[tid]) / cfg.V + cfg.T0
        curr = stations[tid]
    t += dist(curr, 0) / cfg.V
    return t


def compute_trips_energy(trips, stations, weights):
    """
    计算所有趟的总能耗，使用 LPT 分配给 AGV。
    返回: (total_energy, agv_times, makespan)
    """
    trip_times = [compute_trip_time(tr, stations) for tr in trips]
    order = np.argsort(trip_times)[::-1]
    agv_times = [0.0] * cfg.N_AGVS
    total_energy = 0.0
    done = [False] * len(stations)

    for idx in order:
        agv = min(range(cfg.N_AGVS), key=lambda a: agv_times[a])
        trip = trips[idx]
        t = agv_times[agv]
        curr = 0
        remaining = sum(weights[tid] for tid in trip if not done[tid])
        for tid in trip:
            if done[tid]:
                continue
            s = stations[tid]
            seg_d = dist(curr, s)
            t += seg_d / cfg.V
            total_energy += energy_per_segment(remaining, seg_d)
            t += cfg.T0
            remaining -= weights[tid]
            curr = s
            done[tid] = True
        seg_d = dist(curr, 0)
        t += seg_d / cfg.V
        total_energy += energy_per_segment(remaining, seg_d)
        agv_times[agv] = t

    return total_energy, agv_times, max(agv_times)


# ===== 惩罚计算 =====

def compute_lateness_penalty(t, deadline):
    """超时惩罚 (分段线性)"""
    dt = t - deadline
    if dt <= cfg.PENALTY_DELTA:
        return 0.0
    elif dt <= 2 * cfg.PENALTY_DELTA:
        return cfg.PENALTY_C1 * (dt - cfg.PENALTY_DELTA)
    else:
        return (cfg.PENALTY_C1 * cfg.PENALTY_DELTA
                + cfg.PENALTY_C2 * (dt - 2 * cfg.PENALTY_DELTA))


# ===== 可视化 =====

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def plot_path(route, title, save_path):
    """绘制配送路径图。route 可以是单条路线或 {agv_id: route} 字典。"""
    fig, ax = plt.subplots(figsize=(10, 8))
    c = cfg.COORDS

    for i in range(1, len(c)):
        ax.scatter(c[i, 0], c[i, 1], c='steelblue', s=80, zorder=5)
        ax.annotate(str(i), (c[i, 0] + 1.5, c[i, 1] + 1.5), fontsize=10, fontweight='bold')
    ax.scatter(c[0, 0], c[0, 1], c='red', s=150, marker='s', zorder=5, label='Warehouse')

    colors = ['#e41a1c', '#377eb8', '#4daf4a']
    if isinstance(route, dict):
        for agv_id, r in route.items():
            pts = c[r]
            ax.plot(pts[:, 0], pts[:, 1], 'o-', color=colors[agv_id % 3],
                    linewidth=2, markersize=6, label=f'AGV{agv_id + 1}')
            for a, b in zip(r[:-1], r[1:]):
                dx = c[b, 0] - c[a, 0]
                dy = c[b, 1] - c[a, 1]
                ax.arrow(c[a, 0], c[a, 1], dx * 0.85, dy * 0.85,
                         head_width=1.5, head_length=1.5, fc=colors[agv_id % 3],
                         ec=colors[agv_id % 3], alpha=0.6)
    else:
        pts = c[route]
        ax.plot(pts[:, 0], pts[:, 1], 'o-', color='#e41a1c', linewidth=2, markersize=6)

    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_title(title)
    ax.legend()
    ax.set_aspect('equal')
    fig.tight_layout()
    fig.savefig(save_path, dpi=300)
    plt.close(fig)


def plot_gantt(schedule, title, save_path):
    """甘特图。schedule = {agv_id: [(station, start, end), ...]}"""
    fig, ax = plt.subplots(figsize=(12, 5))
    colors = ['#e41a1c', '#377eb8', '#4daf4a']
    for agv_id, tasks in schedule.items():
        for station, start, end in tasks:
            ax.barh(agv_id, end - start, left=start, height=0.6,
                    color=colors[agv_id % 3], edgecolor='black', alpha=0.8)
            ax.text(start + (end - start) / 2, agv_id, str(station),
                    ha='center', va='center', fontsize=8, fontweight='bold')
            # Mark deadline if available
    ax.set_yticks(range(cfg.N_AGVS))
    ax.set_yticklabels([f'AGV{i + 1}' for i in range(cfg.N_AGVS)])
    ax.set_xlabel('Time (s)')
    ax.set_title(title)
    ax.grid(axis='x', alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=300)
    plt.close(fig)


def plot_pareto(times, energies, knee_idx, save_path):
    """Pareto 前沿图"""
    fig, ax = plt.subplots(figsize=(8, 6))
    order = np.argsort(times)
    ax.plot(np.array(times)[order], np.array(energies)[order], 'o-',
            color='steelblue', markersize=6, linewidth=1.5)
    if knee_idx is not None:
        ax.scatter(times[knee_idx], energies[knee_idx], c='red', s=150,
                   marker='*', zorder=10, label='Knee Point')
    ax.set_xlabel('Total Time (s)')
    ax.set_ylabel('Total Energy (kJ)')
    ax.set_title('Pareto Front -- Time vs Energy')
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=300)
    plt.close(fig)


def plot_comparison(labels, values_before, values_after, ylabel, title, save_path):
    """改善前后对比柱状图"""
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(labels))
    w = 0.35
    ax.bar(x - w / 2, values_before, w, label='Original', color='steelblue')
    ax.bar(x + w / 2, values_after, w, label='Optimized', color='#e41a1c')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=300)
    plt.close(fig)


# ===== 指标计算 =====

def build_schedule(agv_trips, stations):
    """从 AGV 任务分配构建甘特图时间线"""
    schedule = {}
    for agv_id, trips in agv_trips.items():
        tasks = []
        t = 0.0
        for trip in trips:
            curr = 0
            for tid in trip:
                s = stations[tid]
                t += dist(curr, s) / cfg.V
                tasks.append((s, t, t + cfg.T0))
                t += cfg.T0
                curr = s
            t += dist(curr, 0) / cfg.V
        schedule[agv_id] = tasks
    return schedule


def compute_metrics(agv_trips, stations, weights, deadlines):
    """
    给定 AGV 行程方案，计算: makespan, total_energy, total_penalty, tardy_count
    agv_trips: {agv_id: [[task_indices], ...]}
    """
    agv_times = [0.0] * cfg.N_AGVS
    total_energy = 0.0
    total_penalty = 0.0
    tardy_count = 0
    done = [False] * len(stations)

    for agv, trips in agv_trips.items():
        t = 0.0
        for trip in trips:
            curr = 0
            trip_load = sum(weights[tid] for tid in trip if not done[tid])
            remaining = trip_load
            for tid in trip:
                if done[tid]:
                    continue
                s = stations[tid]
                seg_d = dist(curr, s)
                t += seg_d / cfg.V
                total_energy += energy_per_segment(remaining, seg_d)
                t += cfg.T0
                remaining -= weights[tid]
                curr = s
                pen = compute_lateness_penalty(t, deadlines[tid])
                total_penalty += pen
                if pen > 0:
                    tardy_count += 1
                done[tid] = True
            seg_d = dist(curr, 0)
            t += seg_d / cfg.V
            total_energy += energy_per_segment(remaining, seg_d)
        agv_times[agv] = t

    makespan = max(agv_times)
    return makespan, total_energy, total_penalty, tardy_count
