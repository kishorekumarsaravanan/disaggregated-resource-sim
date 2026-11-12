"""Application record the orchestrator manages."""
from dataclasses import dataclass, field


@dataclass
class App:
    name: str
    anchor: str | None = None                          # compute node used for locality decisions
    demand: dict = field(default_factory=dict)         # ResourceType -> amount the app wants now
    allocs: list = field(default_factory=list)         # live Allocation objects

    def held(self, rtype):
        return sum(a.amount for a in self.allocs if a.rtype == rtype)

    def allocs_of(self, rtype):
        return [a for a in self.allocs if a.rtype == rtype]
