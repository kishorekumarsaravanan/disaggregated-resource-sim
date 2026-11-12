"""How an application touches its resources: through the fabric (disaggregated) or directly (local baseline)."""
from ..resources.base import ResourceType as RT


class Access:
    def __init__(self, sim, remote=None, mode="remote"):
        self.sim, self.remote, self.mode = sim, remote, mode        # mode: "remote" | "local"

    def _pick(self, app, rtype):
        allocs = app.allocs_of(rtype)
        if not allocs:
            return None
        w = [a.amount for a in allocs]
        return self.sim.rng.choices(allocs, weights=w)[0]

    def _src(self, app):
        return self.sim.components[app.anchor]

    def mem(self, app, nbytes):
        a = self._pick(app, RT.MEMORY)
        node = self.sim.components[a.node]
        if self.mode == "local":
            return (yield from node.access(nbytes))
        return (yield from self.remote.mem_read(self._src(app), node, nbytes))

    def storage(self, app, nbytes, write=False):
        a = self._pick(app, RT.STORAGE)
        if a:
            node = self.sim.components[a.node]
        else:                                                       # no storage held: use the nearest-by-name shared store
            node = next(c for c in self.sim.components.values() if c.rtype == RT.STORAGE)
        if self.mode == "local":
            return (yield from node.io(nbytes, write))
        return (yield from self.remote.storage_io(self._src(app), node, nbytes, write))

    def accel(self, app, flops, in_bytes, out_bytes):
        a = self._pick(app, RT.ACCEL)
        node = self.sim.components[a.node]
        units = sum(x.amount for x in app.allocs_of(RT.ACCEL) if x.node == a.node)
        if self.mode == "local":
            return (yield from node.kernel(flops, units))
        return (yield from self.remote.accel_run(self._src(app), node, flops, units, in_bytes, out_bytes))
