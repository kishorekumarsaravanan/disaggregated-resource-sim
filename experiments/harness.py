"""Shared experiment harness: builds pooled / static / ideal-local systems and runs the 3-app scenario."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sim.engine import Simulator
from sim.config import SimConfig, GB, MS, US
from sim.resources.models import ComputeNode, MemoryNode, StorageNode, AcceleratorNode
from sim.resources.base import ResourceType as RT
from sim.fabric.topology import Fabric
from sim.fabric.remote import RemoteAccess
from sim.manager.registry import Registry
from sim.manager.orchestrator import Orchestrator
from sim.manager.app import App
from sim.workloads.access import Access
from sim.workloads.workload import Workload
from sim.workloads import library

# (name, phase factory, start time, home server in the static baseline)
APPS = [("analytics", library.analytics, 0, 0), ("ml", library.ml_training, 0, 1), ("etl", library.io_heavy, 5 * MS, 2)]
RESULTS = os.path.join(os.path.dirname(__file__), "results")


def make_cfg(hop_ns=None, link_gbps=None, control_ns=None, reconfig_ns=None, seed=42):
    c = SimConfig(seed=seed)
    if hop_ns is not None: c.fabric.hop_latency_ns = hop_ns
    if link_gbps is not None: c.fabric.link_bw_gbps = link_gbps
    if control_ns is not None: c.manager.control_msg_ns = control_ns
    if reconfig_ns is not None: c.manager.reconfig_base_ns = reconfig_ns
    return c


def _sampler(s, mem_nodes, period=250 * US):
    while True:
        yield s.timeout(period)
        s.metrics.sample("pool.mem_used", sum(n.used for n in mem_nodes))


def _finish(s, workloads, mem_nodes, mem_total_gb, label, extra=None):
    s.process(_sampler(s, mem_nodes))
    procs = [s.process(w.run()) for w in workloads]

    def join():
        for p in procs:
            yield p
    s.run(until=s.process(join()))
    m = s.metrics
    ops = [v for w in workloads for _, v in m.samples[f"app.{w.app.name}.op_ns"]]
    used = [v for _, v in m.samples["pool.mem_used"]]
    row = {
        "system": label, "mem_total_gb": mem_total_gb,
        "makespan_ms": round(max(w.finished_at for w in workloads) / MS, 3),
        "mean_op_us": round(sum(ops) / len(ops) / US, 2),
        "p99_op_us": round(sorted(ops)[int(.99 * len(ops))] / US, 2),
        "page_ins": int(sum(m.counters[f"app.{w.app.name}.page_ins"] for w in workloads)),
        "avg_mem_alloc_gb": round(sum(used) / len(used) / GB, 1) if used else 0,
        "mem_util_pct": round(100 * sum(used) / len(used) / (mem_total_gb * GB), 1) if used else 0,
        "reconf_wait_us_total": round(sum(v for w in workloads for _, v in m.samples[f"app.{w.app.name}.reconf_wait_ns"]) / US, 1),
        "mgr_ops": int(sum(m.counters[f"mgr.{k}_ops"] for k in ("alloc", "grow", "shrink", "migrate"))),
        "fabric_gb": round(m.counters["fabric.bytes"] / GB, 3),
    }
    for w in workloads:
        row[f"{w.app.name}_ms"] = round(m.mean(f"app.{w.app.name}.completion_ns") / MS, 3)
    row.update(extra or {})
    return row


def run_pooled(cfg, mem_total_gb, policy="nearest_fit", rebalance_ns=2 * MS):
    s = Simulator(cfg); f = Fabric(s); r = Registry(s)
    nodes = [ComputeNode(s, f"c{i}", 64, rack=i % 2) for i in range(3)]
    mem = [MemoryNode(s, f"m{i}", capacity=mem_total_gb * GB / 4, rack=i % 2) for i in range(4)]
    nodes += mem + [StorageNode(s, f"s{i}", capacity=2048 * GB, rack=i) for i in range(2)]
    nodes += [AcceleratorNode(s, f"g{i}", units=8, rack=i) for i in range(2)]
    for n in nodes:
        r.register(f.attach(n))
    o = Orchestrator(s, f, r, policy)
    acc = Access(s, RemoteAccess(s, f), "remote")
    ws = [Workload(s, o.add_app(App(n)), fn(), o, acc, start_ns=st) for n, fn, st, _ in APPS]
    s.process(o.run_rebalancer(rebalance_ns))
    return _finish(s, ws, mem, mem_total_gb, "pooled")


def run_static(cfg, mem_total_gb, label="static"):
    """Three fixed servers; each app is pinned to one server and holds its peak (capped at what the server has)."""
    s = Simulator(cfg)
    acc = Access(s, None, "local")
    servers, mem = [], []
    for i in range(3):
        c = ComputeNode(s, f"c{i}", 64)
        m = MemoryNode(s, f"m{i}", capacity=mem_total_gb * GB / 3)
        st = StorageNode(s, f"s{i}", capacity=4096 * GB / 3)
        g = AcceleratorNode(s, f"g{i}", units=8 if i < 2 else 0.001)
        servers.append((c, m, st, g)); mem.append(m)
    ws = []
    for name, fn, start, srv in APPS:
        app, phases = App(name, anchor=f"c{srv}"), fn()
        c, m, st, g = servers[srv]
        for rtype, node in ((RT.COMPUTE, c), (RT.MEMORY, m), (RT.STORAGE, st), (RT.ACCEL, g)):
            peak = max((p.demand.get(rtype, 0) for p in phases), default=0)
            if peak > 0:
                a = node.allocate(name, min(peak, node.free))
                if a: app.allocs.append(a)
        ws.append(Workload(s, app, phases, None, acc, start_ns=start, dynamic=False))
    return _finish(s, ws, mem, mem_total_gb, label)


def save_csv(name, rows):
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, name)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
    return path


def table(rows, cols):
    print("  ".join(f"{c:>{max(len(c), 9)}s}" for c in cols))
    for r in rows:
        print("  ".join(f"{str(r.get(c, '')):>{max(len(c), 9)}s}" for c in cols))
