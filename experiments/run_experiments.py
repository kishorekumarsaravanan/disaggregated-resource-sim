"""Step 7 experiments.  Usage: python experiments/run_experiments.py [exp1|exp2|exp3|all]"""
import sys
from harness import *


def exp1():
    """Capacity sweep: same total memory, static servers vs pooled. Also an ideal-local reference (no fabric, no capacity limit)."""
    rows = [run_static(make_cfg(), 3 * 512, "ideal_local")]     # 3 servers x 512 GB
    for total in (512, 384, 256, 192, 128, 96):
        rows += [run_static(make_cfg(), total), run_pooled(make_cfg(), total)]
    save_csv("exp1_capacity_sweep.csv", rows)
    print("\n== EXP1: static vs pooled as total memory shrinks ==")
    table(rows, ["system", "mem_total_gb", "makespan_ms", "mean_op_us", "p99_op_us", "page_ins", "avg_mem_alloc_gb", "mem_util_pct"])
    return rows


def exp2():
    """Fabric sweep at plentiful memory: isolates the cost of remote access."""
    ideal = run_static(make_cfg(), 3 * 512, "ideal_local")
    rows = []
    for hop in (50, 150, 500, 1000, 2000, 5000):
        r = run_pooled(make_cfg(hop_ns=hop), 512); r.update(sweep="hop_latency_ns", value=hop); rows.append(r)
    for bw in (4, 8, 16, 32, 64, 128):
        r = run_pooled(make_cfg(link_gbps=bw), 512); r.update(sweep="link_gbps", value=bw); rows.append(r)
    for r in rows:
        r["makespan_overhead_pct"] = round(100 * (r["makespan_ms"] / ideal["makespan_ms"] - 1), 1)
        r["mean_op_overhead_pct"] = round(100 * (r["mean_op_us"] / ideal["mean_op_us"] - 1), 1)
    rows.insert(0, dict(ideal, sweep="reference", value="-"))
    save_csv("exp2_fabric_sweep.csv", rows)
    print("\n== EXP2: disaggregation overhead vs fabric (reference = ideal local) ==")
    table(rows, ["sweep", "value", "makespan_ms", "mean_op_us", "makespan_overhead_pct", "mean_op_overhead_pct", "fabric_gb"])
    return rows


def exp3():
    """Control plane: reconfiguration cost grid, and placement policy comparison."""
    rows = []
    for ctl in (1 * US, 5 * US, 50 * US, 500 * US):
        for rec in (10 * US, 50 * US, 500 * US, 5 * MS):
            r = run_pooled(make_cfg(control_ns=ctl, reconfig_ns=rec), 512)
            r.update(sweep="control_grid", control_us=ctl / US, reconfig_us=rec / US); rows.append(r)
    for pol in ("first_fit", "nearest_fit"):
        r = run_pooled(make_cfg(), 512, policy=pol); r.update(sweep="policy", policy=pol); rows.append(r)
    save_csv("exp3_control_plane.csv", rows)
    print("\n== EXP3a: control-plane cost grid ==")
    table([r for r in rows if r["sweep"] == "control_grid"],
          ["control_us", "reconfig_us", "makespan_ms", "reconf_wait_us_total", "mgr_ops"])
    print("\n== EXP3b: placement policy ==")
    table([r for r in rows if r["sweep"] == "policy"], ["policy", "makespan_ms", "mean_op_us", "p99_op_us", "fabric_gb"])
    return rows


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("exp1", exp1), ("exp2", exp2), ("exp3", exp3)):
        if which in (name, "all"):
            fn()
