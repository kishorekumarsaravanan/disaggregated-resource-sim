"""Context example: App B's memory demand drops, App A's rises; orchestrator moves memory across apps."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sim.engine import Simulator
from sim.resources.models import ComputeNode, MemoryNode, AcceleratorNode
from sim.resources.base import ResourceType as RT
from sim.fabric.topology import Fabric
from sim.manager.registry import Registry
from sim.manager.orchestrator import Orchestrator
from sim.manager.app import App
from sim.config import GB, MS, US


def main():
    s = Simulator(); f = Fabric(s); r = Registry(s)
    for n in (ComputeNode(s, "c0", rack=0), MemoryNode(s, "m0", capacity=64 * GB, rack=0),
              MemoryNode(s, "m1", capacity=64 * GB, rack=1), AcceleratorNode(s, "g0", rack=1)):
        r.register(f.attach(n))
    o = Orchestrator(s, f, r)
    A, B = o.add_app(App("A", anchor="c0")), o.add_app(App("B", anchor="c0"))

    def scenario():
        yield from o.allocate(B, RT.MEMORY, 100 * GB); yield from o.allocate(A, RT.MEMORY, 20 * GB)
        print(f"t={s.now/MS:8.3f} ms  start    A={A.held(RT.MEMORY)/GB:.0f} GB  B={B.held(RT.MEMORY)/GB:.0f} GB")
        A.demand[RT.MEMORY], B.demand[RT.MEMORY] = 100 * GB, 20 * GB
        t0 = s.now
        yield from o.rebalance_once()
        print(f"t={s.now/MS:8.3f} ms  rebalanced A={A.held(RT.MEMORY)/GB:.0f} GB  B={B.held(RT.MEMORY)/GB:.0f} GB"
              f"  (took {(s.now-t0)/US:.1f} us)")
        yield from o.grow(B, RT.ACCEL, 4)
        print(f"t={s.now/MS:8.3f} ms  B granted {B.held(RT.ACCEL):.0f} accel units on {B.allocs_of(RT.ACCEL)[0].node}")
    s.run(until=s.process(scenario()))
    for k in ("alloc", "grow", "shrink"):
        print(f"mgr.{k}: mean {s.metrics.mean(f'mgr.{k}_ns')/US:.1f} us over {int(s.metrics.counters[f'mgr.{k}_ops'])} ops")


if __name__ == "__main__":
    main()
