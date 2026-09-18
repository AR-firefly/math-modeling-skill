"""
Phase3: 多目标优化 — NSGA-II + VNS 局部搜索
参考: Deb et al. (2002), NSGA-II
"""
import numpy as np
import config as cfg
from utils import (dist, energy_per_segment, compute_trip_time,
                   compute_trips_energy, compute_lateness_penalty)
from vrptw_ga import (scan_pack, ffd_pack, assign_trips_to_agvs,
                       init_population, pmx_crossover,
                       swap_mutation, invert_mutation,
                       two_opt_local_search)

POP_SIZE = 100
N_GEN = 300
P_CROSS = 0.9
P_MUT = 0.15
VNS_K_MAX = 4


def objectives(perm, stations, weights, deadlines):
    """双目标: (makespan, total_energy)"""
    trips = scan_pack(perm, weights)
    total_energy, agv_times, makespan = compute_trips_energy(trips, stations, weights)
    return makespan, total_energy


def non_dominated_sort(obj1, obj2):
    """快速非支配排序"""
    N = len(obj1)
    dominated_by = [0] * N
    dominates = [[] for _ in range(N)]

    for p in range(N):
        for q in range(N):
            if p == q:
                continue
            if (obj1[p] <= obj1[q] and obj2[p] <= obj2[q] and
                    (obj1[p] < obj1[q] or obj2[p] < obj2[q])):
                dominates[p].append(q)
            elif (obj1[q] <= obj1[p] and obj2[q] <= obj2[p] and
                    (obj1[q] < obj1[p] or obj2[q] < obj2[p])):
                dominated_by[p] += 1

    fronts = []
    front = [i for i in range(N) if dominated_by[i] == 0]
    while front:
        fronts.append(front)
        next_front = []
        for p in front:
            for q in dominates[p]:
                dominated_by[q] -= 1
                if dominated_by[q] == 0:
                    next_front.append(q)
        front = next_front
    return fronts


def crowding_distance(obj1, obj2, front):
    """拥挤度距离"""
    if len(front) <= 2:
        return [1e10] * len(front)
    dists = [0.0] * len(front)
    for objs in [obj1, obj2]:
        vals = [objs[i] for i in front]
        order = np.argsort(vals)
        dists[order[0]] = 1e10
        dists[order[-1]] = 1e10
        v_range = vals[order[-1]] - vals[order[0]]
        if v_range < 1e-9:
            continue
        for k in range(1, len(front) - 1):
            dists[order[k]] += (vals[order[k + 1]] - vals[order[k - 1]]) / v_range
    return dists


def nsga2_select(pop, obj1, obj2, n_select):
    """环境选择: rank + crowding"""
    fronts = non_dominated_sort(obj1, obj2)
    selected, selected_idx = [], []
    for front in fronts:
        if len(selected) + len(front) <= n_select:
            selected.extend([pop[i] for i in front])
            selected_idx.extend(front)
        else:
            cd = crowding_distance(obj1, obj2, front)
            order = np.argsort(cd)[::-1]
            need = n_select - len(selected)
            for k in range(need):
                selected.append(pop[front[order[k]]])
                selected_idx.append(front[order[k]])
            break
    return selected, selected_idx


def dominates(o1_a, o2_a, o1_b, o2_b):
    """a 支配 b?"""
    return (o1_a <= o1_b and o2_a <= o2_b and
            (o1_a < o1_b or o2_a < o2_b))


def vns_local_search(perm, stations, weights, deadlines, rng, max_iter=3):
    """VNS: 多邻域局部搜索"""
    n = len(perm)
    orig_o1, orig_o2 = objectives(perm, stations, weights, deadlines)
    best_perm = perm.copy()
    best_o1, best_o2 = orig_o1, orig_o2

    for _ in range(max_iter):
        improved = False
        for k in range(VNS_K_MAX):
            neighbor = best_perm.copy()
            if k == 0:
                i, j = rng.choice(n, 2, replace=False)
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
            elif k == 1:
                i = rng.integers(n)
                val = neighbor.pop(i)
                neighbor.insert(rng.integers(n - 1), val)
            elif k == 2:
                i, j = sorted(rng.choice(n, 2, replace=False))
                neighbor[i:j] = reversed(neighbor[i:j])
            else:
                neighbor = two_opt_local_search(neighbor, stations, weights, deadlines)

            no1, no2 = objectives(neighbor, stations, weights, deadlines)
            if dominates(no1, no2, best_o1, best_o2):
                best_perm = neighbor
                best_o1, best_o2 = no1, no2
                improved = True
                break
        if not improved:
            break
    return best_perm


def optimize(stations, weights, deadlines, seed=cfg.SEED + 100, verbose=True):
    """NSGA-II + VNS 主循环"""
    rng = np.random.default_rng(seed)
    pop = init_population(stations, weights, deadlines, rng)
    if len(pop) > POP_SIZE:
        pop = pop[:POP_SIZE]

    pareto_history = []
    parent_objs = None

    for gen in range(N_GEN):
        if parent_objs is None:
            parent_objs = [objectives(c, stations, weights, deadlines) for c in pop]
        obj1 = [o[0] for o in parent_objs]
        obj2 = [o[1] for o in parent_objs]

        fronts = non_dominated_sort(obj1, obj2)
        pareto_history.append([(obj1[i], obj2[i]) for i in fronts[0]])

        if verbose and gen % 50 == 0:
            t_vals = [obj1[i] for i in fronts[0]]
            e_vals = [obj2[i] for i in fronts[0]]
            print(f"  Gen {gen:4d}: F1={len(fronts[0])}, "
                  f"time=[{min(t_vals):.0f},{max(t_vals):.0f}], "
                  f"energy=[{min(e_vals):.0f},{max(e_vals):.0f}]")

        if gen % 5 == 0 and len(fronts[0]) >= 3:
            f1_cd = crowding_distance(obj1, obj2, fronts[0])
            sorted_f1 = sorted(zip(fronts[0], f1_cd), key=lambda x: -x[1])
            for f1_idx, _ in sorted_f1[:3]:
                pop[f1_idx] = vns_local_search(
                    pop[f1_idx], stations, weights, deadlines, rng, max_iter=2)

        pop_rank = np.zeros(len(pop), dtype=int)
        for r, front in enumerate(fronts):
            for idx in front:
                pop_rank[idx] = r
        pop_cd = np.zeros(len(pop))
        for front in fronts:
            cd = crowding_distance(obj1, obj2, front)
            for k, idx in enumerate(front):
                pop_cd[idx] = cd[k]

        offspring = []
        while len(offspring) < POP_SIZE:
            i1, i2 = rng.choice(len(pop), 2, replace=False)
            p1_idx = i1 if (pop_rank[i1] < pop_rank[i2] or
                           (pop_rank[i1] == pop_rank[i2] and pop_cd[i1] > pop_cd[i2])) else i2
            i1, i2 = rng.choice(len(pop), 2, replace=False)
            p2_idx = i1 if (pop_rank[i1] < pop_rank[i2] or
                           (pop_rank[i1] == pop_rank[i2] and pop_cd[i1] > pop_cd[i2])) else i2
            p1, p2 = pop[p1_idx], pop[p2_idx]

            if rng.random() < P_CROSS:
                c1, c2 = pmx_crossover(p1, p2, rng)
            else:
                c1, c2 = p1.copy(), p2.copy()
            if rng.random() < P_MUT:
                swap_mutation(c1, rng)
            if rng.random() < P_MUT * 0.3:
                invert_mutation(c2, rng)
            offspring.extend([c1, c2])

        off_objs = [objectives(c, stations, weights, deadlines)
                    for c in offspring[:POP_SIZE]]
        combined = pop + offspring[:POP_SIZE]
        comb_o1 = obj1 + [o[0] for o in off_objs]
        comb_o2 = obj2 + [o[1] for o in off_objs]
        pop, selected_idx = nsga2_select(combined, comb_o1, comb_o2, POP_SIZE)

        parent_objs = []
        for idx in selected_idx:
            if idx < len(obj1):
                parent_objs.append((obj1[idx], obj2[idx]))
            else:
                parent_objs.append(off_objs[idx - len(obj1)])

    final_objs = [objectives(c, stations, weights, deadlines) for c in pop]
    final_o1 = [o[0] for o in final_objs]
    final_o2 = [o[1] for o in final_objs]
    fronts = non_dominated_sort(final_o1, final_o2)
    pareto_front = [(pop[i], final_o1[i], final_o2[i]) for i in fronts[0]]

    t_arr = np.array(final_o1)[fronts[0]]
    e_arr = np.array(final_o2)[fronts[0]]
    t_norm = (t_arr - t_arr.min()) / (t_arr.max() - t_arr.min() + 1e-9)
    e_norm = (e_arr - e_arr.min()) / (e_arr.max() - e_arr.min() + 1e-9)
    # 膝点 = 归一化后到理想点 (0,0)（两目标均最小）距离最小的折中点；
    # 原 argmax(|t-e|) 取的是极端点（极速/节能端），语义错误。
    knee_idx = np.argmin(np.sqrt(t_norm ** 2 + e_norm ** 2))

    return pop, pareto_front, fronts[0], knee_idx, pareto_history


def solve():
    """Phase3 主入口"""
    from utils import generate_tasks
    stations, weights, deadlines = generate_tasks()
    print("=" * 60)
    print("Phase3: 多目标能耗优化 (NSGA-II + VNS)")
    print("=" * 60)

    pop, pareto, front0, knee_idx, history = optimize(
        stations, weights, deadlines, verbose=True)
    knee_perm, knee_time, knee_energy = pareto[knee_idx]

    print(f"\nPareto 前沿 ({len(pareto)} 个非支配解)")
    print(f"Knee Point: time={knee_time:.1f}s, energy={knee_energy:.1f}kJ")

    min_time = min(pareto, key=lambda x: x[1])
    min_energy = min(pareto, key=lambda x: x[2])
    print(f"极速: time={min_time[1]:.1f}s, energy={min_time[2]:.1f}kJ")
    print(f"节能: time={min_energy[1]:.1f}s, energy={min_energy[2]:.1f}kJ")
    if min_energy[2] > 0:
        print(f"能耗差: {min_time[2] - min_energy[2]:.1f}kJ "
              f"(极速多耗 {(min_time[2] / min_energy[2] - 1) * 100:.1f}%)")

    return {
        'pareto': pareto, 'knee_idx': knee_idx,
        'knee': (knee_time, knee_energy),
        'min_time': (min_time[1], min_time[2]),
        'min_energy': (min_energy[1], min_energy[2]),
        'history': history,
    }


if __name__ == '__main__':
    solve()
