"""Global parameters. All times are in nanoseconds, sizes in bytes, bandwidth in bytes/ns (= GB/s)."""
from dataclasses import dataclass, field

NS, US, MS, SEC = 1, 1_000, 1_000_000, 1_000_000_000
KB, MB, GB = 1 << 10, 1 << 20, 1 << 30


@dataclass
class FabricConfig:
    hop_latency_ns: int = 150          # per switch hop
    link_bw_gbps: float = 32.0         # GB/s per link
    hops_intra_rack: int = 2
    hops_inter_rack: int = 4
    rack_uplink_gbps: float = 64.0     # shared rack-to-spine bandwidth (oversubscribed)
    header_bytes: int = 64             # request/control packet size


@dataclass
class LatencyConfig:
    local_dram_ns: int = 100
    remote_mem_base_ns: int = 300      # added to hop latency
    remote_storage_ns: int = 20 * US
    accel_launch_ns: int = 10 * US


@dataclass
class ManagerConfig:
    heartbeat_ns: int = 1 * MS
    control_msg_ns: int = 5 * US       # orchestrator <-> node message cost
    reconfig_base_ns: int = 50 * US    # fixed cost to remap a resource
    migrate_gbps: float = 10.0         # GB/s when moving memory pages


@dataclass
class SimConfig:
    seed: int = 42
    fabric: FabricConfig = field(default_factory=FabricConfig)
    latency: LatencyConfig = field(default_factory=LatencyConfig)
    manager: ManagerConfig = field(default_factory=ManagerConfig)
