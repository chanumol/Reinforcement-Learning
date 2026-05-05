@echo off
REM ============================================================
REM  Manual Benchmark Setup + Run
REM  Edit TARGET FREQUENCIES below, then run this file
REM ============================================================

REM ============================================================
REM  TARGET FREQUENCIES — edit these values
REM ============================================================
set CPU=7
set CPU_FREQ=4358400
set DDR=1708000
set LLCC=1066000
set QOS=1
set BUF=40960
REM ============================================================

echo [SETUP] Rooting...
adb root
adb wait-for-device

echo [SETUP] Setting ALL bus_dcvs nodes to hw_min...

REM DDR bwmon
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/min_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/sched_boost_freq"

REM DDR memlat clients
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold-compute/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold-compute/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime-latfloor/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime-latfloor/min_freq"


REM LLCC bwmon
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/min_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/min_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/DDR/310b7500.qcom,bwmon-llcc/sched_boost_freq"

REM LLCC memlat clients
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold/min_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold-compute/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold-compute/min_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:prime/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:prime/min_freq"


REM DDRQOS memlat clients
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:gold/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:gold/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-latfloor/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-latfloor/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-compute/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-compute/min_freq"

echo [SETUP] All nodes set to hw_min

echo.
echo [CONFIG] Applying target frequencies...
echo   CPU%CPU%  CPU_FREQ=%CPU_FREQ%  DDR=%DDR%  LLCC=%LLCC%  QOS=%QOS%

REM CPU freq hard lock
adb shell "echo %CPU_FREQ% > /sys/devices/system/cpu/cpu%CPU%/cpufreq/scaling_min_freq && echo %CPU_FREQ% > /sys/devices/system/cpu/cpu%CPU%/cpufreq/scaling_max_freq && echo %CPU_FREQ% > /sys/devices/system/cpu/cpu%CPU%/cpufreq/scaling_min_freq && echo %CPU_FREQ% > /sys/devices/system/cpu/cpu%CPU%/cpufreq/scaling_max_freq"

REM DDR bwmon hard lock (highest vote wins)
adb shell "echo %DDR% > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/max_freq && echo %DDR% > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/min_freq && echo %DDR% > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/max_freq && echo %DDR% > /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/min_freq"

REM LLCC bwmon hard lock
adb shell "echo %LLCC% > /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/max_freq && echo %LLCC% > /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/min_freq && echo %LLCC% > /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/max_freq && echo %LLCC% > /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/min_freq"

REM DDRQOS prime memlat hard lock
adb shell "echo %QOS% > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/max_freq && echo %QOS% > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/min_freq && echo %QOS% > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/max_freq && echo %QOS% > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/min_freq && echo %QOS% > /sys/devices/system/cpu/bus_dcvs/DDRQOS/boost_freq"

echo.
echo [VERIFY] Reading back actual frequencies...
adb shell "echo CPU_CUR:   && cat /sys/devices/system/cpu/cpu%CPU%/cpufreq/scaling_cur_freq"
adb shell "echo DDR_CUR:   && cat /sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr/cur_freq"
adb shell "echo LLCC_CUR:  && cat /sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc/cur_freq"
adb shell "echo QOS_CUR:   && cat /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/cur_freq"

echo.
echo [RUN] Running benchmark on cpu%CPU%...
adb shell "taskset 80 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"

echo.
echo Done.
pause