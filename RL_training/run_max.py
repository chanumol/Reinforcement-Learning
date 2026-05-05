"""
Reference run: ALL frequencies at maximum, cpu6, 10 times with thermal check.
cpu6 @ 4435.2 MHz (max), DDR=5333 MHz (max), LLCC=1350 MHz (max), QOS=1
Buffer: 65536 KB (64 MB)
Use this as a baseline to compare against the optimized config.
"""

import subprocess
import re
import time

CPU_FREQ  = 4435200   # Prime max
DDR       = 5333000   # DDR max
LLCC      = 1350000   # LLCC max
QOS       = 1
BUF       = 65536
TEMP_MAX  = 35
RUNS      = 10

DDR_BWMON    = "/sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr"
LLCC_BWMON   = "/sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc"
DDRQOS_PRIME = "/sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime"
DDRQOS_BASE  = "/sys/devices/system/cpu/bus_dcvs/DDRQOS"
CPU6_ZONE    = "/sys/class/thermal/thermal_zone18/temp"


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


def verify_freqs():
    """Read back cur_freq and confirm they match targets. Stops if mismatch."""
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
    if cpu_cur != CPU_FREQ:
        mismatches.append(f"CPU: got {cpu_cur} want {CPU_FREQ}")
        ok = False
    if ddr_cur != DDR:
        mismatches.append(f"DDR: got {ddr_cur} want {DDR}")
        ok = False
    if llcc_cur != LLCC:
        mismatches.append(f"LLCC: got {llcc_cur} want {LLCC}")
        ok = False
    if qos_cur not in (QOS, QOS * 1000):
        mismatches.append(f"QOS: got {qos_cur} want {QOS}")
        ok = False

    if ok:
        print(f"    [VERIFY] CPU={cpu_cur/1000:.1f}MHz  DDR={ddr_cur/1000:.0f}MHz  "
              f"LLCC={llcc_cur/1000:.0f}MHz  QOS={qos_cur} — OK")
    else:
        print(f"    [VERIFY] MISMATCH — {', '.join(mismatches)}")
        raise SystemExit(1)


def run_benchmark():
    cmd = (f"taskset 40 /data/local/tmp/FullRandLat memlat "
           f"-min-buffer-size-kb {BUF} -max-buffer-size-kb {BUF}")
    try:
        r = subprocess.run(['adb', 'shell', cmd],
                           capture_output=True, text=True, timeout=120)
        m = re.search(r'\d+,(\d+\.\d+)', r.stdout + r.stderr)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def setup():
    print("[STEP 1] Rooting...")
    subprocess.run(['adb', 'root'], capture_output=True, timeout=15)
    subprocess.run(['adb', 'wait-for-device'], capture_output=True, timeout=30)

    print("[STEP 2] Pushing binary...")
    subprocess.run([
        'adb', 'push',
        r'\\sundae\APT_Logs_PPTKGolden\Kernel\Test-binaries-compact\full-rand-lat\FullRandLat',
        '/data/local/tmp/'
    ], capture_output=True, timeout=60)
    adb("chmod 777 /data/local/tmp/*")

    print("[STEP 3] Wake screen...")
    adb("input keyevent 82"); adb("input keyevent 82")
    adb("input keyevent 3")
    adb("settings put system screen_off_timeout 2147483647")

    print("[STEP 4] Silencing all bus_dcvs nodes to hw_min (baseline)...")
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

    print("[STEP 5] Applying MAX configuration...")
    path = "/sys/devices/system/cpu/cpu6/cpufreq"
    adb(f"echo {CPU_FREQ} > {path}/scaling_min_freq && echo {CPU_FREQ} > {path}/scaling_max_freq && "
        f"echo {CPU_FREQ} > {path}/scaling_min_freq && echo {CPU_FREQ} > {path}/scaling_max_freq")
    adb(f"echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq && "
        f"echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq")
    adb(f"echo 547000 > {DDR_BWMON}/sched_boost_freq && echo 282000 > {LLCC_BWMON}/sched_boost_freq")
    adb(f"echo {DDR} > {DDR_BWMON}/max_freq && echo {DDR} > {DDR_BWMON}/min_freq && "
        f"echo {DDR} > {DDR_BWMON}/max_freq && echo {DDR} > {DDR_BWMON}/min_freq && "
        f"echo {LLCC} > {LLCC_BWMON}/max_freq && echo {LLCC} > {LLCC_BWMON}/min_freq && "
        f"echo {LLCC} > {LLCC_BWMON}/max_freq && echo {LLCC} > {LLCC_BWMON}/min_freq")
    adb(f"echo {QOS} > {DDRQOS_PRIME}/max_freq && echo {QOS} > {DDRQOS_PRIME}/min_freq && "
        f"echo {QOS} > {DDRQOS_PRIME}/max_freq && echo {QOS} > {DDRQOS_PRIME}/min_freq && "
        f"echo {QOS} > {DDRQOS_BASE}/boost_freq")

    print(f"  cpu6={CPU_FREQ/1000:.1f}MHz  DDR={DDR/1000:.0f}MHz  "
          f"LLCC={LLCC/1000:.0f}MHz  QOS={QOS}  (ALL MAX)")


def main():
    setup()

    print()
    print("=" * 60)
    print(f"  MAX FREQ REFERENCE RUN — {RUNS} times with thermal check")
    print(f"  cpu6={CPU_FREQ/1000:.1f}  DDR={DDR/1000:.0f}  LLCC={LLCC/1000:.0f}  QOS={QOS}")
    print("=" * 60)

    results = []
    for i in range(1, RUNS + 1):
        verify_freqs()
        wait_for_cool()
        lat = run_benchmark()
        if lat is not None:
            results.append(lat)
            print(f"  Run {i:>2}/{RUNS}: {lat:.2f} ns")
        else:
            print(f"  Run {i:>2}/{RUNS}: FAILED")

    if results:
        print()
        print("=" * 60)
        print(f"  MAX FREQ RESULTS ({len(results)}/{RUNS} successful)")
        print(f"  Min : {min(results):.2f} ns")
        print(f"  Avg : {sum(results)/len(results):.2f} ns")
        print(f"  Max : {max(results):.2f} ns")
        print()
        print("  Compare with optimized (run_best.py):")
        print(f"  Optimized: cpu6@4435.2  DDR=4224  LLCC=806  QOS=1")
        print(f"  Max freq:  cpu6@4435.2  DDR=5333  LLCC=1350 QOS=1")
        print("=" * 60)


if __name__ == '__main__':
    main()