adb wait-for-device
adb wait-for-device
adb root
adb wait-for-device
adb wait-for-device
adb shell "echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
adb shell "echo performance > /sys/devices/system/cpu/cpu1/cpufreq/scaling_governor"
adb shell "echo performance > /sys/devices/system/cpu/cpu2/cpufreq/scaling_governor"
adb shell "echo performance > /sys/devices/system/cpu/cpu3/cpufreq/scaling_governor"
adb shell "echo performance > /sys/devices/system/cpu/cpu4/cpufreq/scaling_governor"
adb shell "echo performance > /sys/devices/system/cpu/cpu5/cpufreq/scaling_governor"
adb shell "echo performance > /sys/devices/system/cpu/cpu6/cpufreq/scaling_governor"
adb shell "echo performance > /sys/devices/system/cpu/cpu7/cpufreq/scaling_governor"
adb shell "echo 5333000 > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq"
adb shell "echo 1 > /sys/devices/system/cpu/bus_dcvs/DDRQOS/boost_freq"
adb shell "echo 1350000 > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq"