"""Three applications share the disaggregated pools; the orchestrator reallocates as their phases change."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sim.engine import Simulator
from sim.resources.models import ComputeNode, MemoryNode, StorageNode, AcceleratorNode
from sim.fabric.topology import Fabric
from sim.fabric.remote import RemoteAccess
from sim.manager.registry import Registry
from sim.manager.orchestrator import Orchestrator
from sim.manager.app import App
from sim.workloads.access import Access
from sim.workloads.workload import Workload
from sim.workloads import library
from sim.config import GB, MS, US


def build_pool(sim, fabric, registry):
    nodes = []
    for i in range(3):
        nodes.append(ComputeNode(sim, f"c{i}", cores=64, rack=i % 2))
    for i in range(4):
        nodes.append(MemoryNode(sim, f"m{i}", capacity=128 * GB, rack=i % 2))
    for i in range(2):
        nodes.append(StorageNode(sim, f"s{i}", capacity=2048 * GB, rack=i))
    for i in range(2):
        nodes.append(AcceleratorNode(sim, f"g{i}", units=8, rack=i))
    for n in nodes:
        registry.register(fabric.attach(n))


def main():
    s = Simulator(); f = Fabric(s); r = Registry(s)
    build_pool(s, f, r)
    o = Orchestrator(s, f, r, "nearest_fit")
    acc = Access(s, RemoteAccess(s, f), "remote")
    specs = [("analytics", library.analytics(), 0), ("ml", library.ml_training(), 0), ("etl", library.io_heavy(), 5 * MS)]
    ws = [Workload(s, o.add_app(App(n)), ph, o, acc, start_ns=st) for n, ph, st in specs]
    s.process(o.run_rebalancer(2 * MS))
    procs = [s.process(w.run()) for w in ws]

    def join():
        for p in procs:
            yield p
    s.run(until=s.process(join()))

    m = s.metrics
    print(f"{'app':10s} {'done(ms)':>9s} {'mean op(us)':>12s} {'p99 op(us)':>11s} {'reconf wait(us)':>16s} {'page-ins':>9s}")
    for n, _, _ in specs:
        print(f"{n:10s} {m.mean(f'app.{n}.completion_ns')/MS:9.2f} {m.mean(f'app.{n}.op_ns')/US:12.1f} "
              f"{m.percentile(f'app.{n}.op_ns', 99)/US:11.1f} {m.mean(f'app.{n}.reconf_wait_ns')/US:16.1f} "
              f"{int(m.counters[f'app.{n}.page_ins']):9d}")
    for k in ("mem", "storage", "accel"):
        t, fb = m.mean(f"remote.{k}.total_ns"), m.mean(f"remote.{k}.fabric_ns")
        if t:
            print(f"remote {k:7s}: mean {t/US:8.1f} us, of which fabric {100*fb/t:4.1f}%")
    ops = {k: int(m.counters[f'mgr.{k}_ops']) for k in ('alloc', 'grow', 'shrink')}
    print("orchestrator ops:", ops, "| partial grants:", int(m.counters['mgr.partial_grants']),
          "| failed allocs:", int(m.counters['mgr.failed_allocs']))
    print(f"total sim time: {s.now/MS:.2f} ms")


if __name__ == "__main__":
    main()
