"""
freq_space.py
-------------
Discovers all available frequency levels directly from the connected device via adb:
  - CPU cores  : per-cluster scaling_available_frequencies
                 (Qualcomm devices have little/mid/prime clusters with different tables)
  - DDR        : /sys/devices/system/cpu/bus_dcvs/DDR/available_frequencies
  - DDRQOS     : binary (0 = off, 1 = on)
  - LLCC       : /sys/devices/system/cpu/bus_dcvs/LLCC/available_frequencies

A device must be connected via adb at all times.
"""

import subprocess
import logging

logger = logging.getLogger(__name__)


def _adb(cmd: str, timeout: int = 15) -> str:
    """Run an adb shell command and return stdout (stripped). Raises on failure."""
    result = subprocess.run(
        ["adb", "shell", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    out = result.stdout.strip()
    if not out:
        err = result.stderr.strip()
        raise RuntimeError(
            f"adb command returned empty output.\n"
            f"  cmd : {cmd}\n"
            f"  stderr: {err}"
        )
    return out


def _adb_freqs(path: str) -> list:
    """Read a sysfs frequency list and return sorted list of ints (kHz)."""
    raw = _adb(f"cat {path}")
    freqs = sorted(int(f) for f in raw.split())
    if not freqs:
        raise RuntimeError(f"No frequencies found at {path}")
    return freqs


def discover_num_cpus() -> int:
    raw = _adb("nproc")
    n = int(raw)
    logger.info(f"Device has {n} CPUs")
    return n


def discover_cpu_freqs_per_core(num_cpus: int) -> dict:
    """
    Return a dict mapping cpu_id → sorted list of available frequencies (kHz).

    CPUs in the same cluster share one PLL and therefore one frequency table.
    We read only the first CPU of each cluster (the policy's representative)
    and copy the result to all sibling CPUs — avoiding redundant adb calls
    and redundant log lines.

    Cluster layout is discovered dynamically by comparing frequency tables:
    if cpu[i] has the same table as cpu[i-1], it's in the same cluster.
    """
    per_core = {}
    cluster_rep = {}   # freq_table_key → representative cpu_id

    for i in range(num_cpus):
        path = (f"/sys/devices/system/cpu/cpu{i}/cpufreq/"
                f"scaling_available_frequencies")
        try:
            freqs = _adb_freqs(path)
            key   = tuple(freqs)

            if key not in cluster_rep:
                # First CPU seen with this freq table → new cluster
                cluster_rep[key] = i
                logger.info(
                    f"Cluster representative CPU{i} "
                    f"({len(freqs)} freqs, "
                    f"{freqs[0]}–{freqs[-1]} kHz): {freqs}"
                )
            # All CPUs in the cluster share the same table
            per_core[i] = freqs
        except Exception as e:
            logger.warning(f"Could not read CPU{i} freqs: {e}")
            per_core[i] = per_core.get(0, [])

    return per_core


def discover_ddr_freqs() -> list:
    path = "/sys/devices/system/cpu/bus_dcvs/DDR/available_frequencies"
    freqs = _adb_freqs(path)
    logger.info(f"DDR available freqs ({len(freqs)}): {freqs}")
    return freqs


def discover_llcc_freqs() -> list:
    path = "/sys/devices/system/cpu/bus_dcvs/LLCC/available_frequencies"
    freqs = _adb_freqs(path)
    logger.info(f"LLCC available freqs ({len(freqs)}): {freqs}")
    return freqs


class FrequencySpace:
    """
    Holds all discrete frequency levels for every tunable knob,
    discovered live from the connected device.

    Per-core CPU frequencies are supported — Qualcomm devices have
    little / mid / prime clusters with different max frequencies.

    Attributes
    ----------
    cpu_freqs_per_core : dict[int, list[int]]  – per-CPU freq tables (kHz)
    cpu_freqs          : list[int]  – union of all unique CPU freqs (for action space)
    ddr_freqs          : list[int]  – DDR boost_freq levels (kHz)
    ddrqos_freqs       : list[int]  – DDRQOS boost_freq levels  [0, 1]
    llcc_freqs         : list[int]  – LLCC boost_freq levels (kHz)
    num_cpus           : int        – number of CPU cores
    cpu_masks          : list[int]  – taskset decimal masks (CPU i → 1 << i)
    """

    def __init__(self):
        logger.info("Discovering frequency space from device...")
        self.num_cpus          = discover_num_cpus()
        self.cpu_freqs_per_core = discover_cpu_freqs_per_core(self.num_cpus)
        self.ddr_freqs         = discover_ddr_freqs()
        self.ddrqos_freqs      = [0, 1]
        self.llcc_freqs        = discover_llcc_freqs()

        # Union of all unique CPU frequencies across all cores (sorted)
        all_freqs = set()
        for freqs in self.cpu_freqs_per_core.values():
            all_freqs.update(freqs)
        self.cpu_freqs = sorted(all_freqs)

        # taskset uses decimal masks: CPU i → 1 << i
        self.cpu_masks = [1 << i for i in range(self.num_cpus)]

        logger.info(
            f"Union CPU freqs ({len(self.cpu_freqs)}): {self.cpu_freqs}"
        )

    def valid_freq_for_cpu(self, cpu_freq: int, cpu_id: int) -> int:
        """
        Return the closest valid frequency for cpu_id that is <= cpu_freq.
        If cpu_freq exceeds the core's max, clamp to its maximum.
        """
        valid = self.cpu_freqs_per_core.get(cpu_id, self.cpu_freqs)
        # Find largest valid freq that does not exceed cpu_freq
        candidates = [f for f in valid if f <= cpu_freq]
        if candidates:
            return max(candidates)
        return min(valid)   # cpu_freq is below all valid freqs → use minimum

    @property
    def total_combinations(self) -> int:
        return (
            len(self.cpu_freqs)
            * len(self.ddr_freqs)
            * len(self.ddrqos_freqs)
            * len(self.llcc_freqs)
            * self.num_cpus
        )

    def decode_action(self, action_idx: int) -> dict:
        """
        Convert a flat integer action index into a configuration dict.
        Encoding order (least-significant first):
          target_cpu → llcc_idx → ddrqos_idx → ddr_idx → cpu_freq_idx
        """
        n_cpu    = self.num_cpus
        n_llcc   = len(self.llcc_freqs)
        n_ddrqos = len(self.ddrqos_freqs)
        n_ddr    = len(self.ddr_freqs)

        idx = action_idx
        target_cpu   = idx % n_cpu;    idx //= n_cpu
        llcc_idx     = idx % n_llcc;   idx //= n_llcc
        ddrqos_idx   = idx % n_ddrqos; idx //= n_ddrqos
        ddr_idx      = idx % n_ddr;    idx //= n_ddr
        cpu_freq_idx = idx % len(self.cpu_freqs)

        requested_cpu_freq = self.cpu_freqs[cpu_freq_idx]
        # Clamp to what the target CPU actually supports
        actual_cpu_freq = self.valid_freq_for_cpu(requested_cpu_freq, target_cpu)

        return {
            "cpu_freq":     actual_cpu_freq,
            "ddr_freq":     self.ddr_freqs[ddr_idx],
            "ddrqos_freq":  self.ddrqos_freqs[ddrqos_idx],
            "llcc_freq":    self.llcc_freqs[llcc_idx],
            "target_cpu":   target_cpu,
            "taskset_mask": str(self.cpu_masks[target_cpu]),
            # indices for state encoding
            "_cpu_freq_idx":  cpu_freq_idx,
            "_ddr_idx":       ddr_idx,
            "_ddrqos_idx":    ddrqos_idx,
            "_llcc_idx":      llcc_idx,
        }

    def encode_action(self, cpu_freq_idx, ddr_idx, ddrqos_idx, llcc_idx, target_cpu) -> int:
        n_cpu    = self.num_cpus
        n_llcc   = len(self.llcc_freqs)
        n_ddrqos = len(self.ddrqos_freqs)
        n_ddr    = len(self.ddr_freqs)
        return (
            target_cpu
            + n_cpu * (
                llcc_idx
                + n_llcc * (
                    ddrqos_idx
                    + n_ddrqos * (
                        ddr_idx
                        + n_ddr * cpu_freq_idx
                    )
                )
            )
        )

    def __repr__(self):
        return (
            f"FrequencySpace("
            f"union_cpu_freqs={len(self.cpu_freqs)}, "
            f"ddr_freqs={len(self.ddr_freqs)}, "
            f"ddrqos_freqs={len(self.ddrqos_freqs)}, "
            f"llcc_freqs={len(self.llcc_freqs)}, "
            f"num_cpus={self.num_cpus}, "
            f"total_combinations={self.total_combinations:,})"
        )