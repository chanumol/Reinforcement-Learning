@echo off
REM ============================================================
REM  Reproduce the sched_boost_freq race condition test
REM  Step A: Max all CPUs + min all bus_dcvs
REM  Step B: Cat to verify all at hw_min
REM  Step C: Change DDR to a target freq (e.g. 4224000)
REM  Step D: Cat to verify DDR changed
REM  Step E: Max all CPUs again (simulate what RL does per episode)
REM  Step F: Cat to verify if sched_boost_freq got reset by kernel
REM ============================================================

set DDR_TARGET=4224000
set LLCC_TARGET=1066000
set DDR_BWMON=/sys/devices/system/cpu/bus_dcvs/DDR/31081000.qcom,bwmon-ddr
set LLCC_BWMON=/sys/devices/system/cpu/bus_dcvs/LLCC/310b7500.qcom,bwmon-llcc

echo ============================================================
echo  STEP A: Root + Max all CPUs + Min all bus_dcvs
echo ============================================================
adb root
adb wait-for-device

REM Max all CPUs
adb shell "echo 3475200 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
adb shell "echo 3475200 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_max_freq"
adb shell "echo 3475200 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_max_freq"
adb shell "echo 3916800 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_max_freq"
adb shell "echo 3916800 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_max_freq"
adb shell "echo 3916800 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_max_freq"
adb shell "echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq"
adb shell "echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq"

REM Min all bus_dcvs (DDR, LLCC, DDRQOS) including boost + sched_boost
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq"
adb shell "echo 547000 > %DDR_BWMON%/max_freq && echo 547000 > %DDR_BWMON%/min_freq && echo 547000 > %DDR_BWMON%/max_freq && echo 547000 > %DDR_BWMON%/min_freq"
adb shell "echo 547000 > %DDR_BWMON%/sched_boost_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold-compute/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:gold-compute/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime/min_freq"
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime-latfloor/max_freq && echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/soc:qcom,memlat:ddr:prime-latfloor/min_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq"
adb shell "echo 282000 > %LLCC_BWMON%/max_freq && echo 282000 > %LLCC_BWMON%/min_freq && echo 282000 > %LLCC_BWMON%/max_freq && echo 282000 > %LLCC_BWMON%/min_freq"
adb shell "echo 282000 > %LLCC_BWMON%/sched_boost_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold/min_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold-compute/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:gold-compute/min_freq"
adb shell "echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:prime/max_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/soc:qcom,memlat:llcc:prime/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:gold/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:gold/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-latfloor/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-latfloor/min_freq"
adb shell "echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-compute/max_freq && echo 0 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/soc:qcom,memlat:ddrqos:prime-compute/min_freq"
echo   Done.
echo.

echo ============================================================
echo  STEP B: CAT — Verify all at hw_min (CPUs at max)
echo ============================================================
adb shell "echo === CPU cur_freq === && for cpu in 0 1 2 3 4 5 6 7; do echo -n cpu$cpu=; cat /sys/devices/system/cpu/cpu$cpu/cpufreq/scaling_cur_freq; done"
adb shell "echo === Bus cur_freq === && echo DDR= && cat /sys/devices/system/cpu/bus_dcvs/DDR/cur_freq && echo LLCC= && cat /sys/devices/system/cpu/bus_dcvs/LLCC/cur_freq && echo DDRQOS= && cat /sys/devices/system/cpu/bus_dcvs/DDRQOS/cur_freq"
adb shell "echo === sched_boost_freq === && echo DDR_sched= && cat %DDR_BWMON%/sched_boost_freq && echo LLCC_sched= && cat %LLCC_BWMON%/sched_boost_freq"
echo.
pause

echo ============================================================
echo  STEP C: Change DDR to %DDR_TARGET% and LLCC to %LLCC_TARGET%
echo          (simulating what RL does per episode)
echo ============================================================
adb shell "echo 547000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq && echo 282000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq"
adb shell "echo 547000 > %DDR_BWMON%/sched_boost_freq && echo 282000 > %LLCC_BWMON%/sched_boost_freq"
adb shell "echo %DDR_TARGET% > %DDR_BWMON%/max_freq && echo %DDR_TARGET% > %DDR_BWMON%/min_freq && echo %DDR_TARGET% > %DDR_BWMON%/max_freq && echo %DDR_TARGET% > %DDR_BWMON%/min_freq"
adb shell "echo %LLCC_TARGET% > %LLCC_BWMON%/max_freq && echo %LLCC_TARGET% > %LLCC_BWMON%/min_freq && echo %LLCC_TARGET% > %LLCC_BWMON%/max_freq && echo %LLCC_TARGET% > %LLCC_BWMON%/min_freq"
echo   Set DDR=%DDR_TARGET%  LLCC=%LLCC_TARGET%
echo.

echo ============================================================
echo  STEP D: CAT — Verify DDR/LLCC changed to target
echo ============================================================
adb shell "echo === Bus cur_freq after change === && echo DDR= && cat /sys/devices/system/cpu/bus_dcvs/DDR/cur_freq && echo LLCC= && cat /sys/devices/system/cpu/bus_dcvs/LLCC/cur_freq"
adb shell "echo === sched_boost_freq after change === && echo DDR_sched= && cat %DDR_BWMON%/sched_boost_freq && echo LLCC_sched= && cat %LLCC_BWMON%/sched_boost_freq"
echo.
pause

echo ============================================================
echo  STEP E: Max all CPUs again (simulate next RL episode)
echo ============================================================
adb shell "echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq"
adb shell "echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq"
echo   CPU6-7 set to max again.
echo.

echo ============================================================
echo  STEP F: CAT — Did sched_boost_freq get reset by kernel?
echo          If DDR/LLCC cur_freq jumped back to max = RACE CONDITION
echo          If DDR/LLCC cur_freq stayed at target = NO RACE CONDITION
echo ============================================================
adb shell "echo === Bus cur_freq AFTER re-maxing CPUs === && echo DDR= && cat /sys/devices/system/cpu/bus_dcvs/DDR/cur_freq && echo LLCC= && cat /sys/devices/system/cpu/bus_dcvs/LLCC/cur_freq"
adb shell "echo === sched_boost_freq AFTER re-maxing CPUs === && echo DDR_sched= && cat %DDR_BWMON%/sched_boost_freq && echo LLCC_sched= && cat %LLCC_BWMON%/sched_boost_freq"
echo.
echo ============================================================
echo  RESULT:
echo    DDR=%DDR_TARGET% and LLCC=%LLCC_TARGET% = NO race condition (good)
echo    DDR=5333000 or LLCC=1350000             = RACE CONDITION (kernel reset sched_boost)
echo ============================================================
pause