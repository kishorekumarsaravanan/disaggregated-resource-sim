"""Lightweight k-server FIFO queue (no SimPy Resource needed): tracks when each server frees up."""


class MultiServer:
    def __init__(self, sim, servers=1):
        self.sim = sim
        self.free_at = [0] * servers
        self.busy_ns = 0

    def serve(self, service_ns):
        """Generator: wait for a server, run for service_ns. Returns (wait_ns, total_ns)."""
        now = self.sim.now
        i = min(range(len(self.free_at)), key=self.free_at.__getitem__)
        start = max(now, self.free_at[i])
        end = start + service_ns
        self.free_at[i] = end
        self.busy_ns += service_ns
        yield self.sim.timeout(end - now)
        return start - now, end - now

    @property
    def queue_depth_hint(self):
        return sum(1 for t in self.free_at if t > self.sim.now)
