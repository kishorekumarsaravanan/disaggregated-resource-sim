"""Three representative application types with time-varying demand."""
from .workload import Phase
from ..resources.base import ResourceType as RT
from ..config import GB, KB, MB

C, M, S, A = RT.COMPUTE, RT.MEMORY, RT.STORAGE, RT.ACCEL


def analytics(scale=1.0):
    """In-memory analytics: small load phase, big memory burst, then cool-down."""
    return [
        Phase("load",  {C: 8,  M: 40 * GB,  S: 50 * GB}, int(400 * scale), instr=2e5, mem_accesses=8, working_set=40 * GB, storage_bytes=64 * KB),
        Phase("burst", {C: 16, M: 180 * GB, S: 50 * GB}, int(1500 * scale), instr=4e5, mem_accesses=16, mem_bytes=8 * KB, working_set=180 * GB),
        Phase("cool",  {C: 4,  M: 20 * GB,  S: 50 * GB}, int(300 * scale), instr=1e5, mem_accesses=4, working_set=20 * GB),
    ]


def ml_training(scale=1.0):
    """ML training: CPU preprocessing, then accelerator-heavy training."""
    return [
        Phase("prep",  {C: 16, M: 24 * GB, S: 200 * GB}, int(200 * scale), instr=1e6, mem_accesses=8, working_set=24 * GB, storage_bytes=256 * KB),
        Phase("train", {C: 8,  M: 48 * GB, A: 8},        int(250 * scale), instr=2e5, mem_accesses=8, mem_bytes=64 * KB, working_set=48 * GB,
              accel_flops=2e10, accel_in=1 * MB, accel_out=64 * KB, streams=2),
    ]


def io_heavy(scale=1.0):
    """Log/ETL processing: storage-bound with modest memory."""
    return [
        Phase("scan",  {C: 8, M: 16 * GB, S: 400 * GB}, int(800 * scale), instr=2e5, mem_accesses=4, working_set=16 * GB, storage_bytes=1 * MB, streams=8),
        Phase("merge", {C: 8, M: 32 * GB, S: 400 * GB}, int(400 * scale), instr=4e5, mem_accesses=8, working_set=32 * GB, storage_bytes=512 * KB),
    ]
