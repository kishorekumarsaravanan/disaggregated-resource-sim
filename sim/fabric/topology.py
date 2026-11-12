"""Interconnect model: per-node ports + per-rack uplinks, hop latency, cut-through with contention."""


class Link:
    def __init__(self, name, bw):
        self.name, self.bw = name, bw        # bw in bytes/ns
        self.free_at = 0.0
        self.bytes = 0.0
        self.busy_ns = 0.0


class Fabric:
    def __init__(self, sim):
        self.sim, self.cfg = sim, sim.config.fabric
        self.ports: dict[str, Link] = {}
        self.uplinks: dict[int, Link] = {}
        self.racks: dict[str, int] = {}

    def attach(self, node):
        self.racks[node.name] = node.rack
        self.ports[node.name] = Link(f"port:{node.name}", self.cfg.link_bw_gbps)
        if node.rack not in self.uplinks:
            self.uplinks[node.rack] = Link(f"uplink:rack{node.rack}", self.cfg.rack_uplink_gbps)
        return node

    def hops(self, a, b):
        if a == b:
            return 0
        return self.cfg.hops_intra_rack if self.racks[a] == self.racks[b] else self.cfg.hops_inter_rack

    def path(self, a, b):
        links = [self.ports[a], self.ports[b]]
        if self.racks[a] != self.racks[b]:
            links += [self.uplinks[self.racks[a]], self.uplinks[self.racks[b]]]
        return links

    def transfer(self, a, b, nbytes):
        """Generator: move nbytes from node a to node b. Returns elapsed ns (queueing + serialization + propagation)."""
        if a == b:
            return 0.0
        now = self.sim.now
        links = self.path(a, b)
        start = max(now, max(l.free_at for l in links))     # all links on path busy together (cut-through)
        ser = nbytes / min(l.bw for l in links)             # bottleneck serialization
        for l in links:
            l.free_at = start + ser
            l.bytes += nbytes
            l.busy_ns += ser
        elapsed = (start - now) + ser + self.hops(a, b) * self.cfg.hop_latency_ns
        yield self.sim.timeout(elapsed)
        m = self.sim.metrics
        m.inc("fabric.bytes", nbytes)
        m.sample("fabric.transfer_ns", elapsed)
        m.sample("fabric.queue_ns", start - now)
        return elapsed

    def utilization(self, link, horizon_ns=None):
        t = horizon_ns or self.sim.now
        return link.busy_ns / t if t else 0.0
