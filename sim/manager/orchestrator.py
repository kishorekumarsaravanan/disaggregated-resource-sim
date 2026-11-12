"""Orchestrator: allocate / grow / shrink / migrate / rebalance, with control-plane and data-movement costs."""
from .policies import POLICIES
from ..resources.base import ResourceType

EPS = 1e-9


class Orchestrator:
    def __init__(self, sim, fabric, registry, policy="nearest_fit", slack=0.1):
        self.sim, self.fabric, self.registry = sim, fabric, registry
        self.cfg = sim.config.manager
        self.policy = POLICIES[policy]
        self.slack = slack
        self.apps = {}
        self._busy, self._waiters = False, []

    def add_app(self, app):
        self.apps[app.name] = app
        return app

    # --- control plane is single-threaded: one operation at a time, FIFO ---------------------------------
    def _acquire(self):
        if self._busy:
            ev = self.sim.env.event()
            self._waiters.append(ev)
            yield ev                                   # lock is handed over directly, _busy stays True
        else:
            self._busy = True

    def _unlock(self):
        if self._waiters:
            self._waiters.pop(0).succeed()
        else:
            self._busy = False

    def _locked(self, gen):
        t0 = self.sim.now
        yield from self._acquire()
        self.sim.metrics.sample("mgr.lock_wait_ns", self.sim.now - t0)
        result = yield from gen
        self._unlock()
        return result

    def allocate(self, app, rtype, amount, kind="alloc"):
        return self._locked(self._allocate(app, rtype, amount, kind))

    def grow(self, app, rtype, amount):
        return self._locked(self._grow(app, rtype, amount))

    def shrink(self, app, rtype, amount):
        return self._locked(self._shrink(app, rtype, amount))

    def release_all(self, app):
        return self._locked(self._release_all(app))

    def migrate(self, app, alloc, dest_name):
        return self._locked(self._migrate(app, alloc, dest_name))

    def reconcile(self, app):
        return self._locked(self._reconcile(app))

    def rebalance_once(self):
        return self._locked(self._rebalance_once())

    def _node(self, name):
        return self.sim.components[name]

    def _record(self, kind, t0):
        self.sim.metrics.sample(f"mgr.{kind}_ns", self.sim.now - t0)
        self.sim.metrics.inc(f"mgr.{kind}_ops")

    def _allocate(self, app, rtype, amount, kind="alloc"):
        """Generator. Returns list of Allocation (may span nodes) or None if the request cannot be met."""
        t0 = self.sim.now
        yield self.sim.timeout(2 * self.cfg.control_msg_ns)                 # request + decision
        order = self.policy(self.fabric, app.anchor, self.registry.candidates(rtype), amount)
        got, remaining = [], amount
        for v in order:
            node = self._node(v.name)
            take = min(remaining, node.free)                                # verify against the real node, not the stale view
            if take <= EPS:
                continue
            yield self.sim.timeout(self.cfg.control_msg_ns)                 # command to node
            a = node.allocate(app.name, take)
            if a:
                got.append(a); remaining -= take
                self.registry.refresh(node)
            if remaining <= EPS:
                break
        if remaining > EPS:                                                 # all-or-nothing
            for a in got:
                n = self._node(a.node); n.release(a.alloc_id); self.registry.refresh(n)
            self.sim.metrics.inc("mgr.failed_allocs")
            return None
        yield self.sim.timeout(self.cfg.reconfig_base_ns)                   # map resources into the app's composed system
        app.allocs.extend(got)
        if rtype == ResourceType.COMPUTE and app.anchor is None and got:
            app.anchor = got[0].node
        self._record(kind, t0)
        return got

    def _grow(self, app, rtype, amount):
        return self._allocate(app, rtype, amount, kind="grow")

    def _shrink(self, app, rtype, amount):
        """Generator. Release `amount`, furthest-from-anchor allocations first. Returns amount actually freed."""
        t0 = self.sim.now
        yield self.sim.timeout(self.cfg.control_msg_ns)
        allocs = sorted(app.allocs_of(rtype),
                        key=lambda a: -(self.fabric.hops(app.anchor, a.node) if app.anchor else 0))
        freed = 0.0
        for a in allocs:
            if freed >= amount - EPS:
                break
            cut = min(a.amount, amount - freed)
            node = self._node(a.node)
            yield self.sim.timeout(self.cfg.control_msg_ns)
            if cut >= a.amount - EPS:
                node.release(a.alloc_id); app.allocs.remove(a)
            else:
                node.resize(a.alloc_id, -cut)
            self.registry.refresh(node)
            freed += cut
        yield self.sim.timeout(self.cfg.reconfig_base_ns)
        self._record("shrink", t0)
        return freed

    def _release_all(self, app):
        for a in list(app.allocs):
            n = self._node(a.node); n.release(a.alloc_id); self.registry.refresh(n)
        app.allocs.clear()
        yield self.sim.timeout(self.cfg.control_msg_ns)

    def _migrate(self, app, alloc, dest_name):
        """Generator. Move a (memory/storage) allocation to another node; data crosses the fabric."""
        t0 = self.sim.now
        dest, src = self._node(dest_name), self._node(alloc.node)
        yield self.sim.timeout(2 * self.cfg.control_msg_ns)
        new = dest.allocate(app.name, alloc.amount)
        if not new:
            self.sim.metrics.inc("mgr.failed_migrations")
            return None
        t_copy = self.sim.now
        yield from self.fabric.transfer(src.name, dest.name, alloc.amount)
        floor = alloc.amount / self.cfg.migrate_gbps                         # copy-engine limit
        if self.sim.now - t_copy < floor:
            yield self.sim.timeout(floor - (self.sim.now - t_copy))
        yield self.sim.timeout(self.cfg.reconfig_base_ns)                    # remap + cutover
        src.release(alloc.alloc_id)
        app.allocs.remove(alloc); app.allocs.append(new)
        self.registry.refresh(src); self.registry.refresh(dest)
        self.sim.metrics.inc("mgr.migrated_bytes", alloc.amount)
        self._record("migrate", t0)
        return new

    def _reconcile(self, app):
        """Generator. Bring one app's holdings in line with its current demand (shrink surplus, grow deficit,
        partial grant if the pool is short). Returns ns spent."""
        t0 = self.sim.now
        for rtype, want in list(app.demand.items()) + [(rt, 0) for rt in {a.rtype for a in app.allocs} - set(app.demand)]:
            held = app.held(rtype)
            if held > want * (1 + self.slack) + EPS:
                yield from self._shrink(app, rtype, held - want)
            elif want - held > EPS:
                got = yield from self._grow(app, rtype, want - held)
                if got is None:
                    free = sum(self._node(v.name).free for v in self.registry.candidates(rtype))
                    if free > EPS:
                        self.sim.metrics.inc("mgr.partial_grants")
                        yield from self._grow(app, rtype, min(want - held, free))
        return self.sim.now - t0

    def _rebalance_once(self):
        """Generator. Reclaim surplus from apps, then satisfy deficits (largest first)."""
        for app in self.apps.values():
            for rtype, want in app.demand.items():
                held = app.held(rtype)
                if held > want * (1 + self.slack) + EPS:
                    yield from self._shrink(app, rtype, held - want)
        deficits = sorted(((want - app.held(rt), app, rt)
                           for app in self.apps.values() for rt, want in app.demand.items()
                           if want - app.held(rt) > EPS), key=lambda x: -x[0])
        for deficit, app, rt in deficits:
            got = yield from self._grow(app, rt, deficit)
            if got is None:                                                  # pool short: grant what is free
                free = sum(self._node(v.name).free for v in self.registry.candidates(rt))
                if free > EPS:
                    self.sim.metrics.inc("mgr.partial_grants")
                    yield from self._grow(app, rt, min(deficit, free))

    def run_rebalancer(self, interval_ns):
        while True:
            yield self.sim.timeout(interval_ns)
            yield from self.rebalance_once()
