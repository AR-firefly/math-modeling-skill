"""
Phase4: 车间布局微调 — 两阶段搜索 (TSP筛选 + GA精评)
"""
import numpy as np
import config as cfg
from utils import (dist, compute_trip_time, compute_trips_energy,
                   energy_per_segment, generate_tasks, invalidate_dm)
from tsp_solver import held_karp as tsp_solve
from vrptw_ga import (optimize as ga_optimize, evaluate as ga_evaluate,
                       ffd_pack, assign_trips_to_agvs, scan_pack)

GRID_RANGE = 20
GRID_STEP = 5
TOP_K_PHASE1 = 3


def _with_temp_coords(sid, nx, ny, fn, *args):
    """安全地临时修改坐标，执行 fn(*args)，自动恢复并刷新距离矩阵"""
    original = cfg.COORDS[sid].copy()
    cfg.COORDS[sid] = [nx, ny]
    invalidate_dm()
    try:
        return fn(*args)
    finally:
        cfg.COORDS[sid] = original
        invalidate_dm()


def phase1_tsp_filter(candidates):
    """TSP 快速筛选"""
    results = []
    for sid, nx, ny in candidates:
        d, _ = _with_temp_coords(sid, nx, ny, tsp_solve)
        results.append((sid, nx, ny, d))
    results.sort(key=lambda x: x[3])
    return results


def phase2_ga_precise(candidates, stations, weights, deadlines):
    """GA 精评"""
    all_results = []
    for sid, nx, ny, _ in candidates:
        def _eval():
            perm, _ = ga_optimize(stations, weights, deadlines,
                                   seed=cfg.SEED + sid, verbose=False)
            _, makespan, penalty = ga_evaluate(perm, stations, weights, deadlines)
            trips = ffd_pack(perm, weights)
            total_energy, _, _ = compute_trips_energy(trips, stations, weights)
            return (sid, nx, ny, makespan, total_energy, penalty)
        all_results.append(_with_temp_coords(sid, nx, ny, _eval))
    return all_results


def optimize(stations, weights, deadlines, step=GRID_STEP):
    """两阶段搜索主流程（step: 布局搜索网格步长，默认 5；用于网格无关性检验）"""
    print("=" * 60)
    print("Phase4: 车间布局微调优化")
    print("=" * 60)

    xs = np.arange(-GRID_RANGE, GRID_RANGE + 1, step)
    ys = np.arange(-GRID_RANGE, GRID_RANGE + 1, step)
    print(f"搜索网格: {len(xs)}x{len(ys)}={len(xs) * len(ys)} 候选/工位")

    print("\n--- Phase 1: TSP 筛选 ---")
    all_candidates = []
    for sid in range(1, cfg.N_STATIONS + 1):
        ox, oy = cfg.COORDS[sid]
        for dx in xs:
            for dy in ys:
                all_candidates.append((sid, ox + dx, oy + dy))

    print(f"总计 {len(all_candidates)} 个候选, 正在评估...")
    tsp_results = phase1_tsp_filter(all_candidates)

    from collections import defaultdict
    by_station = defaultdict(list)
    for r in tsp_results:
        by_station[r[0]].append(r)
    top_candidates = []
    for sid in range(1, cfg.N_STATIONS + 1):
        best_n = sorted(by_station[sid], key=lambda x: x[3])[:TOP_K_PHASE1]
        top_candidates.extend(best_n)
        if best_n:
            b = best_n[0]
            print(f"  工位{sid}: 最佳候选 ({b[1]:.0f},{b[2]:.0f}) TSP={b[3]:.1f}m")

    print(f"Phase1 保留 {len(top_candidates)} 个候选进入 Phase2")

    print("\n--- Phase 2: GA 精评 ---")
    ga_results = phase2_ga_precise(top_candidates, stations, weights, deadlines)

    perm0, _ = ga_optimize(stations, weights, deadlines, seed=cfg.SEED, verbose=False)
    _, base_makespan, base_penalty = ga_evaluate(perm0, stations, weights, deadlines)
    trips0 = ffd_pack(perm0, weights)
    base_energy, _, _ = compute_trips_energy(trips0, stations, weights)

    print(f"\n基线 (原布局): makespan={base_makespan:.1f}s, "
          f"energy={base_energy:.1f}kJ, penalty={base_penalty:.1f}")

    best = min(ga_results, key=lambda x: x[3])
    print(f"\n最佳布局: 移动工位{best[0]} 到 ({best[1]:.0f}, {best[2]:.0f})")
    print(f"  改善后: makespan={best[3]:.1f}s, energy={best[4]:.1f}kJ, "
          f"penalty={best[5]:.1f}")
    m_imp = (base_makespan - best[3]) / base_makespan * 100
    e_imp = (base_energy - best[4]) / base_energy * 100
    print(f"  Makespan: {base_makespan:.1f} -> {best[3]:.1f} s (改善 {m_imp:+.1f}%)")
    print(f"  能耗: {base_energy:.1f} -> {best[4]:.1f} kJ (改善 {e_imp:+.1f}%)")

    return {
        'base': (base_makespan, base_energy, base_penalty),
        'best': best,
        'improvements': (m_imp, e_imp),
        'all_ga_results': ga_results,
    }


def solve():
    stations, weights, deadlines = generate_tasks()
    return optimize(stations, weights, deadlines)


if __name__ == '__main__':
    solve()
