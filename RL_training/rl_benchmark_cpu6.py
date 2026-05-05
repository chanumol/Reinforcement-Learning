"""
RL Optimizer: cpu6 (Prime) × top-half CPU_freq × DDR × LLCC × DDRQOS
=====================================================================
Focused search on cpu6 only, upper half of Prime frequencies.

Action space: 1 × 18 × 11 × 9 × 2 = 3,564 combinations
  CPU          : cpu6 (Prime cluster, taskset 40)
  CPU_freq     : 18   (1920 MHz to 4435 MHz — top half of Prime)
  DDR          : 11   (547 MHz to 5333 MHz)
  LLCC         : 9    (282 MHz to 1350 MHz)
  DDRQOS       : 2    (0 or 1)

Setup approach (strictly followed):
  1. Set ALL CPUs in all clusters to max frequency
  2. Set ALL bus_dcvs nodes (bwmon + memlat + sched_boost) to hw_min
  3. Per episode: set cpu6 freq + DDR/LLCC bwmon + DDRQOS memlat → highest vote wins

Usage:
    python rl_benchmark_cpu6.py
    python rl_benchmark_cpu6.py --episodes 500
    python rl_benchmark_cpu6.py --episodes 1000

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
# Device CPU map (cpu6 only used for benchmarking)
# ---------------------------------------------------------------------------
_TZ = '/sys/class/thermal/thermal_zone{}/temp'
CPU_INFO = {
    0: {'mask': '1',  'cluster': 'LITTLE', 'thermal': _TZ.format(28), 'max_freq': 3475200},
    1: {'mask': '2',  'cluster': 'LITTLE', 'thermal': _TZ.format(31), 'max_freq': 3475200},
    2: {'mask': '4',  'cluster': 'LITTLE', 'thermal': _TZ.format(10), 'max_freq': 3475200},
    3: {'mask': '8',  'cluster': 'Gold',   'thermal': _TZ.format(0),  'max_freq': 3916800},
    4: {'mask': '10', 'cluster': 'Gold',   'thermal': _TZ.format(14), 'max_freq': 3916800},
    5: {'mask': '20', 'cluster': 'Gold',   'thermal': _TZ.format(2),  'max_freq': 3916800},
    6: {'mask': '40', 'cluster': 'Prime',  'thermal': _TZ.format(18), 'max_freq': 4435200},
    7: {'mask': '80', 'cluster': 'Prime',  'thermal': _TZ.format(6),  'max_freq': 4435200},
}

# cpu6 top-half Prime frequencies (>= 1920 MHz)
CPU6_FREQS = [
    1920000, 2016000, 2112000, 2208000, 2400000, 2630400, 2860800,
    3091200, 3321600, 3552000, 3667200, 3782400, 3897600, 4012800,
    4128000, 4243200, 4358400, 4435200
]

DDR_FREQS   = [547000, 1353000, 1555000, 1708000, 2092000, 2736000,
               3187000, 3686000, 4224000, 4780000, 5333000]
LLCC_FREQS  = [282000, 350000, 533000, 600000, 806000, 933000, 1066000, 1211000, 1350000]
DDRQOS_VALS = [0, 1]

ACTIONS = [
    (6, cf, d, l, q)
    for cf in CPU6_FREQS
    for d in DDR_FREQS
    for l in LLCC_FREQS
    for q in DDRQOS_VALS
]
N_ACTIONS = len(ACTIONS)   # 3,564

DEFAULT_BUF  = 65536   # 64 MB
DEFAULT_TEMP = 35      # °C

# bwmon / memlat paths
DDR_BWMON    = "/sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr"
LLCC_BWMON   = "/sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc"
DDRQOS_PRIME = "/sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime"
DDRQOS_BASE  = "/sys/devices/system/cpu/bus_dcvs/DDRQOS"


# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------
def _adb(cmd, timeout=15):
    subprocess.run(['adb', 'shell', cmd], capture_output=True, timeout=timeout)


def _lock(path, freq):
    """Set min=max=freq (max first, repeated twice for ordering safety)."""
    _adb(f"echo {freq} > {path}/max_freq && echo {freq} > {path}/min_freq && "
         f"echo {freq} > {path}/max_freq && echo {freq} > {path}/min_freq")


# ---------------------------------------------------------------------------
# Device setup
# ---------------------------------------------------------------------------
def setup_device():
    print("  [SETUP] Rooting...")
    subprocess.run(['adb', 'root'], capture_output=True, timeout=15)
    subprocess.run(['adb', 'wait-for-device'], capture_output=True, timeout=30)

    print("  [SETUP] Pushing benchmark binary...")
    subprocess.run([
        'adb', 'push',
        r'\\sundae\APT_Logs_PPTKGolden\Kernel\Test-binaries-compact\full-rand-lat\FullRandLat',
        '/data/local/tmp/'
    ], capture_output=True, timeout=60)
    _adb("chmod 777 /data/local/tmp/*")

    print("  [SETUP] Waking screen...")
    _adb("input keyevent 82")
    _adb("input keyevent 82")
    _adb("input keyevent 82")
    _adb("input keyevent 3")
    _adb("settings put system screen_off_timeout 2147483647")

    # Step 1: Set ALL bus_dcvs nodes to hw_min (exact commands as specified)
    print("  [SETUP] Setting ALL bus_dcvs nodes to hw_min...")

    # DDR bus-level boost + bwmon
    _adb("echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq")
    _adb(f"echo 547000 > {DDR_BWMON}/max_freq && echo 547000 > {DDR_BWMON}/min_freq && "
         f"echo 547000 > {DDR_BWMON}/max_freq && echo 547000 > {DDR_BWMON}/min_freq")
    _adb(f"echo 547000 > {DDR_BWMON}/sched_boost_freq")

    # DDR memlat clients
    for client in ('soc:qcom,memlat:ddr:gold', 'soc:'
        ',memlat:ddr:gold-compute',
                   'soc:qcom,memlat:ddr:prime', 'soc:qcom,memlat:ddr:prime-latfloor'):
        p = f"/sys/devices/system/cpu/bus_dcvs/DDR/{client}"
        _adb(f"echo 547000 > {p}/max_freq && echo 547000 > {p}/min_freq && "
             f"echo 547000 > {p}/max_freq && echo 547000 > {p}/min_freq")

    # LLCC bus-level boost + bwmon
    _adb("echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq")
    _adb(f"echo 282000 > {LLCC_BWMON}/max_freq && echo 282000 > {LLCC_BWMON}/min_freq && "
         f"echo 282000 > {LLCC_BWMON}/max_freq && echo 282000 > {LLCC_BWMON}/min_freq")
    _adb(f"echo 282000 > {LLCC_BWMON}/sched_boost_freq")

    # LLCC memlat clients
    for client in ('soc:qcom,memlat:llcc:gold', 'soc:qcom,memlat:llcc:gold-compute',
                   'soc:qcom,memlat:llcc:prime'):
        p = f"/sys/devices/system/cpu/bus_dcvs/LLCC/{client}"
        _adb(f"echo 282000 > {p}/max_freq && echo 282000 > {p}/min_freq && "
             f"echo 282000 > {p}/max_freq && echo 282000 > {p}/min_freq")

    # DDRQOS memlat clients
    for client in ('soc:qcom,memlat:ddrqos:gold', 'soc:qcom,memlat:ddrqos:prime',
                   'soc:qcom,memlat:ddrqos:prime-latfloor', 'soc:qcom,memlat:ddrqos:prime-compute'):
        p = f"/sys/devices/system/cpu/bus_dcvs/DDRQOS/{client}"
        _adb(f"echo 0 > {p}/max_freq && echo 0 > {p}/min_freq && "
             f"echo 0 > {p}/max_freq && echo 0 > {p}/min_freq")

    print("  [SETUP] All nodes set to hw_min")
    print("  [SETUP] Done")


# ---------------------------------------------------------------------------
# Frequency control
# ---------------------------------------------------------------------------
def set_cpu6_freq(freq_hz):
    path = "/sys/devices/system/cpu/cpu6/cpufreq"
    _adb(f"echo {freq_hz} > {path}/scaling_min_freq && echo {freq_hz} > {path}/scaling_max_freq && "
         f"echo {freq_hz} > {path}/scaling_min_freq && echo {freq_hz} > {path}/scaling_max_freq")


def set_mem_freqs(ddr_hz, llcc_hz, ddrqos):
    """
    Lock DDR/LLCC via bwmon, DDRQOS via memlat prime.
    Step 1: Reset sched_boost_freq to hw_min (kernel scheduler may have reset it to max)
    Step 2: Set bwmon min=max=target (highest vote → wins)
    """
    # Step 1: Reset bus boost_freq + sched_boost_freq to hw_min
    _adb("echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq && "
         "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq")
    _adb(f"echo 547000 > {DDR_BWMON}/sched_boost_freq && "
         f"echo 282000 > {LLCC_BWMON}/sched_boost_freq")

    # Step 2: Set bwmon min=max=target
    _adb(
        f"echo {ddr_hz} > {DDR_BWMON}/max_freq && echo {ddr_hz} > {DDR_BWMON}/min_freq && "
        f"echo {ddr_hz} > {DDR_BWMON}/max_freq && echo {ddr_hz} > {DDR_BWMON}/min_freq && "
        f"echo {llcc_hz} > {LLCC_BWMON}/max_freq && echo {llcc_hz} > {LLCC_BWMON}/min_freq && "
        f"echo {llcc_hz} > {LLCC_BWMON}/max_freq && echo {llcc_hz} > {LLCC_BWMON}/min_freq"
    )
    _adb(
        f"echo {ddrqos} > {DDRQOS_PRIME}/max_freq && echo {ddrqos} > {DDRQOS_PRIME}/min_freq && "
        f"echo {ddrqos} > {DDRQOS_PRIME}/max_freq && echo {ddrqos} > {DDRQOS_PRIME}/min_freq && "
        f"echo {ddrqos} > {DDRQOS_BASE}/boost_freq"
    )


# ---------------------------------------------------------------------------
# Thermal wait (cpu6, threshold 35°C)
# ---------------------------------------------------------------------------
def wait_for_cool(threshold_c=DEFAULT_TEMP, poll_sec=3):
    zone_path = CPU_INFO[6]['thermal']
    waiting   = False
    while True:
        try:
            result = subprocess.run(
                ['adb', 'shell', f'cat {zone_path}'],
                capture_output=True, text=True, timeout=10)
            raw = result.stdout.strip()
            if raw.lstrip('-').isdigit():
                temp = int(raw) / 1000.0
                if temp <= threshold_c:
                    if waiting:
                        print(f"    [TEMP] cpu6 {temp:.1f}C — OK")
                    return
                if not waiting:
                    print(f"    [TEMP] cpu6 {temp:.1f}C > {threshold_c}C — cooling...")
                    waiting = True
            else:
                return
        except Exception:
            return
        time.sleep(poll_sec)


# ---------------------------------------------------------------------------
# Frequency verification
# ---------------------------------------------------------------------------
def _read_cur(path):
    try:
        r = subprocess.run(['adb', 'shell', f'cat {path}'],
                           capture_output=True, text=True, timeout=10)
        v = r.stdout.strip()
        return int(v) if v.isdigit() else None
    except Exception:
        return None


def verify_freqs(cpu_freq, ddr_hz, llcc_hz, ddrqos):
    """
    Read back actual cur_freq values and verify they match targets.
    Returns True if all match, False otherwise.
    Uses: head /sys/devices/system/cpu/bus_dcvs/*/cur_freq
    """
    cpu_cur  = _read_cur("/sys/devices/system/cpu/cpu6/cpufreq/scaling_cur_freq")
    ddr_cur  = _read_cur("/sys/devices/system/cpu/bus_dcvs/DDR/cur_freq")
    llcc_cur = _read_cur("/sys/devices/system/cpu/bus_dcvs/LLCC/cur_freq")
    qos_cur  = _read_cur("/sys/devices/system/cpu/bus_dcvs/DDRQOS/cur_freq")

    ok = True
    mismatches = []

    if cpu_cur != cpu_freq:
        mismatches.append(f"CPU: got {cpu_cur} want {cpu_freq}")
        ok = False
    if ddr_cur != ddr_hz:
        mismatches.append(f"DDR: got {ddr_cur} want {ddr_hz}")
        ok = False
    if llcc_cur != llcc_hz:
        mismatches.append(f"LLCC: got {llcc_cur} want {llcc_hz}")
        ok = False
    # DDRQOS cur_freq may show 1000x scale (known display quirk) — accept both
    if qos_cur not in (ddrqos, ddrqos * 1000):
        mismatches.append(f"QOS: got {qos_cur} want {ddrqos}")
        ok = False

    if ok:
        print(f"    [VERIFY] CPU={cpu_cur/1000:.1f}MHz  DDR={ddr_cur/1000:.0f}MHz  "
              f"LLCC={llcc_cur/1000:.0f}MHz  QOS={qos_cur} — OK")
    else:
        print(f"    [VERIFY] MISMATCH — {', '.join(mismatches)}")
        print(f"    [VERIFY] Frequency lock failed — stopping execution")
        raise SystemExit(1)

    return ok


# ---------------------------------------------------------------------------
# Benchmark runner (cpu6, taskset 40)
# ---------------------------------------------------------------------------
def run_benchmark(buffer_kb, cpu_freq, ddr_hz, llcc_hz, ddrqos):
    verify_freqs(cpu_freq, ddr_hz, llcc_hz, ddrqos)  # raises SystemExit on mismatch

    cmd = (f"taskset 40 /data/local/tmp/FullRandLat memlat "
           f"-min-buffer-size-kb {buffer_kb} -max-buffer-size-kb {buffer_kb}")
    try:
        result = subprocess.run(['adb', 'shell', cmd],
                                capture_output=True, text=True, timeout=120)
        match = re.search(r'\d+,(\d+\.\d+)', result.stdout + result.stderr)
        return float(match.group(1)) if match else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Thompson Sampling Agent
# Prior: N(150, 30) — pessimistic so untested combos rarely beat the best
# ---------------------------------------------------------------------------
class ThompsonAgent:
    def __init__(self, n_actions, prior_mean=150.0, prior_std=30.0):
        self.n      = n_actions
        self.mu     = np.full(n_actions, prior_mean)
        self.sigma  = np.full(n_actions, prior_std)
        self.counts = np.zeros(n_actions)
        self.sum_x  = np.zeros(n_actions)
        self.sum_x2 = np.zeros(n_actions)

    def select(self):
        return int(np.argmin(np.random.normal(self.mu, self.sigma)))

    def update(self, a, latency):
        self.counts[a] += 1
        self.sum_x[a]  += latency
        self.sum_x2[a] += latency ** 2
        n = self.counts[a]
        self.mu[a] = self.sum_x[a] / n
        if n > 1:
            var = (self.sum_x2[a] - n * self.mu[a] ** 2) / (n - 1)
            self.sigma[a] = max(0.5, np.sqrt(var / n))
        else:
            self.sigma[a] = 20.0

    def best(self):
        tested = [i for i in range(self.n) if self.counts[i] > 0]
        return min(tested, key=lambda i: self.mu[i])

    def avg_latency(self, a):
        return self.mu[a] if self.counts[a] > 0 else None


# ---------------------------------------------------------------------------
# Periodic save every 10 episodes
# ---------------------------------------------------------------------------
def _save_partial(agent, best_idx, history, buffer_kb, n_episodes, ep):
    _, rec_freq, rec_ddr, rec_llcc, rec_qos = ACTIONS[best_idx]
    tried  = sum(1 for i in range(N_ACTIONS) if agent.counts[i] > 0)
    tested = sorted(
        [(i, agent.avg_latency(i), int(agent.counts[i]))
         for i in range(N_ACTIONS) if agent.counts[i] > 0],
        key=lambda x: x[1])
    results = {
        'status': f'running (ep {ep}/{n_episodes})',
        'recommended': {
            'cpu': 6, 'cluster': 'Prime',
            'cpu_freq_hz': rec_freq, 'cpu_freq_mhz': rec_freq / 1000,
            'ddr_hz': rec_ddr, 'ddr_mhz': rec_ddr / 1000,
            'llcc_hz': rec_llcc, 'llcc_mhz': rec_llcc / 1000,
            'ddrqos': rec_qos, 'taskset_mask': '40',
        },
        'avg_latency_ns': float(agent.avg_latency(best_idx)),
        'explored': tried, 'total_actions': N_ACTIONS,
        'buffer_kb': buffer_kb,
        'episodes_completed': ep, 'episodes_total': n_episodes,
        'top_results': [
            {'cpu_freq_hz': ACTIONS[i][1], 'ddr_hz': ACTIONS[i][2],
             'llcc_hz': ACTIONS[i][3], 'ddrqos': ACTIONS[i][4],
             'avg_latency_ns': float(lat), 'runs': runs}
            for i, lat, runs in tested[:20]
        ],
        'history': history
    }
    with open('rl_results_cpu6.json', 'w') as f:
        json.dump(results, f, indent=2)


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def train(n_episodes, buffer_kb):
    agent = ThompsonAgent(N_ACTIONS)
    setup_device()

    print("\n" + "=" * 80)
    print("  RL Optimizer: cpu6 (Prime) × top-half freq × DDR × LLCC × DDRQOS")
    print("=" * 80)
    print(f"  Agent    : THOMPSON SAMPLING  (prior N(150, 30))")
    print(f"  Actions  : {N_ACTIONS:,}  (18 CPU_freq × 11 DDR × 9 LLCC × 2 DDRQOS)")
    print(f"  Episodes : {n_episodes}")
    print(f"  Buffer   : {buffer_kb} KB  ({buffer_kb//1024} MB)")
    print(f"  Thermal  : wait <= {DEFAULT_TEMP}C before each run")
    print(f"  Taskset  : 40 (cpu6)")
    print("=" * 80)
    print(f"  {'Ep':>4}  {'CPU MHz':>8}  {'DDR MHz':>8}  {'LLCC MHz':>9}  "
          f"{'QOS':>4}  {'Latency':>10}  {'Best so far'}")
    print("  " + "-" * 75)

    history  = []
    best_lat = float('inf')
    best_idx = None

    for ep in range(1, n_episodes + 1):
        idx                          = agent.select()
        _, cpu_freq, ddr_hz, llcc_hz, ddrqos = ACTIONS[idx]

        set_cpu6_freq(cpu_freq)
        set_mem_freqs(ddr_hz, llcc_hz, ddrqos)
        wait_for_cool()
        try:
            latency = run_benchmark(buffer_kb, cpu_freq, ddr_hz, llcc_hz, ddrqos)
        except SystemExit:
            # Frequency lock failed — save progress then stop
            if best_idx is not None:
                _save_partial(agent, best_idx, history, buffer_kb, n_episodes, ep)
                print(f"  [SAVE] Progress saved to rl_results_cpu6.json (ep {ep})")
            raise

        if latency is not None:
            agent.update(idx, latency)
            if latency < best_lat:
                best_lat = latency
                best_idx = idx

        lat_str  = f"{latency:.2f} ns" if latency else "FAILED"
        if best_idx is not None:
            b = ACTIONS[best_idx]
            best_str = (f"cpu6@{b[1]/1000:.0f} "
                        f"DDR{b[2]/1000:.0f} "
                        f"LLCC{b[3]/1000:.0f} "
                        f"QOS{b[4]} "
                        f"= {best_lat:.1f}ns")
        else:
            best_str = "-"

        print(f"  {ep:>4}  {cpu_freq/1000:>6.1f}  {ddr_hz/1000:>6.0f}  "
              f"{llcc_hz/1000:>7.0f}  {ddrqos:>4}  {lat_str:>10}  {best_str}")

        history.append({
            'episode': ep, 'cpu_freq_hz': cpu_freq,
            'ddr_hz': ddr_hz, 'llcc_hz': llcc_hz,
            'ddrqos': ddrqos, 'latency_ns': latency
        })

        if best_idx is not None and ep % 10 == 0:
            _save_partial(agent, best_idx, history, buffer_kb, n_episodes, ep)

    # -----------------------------------------------------------------------
    # Final recommendation
    # -----------------------------------------------------------------------
    rec_idx                              = agent.best()
    _, rec_freq, rec_ddr, rec_llcc, rec_qos = ACTIONS[rec_idx]
    tried = sum(1 for i in range(N_ACTIONS) if agent.counts[i] > 0)

    print("\n" + "=" * 80)
    print("  RECOMMENDATION")
    print("=" * 80)
    print(f"  CPU          : cpu6  (Prime cluster, taskset 40)")
    print(f"  CPU freq     : {rec_freq:,} Hz  ({rec_freq/1000:.1f} MHz)")
    print(f"  DDR freq     : {rec_ddr:,} Hz  ({rec_ddr/1000:.0f} MHz)")
    print(f"  LLCC freq    : {rec_llcc:,} Hz  ({rec_llcc/1000:.0f} MHz)")
    print(f"  DDRQOS       : {rec_qos}")
    print(f"  Avg latency  : {agent.avg_latency(rec_idx):.2f} ns")
    print(f"  Explored     : {tried:,}/{N_ACTIONS:,} ({tried*100//N_ACTIONS}%)")
    print()

    tested = sorted(
        [(i, agent.avg_latency(i), int(agent.counts[i]))
         for i in range(N_ACTIONS) if agent.counts[i] > 0],
        key=lambda x: x[1])

    print(f"  {'CPU MHz':>8}  {'DDR MHz':>8}  {'LLCC MHz':>9}  {'QOS':>4}  "
          f"{'Avg Latency':>12}  {'Runs':>5}")
    print("  " + "-" * 55)
    for i, lat, runs in tested[:15]:
        a   = ACTIONS[i]
        tag = " <-- BEST" if i == rec_idx else ""
        print(f"  {a[1]/1000:>6.1f}  {a[2]/1000:>6.0f}  {a[3]/1000:>7.0f}  "
              f"{a[4]:>4}  {lat:>10.2f} ns  {runs:>5}{tag}")

    print()
    print("  Apply this configuration (hard lock via bwmon):")
    print(f"  adb shell \"echo {rec_freq} > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && "
          f"echo {rec_freq} > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq && "
          f"echo {rec_freq} > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && "
          f"echo {rec_freq} > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq\"")
    print(f"  adb shell \"echo {rec_ddr} > {DDR_BWMON}/max_freq && echo {rec_ddr} > {DDR_BWMON}/min_freq && "
          f"echo {rec_ddr} > {DDR_BWMON}/max_freq && echo {rec_ddr} > {DDR_BWMON}/min_freq\"")
    print(f"  adb shell \"echo {rec_llcc} > {LLCC_BWMON}/max_freq && echo {rec_llcc} > {LLCC_BWMON}/min_freq && "
          f"echo {rec_llcc} > {LLCC_BWMON}/max_freq && echo {rec_llcc} > {LLCC_BWMON}/min_freq\"")
    print(f"  adb shell \"echo {rec_qos} > {DDRQOS_PRIME}/max_freq && echo {rec_qos} > {DDRQOS_PRIME}/min_freq && "
          f"echo {rec_qos} > {DDRQOS_PRIME}/max_freq && echo {rec_qos} > {DDRQOS_PRIME}/min_freq\"")
    print(f"  adb shell taskset 40 /data/local/tmp/FullRandLat memlat "
          f"-min-buffer-size-kb {buffer_kb} -max-buffer-size-kb {buffer_kb}")
    print("=" * 80)

    tested_full = sorted(
        [(i, agent.avg_latency(i), int(agent.counts[i]))
         for i in range(N_ACTIONS) if agent.counts[i] > 0],
        key=lambda x: x[1])

    results = {
        'recommended': {
            'cpu': 6, 'cluster': 'Prime',
            'cpu_freq_hz': rec_freq, 'cpu_freq_mhz': rec_freq / 1000,
            'ddr_hz': rec_ddr, 'ddr_mhz': rec_ddr / 1000,
            'llcc_hz': rec_llcc, 'llcc_mhz': rec_llcc / 1000,
            'ddrqos': rec_qos, 'taskset_mask': '40',
        },
        'avg_latency_ns': float(agent.avg_latency(rec_idx)),
        'explored': tried, 'total_actions': N_ACTIONS,
        'buffer_kb': buffer_kb, 'episodes': n_episodes,
        'top_results': [
            {'cpu_freq_hz': ACTIONS[i][1], 'ddr_hz': ACTIONS[i][2],
             'llcc_hz': ACTIONS[i][3], 'ddrqos': ACTIONS[i][4],
             'avg_latency_ns': float(lat), 'runs': runs}
            for i, lat, runs in tested_full[:20]
        ],
        'history': history
    }
    with open('rl_results_cpu6.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("  Saved -> rl_results_cpu6.json")
    return results['recommended']


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='RL: cpu6 only — find best (CPU_freq, DDR, LLCC, DDRQOS) for min DRAM latency'
    )
    parser.add_argument('--episodes', type=int, default=500,
                        help='Total runs (default 500; action space = 3,564)')
    parser.add_argument('--buffer-kb', type=int, default=DEFAULT_BUF,
                        help='Buffer size in KB (default 65536 = 64MB)')
    args = parser.parse_args()

    train(args.episodes, args.buffer_kb)