import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sim.engine import Simulator
from sim.resources.models import ComputeNode, MemoryNode, StorageNode, AcceleratorNode
from sim.fabric.topology import Fabric
from sim.fabric.remote import RemoteAccess
from sim.config import KB, MB


def build(**kw):
    s = Simulator(); f = Fabric(s)
    c = f.attach(ComputeNode(s, "c0", rack=0))
    m0 = f.attach(MemoryNode(s, "m0", rack=0, **kw))
    m1 = f.attach(MemoryNode(s, "m1", rack=1, **kw))
    return s, f, c, m0, m1


def run(sim, gen):
    out = []
    def w(): out.append((yield from gen))
    sim.process(w()); sim.run(); return out[0]


def test_hops():
    s, f, c, m0, m1 = build()
    assert f.hops("c0", "c0") == 0 and f.hops("c0", "m0") == 2 and f.hops("c0", "m1") == 4


def test_transfer_latency():
    s, f, c, m0, m1 = build()
    t = run(s, f.transfer("c0", "m0", 64))
    assert abs(t - (2 * 150 + 64 / 32.0)) < 1e-9


def test_inter_rack_slower():
    s, f, c, m0, m1 = build()
    near = run(s, f.transfer("c0", "m0", 1 * MB))
    s, f, c, m0, m1 = build()
    far = run(s, f.transfer("c0", "m1", 1 * MB))
    assert far > near


def test_port_contention():
    s, f, c, m0, m1 = build()
    s.process(f.transfer("c0", "m0", 1 * MB)); s.process(f.transfer("c0", "m0", 1 * MB)); s.run()
    ts = [v for _, v in s.metrics.samples["fabric.transfer_ns"]]
    assert ts[1] > ts[0] + 1 * MB / 32.0 * 0.99


def test_remote_slowdown_vs_local():
    s, f, c, m0, m1 = build()
    local = run(s, m0.access(4 * KB))
    s, f, c, m0, m1 = build()
    ra = RemoteAccess(s, f)
    remote = run(s, ra.mem_read(c, m0, 4 * KB))
    assert remote > 3 * local
    assert s.metrics.mean("remote.mem.fabric_ns") > 0


if __name__ == "__main__":
    for fn in (test_hops, test_transfer_latency, test_inter_rack_slower, test_port_contention, test_remote_slowdown_vs_local):
        fn(); print("PASS", fn.__name__)
