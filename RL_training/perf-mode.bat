adb wait-for-device
adb wait-for-device
adb root
adb wait-for-device
adb wait-for-device

REM === Wake screen and prevent timeout ===
adb shell input keyevent 82
adb shell input keyevent 82
adb shell input keyevent 82
adb shell input keyevent 82
adb shell input keyevent 3
adb shell settings put system screen_off_timeout 2147483647

REM =========================================================
REM  Pass "max" or "min" as argument: perf-mode.bat max
REM  Default = max if no argument supplied
IF "%1"=="" (SET MODE=max) ELSE (SET MODE=%1)
ECHO Running in %MODE% frequency mode
REM =========================================================

IF "%MODE%"=="max" (
    REM === MAX frequency: lock each cluster at hw_max ===
    adb shell "echo 3475200 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq"
    adb shell "echo 3475200 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_min_freq"
    adb shell "echo 3475200 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_min_freq && echo 3475200 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_max_freq && echo 3475200 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_min_freq"
    adb shell "echo 3916800 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_min_freq"
    adb shell "echo 3916800 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_min_freq"
    adb shell "echo 3916800 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_min_freq && echo 3916800 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_max_freq && echo 3916800 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_min_freq"
    adb shell "echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq && echo 4435200 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq"
    adb shell "echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_min_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq && echo 4435200 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_min_freq"
) ELSE (
    REM === MIN frequency: lock each cluster at hw_min ===
    adb shell "echo 864000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq && echo 864000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq && echo 864000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq && echo 864000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
    adb shell "echo 864000 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_min_freq && echo 864000 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_max_freq && echo 864000 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_min_freq && echo 864000 > /sys/devices/system/cpu/cpu1/cpufreq/scaling_max_freq"
    adb shell "echo 864000 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_min_freq && echo 864000 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_max_freq && echo 864000 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_min_freq && echo 864000 > /sys/devices/system/cpu/cpu2/cpufreq/scaling_max_freq"
    adb shell "echo 960000 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_min_freq && echo 960000 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_max_freq && echo 960000 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_min_freq && echo 960000 > /sys/devices/system/cpu/cpu3/cpufreq/scaling_max_freq"
    adb shell "echo 960000 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_min_freq && echo 960000 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_max_freq && echo 960000 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_min_freq && echo 960000 > /sys/devices/system/cpu/cpu4/cpufreq/scaling_max_freq"
    adb shell "echo 960000 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_min_freq && echo 960000 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_max_freq && echo 960000 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_min_freq && echo 960000 > /sys/devices/system/cpu/cpu5/cpufreq/scaling_max_freq"
    adb shell "echo 288000 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo 288000 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq && echo 288000 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_min_freq && echo 288000 > /sys/devices/system/cpu/cpu6/cpufreq/scaling_max_freq"
    adb shell "echo 288000 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_min_freq && echo 288000 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq && echo 288000 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_min_freq && echo 288000 > /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq"
)

REM === DDR / LLCC / DDRQOS: boost to max ===
adb shell "echo 5333000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq"
adb shell "echo 1 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/boost_freq"
adb shell "echo 1350000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq"

REM === Verify: cur = min = max for each cluster ===
adb shell "echo --- policy0 cpu0-2 cur/min/max --- && cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq && cat /sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq && cat /sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq"
adb shell "echo --- policy3 cpu3-5 cur/min/max --- && cat /sys/devices/system/cpu/cpufreq/policy3/scaling_cur_freq && cat /sys/devices/system/cpu/cpufreq/policy3/scaling_min_freq && cat /sys/devices/system/cpu/cpufreq/policy3/scaling_max_freq"
adb shell "echo --- policy6 cpu6-7 cur/min/max --- && cat /sys/devices/system/cpu/cpufreq/policy6/scaling_cur_freq && cat /sys/devices/system/cpu/cpufreq/policy6/scaling_min_freq && cat /sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq"
adb shell "echo --- DDR cur_freq --- && cat /sys/devices/system/cpu/bus_dcvs/DDR/cur_freq"
adb shell "echo --- LLCC cur_freq --- && cat /sys/devices/system/cpu/bus_dcvs/LLCC/cur_freq"