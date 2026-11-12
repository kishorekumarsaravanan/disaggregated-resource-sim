"""Simulation core: wraps the SimPy environment, config, RNG, metrics and component registry."""
import random
import simpy

from .config import SimConfig
from .metrics import Metrics


class Simulator:
    def __init__(self, config: SimConfig | None = None):
        self.config = config or SimConfig()
        self.env = simpy.Environment()
        self.rng = random.Random(self.config.seed)
        self.metrics = Metrics(self.env)
        self.components = {}

    @property
    def now(self):
        return self.env.now

    def register(self, component):
        if component.name in self.components:
            raise ValueError(f"duplicate component name: {component.name}")
        self.components[component.name] = component
        return component

    def process(self, gen):
        return self.env.process(gen)

    def timeout(self, delay_ns):
        return self.env.timeout(delay_ns)

    def run(self, until=None):
        """until: a time in ns, a process/event (run until it finishes), or None (run until no events remain)."""
        return self.env.run(until=until)
