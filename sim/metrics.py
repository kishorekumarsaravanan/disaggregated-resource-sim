"""Metrics collector: counters, timestamped samples, and an event log."""
from collections import defaultdict


class Metrics:
    def __init__(self, env):
        self.env = env
        self.counters = defaultdict(float)
        self.samples = defaultdict(list)    # name -> [(t_ns, value)]
        self.events = []                    # (t_ns, kind, details)

    def inc(self, name, amount=1.0):
        self.counters[name] += amount

    def sample(self, name, value):
        self.samples[name].append((self.env.now, value))

    def log(self, kind, **details):
        self.events.append((self.env.now, kind, details))

    def mean(self, name):
        v = [x for _, x in self.samples[name]]
        return sum(v) / len(v) if v else 0.0

    def percentile(self, name, p):
        v = sorted(x for _, x in self.samples[name])
        return v[min(len(v) - 1, int(p / 100 * len(v)))] if v else 0.0
