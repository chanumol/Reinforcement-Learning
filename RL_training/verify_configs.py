"""
Verify configurations: cpu7@4358 DDR1708, sweep LLCC + QOS.

Approach (same as rl_benchmark.py):
  Setup:    Set ALL nodes (bwmon + memlat) to hw_min → all votes = minimum
  Per run:  Set only the target bwmon/memlat to desired freq → highest vote → wins
"""

import subprocess
import re
import time

DDR_BWMON    = "/sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr"
LLCC_BWMON   = "/sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc"
DDRQOS_PRIME = "/sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime"
DDRQOS_BASE  = "/sys/devices/system/cpu/bus_dcvs/DDRQOS"
CPU7_ZONE    = '/sys/class/thermal/thermal_zone6/temp'

LLCC_FREQS   = [1350000, 1211000, 1066000, 933000, 806000, 600000, 533000, 350000, 282000]
DDRQOS_VALS  = [0, 1]

CONFIGS = [
    {'name': 'cpu7@4358 DDR1708', 'cpu': 7, 'cpu_freq': 4358400, 'ddr': 1708000},
]

VERIFY_RUNS = 20
BUF         = 40960
TEMP_MAX    = 30


def adb(cmd, timeout=15):
    subprocess.run(['adb', 'shell', cmd], capture_output=True, timeout=timeout)


def read_freq(path):
    try:
        r = subprocess.run(['adb', 'shell', f'cat {path}'],
                           capture_output=True, text=True, timeout=10)
        v = r.stdout.strip()
        return int(v) if v.isdigit() else None
    except Exception:
        return None


def read_temp():
    try:
        r = subprocess.run(['adb', 'shell', f'cat {CPU7_ZONE}'],
                           capture_output=True, text=True, timeout=10)
        v = r.stdout.strip()
        return int(v) / 1000.0 if v.isdigit() else None
    except Exception:
        return None


def wait_for_cool(threshold=TEMP_MAX, poll=3):
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


def lock_node(path, freq):
    """Set min=max=freq on a sysfs node (max first for ordering safety)."""
    adb(f"echo {freq} > {path}/max_freq && echo {freq} > {path}/min_freq && "
        f"echo {freq} > {path}/max_freq && echo {freq} > {path}/min_freq")


def setup_all_to_hwmin():
    """
    Set ALL bus_dcvs nodes (bwmon + memlat) to hw_min.
    This silences all votes so per-run writes become the only active vote.
    """
    print("  [SETUP] Setting all bus_dcvs nodes to hw_min...")
    result = subprocess.run(
        ['adb', 'shell', 'ls -d /sys/devices/system/cpu/bus_dcvs/*/*qcom*'],
        capture_output=True, text=True, timeout=15)
    paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]

    hw_min = {}
    for bus in ('DDR', 'DDRQOS', 'LLCC'):
        try:
            r = subprocess.run(
                ['adb', 'shell', f'cat /sys/devices/system/cpu/bus_dcvs/{bus}/hw_min_freq'],
                capture_output=True, text=True, timeout=10)
            v = r.stdout.strip()
            hw_min[bus] = int(v) if v.isdigit() else 0
        except Exception:
            hw_min[bus] = 0

    print(f"  [SETUP] hw_min: DDR={hw_min['DDR']} DDRQOS={hw_min['DDRQOS']} LLCC={hw_min['LLCC']}")

    for path in paths:
        bus = next((b for b in ('DDR', 'DDRQOS', 'LLCC') if f'/bus_dcvs/{b}/' in path), None)
        if bus is None:
            continue
        freq = hw_min[bus]
        lock_node(path, freq)
        kind = "bwmon " if 'bwmon' in path else "memlat"
        print(f"  [SETUP]   {kind} {path.split('/')[-1]} → {freq}")

    print(f"  [SETUP] Done — {len(paths)} nodes set to hw_min")


def apply_config(cpu, cpu_freq, ddr, llcc, qos):
    """
    Set CPU freq + DDR/LLCC bwmon + DDRQOS memlat to target.
    All other nodes are at hw_min (set in setup), so these become the highest vote → win.
    """
    # CPU freq hard lock
    path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq"
    adb(f"echo {cpu_freq} > {path}/scaling_min_freq && echo {cpu_freq} > {path}/scaling_max_freq && "
        f"echo {cpu_freq} > {path}/scaling_min_freq && echo {cpu_freq} > {path}/scaling_max_freq")

    # DDR bwmon → target (highest vote → wins over all silenced memlat clients)
    lock_node(DDR_BWMON, ddr)

    # LLCC bwmon → target
    lock_node(LLCC_BWMON, llcc)

    # DDRQOS prime memlat → target (all other DDRQOS memlat at 0)
    lock_node(DDRQOS_PRIME, qos)
    adb(f"echo {qos} > {DDRQOS_BASE}/boost_freq")

    # Print actual frequencies after setting
    cpu_cur  = read_freq(f"{path}/scaling_cur_freq")
    ddr_cur  = read_freq(f"{DDR_BWMON}/cur_freq")
    llcc_cur = read_freq(f"{LLCC_BWMON}/cur_freq")
    print(f"    [SET]  CPU={cpu_cur/1000:.1f} MHz  DDR={ddr_cur/1000:.0f} MHz  "
          f"LLCC={llcc_cur/1000:.0f} MHz  QOS={qos}")


def run_once(cpu, taskset='80'):
    # Print actual frequencies at run time
    cpu_path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq"
    cpu_cur  = read_freq(f"{cpu_path}/scaling_cur_freq")
    ddr_cur  = read_freq(f"{DDR_BWMON}/cur_freq")
    llcc_cur = read_freq(f"{LLCC_BWMON}/cur_freq")
    print(f"    [RUN]  CPU={cpu_cur/1000:.1f} MHz  DDR={ddr_cur/1000:.0f} MHz  "
          f"LLCC={llcc_cur/1000:.0f} MHz", end="  ")

    cmd = (f"taskset {taskset} /data/local/tmp/FullRandLat memlat "
           f"-min-buffer-size-kb {BUF} -max-buffer-size-kb {BUF}")
    try:
        r = subprocess.run(['adb', 'shell', cmd], capture_output=True, text=True, timeout=120)
        m = re.search(r'\d+,(\d+\.\d+)', r.stdout + r.stderr)
        lat = float(m.group(1)) if m else None
        print(f"→ {lat:.2f} ns" if lat else "→ FAILED")
        return lat
    except Exception:
        print("→ FAILED")
        return None


def sweep_llcc_qos(cfg):
    print(f"\n  Sweeping LLCC x QOS for {cfg['name']}...")
    print(f"  {'LLCC MHz':>10}  {'QOS':>4}  {'Latency':>10}")
    print("  " + "-" * 30)

    best_lat, best_llcc, best_qos = float('inf'), None, None

    for llcc in LLCC_FREQS:
        for qos in DDRQOS_VALS:
            apply_config(cfg['cpu'], cfg['cpu_freq'], cfg['ddr'], llcc, qos)
            wait_for_cool()
            lat = run_once(cfg['cpu'])
            if lat is not None:
                tag = " <-- best" if lat < best_lat else ""
                if lat < best_lat:
                    best_lat, best_llcc, best_qos = lat, llcc, qos
                print(f"  {llcc/1000:>8.0f}  {qos:>4}  {lat:>8.2f} ns{tag}")
            else:
                print(f"  {llcc/1000:>8.0f}  {qos:>4}  FAILED")

    print(f"\n  Best LLCC: {best_llcc/1000:.0f} MHz  QOS: {best_qos}  → {best_lat:.2f} ns")
    return best_llcc, best_qos, best_lat


def verify_best(cfg, llcc, qos):
    print(f"\n  Verifying {cfg['name']} LLCC={llcc/1000:.0f} QOS={qos} x {VERIFY_RUNS} runs...")
    apply_config(cfg['cpu'], cfg['cpu_freq'], cfg['ddr'], llcc, qos)

    results = []
    for i in range(1, VERIFY_RUNS + 1):
        wait_for_cool()
        print(f"  Run {i:>2}/{VERIFY_RUNS}:", end=" ")
        lat = run_once(cfg['cpu'])
        if lat is not None:
            results.append(lat)

    if results:
        avg = sum(results) / len(results)
        print(f"\n  Min={min(results):.2f}  Avg={avg:.2f}  Max={max(results):.2f} ns")
        return avg, min(results), max(results)
    return None, None, None


def main():
    print("  [SETUP] Rooting...")
    subprocess.run(['adb', 'root'], capture_output=True, timeout=15)
    subprocess.run(['adb', 'wait-for-device'], capture_output=True, timeout=30)
    setup_all_to_hwmin()

    summary = []

    for cfg in CONFIGS:
        print(f"\n{'='*60}")
        print(f"  {cfg['name']}")
        print(f"{'='*60}")

        best_llcc, best_qos, sweep_best = sweep_llcc_qos(cfg)
        avg, mn, mx = verify_best(cfg, best_llcc, best_qos)

        summary.append({
            'name': cfg['name'],
            'cpu_freq_mhz': cfg['cpu_freq'] / 1000,
            'ddr_mhz': cfg['ddr'] / 1000,
            'llcc_mhz': best_llcc / 1000,
            'qos': best_qos,
            'avg': avg, 'min': mn, 'max': mx
        })

    print(f"\n{'='*60}")
    print("  FINAL SUMMARY")
    print(f"{'='*60}")
    for s in summary:
        print(f"  {s['name']}")
        print(f"    CPU={s['cpu_freq_mhz']:.1f} MHz  DDR={s['ddr_mhz']:.0f} MHz  "
              f"LLCC={s['llcc_mhz']:.0f} MHz  QOS={s['qos']}")
        if s['avg']:
            print(f"    Min={s['min']:.2f}  Avg={s['avg']:.2f}  Max={s['max']:.2f} ns")


if __name__ == '__main__':
    main()