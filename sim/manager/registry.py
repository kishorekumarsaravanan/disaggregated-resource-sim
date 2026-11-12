"""Resource discovery: nodes register, send heartbeats; the orchestrator works from this (possibly stale) view."""
from dataclasses import dataclass


@dataclass
class NodeView:
    name: str
    rtype: object
    rack: int
    capacity: float
    free: float
    last_seen: float


class Registry:
    MISSED_BEATS = 3

    def __init__(self, sim):
        self.sim = sim
        self.view: dict[str, NodeView] = {}
        self.order: list[str] = []

    def register(self, node):
        """Discovery: node announces itself and starts heartbeating."""
        self.view[node.name] = NodeView(node.name, node.rtype, node.rack, node.capacity, node.free, self.sim.now)
        self.order.append(node.name)
        self.sim.metrics.log("discover", node=node.name, rtype=node.rtype.value)
        self.sim.process(self._heartbeat(node))
        return node

    def _heartbeat(self, node):
        hb = self.sim.config.manager.heartbeat_ns
        while True:
            yield self.sim.timeout(hb)
            if node.alive:
                self.refresh(node)
                self.sim.metrics.inc("mgr.heartbeats")

    def refresh(self, node):
        v = self.view[node.name]
        v.free, v.last_seen = node.free, self.sim.now

    def is_alive(self, name):
        v = self.view[name]
        return self.sim.now - v.last_seen <= self.MISSED_BEATS * self.sim.config.manager.heartbeat_ns

    def candidates(self, rtype):
        return [self.view[n] for n in self.order
                if self.view[n].rtype == rtype and self.is_alive(n)]
