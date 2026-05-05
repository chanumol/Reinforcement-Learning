"""
RL CPU + Frequency Optimizer for Memory Latency Benchmarks
============================================================
Uses Thompson Sampling (Bayesian bandit) to find the best (cpu, frequency)
pair for minimum DRAM latency.

Each (cpu, freq) pair is treated as an INDEPENDENT action with its own
Bayesian posterior. The agent does NOT assume cpu6 and cpu7 behave the same
just because they share a cluster — it learns each pair independently.

How Thompson Sampling works here:
  - Each (cpu, freq) pair has its own Gaussian posterior N(mu, sigma^2)
  - Prior: N(mean=150ns, std=50ns) — high uncertainty, all pairs equal
  - Each episode: sample one latency estimate per pair from its posterior,
    pick the pair with the LOWEST sample → run benchmark → update that pair's posterior
  - High uncertainty = wide distribution = more likely to be sampled (explored)
  - After a good result: posterior narrows around that latency → exploited more
  - After a bad result: posterior narrows around high latency → rarely sampled

Thermal control:
  - Before each run, waits for the CPU temp to drop to ≤ 30°C
  - Ensures latency measurements are not affected by thermal state

Device setup is handled internally (no perf-mode.bat needed):
  - Wake screen, prevent timeout
  - DDR/LLCC always at max (only CPU freq varies per episode)

Usage:
    python rl_benchmark.py
    python rl_benchmark.py --episodes 100
    python rl_benchmark.py --buffer-kb 65536

Requirements:
    pip install numpy
"""

import subprocess
import re
import time
import numpy as np
import json
import argparse

# ---------------------------------------------------------------------------
# Device CPU map  (each CPU is independent — no cluster-level assumptions)
# ---------------------------------------------------------------------------
_TZ = '/sys/class/thermal/thermal_zone{}/temp'
CPU_INFO = {
    0: {'mask': '1',  'cluster': 'LITTLE', 'thermal': _TZ.format(28)},
    1: {'mask': '2',  'cluster': 'LITTLE', 'thermal': _TZ.format(31)},
    2: {'mask': '4',  'cluster': 'LITTLE', 'thermal': _TZ.format(10)},
    3: {'mask': '8',  'cluster': 'Gold',   'thermal': _TZ.format(0)},
    4: {'mask': '10', 'cluster': 'Gold',   'thermal': _TZ.format(14)},
    5: {'mask': '20', 'cluster': 'Gold',   'thermal': _TZ.format(2)},
    6: {'mask': '40', 'cluster': 'Prime',  'thermal': _TZ.format(18)},
    7: {'mask': '80', 'cluster': 'Prime',  'thermal': _TZ.format(6)},
}

# Available frequencies per cluster (Hz) — from device
CLUSTER_FREQS = {
    'LITTLE': [864000, 960000, 1056000, 1152000, 1248000, 1344000, 1440000,
               1536000, 1632000, 1728000, 1824000, 1920000, 2016000, 2112000,
               2208000, 2304000, 2400000, 2496000, 2592000, 2707200, 2822400,
               2937600, 3052800, 3168000, 3283200, 3398400, 3475200],
    'Gold':   [960000, 1056000, 1152000, 1248000, 1344000, 1440000, 1536000,
               1632000, 1728000, 1824000, 1920000, 2016000, 2112000, 2208000,
               2304000, 2400000, 2496000, 2592000, 2707200, 2822400, 2937600,
               3052800, 3168000, 3283200, 3398400, 3513600, 3628800, 3744000,
               3859200, 3916800],
    'Prime':  [288000, 384000, 518400, 576000, 672000, 768000, 864000, 960000,
               1056000, 1152000, 1248000, 1344000, 1440000, 1536000, 1632000,
               1728000, 1824000, 1920000, 2016000, 2112000, 2208000, 2400000,
               2630400, 2860800, 3091200, 3321600, 3552000, 3667200, 3782400,
               3897600, 4012800, 4128000, 4243200, 4358400, 4435200],
}

# Flat action list: [(cpu_id, freq_hz), ...]
# Each entry is an INDEPENDENT action — no cluster-level sharing
ACTIONS   = [(cpu, f) for cpu, info in CPU_INFO.items()
             for f in CLUSTER_FREQS[info['cluster']]]
N_ACTIONS = len(ACTIONS)   # 241

DEFAULT_FIXED_BUF = 40960
DEFAULT_TEMP_C    = 30


# ---------------------------------------------------------------------------
# Device setup (replaces perf-mode.bat)
# ---------------------------------------------------------------------------
def _adb(cmd, timeout=15):
    subprocess.run(['adb', 'shell', cmd], capture_output=True, timeout=timeout)


def setup_device():
    """Wake screen, prevent timeout, lock DDR/LLCC to max."""
    print("  [SETUP] Waking screen, locking DDR/LLCC to max...")
    _adb("input keyevent 82")
    _adb("input keyevent 82")
    _adb("input keyevent 82")
    _adb("input keyevent 82")
    _adb("input keyevent 3")
    _adb("settings put system screen_off_timeout 2147483647")
    _adb("echo 5333000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq")
    _adb("echo 1 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/boost_freq")
    _adb("echo 1350000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq")
    print("  [SETUP] Done — DDR=5333 MHz, LLCC=1350 MHz")


# ---------------------------------------------------------------------------
# CPU frequency control
# ---------------------------------------------------------------------------
def set_cpu_freq(cpu_id, freq_hz):
    """Lock cpu_id to freq_hz (min = max = freq_hz)."""
    path = f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq"
    cmd  = (f"echo {freq_hz} > {path}/scaling_min_freq && "
            f"echo {freq_hz} > {path}/scaling_max_freq && "
            f"echo {freq_hz} > {path}/scaling_min_freq && "
            f"echo {freq_hz} > {path}/scaling_max_freq")
    subprocess.run(['adb', 'shell', cmd], capture_output=True, timeout=15)


# ---------------------------------------------------------------------------
# Thermal wait
# ---------------------------------------------------------------------------
def wait_for_cool(cpu_id, threshold_c=DEFAULT_TEMP_C, poll_sec=3):
    """Wait until cpu_id's temperature drops to ≤ threshold_c."""
    zone_path = CPU_INFO[cpu_id]['thermal']
    while True:
        try:
            result = subprocess.run(
                ['adb', 'shell', f'cat {zone_path}'],
                capture_output=True, text=True, timeout=10
            )
            raw = result.stdout.strip()
            if raw.lstrip('-').isdigit():
                temp = int(raw) / 1000.0
                if temp <= threshold_c:
                    print(f"    [TEMP] cpu{cpu_id} {temp:.1f}°C ≤ {threshold_c}°C — OK")
                    return
                print(f"    [TEMP] cpu{cpu_id} {temp:.1f}°C > {threshold_c}°C — waiting {poll_sec}s")
            else:
                print(f"    [TEMP] cpu{cpu_id} sensor unreadable, skipping wait")
                return
        except Exception:
            print(f"    [TEMP] cpu{cpu_id} read error, skipping wait")
            return
        time.sleep(poll_sec)


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------
def run_on_cpu(cpu_id, buffer_kb):
    """Run FullRandLat on cpu_id. Returns latency (ns) or None."""
    mask = CPU_INFO[cpu_id]['mask']
    cmd  = (f"taskset {mask} /data/local/tmp/FullRandLat memlat "
            f"-min-buffer-size-kb {buffer_kb} -max-buffer-size-kb {buffer_kb}")
    try:
        result = subprocess.run(['adb', 'shell', cmd],
                                capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        match  = re.search(r'\d+,(\d+\.\d+)', output)
        if match:
            return float(match.group(1))
        print(f"    [WARN] Parse failed: {output.strip()[:80]}")
        return None
    except subprocess.TimeoutExpired:
        print(f"    [ERROR] Timeout on cpu{cpu_id}")
        return None
    except Exception as e:
        print(f"    [ERROR] {e}")
        return None


# ---------------------------------------------------------------------------
# Thompson Sampling Agent
# ---------------------------------------------------------------------------
class ThompsonAgent:
    """
    Bayesian bandit over all (cpu, freq) pairs.

    Each pair has its own INDEPENDENT posterior N(mu, sigma^2).
    cpu6@2GHz and cpu7@2GHz are completely separate beliefs — the agent
    does NOT assume they behave the same.

    Selection: sample one latency estimate per pair from its posterior,
               pick the pair with the LOWEST sample.
    Update:    after observing latency, update that pair's posterior.
               Other pairs are NOT updated — fully independent.

    Prior: N(mean=150ns, std=50ns) — high uncertainty, all pairs equal at start.
    """

    def __init__(self, n_actions, prior_mean=150.0, prior_std=50.0):
        self.n      = n_actions
        self.mu     = np.full(n_actions, prior_mean)   # posterior mean per pair
        self.sigma  = np.full(n_actions, prior_std)    # posterior std per pair
        self.counts = np.zeros(n_actions)
        self.sum_x  = np.zeros(n_actions)
        self.sum_x2 = np.zeros(n_actions)

    def select(self):
        # Sample one latency estimate per pair from its posterior
        # Pick the pair with the LOWEST sampled latency
        samples = np.random.normal(self.mu, self.sigma)
        return int(np.argmin(samples))

    def update(self, a, latency):
        # Update ONLY this pair's posterior — all others unchanged
        self.counts[a] += 1
        self.sum_x[a]  += latency
        self.sum_x2[a] += latency ** 2
        n = self.counts[a]
        self.mu[a] = self.sum_x[a] / n
        if n > 1:
            var = (self.sum_x2[a] - n * self.mu[a] ** 2) / (n - 1)
            self.sigma[a] = max(0.5, np.sqrt(var / n))
        else:
            self.sigma[a] = 20.0   # high uncertainty after 1 run

    def best(self):
        tested = [i for i in range(self.n) if self.counts[i] > 0]
        return min(tested, key=lambda i: self.mu[i])

    def avg_latency(self, a):
        return self.mu[a] if self.counts[a] > 0 else None


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def train(n_episodes, buffer_kb):
    agent = ThompsonAgent(N_ACTIONS)

    setup_device()

    print("\n" + "=" * 72)
    print("  RL CPU + Frequency Optimizer  —  Thompson Sampling")
    print("=" * 72)
    print(f"  Agent    : THOMPSON SAMPLING (Bayesian, CPU-level independent)")
    print(f"  Buffer   : {buffer_kb} KB")
    print(f"  Episodes : {n_episodes}  (action space: {N_ACTIONS} pairs)")
    print(f"  Thermal  : wait ≤ {DEFAULT_TEMP_C}°C before each run")
    print(f"  Note     : each (cpu, freq) pair has its own independent posterior")
    print("=" * 72)
    print(f"  {'Ep':>3}  {'CPU':>4}  {'Cluster':>7}  {'Freq MHz':>9}  "
          f"{'Latency':>10}  {'Best so far'}")
    print("  " + "-" * 65)

    history  = []
    best_lat = float('inf')
    best_idx = None

    for ep in range(1, n_episodes + 1):
        idx          = agent.select()
        cpu_id, freq = ACTIONS[idx]
        cluster      = CPU_INFO[cpu_id]['cluster']

        set_cpu_freq(cpu_id, freq)
        wait_for_cool(cpu_id)
        latency = run_on_cpu(cpu_id, buffer_kb)

        if latency is not None:
            agent.update(idx, latency)
            if latency < best_lat:
                best_lat = latency
                best_idx = idx

        lat_str  = f"{latency:.2f} ns" if latency else "FAILED"
        best_str = (f"cpu{ACTIONS[best_idx][0]} "
                    f"{ACTIONS[best_idx][1]/1000:.0f}MHz "
                    f"@ {best_lat:.1f}"
                    if best_idx is not None else "-")
        print(f"  {ep:>3}  cpu{cpu_id}  {cluster:>7}  {freq/1000:>7.1f}  "
              f"{lat_str:>10}  {best_str}")

        history.append({'episode': ep, 'cpu': cpu_id, 'cluster': cluster,
                        'freq_hz': freq, 'freq_mhz': freq/1000, 'latency_ns': latency})

    # -----------------------------------------------------------------------
    # Final recommendation
    # -----------------------------------------------------------------------
    rec_idx           = agent.best()
    rec_cpu, rec_freq = ACTIONS[rec_idx]
    rec_cluster       = CPU_INFO[rec_cpu]['cluster']

    print("\n" + "=" * 72)
    print("  RECOMMENDATION")
    print("=" * 72)
    print(f"  Best CPU     : cpu{rec_cpu}  ({rec_cluster} cluster)")
    print(f"  Best freq    : {rec_freq:,} Hz  ({rec_freq/1000:.1f} MHz)")
    print(f"  Taskset mask : {CPU_INFO[rec_cpu]['mask']}")
    print(f"  Avg latency  : {agent.avg_latency(rec_idx):.2f} ns")
    print()

    tested = [(i, ACTIONS[i][0], ACTIONS[i][1], agent.avg_latency(i), int(agent.counts[i]))
              for i in range(N_ACTIONS) if agent.counts[i] > 0]
    tested.sort(key=lambda x: x[3])
    tried   = len(tested)
    skipped = N_ACTIONS - tried

    print(f"  Explored {tried}/{N_ACTIONS} pairs, skipped {skipped} (agent learned to ignore them)")
    print()
    print(f"  Top results (sorted by avg latency):")
    print(f"  {'CPU':<5} {'Cluster':<8} {'Freq MHz':>9}  {'Avg Latency':>12}  {'Runs':>5}")
    print("  " + "-" * 50)
    for i, cpu, freq, lat, runs in tested[:15]:
        tag = " <-- BEST" if i == rec_idx else ""
        print(f"  cpu{cpu}  {CPU_INFO[cpu]['cluster']:<8} {freq/1000:>7.1f}  "
              f"{lat:>10.2f} ns  {runs:>5}{tag}")

    print()
    print(f"  Verify manually:")
    print(f"  adb shell \"echo {rec_freq} > /sys/devices/system/cpu/cpu{rec_cpu}/cpufreq/scaling_min_freq && "
          f"echo {rec_freq} > /sys/devices/system/cpu/cpu{rec_cpu}/cpufreq/scaling_max_freq\"")
    print(f"  adb shell taskset {CPU_INFO[rec_cpu]['mask']} "
          f"/data/local/tmp/FullRandLat memlat "
          f"-min-buffer-size-kb {buffer_kb} -max-buffer-size-kb {buffer_kb}")
    print("=" * 72)

    results = {
        'recommended_cpu': rec_cpu,
        'recommended_cluster': rec_cluster,
        'recommended_freq_hz': rec_freq,
        'recommended_freq_mhz': rec_freq / 1000,
        'taskset_mask': CPU_INFO[rec_cpu]['mask'],
        'avg_latency_ns': float(agent.avg_latency(rec_idx)),
        'buffer_kb': buffer_kb,
        'episodes': n_episodes,
        'combinations_explored': tried,
        'combinations_skipped': skipped,
        'top_results': [
            {'cpu': cpu, 'cluster': CPU_INFO[cpu]['cluster'],
             'freq_hz': freq, 'freq_mhz': freq/1000,
             'avg_latency_ns': float(lat), 'runs': runs}
            for _, cpu, freq, lat, runs in tested[:20]
        ],
        'history': history
    }
    with open('rl_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("  Saved -> rl_results.json")

    return rec_cpu, rec_freq


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='RL Thompson Sampling: find best (CPU, frequency) for min DRAM latency'
    )
    parser.add_argument('--episodes', type=int, default=100,
                        help='Total runs (default 100; action space = 241 pairs)')
    parser.add_argument('--buffer-kb', type=int, default=DEFAULT_FIXED_BUF,
                        help='Buffer size in KB (default 40960 = 40MB)')
    args = parser.parse_args()

    train(args.episodes, args.buffer_kb)