"""Base class for all disaggregated resource nodes."""
from dataclasses import dataclass
from enum import Enum


class ResourceType(Enum):
    COMPUTE = "compute"
    MEMORY = "memory"
    STORAGE = "storage"
    ACCEL = "accelerator"


@dataclass
class Allocation:
    alloc_id: int
    node: str
    rtype: ResourceType
    amount: float          # cores / bytes / bytes / accel units
    owner: str             # application id


class ResourceNode:
    """A node in one pool. Tracks capacity and allocations; subclasses add behaviour."""
    rtype: ResourceType
    _next_id = 0

    def __init__(self, sim, name, capacity, rack=0):
        self.sim, self.name, self.capacity, self.rack = sim, name, capacity, rack
        self.allocations: dict[int, Allocation] = {}
        self.alive = True
        sim.register(self)

    @property
    def used(self):
        return sum(a.amount for a in self.allocations.values())

    @property
    def free(self):
        return self.capacity - self.used

    @property
    def utilization(self):
        return self.used / self.capacity if self.capacity else 0.0

    def allocate(self, owner, amount):
        if not self.alive or amount > self.free:
            return None
        ResourceNode._next_id += 1
        a = Allocation(ResourceNode._next_id, self.name, self.rtype, amount, owner)
        self.allocations[a.alloc_id] = a
        self.sim.metrics.log("alloc", node=self.name, owner=owner, amount=amount)
        return a

    def release(self, alloc_id):
        a = self.allocations.pop(alloc_id, None)
        if a:
            self.sim.metrics.log("release", node=self.name, owner=a.owner, amount=a.amount)
        return a

    def resize(self, alloc_id, delta):
        a = self.allocations[alloc_id]
        if delta > self.free or a.amount + delta < 0:
            return False
        a.amount += delta
        return True
