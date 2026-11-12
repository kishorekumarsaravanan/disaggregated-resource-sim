"""Phase-based application workload. Demand changes per phase; ops hit compute, memory, storage, accelerator."""
from dataclasses import dataclass, field
from ..resources.base import ResourceType as RT
from ..config import KB, US

CPU_FLOPS_PER_INSTR = 8          # CPU fallback when no accelerator is held
PAGE = 4 * KB


@dataclass
class Phase:
    name: str
    demand: dict                  # ResourceType -> amount wanted during this phase
    ops: int                      # total operations in the phase
    instr: float = 0.0            # compute instructions per op
    mem_accesses: int = 0         # memory reads per op
    mem_bytes: int = 4 * KB       # bytes per memory read
    working_set: float = 0.0      # bytes; if held memory is smaller, the shortfall fraction of reads becomes page-ins from storage
    storage_bytes: int = 0        # storage read per op
    accel_flops: float = 0.0
    accel_in: int = 0
    accel_out: int = 0
    streams: int = 4              # concurrent op streams


class Workload:
    def __init__(self, sim, app, phases, orch, access, start_ns=0, dynamic=True, release_at_end=True):
        self.sim, self.app, self.phases, self.orch, self.access = sim, app, phases, orch, access
        self.start_ns, self.dynamic, self.release_at_end = start_ns, dynamic, release_at_end
        self.finished_at = None

    def _m(self, name):
        return f"app.{self.app.name}.{name}"

    def run(self):
        sim, app, m = self.sim, self.app, self.sim.metrics
        yield sim.timeout(self.start_ns)
        t_start = sim.now
        for ph in self.phases:
            app.demand = dict(ph.demand)
            t0 = sim.now
            if self.dynamic:
                yield from self.orch.reconcile(app)
            m.sample(self._m("reconf_wait_ns"), sim.now - t0)
            t1 = sim.now
            share, extra = divmod(ph.ops, ph.streams)
            procs = [sim.process(self._stream(ph, share + (1 if i < extra else 0))) for i in range(ph.streams)]
            for p in procs:
                yield p
            m.sample(self._m(f"phase.{ph.name}_ns"), sim.now - t1)
        if self.release_at_end and self.dynamic:
            app.demand = {}
            yield from self.orch.reconcile(app)
        self.finished_at = sim.now
        m.sample(self._m("completion_ns"), sim.now - t_start)

    def _stream(self, ph, n_ops):
        for _ in range(n_ops):
            yield from self._op(ph)

    def _op(self, ph):
        sim, app, m, acc = self.sim, self.app, self.sim.metrics, self.access
        cores = app.held(RT.COMPUTE) / ph.streams
        while cores <= 0:                                           # starved: no compute granted yet
            m.inc(self._m("starved"))
            yield sim.timeout(100 * US)
            cores = app.held(RT.COMPUTE) / ph.streams
        t0 = sim.now
        node = sim.components[app.anchor]
        if ph.instr:
            yield from node.execute(ph.instr, cores)
        held_mem = app.held(RT.MEMORY)
        miss = max(0.0, 1 - held_mem / ph.working_set) if ph.working_set else 0.0
        for _ in range(ph.mem_accesses):
            if held_mem <= 0 or sim.rng.random() < miss:            # capacity miss -> page-in from storage
                m.inc(self._m("page_ins"))
                yield from acc.storage(app, PAGE)
            else:
                yield from acc.mem(app, ph.mem_bytes)
        if ph.storage_bytes:
            yield from acc.storage(app, ph.storage_bytes)
        if ph.accel_flops:
            if app.held(RT.ACCEL) > 0:
                yield from acc.accel(app, ph.accel_flops, ph.accel_in, ph.accel_out)
            else:                                                   # CPU fallback
                m.inc(self._m("cpu_fallback"))
                yield from node.execute(ph.accel_flops / CPU_FLOPS_PER_INSTR, cores)
        m.sample(self._m("op_ns"), sim.now - t0)
