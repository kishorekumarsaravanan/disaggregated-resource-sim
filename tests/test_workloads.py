import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sim.engine import Simulator
from sim.resources.models import ComputeNode, MemoryNode, StorageNode, AcceleratorNode
from sim.resources.base import ResourceType as RT
from sim.fabric.topology import Fabric
from sim.fabric.remote import RemoteAccess
from sim.manager.registry import Registry
from sim.manager.orchestrator import Orchestrator
from sim.manager.app import App
from sim.workloads.access import Access
from sim.workloads.workload import Workload, Phase
from sim.config import GB, KB, MS


def build(mode="remote", mem_gb=64, accel_units=8):
    s = Simulator(); f = Fabric(s); r = Registry(s)
    for n in (ComputeNode(s, "c0", rack=0), MemoryNode(s, "m0", capacity=mem_gb * GB, rack=0),
              StorageNode(s, "s0", rack=0), AcceleratorNode(s, "g0", units=accel_units, rack=1)):
        r.register(f.attach(n))
    o = Orchestrator(s, f, r)
    acc = Access(s, RemoteAccess(s, f), mode)
    return s, o, acc


def go(s, o, acc, name, phases, **kw):
    app = o.add_app(App(name))
    w = Workload(s, app, phases, o, acc, **kw)
    s.run(until=s.process(w.run()))
    return app, w


def mem_phase(ops=40, mem=16 * GB, ws=0, cores=8):
    return Phase("p", {RT.COMPUTE: cores, RT.MEMORY: mem, RT.STORAGE: 1 * GB}, ops,
                 instr=1e5, mem_accesses=8, working_set=ws)


def test_completes_and_records():
    s, o, acc = build()
    app, w = go(s, o, acc, "a", [mem_phase()])
    assert w.finished_at and len(s.metrics.samples["app.a.op_ns"]) == 40
    assert app.allocs == []                                   # released at end


def test_remote_slower_than_local():
    s, o, acc = build("remote"); go(s, o, acc, "a", [mem_phase()])
    remote = s.metrics.mean("app.a.op_ns")
    s, o, acc = build("local"); go(s, o, acc, "a", [mem_phase()])
    assert remote > s.metrics.mean("app.a.op_ns")


def test_memory_shortage_causes_page_ins():
    s, o, acc = build(mem_gb=64)
    go(s, o, acc, "a", [mem_phase(mem=128 * GB, ws=128 * GB)])    # pool only has 64 GB -> partial grant
    assert s.metrics.counters["app.a.page_ins"] > 0
    t_short = s.metrics.mean("app.a.op_ns")
    s, o, acc = build(mem_gb=256)
    go(s, o, acc, "a", [mem_phase(mem=128 * GB, ws=128 * GB)])
    assert s.metrics.counters["app.a.page_ins"] == 0
    assert t_short > s.metrics.mean("app.a.op_ns")


def test_accel_vs_cpu_fallback():
    ph = lambda: Phase("t", {RT.COMPUTE: 8, RT.MEMORY: 8 * GB, RT.ACCEL: 8}, 8, accel_flops=1e10,
                       accel_in=64 * KB, accel_out=64 * KB)
    s, o, acc = build(); go(s, o, acc, "a", [ph()]); fast = s.metrics.mean("app.a.op_ns")
    s, o, acc = build(accel_units=0.0001)                       # effectively no accelerator capacity
    go(s, o, acc, "a", [Phase("t", {RT.COMPUTE: 8, RT.MEMORY: 8 * GB}, 8, accel_flops=1e10)])
    assert s.metrics.counters["app.a.cpu_fallback"] > 0 and s.metrics.mean("app.a.op_ns") > fast


def test_deterministic():
    r = []
    for _ in range(2):
        s, o, acc = build(); go(s, o, acc, "a", [mem_phase()]); r.append(s.metrics.mean("app.a.op_ns"))
    assert r[0] == r[1]


if __name__ == "__main__":
    for fn in (test_completes_and_records, test_remote_slower_than_local, test_memory_shortage_causes_page_ins,
               test_accel_vs_cpu_fallback, test_deterministic):
        fn(); print("PASS", fn.__name__)
