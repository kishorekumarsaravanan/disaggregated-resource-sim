import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sim.engine import Simulator
from sim.resources.models import ComputeNode, MemoryNode, StorageNode, AcceleratorNode
from sim.config import GB, KB, US


def run(sim, gen):
    out = []
    def wrap():
        out.append((yield from gen))
    sim.process(wrap()); sim.run()
    return out[0]


def test_compute_scales_with_cores():
    s = Simulator(); n = ComputeNode(s, "c0", cores=64, ghz=2.0, ipc=1.0)
    assert run(s, n.execute(8e9, 4)) == 1e9          # 8e9 / (4*2*1) ns
    s2 = Simulator(); n2 = ComputeNode(s2, "c0", cores=64, ghz=2.0, ipc=1.0)
    assert run(s2, n2.execute(8e9, 8)) == 5e8        # twice the cores, half the time


def test_memory_latency_and_contention():
    s = Simulator(); m = MemoryNode(s, "m0", channels=1, bw_gbps=10.0)
    t = run(s, m.access(64))
    assert abs(t - (100 + 6.4)) < 1e-6               # 100 ns + 64B/10 B/ns
    # two simultaneous accesses on 1 channel: second one queues
    s = Simulator(); m = MemoryNode(s, "m0", channels=1, bw_gbps=10.0)
    s.process(m.access(1000)); s.process(m.access(1000)); s.run()
    ts = [v for _, v in s.metrics.samples["m0.access_ns"]]
    assert ts[1] == 2 * ts[0]


def test_storage_write_slower_than_read():
    s = Simulator(); d = StorageNode(s, "s0")
    r = run(s, d.io(4 * KB)); s2 = Simulator(); d2 = StorageNode(s2, "s0")
    w = run(s2, d2.io(4 * KB, write=True))
    assert w > r


def test_accelerator_kernel():
    s = Simulator(); a = AcceleratorNode(s, "g0", units=8, tflops_per_unit=10.0)
    t = run(s, a.kernel(1e12, 4))                    # 1 TFLOP on 40 TFLOPs
    assert abs(t - (10 * US + 1e12 / (4 * 1e4))) < 1e-3


if __name__ == "__main__":
    for f in (test_compute_scales_with_cores, test_memory_latency_and_contention,
              test_storage_write_slower_than_read, test_accelerator_kernel):
        f(); print("PASS", f.__name__)
