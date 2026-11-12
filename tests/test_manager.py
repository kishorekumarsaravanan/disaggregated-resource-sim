import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sim.engine import Simulator
from sim.resources.models import ComputeNode, MemoryNode
from sim.resources.base import ResourceType as RT
from sim.fabric.topology import Fabric
from sim.manager.registry import Registry
from sim.manager.orchestrator import Orchestrator
from sim.manager.app import App
from sim.config import GB, MS, US


def build(policy="nearest_fit", mem_gb=64):
    s = Simulator(); f = Fabric(s); r = Registry(s)
    nodes = {}
    for n in (ComputeNode(s, "c0", rack=0), MemoryNode(s, "mA", capacity=mem_gb * GB, rack=1),
              MemoryNode(s, "mB", capacity=mem_gb * GB, rack=0)):     # registered far-first on purpose
        f.attach(n); r.register(n); nodes[n.name] = n
    return s, f, r, Orchestrator(s, f, r, policy), nodes


def run(s, gen, until=None):
    out = []
    def w(): out.append((yield from gen))
    p = s.process(w())
    s.run(until if until is not None else p)     # heartbeats never end, so run until this process finishes
    return out[0] if out else None


def test_discovery_and_failure_detection():
    s, f, r, o, n = build()
    s.run(2 * MS)
    assert len(r.view) == 3 and all(r.is_alive(k) for k in r.view)
    n["mA"].alive = False
    s.run(8 * MS)
    assert not r.is_alive("mA") and r.is_alive("mB")
    assert [v.name for v in r.candidates(RT.MEMORY)] == ["mB"]


def test_policies():
    app_n = App("a", anchor="c0")
    s, f, r, o, n = build("nearest_fit")
    assert run(s, o.allocate(app_n, RT.MEMORY, 8 * GB))[0].node == "mB"      # same rack
    s, f, r, o, n = build("first_fit")
    assert run(s, o.allocate(App("a", anchor="c0"), RT.MEMORY, 8 * GB))[0].node == "mA"


def test_spill_and_rollback():
    s, f, r, o, n = build()
    app = App("a", anchor="c0")
    got = run(s, o.allocate(app, RT.MEMORY, 100 * GB))
    assert len(got) == 2 and app.held(RT.MEMORY) == 100 * GB
    s, f, r, o, n = build()
    app = App("a", anchor="c0")
    assert run(s, o.allocate(app, RT.MEMORY, 200 * GB)) is None
    assert n["mA"].used == 0 and n["mB"].used == 0                           # rolled back


def test_grow_shrink_cost():
    s, f, r, o, n = build(); app = App("a", anchor="c0")
    t0 = s.now; run(s, o.grow(app, RT.MEMORY, 10 * GB))
    cm = s.config.manager
    assert s.now - t0 >= 3 * cm.control_msg_ns + cm.reconfig_base_ns
    freed = run(s, o.shrink(app, RT.MEMORY, 4 * GB))
    assert freed == 4 * GB and app.held(RT.MEMORY) == 6 * GB


def test_migrate():
    s, f, r, o, n = build(); app = App("a", anchor="c0")
    a = run(s, o.allocate(app, RT.MEMORY, 8 * GB))[0]
    assert a.node == "mB"
    t0 = s.now; new = run(s, o.migrate(app, a, "mA"))
    assert new.node == "mA" and n["mB"].used == 0 and n["mA"].used == 8 * GB
    assert s.now - t0 >= 8 * GB / s.config.manager.migrate_gbps


def test_rebalance_moves_memory_between_apps():
    s, f, r, o, n = build()
    A, B = App("A", anchor="c0"), App("B", anchor="c0")
    o.add_app(A); o.add_app(B)
    run(s, o.allocate(B, RT.MEMORY, 100 * GB)); run(s, o.allocate(A, RT.MEMORY, 20 * GB))
    A.demand[RT.MEMORY] = 100 * GB; B.demand[RT.MEMORY] = 20 * GB
    run(s, o.rebalance_once())
    assert abs(A.held(RT.MEMORY) - 100 * GB) < 1 and abs(B.held(RT.MEMORY) - 20 * GB) < 1


def test_concurrent_ops_are_serialized():
    from sim.workloads.workload import Workload, Phase
    s, f, r, o, n = build()
    s.config.manager.reconfig_base_ns = 2 * MS                        # slow control plane exposes races
    A = o.add_app(App("A", anchor="c0")); B = o.add_app(App("B", anchor="c0"))
    run(s, o.allocate(A, RT.MEMORY, 40 * GB)); run(s, o.allocate(B, RT.MEMORY, 40 * GB))
    A.demand[RT.MEMORY] = 5 * GB; B.demand[RT.MEMORY] = 5 * GB
    p = [s.process(o.reconcile(A)), s.process(o.rebalance_once()), s.process(o.reconcile(B))]   # all at once
    def join():
        for q in p: yield q
    s.run(until=s.process(join()))
    assert A.held(RT.MEMORY) == 5 * GB and B.held(RT.MEMORY) == 5 * GB
    assert n["mA"].used + n["mB"].used == 10 * GB
    assert len(s.metrics.samples["mgr.lock_wait_ns"]) >= 3


if __name__ == "__main__":
    for fn in (test_discovery_and_failure_detection, test_policies, test_spill_and_rollback,
               test_grow_shrink_cost, test_migrate, test_rebalance_moves_memory_between_apps, test_concurrent_ops_are_serialized):
        fn(); print("PASS", fn.__name__)
