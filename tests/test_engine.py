import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sim.engine import Simulator
from sim.resources.base import ResourceNode, ResourceType
from sim.config import GB, US


class Dummy(ResourceNode):
    rtype = ResourceType.MEMORY


def test_clock_and_processes():
    sim = Simulator()
    order = []

    def worker(name, delay):
        yield sim.timeout(delay)
        order.append((name, sim.now))

    sim.process(worker("a", 5 * US))
    sim.process(worker("b", 2 * US))
    sim.run()
    assert order == [("b", 2 * US), ("a", 5 * US)]


def test_allocation_lifecycle():
    sim = Simulator()
    n = Dummy(sim, "mem0", 64 * GB)
    a = n.allocate("appA", 16 * GB)
    assert a and n.free == 48 * GB
    assert n.allocate("appB", 60 * GB) is None       # over capacity rejected
    assert n.resize(a.alloc_id, 8 * GB) and n.used == 24 * GB
    n.release(a.alloc_id)
    assert n.used == 0


def test_duplicate_name_rejected():
    sim = Simulator()
    Dummy(sim, "x", 1)
    try:
        Dummy(sim, "x", 1)
        assert False
    except ValueError:
        pass


if __name__ == "__main__":
    for f in (test_clock_and_processes, test_allocation_lifecycle, test_duplicate_name_rejected):
        f(); print("PASS", f.__name__)
