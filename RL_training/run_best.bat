@echo off
REM ============================================================
REM  Run Best Configuration from RL Benchmark
REM  cpu6 @ 4435.2 MHz, DDR=4224 MHz, LLCC=806 MHz, QOS=1
REM  Buffer: 65536 KB (64 MB)
REM  Same conditions as rl_benchmark_cpu6.py
REM ============================================================

set CPU=6
set CPU_FREQ=4358400
set DDR=4224000
set LLCC=933000
set QOS=1
set BUF=65536
set TEMP_MAX=35
set DDR_BWMON=/sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr
set LLCC_BWMON=/sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc
set DDRQOS_PRIME=/sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime
set DDRQOS_BASE=/sys/devices/system/cpu/bus_dcvs/DDRQOS

echo ============================================================
echo  STEP 1: Root
echo ============================================================
adb root
adb wait-for-device
echo.

echo ============================================================
echo  STEP 2: Push benchmark binary
echo ============================================================
adb push \\sundae\APT_Logs_PPTKGolden\Kernel\Test-binaries-compact\full-rand-lat\FullRandLat /data/local/tmp/
adb shell "chmod 777 /data/local/tmp/FullRandLat"
echo.

echo ============================================================
echo  STEP 3: Wake screen + prevent timeout
echo ============================================================
adb shell "input keyevent 82"
adb shell "input keyevent 82"
adb shell "input keyevent 82"
adb shell "input keyevent 3"
adb shell "settings put system screen_off_timeout 2147483647"
echo.

echo ============================================================
echo  STEP 4: Silence all bus_dcvs nodes to hw_min
echo          (bwmon + memlat + boost + sched_boost)
echo ============================================================
REM DDR bus boost
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq"
REM DDR bwmon
adb shell "echo 547000 > %DDR_BWMON%/max_freq && echo 547000 > %DDR_BWMON%/min_freq && echo 547000 > %DDR_BWMON%/max_freq && echo 547000 > %DDR_BWMON%/min_freq"
adb shell "echo 547000 > %DDR_BWMON%/sched_boost_freq"
REM DDR memlat clients
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold/min_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold-compute/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold-compute/min_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold-compute/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold-compute/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime/min_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime-latfloor/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime-latfloor/min_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime-latfloor/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime-latfloor/min_freq"
REM LLCC bus boost
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq"
REM LLCC bwmon
adb shell "echo 282000 > %LLCC_BWMON%/max_freq && echo 282000 > %LLCC_BWMON%/min_freq && echo 282000 > %LLCC_BWMON%/max_freq && echo 282000 > %LLCC_BWMON%/min_freq"
adb shell "echo 282000 > %LLCC_BWMON%/sched_boost_freq"
REM LLCC memlat clients
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold/min_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold/min_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold-compute/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold-compute/min_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold-compute/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold-compute/min_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:prime/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:prime/min_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:prime/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:prime/min_freq"
REM DDRQOS memlat clients
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:gold/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:gold/min_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:gold/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:gold/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/min_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-latfloor/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-latfloor/min_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-latfloor/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-latfloor/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-compute/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-compute/min_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-compute/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-compute/min_freq"
echo   All nodes set to hw_min.
echo.

echo ============================================================
echo  STEP 5: Apply best configuration
echo          cpu6=%CPU_FREQ%  DDR=%DDR%  LLCC=%LLCC%  QOS=%QOS%
echo ============================================================
REM CPU6 hard lock
adb shell "echo %CPU_FREQ% > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo %CPU_FREQ% > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq && echo %CPU_FREQ% > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo %CPU_FREQ% > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq"
REM Reset sched_boost + bus boost before setting target
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq"
adb shell "echo 547000 > %DDR_BWMON%/sched_boost_freq && echo 282000 > %LLCC_BWMON%/sched_boost_freq"
REM DDR hard lock
adb shell "echo %DDR% > %DDR_BWMON%/max_freq && echo %DDR% > %DDR_BWMON%/min_freq && echo %DDR% > %DDR_BWMON%/max_freq && echo %DDR% > %DDR_BWMON%/min_freq"
REM LLCC hard lock
adb shell "echo %LLCC% > %LLCC_BWMON%/max_freq && echo %LLCC% > %LLCC_BWMON%/min_freq && echo %LLCC% > %LLCC_BWMON%/max_freq && echo %LLCC% > %LLCC_BWMON%/min_freq"
REM DDRQOS
adb shell "echo %QOS% > %DDRQOS_PRIME%/max_freq && echo %QOS% > %DDRQOS_PRIME%/min_freq && echo %QOS% > %DDRQOS_PRIME%/max_freq && echo %QOS% > %DDRQOS_PRIME%/min_freq && echo %QOS% > %DDRQOS_BASE%/boost_freq"
echo.

echo ============================================================
echo  STEP 6: Verify frequencies
echo ============================================================
adb shell "echo CPU6_cur: && cat /sys/devices/system/cpu/cpu6/cpufreq/scaling_cur_freq"
adb shell "echo DDR_cur:  && cat /sys/devices/system/cpu/bus_dcvs/DDR/cur_freq"
adb shell "echo LLCC_cur: && cat /sys/devices/system/cpu/bus_dcvs/LLCC/cur_freq"
adb shell "echo QOS_cur:  && cat /sys/devices/system/cpu/bus_dcvs/DDRQOS/cur_freq"
echo.

echo ============================================================
echo  STEP 7: Wait for cpu6 temp to drop to <= %TEMP_MAX%C
echo ============================================================
:WAIT_TEMP
for /f %%T in ('adb shell "cat /sys/class/thermal/thermal_zone18/temp"') do set RAW_TEMP=%%T
set /a TEMP_C=%RAW_TEMP% / 1000
echo   cpu6 temp: %TEMP_C%C
if %TEMP_C% GTR %TEMP_MAX% (
    echo   Too hot, waiting 3s...
    timeout /t 3 /nobreak >nul
    goto WAIT_TEMP
)
echo   Temperature OK: %TEMP_C%C
echo.

echo ============================================================
echo  STEP 8: Run benchmark 10 times (taskset 40 = cpu6, 64MB)
echo ============================================================

echo   Run 1/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 2/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 3/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 4/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 5/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 6/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 7/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 8/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 9/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"
timeout /t 5 /nobreak >nul

echo   Run 10/10...
adb shell "taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb %BUF% -max-buffer-size-kb %BUF%"

echo.
echo ============================================================
echo  All 10 runs complete.
echo  Config: cpu6@%CPU_FREQ%Hz  DDR=%DDR%  LLCC=%LLCC%  QOS=%QOS%
echo  Scroll up to see all latency values.
echo ============================================================
pause
