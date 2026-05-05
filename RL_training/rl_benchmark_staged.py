"""
Staged RL Optimizer with Thompson Sampling per stage
=====================================================
Stage 1: Thompson Sampling over CPU freq  (fix DDR/LLCC/QOS at defaults)
Stage 2: Thompson Sampling over DDR freq  (fix CPU at Stage 1 best)
Stage 3: Thompson Sampling over DDRQOS   (fix CPU+DDR at Stage 1+2 best)
Stage 4: Thompson Sampling over LLCC freq (fix CPU+DDR+QOS at Stage 1+2+3 best)

Intelligence: Thompson Sampling allocates more episodes to promising values
              and fewer to clearly bad ones — same algorithm as rl_benchmark_cpu6.py

Usage:
    python rl_benchmark_staged.py                         # all 4 stages, 30 eps each
    python rl_benchmark_staged.py --episodes 50           # 50 eps per stage
    python rl_benchmark_staged.py --stage 2               # only stage 2
    python rl_benchmark_staged.py --stage 4 --cpu-freq 4358400 --ddr 4224000 --qos 1
    python rl_benchmark_staged.py --stage 1 --episodes 20 --buf 40960

Requirements:
    pip install numpy
"""

import subprocess
import re
import time
import argparse
import numpy as np

# ---------------------------------------------------------------------------
# Device config
# ---------------------------------------------------------------------------
DDR_BWMON    = "/sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr"
LLCC_BWMON   = "/sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc"
DDRQOS_PRIME = "/sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime"
DDRQOS_BASE  = "/sys/devices/system/cpu/bus_dcvs/DDRQOS"
CPU6_ZONE    = "/sys/class/thermal/thermal_zone18/temp"

# Available frequencies
CPU6_FREQS = [
    1920000, 2016000, 2112000, 2208000, 2400000, 2630400, 2860800,
    3091200, 3321600, 3552000, 3667200, 3782400, 3897600, 4012800,
    4128000, 4243200, 4358400, 4435200
]
DDR_FREQS   = [547000, 1353000, 1555000, 1708000, 2092000, 2736000,
               3187000, 3686000, 4224000]
LLCC_FREQS  = [282000, 350000, 533000, 600000, 806000, 933000, 1066000, 1211000, 1350000]
DDRQOS_VALS = [0, 1]

# Defaults used when a dimension is not being swept (max = high-performance baseline)
DEFAULT_CPU_FREQ = 4435200   # 4435.2 MHz (Prime max)
DEFAULT_DDR      = 4224000   # 4224 MHz
DEFAULT_LLCC     = 1350000   # 1350 MHz (LLCC max)
DEFAULT_QOS      = 1         # QOS maximum
DEFAULT_BUF      = 65536
DEFAULT_TEMP     = 35
DEFAULT_EPISODES = 30        # Thompson Sampling episodes per stage


# ---------------------------------------------------------------------------
# Thompson Sampling Agent (same as rl_benchmark_cpu6.py)
# ---------------------------------------------------------------------------
class ThompsonAgent:
    def __init__(self, n_actions, prior_mean=110.0, prior_std=15.0):
        self.n      = n_actions
        self.mu     = np.full(n_actions, prior_mean)
        self.sigma  = np.full(n_actions, prior_std)
        self.counts = np.zeros(n_actions)
        self.sum_x  = np.zeros(n_actions)
        self.sum_x2 = np.zeros(n_actions)

    def select(self):
        """Sample from each action's distribution, pick the one with lowest sample."""
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
        return min(tested, key=lambda i: self.mu[i]) if tested else 0

    def avg(self, i):
        return self.mu[i] if self.counts[i] > 0 else None


# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------
def adb(cmd, timeout=15):
    subprocess.run(['adb', 'shell', cmd], capture_output=True, timeout=timeout)


def read_temp():
    try:
        r = subprocess.run(['adb', 'shell', f'cat {CPU6_ZONE}'],
                           capture_output=True, text=True, timeout=10)
        v = r.stdout.strip()
        return int(v) / 1000.0 if v.isdigit() else None
    except Exception:
        return None


def wait_for_cool(threshold=DEFAULT_TEMP, poll=3):
    waiting = False
    while True:
        temp = read_temp()
        if temp is None:
            return
        if temp <= threshold:
            if waiting:
                print(f"    [TEMP] {temp:.1f}C — OK")
            return
        if not waiting:
            print(f"    [TEMP] {temp:.1f}C > {threshold}C — cooling...")
            waiting = True
        time.sleep(poll)


def set_config(cpu_freq, ddr, llcc, qos):
    path = "/sys/devices/system/cpu/cpu6/cpufreq"
    adb(f"echo {cpu_freq} > {path}/scaling_min_freq && echo {cpu_freq} > {path}/scaling_max_freq && "
        f"echo {cpu_freq} > {path}/scaling_min_freq && echo {cpu_freq} > {path}/scaling_max_freq")
    adb(f"echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq && "
        f"echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq")
    adb(f"echo 547000 > {DDR_BWMON}/sched_boost_freq && echo 282000 > {LLCC_BWMON}/sched_boost_freq")
    adb(f"echo {ddr} > {DDR_BWMON}/max_freq && echo {ddr} > {DDR_BWMON}/min_freq && "
        f"echo {ddr} > {DDR_BWMON}/max_freq && echo {ddr} > {DDR_BWMON}/min_freq && "
        f"echo {llcc} > {LLCC_BWMON}/max_freq && echo {llcc} > {LLCC_BWMON}/min_freq && "
        f"echo {llcc} > {LLCC_BWMON}/max_freq && echo {llcc} > {LLCC_BWMON}/min_freq")
    adb(f"echo {qos} > {DDRQOS_PRIME}/max_freq && echo {qos} > {DDRQOS_PRIME}/min_freq && "
        f"echo {qos} > {DDRQOS_PRIME}/max_freq && echo {qos} > {DDRQOS_PRIME}/min_freq && "
        f"echo {qos} > {DDRQOS_BASE}/boost_freq")


def verify_freqs(cpu_freq, ddr, llcc, qos):
    def read_cur(path):
        try:
            r = subprocess.run(['adb', 'shell', f'cat {path}'],
                               capture_output=True, text=True, timeout=10)
            v = r.stdout.strip()
            return int(v) if v.isdigit() else None
        except Exception:
            return None

    cpu_cur  = read_cur("/sys/devices/system/cpu/cpu6/cpufreq/scaling_cur_freq")
    ddr_cur  = read_cur("/sys/devices/system/cpu/bus_dcvs/DDR/cur_freq")
    llcc_cur = read_cur("/sys/devices/system/cpu/bus_dcvs/LLCC/cur_freq")
    qos_cur  = read_cur("/sys/devices/system/cpu/bus_dcvs/DDRQOS/cur_freq")

    ok = True
    mismatches = []
    if cpu_cur != cpu_freq:
        mismatches.append(f"CPU: got {cpu_cur} want {cpu_freq}")
        ok = False
    if ddr_cur != ddr:
        mismatches.append(f"DDR: got {ddr_cur} want {ddr}")
        ok = False
    if llcc_cur != llcc:
        mismatches.append(f"LLCC: got {llcc_cur} want {llcc}")
        ok = False
    if qos_cur not in (qos, qos * 1000):
        mismatches.append(f"QOS: got {qos_cur} want {qos}")
        ok = False

    if ok:
        print(f"    [VERIFY] CPU={cpu_cur/1000:.1f}MHz  DDR={ddr_cur/1000:.0f}MHz  "
              f"LLCC={llcc_cur/1000:.0f}MHz  QOS={qos_cur} — OK", flush=True)
    else:
        print(f"    [VERIFY] MISMATCH — {', '.join(mismatches)}", flush=True)
        raise SystemExit(1)


def run_benchmark(buf=DEFAULT_BUF):
    cmd = (f"taskset 40 /data/local/tmp/FullRandLat memlat "
           f"-min-buffer-size-kb {buf} -max-buffer-size-kb {buf}")
    try:
        r = subprocess.run(['adb', 'shell', cmd],
                           capture_output=True, text=True, timeout=120)
        m = re.search(r'\d+,(\d+\.\d+)', r.stdout + r.stderr)
        return float(m.group(1)) if m else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Thompson Sampling stage runner
# ---------------------------------------------------------------------------
def run_stage(stage_name, values, val_to_str, fixed_config, dim_key, episodes, buf):
    """
    Run Thompson Sampling over `values` for `episodes` episodes.
    fixed_config: dict with cpu_freq, ddr, llcc, qos — dim_key will be overridden.
    Returns best value found.
    """
    n = len(values)
    agent = ThompsonAgent(n)

    print(f"\n  {'Ep':>4}  {'Value':>12}  {'Latency':>10}  {'Best so far'}")
    print("  " + "-" * 60)

    best_lat = float('inf')
    best_idx = None

    for ep in range(1, episodes + 1):
        idx = agent.select()
        val = values[idx]

        cfg = dict(fixed_config)
        cfg[dim_key] = val
        set_config(cfg['cpu_freq'], cfg['ddr'], cfg['llcc'], cfg['qos'])
        verify_freqs(cfg['cpu_freq'], cfg['ddr'], cfg['llcc'], cfg['qos'])
        wait_for_cool()
        lat = run_benchmark(buf)

        if lat is not None:
            agent.update(idx, lat)
            if lat < best_lat:
                best_lat = lat
                best_idx = idx

        lat_str  = f"{lat:.2f} ns" if lat else "FAILED"
        best_str = (f"{val_to_str(values[best_idx])} = {best_lat:.2f} ns"
                    if best_idx is not None else "-")
        print(f"  {ep:>4}  {val_to_str(val):>12}  {lat_str:>10}  {best_str}", flush=True)

    # Summary table
    tested = [(i, agent.avg(i), int(agent.counts[i]))
              for i in range(n) if agent.counts[i] > 0]
    tested.sort(key=lambda x: x[1])

    print(f"\n  {stage_name} results (sorted by avg latency):")
    print(f"  {'Value':>12}  {'Runs':>5}  {'Avg ns':>8}")
    print("  " + "-" * 30)
    for i, avg, runs in tested:
        tag = " ← BEST" if i == agent.best() else ""
        print(f"  {val_to_str(values[i]):>12}  {runs:>5}  {avg:>8.2f}{tag}")

    best_val = values[agent.best()]
    print(f"\n  Best {stage_name}: {val_to_str(best_val)}  "
          f"avg={agent.avg(agent.best()):.2f} ns")
    return best_val


# ---------------------------------------------------------------------------
# Device setup
# ---------------------------------------------------------------------------
def setup_device(buf):
    print("[SETUP] Rooting...")
    subprocess.run(['adb', 'root'], capture_output=True, timeout=15)
    subprocess.run(['adb', 'wait-for-device'], capture_output=True, timeout=30)

    print("[SETUP] Pushing binary...")
    subprocess.run([
        'adb', 'push',
        r'\\sundae\APT_Logs_PPTKGolden\Kernel\Test-binaries-compact\full-rand-lat\FullRandLat',
        '/data/local/tmp/'
    ], capture_output=True, timeout=60)
    adb("chmod 777 /data/local/tmp/*")

    adb("input keyevent 82"); adb("input keyevent 82")
    adb("input keyevent 3")
    adb("settings put system screen_off_timeout 2147483647")

    print("[SETUP] Silencing all bus_dcvs nodes to hw_min...")
    adb("echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq")
    adb(f"echo 547000 > {DDR_BWMON}/max_freq && echo 547000 > {DDR_BWMON}/min_freq && "
        f"echo 547000 > {DDR_BWMON}/max_freq && echo 547000 > {DDR_BWMON}/min_freq")
    adb(f"echo 547000 > {DDR_BWMON}/sched_boost_freq")
    for c in ('soc:qcom,memlat:ddr:gold','soc:qcom,memlat:ddr:gold-compute',
              'soc:qcom,memlat:ddr:prime','soc:qcom,memlat:ddr:prime-latfloor'):
        p = f"/sys/devices/system/cpu/bus_dcvs/DDR/{c}"
        adb(f"echo 547000 > {p}/max_freq && echo 547000 > {p}/min_freq && "
            f"echo 547000 > {p}/max_freq && echo 547000 > {p}/min_freq")
    adb("echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq")
    adb(f"echo 282000 > {LLCC_BWMON}/max_freq && echo 282000 > {LLCC_BWMON}/min_freq && "
        f"echo 282000 > {LLCC_BWMON}/max_freq && echo 282000 > {LLCC_BWMON}/min_freq")
    adb(f"echo 282000 > {LLCC_BWMON}/sched_boost_freq")
    for c in ('soc:qcom,memlat:llcc:gold','soc:qcom,memlat:llcc:gold-compute',
              'soc:qcom,memlat:llcc:prime'):
        p = f"/sys/devices/system/cpu/bus_dcvs/LLCC/{c}"
        adb(f"echo 282000 > {p}/max_freq && echo 282000 > {p}/min_freq && "
            f"echo 282000 > {p}/max_freq && echo 282000 > {p}/min_freq")
    for c in ('soc:qcom,memlat:ddrqos:gold','soc:qcom,memlat:ddrqos:prime',
              'soc:qcom,memlat:ddrqos:prime-latfloor','soc:qcom,memlat:ddrqos:prime-compute'):
        p = f"/sys/devices/system/cpu/bus_dcvs/DDRQOS/{c}"
        adb(f"echo 0 > {p}/max_freq && echo 0 > {p}/min_freq && "
            f"echo 0 > {p}/max_freq && echo 0 > {p}/min_freq")
    print("[SETUP] Done")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='Staged Thompson Sampling optimizer for cpu6')
    parser.add_argument('--stage', type=int, default=0,
                        help='Run specific stage only (1=CPU, 2=DDR, 3=QOS, 4=LLCC). 0=all')
    parser.add_argument('--episodes', type=int, default=DEFAULT_EPISODES,
                        help=f'Thompson Sampling episodes per stage (default {DEFAULT_EPISODES})')
    parser.add_argument('--buf', type=int, default=DEFAULT_BUF,
                        help=f'Buffer KB (default {DEFAULT_BUF})')
    parser.add_argument('--cpu-freq', type=int, default=None,
                        help='Lock CPU freq (skip stage 1)')
    parser.add_argument('--ddr', type=int, default=None,
                        help='Lock DDR freq (skip stage 2)')
    parser.add_argument('--qos', type=int, default=None,
                        help='Lock QOS (skip stage 3)')
    parser.add_argument('--llcc', type=int, default=None,
                        help='Lock LLCC freq (skip stage 4)')
    args = parser.parse_args()

    setup_device(args.buf)

    best_cpu  = args.cpu_freq if args.cpu_freq else DEFAULT_CPU_FREQ
    best_ddr  = args.ddr      if args.ddr      else DEFAULT_DDR
    best_qos  = args.qos      if args.qos is not None else DEFAULT_QOS
    best_llcc = args.llcc     if args.llcc     else DEFAULT_LLCC

    run_all = (args.stage == 0)

    # -----------------------------------------------------------------------
    # Stage 1: CPU freq
    # -----------------------------------------------------------------------
    if run_all or args.stage == 1:
        if args.cpu_freq:
            print(f"\n[STAGE 1] CPU freq locked to {args.cpu_freq/1000:.1f} MHz — skipping")
        else:
            print(f"\n{'='*60}")
            print(f"  STAGE 1: CPU freq  ({len(CPU6_FREQS)} values, {args.episodes} episodes)")
            print(f"  Fixed: DDR={best_ddr//1000} MHz  LLCC={best_llcc//1000} MHz  QOS={best_qos}")
            print(f"{'='*60}")
            cfg = dict(cpu_freq=DEFAULT_CPU_FREQ, ddr=best_ddr, llcc=best_llcc, qos=best_qos)
            best_cpu = run_stage("CPU freq", CPU6_FREQS,
                                 lambda v: f"{v/1000:.1f} MHz",
                                 cfg, 'cpu_freq', args.episodes, args.buf)

    # -----------------------------------------------------------------------
    # Stage 2: DDR freq
    # -----------------------------------------------------------------------
    if run_all or args.stage == 2:
        if args.ddr:
            print(f"\n[STAGE 2] DDR locked to {args.ddr//1000} MHz — skipping")
        else:
            print(f"\n{'='*60}")
            print(f"  STAGE 2: DDR freq  ({len(DDR_FREQS)} values, {args.episodes} episodes)")
            print(f"  Fixed: CPU={best_cpu/1000:.1f} MHz  LLCC={best_llcc//1000} MHz  QOS={best_qos}")
            print(f"{'='*60}")
            cfg = dict(cpu_freq=best_cpu, ddr=DEFAULT_DDR, llcc=best_llcc, qos=best_qos)
            best_ddr = run_stage("DDR freq", DDR_FREQS,
                                 lambda v: f"{v//1000} MHz",
                                 cfg, 'ddr', args.episodes, args.buf)

    # -----------------------------------------------------------------------
    # Stage 3: DDRQOS
    # -----------------------------------------------------------------------
    if run_all or args.stage == 3:
        if args.qos is not None:
            print(f"\n[STAGE 3] QOS locked to {args.qos} — skipping")
        else:
            print(f"\n{'='*60}")
            print(f"  STAGE 3: DDRQOS  ({len(DDRQOS_VALS)} values, {args.episodes} episodes)")
            print(f"  Fixed: CPU={best_cpu/1000:.1f} MHz  DDR={best_ddr//1000} MHz  LLCC={best_llcc//1000} MHz")
            print(f"{'='*60}")
            cfg = dict(cpu_freq=best_cpu, ddr=best_ddr, llcc=best_llcc, qos=DEFAULT_QOS)
            best_qos = run_stage("DDRQOS", DDRQOS_VALS,
                                 lambda v: f"QOS={v}",
                                 cfg, 'qos', args.episodes, args.buf)

    # -----------------------------------------------------------------------
    # Stage 4: LLCC freq
    # -----------------------------------------------------------------------
    if run_all or args.stage == 4:
        if args.llcc:
            print(f"\n[STAGE 4] LLCC locked to {args.llcc//1000} MHz — skipping")
        else:
            print(f"\n{'='*60}")
            print(f"  STAGE 4: LLCC freq  ({len(LLCC_FREQS)} values, {args.episodes} episodes)")
            print(f"  Fixed: CPU={best_cpu/1000:.1f} MHz  DDR={best_ddr//1000} MHz  QOS={best_qos}")
            print(f"{'='*60}")
            cfg = dict(cpu_freq=best_cpu, ddr=best_ddr, llcc=DEFAULT_LLCC, qos=best_qos)
            best_llcc = run_stage("LLCC freq", LLCC_FREQS,
                                  lambda v: f"{v//1000} MHz",
                                  cfg, 'llcc', args.episodes, args.buf)

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  FINAL RECOMMENDATION")
    print(f"{'='*60}")
    print(f"  CPU6  : {best_cpu/1000:.1f} MHz")
    print(f"  DDR   : {best_ddr//1000} MHz")
    print(f"  LLCC  : {best_llcc//1000} MHz")
    print(f"  QOS   : {best_qos}")
    print(f"  Buffer: {args.buf} KB")
    print()
    print(f"  Confirm with run_best.py after updating its values.")
    print(f"  Re-run any stage:")
    print(f"  python rl_benchmark_staged.py --stage 4 "
          f"--cpu-freq {best_cpu} --ddr {best_ddr} --qos {best_qos} --episodes {args.episodes}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()