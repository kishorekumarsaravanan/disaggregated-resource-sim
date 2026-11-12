"""Remote access = fabric cost + node service. Used by the orchestrator and workloads."""


class RemoteAccess:
    def __init__(self, sim, fabric):
        self.sim, self.fabric = sim, fabric
        self.cfg = sim.config
        self.hdr = sim.config.fabric.header_bytes

    def _record(self, kind, total, node_ns):
        m = self.sim.metrics
        m.sample(f"remote.{kind}.total_ns", total)
        m.sample(f"remote.{kind}.fabric_ns", total - node_ns)

    def mem_read(self, src, mem, nbytes):
        """Compute node `src` reads nbytes from remote MemoryNode `mem`."""
        t0 = self.sim.now
        yield from self.fabric.transfer(src.name, mem.name, self.hdr)          # request
        yield self.sim.timeout(self.cfg.latency.remote_mem_base_ns)            # controller/protocol cost
        node_ns = yield from mem.access(nbytes)
        yield from self.fabric.transfer(mem.name, src.name, nbytes)            # data back
        total = self.sim.now - t0
        self._record("mem", total, node_ns)
        return total

    def storage_io(self, src, st, nbytes, write=False):
        t0 = self.sim.now
        if write:
            yield from self.fabric.transfer(src.name, st.name, nbytes + self.hdr)
            node_ns = yield from st.io(nbytes, write=True)
            yield from self.fabric.transfer(st.name, src.name, self.hdr)       # ack
        else:
            yield from self.fabric.transfer(src.name, st.name, self.hdr)
            node_ns = yield from st.io(nbytes)
            yield from self.fabric.transfer(st.name, src.name, nbytes)
        total = self.sim.now - t0
        self._record("storage", total, node_ns)
        return total

    def accel_run(self, src, acc, flops, units, in_bytes, out_bytes):
        t0 = self.sim.now
        yield from self.fabric.transfer(src.name, acc.name, in_bytes + self.hdr)
        node_ns = yield from acc.kernel(flops, units)
        yield from self.fabric.transfer(acc.name, src.name, out_bytes)
        total = self.sim.now - t0
        self._record("accel", total, node_ns)
        return total
