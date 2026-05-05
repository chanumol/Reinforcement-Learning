"""
env.py
------
RL Environment: AndroidFreqEnv

Each step:
  1. Applies a frequency configuration to the connected device via adb
  2. Runs FullRandLat memlat benchmark on the chosen CPU
  3. Parses the measured latency (ns) from benchmark output
  4. Returns (next_state, reward, done, info)

State vector (7 floats, all normalised to [0, 1]):
  [cpu_freq_idx_norm, ddr_freq_idx_norm, ddrqos_freq_idx_norm,
   llcc_freq_idx_norm, target_cpu_norm,
   last_latency_norm, step_norm]

Reward:
  reward = -latency_ns / 1_000_000   (maximising reward = minimising latency)
  PENALTY_LATENCY_NS is returned when the benchmark fails to produce output.
"""

import re
import subprocess
import time
import logging
import numpy as np

from freq_space import FrequencySpace

logger = logging.getLogger(__name__)

BENCHMARK_BINARY      = "/data/local/tmp/FullRandLat"
BENCHMARK_ARGS        = "memlat -min-buffer-size-kb 40960 -max-buffer-size-kb 40960"
BENCHMARK_TIMEOUT_SEC = 120
PENALTY_LATENCY_NS    = 10_000_000   # 10 ms penalty when output cannot be parsed
MAX_STEPS_PER_EPISODE = 200

# cpufreq policy nodes on this device (Qualcomm, 3 clusters)
# policy0 → CPU0-2 (little), policy3 → CPU3-5 (mid), policy6 → CPU6-7 (prime)
CPU_POLICY_NODES = [
    "/sys/devices/system/cpu/cpufreq/policy0",
    "/sys/devices/system/cpu/cpufreq/policy3",
    "/sys/devices/system/cpu/cpufreq/policy6",
]

# Map each CPU to its shared policy node (hardware constraint: all CPUs in a
# cluster share one PLL, so frequency must be set at the policy level)
CPU_TO_POLICY = {
    0: "/sys/devices/system/cpu/cpufreq/policy0",
    1: "/sys/devices/system/cpu/cpufreq/policy0",
    2: "/sys/devices/system/cpu/cpufreq/policy0",
    3: "/sys/devices/system/cpu/cpufreq/policy3",
    4: "/sys/devices/system/cpu/cpufreq/policy3",
    5: "/sys/devices/system/cpu/cpufreq/policy3",
    6: "/sys/devices/system/cpu/cpufreq/policy6",
    7: "/sys/devices/system/cpu/cpufreq/policy6",
}


class AndroidFreqEnv:
    """
    OpenAI-Gym-style environment that controls an Android device via adb.
    A device must be connected at all times.
    """

    def __init__(self, freq_space: FrequencySpace):
        self.fs        = freq_space
        self.n_actions = freq_space.total_combinations
        self.state_dim = 7

        self._step_count   = 0
        self._last_latency = PENALTY_LATENCY_NS
        self._last_config  = None
        self._best_latency = float("inf")
        self._best_config  = None

    # ── Public API ────────────────────────────────────────────────────────────

    def reset(self) -> np.ndarray:
        self._step_count   = 0
        self._last_latency = PENALTY_LATENCY_NS
        self._last_config  = None
        return self._make_state(0, 0, 0, 0, 0)

    def step(self, action_idx: int):
        cfg = self.fs.decode_action(action_idx)
        self._last_config = cfg
        self._step_count += 1

        # 1. Apply frequencies to device
        self._apply_config(cfg)

        # 2. Run benchmark
        latency_ns = self._run_benchmark(cfg["taskset_mask"])
        self._last_latency = latency_ns

        # 3. Track global best
        if latency_ns < self._best_latency:
            self._best_latency = latency_ns
            mask_dec = cfg["taskset_mask"]                    # decimal string, e.g. "128"
            mask_hex = hex(int(mask_dec))                     # hex string, e.g. "0x80"
            self._best_config  = {
                "cpu_freq":          cfg["cpu_freq"],
                "ddr_freq":          cfg["ddr_freq"],
                "ddrqos_freq":       cfg["ddrqos_freq"],
                "llcc_freq":         cfg["llcc_freq"],
                "target_cpu":        cfg["target_cpu"],
                "taskset_mask":      mask_dec,
                "taskset_mask_hex":  mask_hex,
                "latency_ns":        latency_ns,
            }
            logger.info(
                "[NEW BEST] latency=%d ns | cpu=%d kHz | ddr=%d kHz | "
                "ddrqos=%d | llcc=%d kHz | CPU%d (taskset %s / %s)",
                latency_ns,
                cfg["cpu_freq"], cfg["ddr_freq"],
                cfg["ddrqos_freq"], cfg["llcc_freq"],
                cfg["target_cpu"], mask_dec, mask_hex,
            )

        # 4. Reward
        reward = -latency_ns / 1_000_000   # negative ms

        # 5. Next state
        next_state = self._make_state(
            cfg["_cpu_freq_idx"],
            cfg["_ddr_idx"],
            cfg["_ddrqos_idx"],
            cfg["_llcc_idx"],
            cfg["target_cpu"],
        )

        done = self._step_count >= MAX_STEPS_PER_EPISODE

        info = {
            "latency_ns": latency_ns,
            "config":     cfg,
            "step":       self._step_count,
        }
        return next_state, reward, done, info

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _make_state(self, cpu_idx, ddr_idx, ddrqos_idx, llcc_idx, target_cpu) -> np.ndarray:
        n_cpu_f  = max(len(self.fs.cpu_freqs) - 1, 1)
        n_ddr    = max(len(self.fs.ddr_freqs) - 1, 1)
        n_ddrqos = max(len(self.fs.ddrqos_freqs) - 1, 1)
        n_llcc   = max(len(self.fs.llcc_freqs) - 1, 1)
        n_cpus   = max(self.fs.num_cpus - 1, 1)

        return np.array([
            cpu_idx    / n_cpu_f,
            ddr_idx    / n_ddr,
            ddrqos_idx / n_ddrqos,
            llcc_idx   / n_llcc,
            target_cpu / n_cpus,
            min(self._last_latency, PENALTY_LATENCY_NS) / PENALTY_LATENCY_NS,
            self._step_count / MAX_STEPS_PER_EPISODE,
        ], dtype=np.float32)

    def _adb(self, cmd: str, timeout: int = 30) -> str:
        """
        Run an adb shell command and return combined stdout+stderr (stripped).
        FullRandLat writes its output to stderr on some builds, so we merge both.
        If the device is disconnected, waits up to 120 s for it to reconnect.
        """
        for attempt in range(3):
            try:
                r = subprocess.run(
                    ["adb", "shell", cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
                output = r.stdout.decode("utf-8", errors="replace").strip()
                # Detect device disconnection
                if "no devices/emulators found" in output or "error: closed" in output:
                    logger.warning(
                        "Device disconnected (attempt %d/3). "
                        "Waiting 30s for reconnect...", attempt + 1
                    )
                    time.sleep(30)
                    continue
                return output
            except subprocess.TimeoutExpired:
                logger.warning("adb timeout (%ds): %s", timeout, cmd[:100])
                return ""
            except Exception as exc:
                logger.warning("adb error: %s", exc)
                return ""
        logger.error("Device did not reconnect after 3 attempts.")
        return ""

    def _apply_config(self, cfg: dict):
        """
        Push all frequency settings to the device via adb sysfs writes.

        CPU frequency mechanism
        -----------------------
        This device uses the 'walt' governor which cannot be overridden to
        'userspace'. We lock the frequency by writing the same value to both
        scaling_min_freq and scaling_max_freq (double-write to avoid kernel
        ordering rejection).

        IMPORTANT: walt resets scaling_min_freq back to the hardware minimum
        when the CPU goes idle. To prevent this, _apply_config and
        _run_benchmark are merged into a single adb shell call — the
        frequency is written and the benchmark starts immediately with no
        gap for walt to reset anything.

        Bus frequency mechanism
        -----------------------
        DDR/LLCC use boost_freq (floor request). bwmon min/max nodes are
        read-only from adb shell. boost_freq is sufficient — under benchmark
        load the bus stays at or above the requested floor.
        """
        # Config is stored; actual adb writes happen in _run_benchmark_with_config
        # so that freq write + benchmark launch are in one shell call.
        self._pending_cfg = cfg

    def _run_benchmark(self, taskset_mask: str) -> int:
        """
        Write frequencies AND run the benchmark in a single adb shell call.
        This prevents the walt governor from resetting scaling_min_freq
        between the frequency write and the benchmark start.
        """
        cfg         = self._pending_cfg
        cpu_freq    = cfg["cpu_freq"]
        ddr_freq    = cfg["ddr_freq"]
        ddrqos_freq = cfg["ddrqos_freq"]
        llcc_freq   = cfg["llcc_freq"]
        target_cpu  = cfg["target_cpu"]
        pol = CPU_TO_POLICY.get(target_cpu,
              f"/sys/devices/system/cpu/cpufreq/policy{target_cpu}")

        # Build one shell command: set freqs → settle → run benchmark
        # All in a single adb call so walt has no chance to reset min_freq.
        bench_cmd = (
            f"echo {cpu_freq} > {pol}/scaling_max_freq ; "
            f"echo {cpu_freq} > {pol}/scaling_min_freq ; "
            f"echo {cpu_freq} > {pol}/scaling_max_freq ; "
            f"echo {cpu_freq} > {pol}/scaling_min_freq ; "
            f"echo {ddr_freq} > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq ; "
            f"echo {ddrqos_freq} > /sys/devices/system/cpu/bus_dcvs/DDRQOS/boost_freq ; "
            f"echo {llcc_freq} > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq ; "
            f"sleep 0.3 ; "
            f"taskset {taskset_mask} {BENCHMARK_BINARY} {BENCHMARK_ARGS}"
        )
        cmd    = bench_cmd
        output = self._adb(cmd, timeout=BENCHMARK_TIMEOUT_SEC)

        if output:
            logger.debug("Benchmark raw output (taskset %s):\n%s",
                         taskset_mask, output[:600])

        lat = self._parse_latency(output)
        if lat is None:
            logger.warning(
                "Could not parse latency (taskset %s). Full raw output:\n%s",
                taskset_mask,
                output if output else "<empty>",
            )
            return PENALTY_LATENCY_NS
        return lat

    @staticmethod
    def _parse_latency(output: str):
        """
        Extract latency (ns) from FullRandLat output.

        Primary: CSV row  "40960,91.37"  (memory footprint KB, latency ns)
        Fallback: "Latency: 12345 ns" / "12345 ns" / "12345ns"

        Returns the first match as an int, or None if nothing found.
        """
        if not output:
            return None

        # Primary: CSV data row produced by FullRandLat memlat
        csv = re.search(
            r"^\s*[0-9]+\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*$",
            output, re.MULTILINE
        )
        if csv:
            val = float(csv.group(1))
            if val > 0:
                return int(round(val))

        # Fallback patterns
        for pat in [
            r"[Ll]atency[^0-9\n]*([0-9]+(?:\.[0-9]+)?)\s*ns",
            r"([0-9]+(?:\.[0-9]+)?)\s*ns",
        ]:
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                val = float(m.group(1))
                if val > 0:
                    return int(round(val))

        return None