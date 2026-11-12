"""Pool node models. Each node models LOCAL behaviour only; fabric cost is added in Step 4."""
from .base import ResourceNode, ResourceType
from .queueing import MultiServer
from ..config import GB, US


class ComputeNode(ResourceNode):
    rtype = ResourceType.COMPUTE

    def __init__(self, sim, name, cores=64, ghz=3.0, ipc=2.0, rack=0):
        super().__init__(sim, name, cores, rack)
        self.ghz, self.ipc = ghz, ipc

    def execute(self, instructions, cores):
        """Run `instructions` on `cores` allocated cores. Returns elapsed ns."""
        t = instructions / (cores * self.ghz * self.ipc)     # ns (GHz = cycles/ns)
        yield self.sim.timeout(t)
        self.sim.metrics.inc(f"{self.name}.busy_ns", t)
        return t


class MemoryNode(ResourceNode):
    rtype = ResourceType.MEMORY

    def __init__(self, sim, name, capacity=256 * GB, channels=8, bw_gbps=25.6, latency_ns=None, rack=0):
        super().__init__(sim, name, capacity, rack)
        self.bw = bw_gbps                                    # GB/s per channel = bytes/ns
        self.latency_ns = latency_ns or sim.config.latency.local_dram_ns
        self.channels = MultiServer(sim, channels)

    def access(self, nbytes):
        """Local DRAM access: fixed latency + transfer time, queued on channels."""
        service = self.latency_ns + nbytes / self.bw
        wait, total = yield from self.channels.serve(service)
        self.sim.metrics.sample(f"{self.name}.access_ns", total)
        return total


class StorageNode(ResourceNode):
    rtype = ResourceType.STORAGE

    def __init__(self, sim, name, capacity=8 * 1024 * GB, queue_depth=32, bw_gbps=6.0, latency_ns=None, rack=0):
        super().__init__(sim, name, capacity, rack)
        self.bw = bw_gbps
        self.latency_ns = latency_ns or 80 * US              # device latency (SSD)
        self.queue = MultiServer(sim, queue_depth)

    def io(self, nbytes, write=False):
        service = self.latency_ns * (1.5 if write else 1.0) + nbytes / self.bw
        wait, total = yield from self.queue.serve(service)
        self.sim.metrics.sample(f"{self.name}.io_ns", total)
        return total


class AcceleratorNode(ResourceNode):
    rtype = ResourceType.ACCEL

    def __init__(self, sim, name, units=8, tflops_per_unit=10.0, engines=1, rack=0):
        super().__init__(sim, name, units, rack)
        self.flops_per_ns = tflops_per_unit * 1e3            # 1 TFLOP/s = 1e3 FLOP/ns
        self.engines = MultiServer(sim, engines)

    def kernel(self, flops, units):
        """Launch a kernel using `units` allocated units; local launch overhead included."""
        service = self.sim.config.latency.accel_launch_ns + flops / (units * self.flops_per_ns)
        wait, total = yield from self.engines.serve(service)
        self.sim.metrics.sample(f"{self.name}.kernel_ns", total)
        return total
