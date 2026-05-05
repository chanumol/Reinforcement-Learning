adb wait-for-device
adb wait-for-device
adb root
adb wait-for-device
adb wait-for-device
REM Clear old traces
adb shell "echo 0 > /sys/kernel/tracing/tracing_on"
adb shell "echo > /sys/kernel/tracing/set_event"
adb shell "echo > /sys/kernel/tracing/trace"
adb shell "echo 0 > /sys/kernel/tracing/options/irq-info"
REM Bus traces
REM adb shell "echo power:memlat_dev_update >> /sys/kernel/tracing/set_event"
REM adb shell "echo power:memlat_dev_meas >> /sys/kernel/tracing/set_event"
REM adb shell "echo power:bw_hwmon_meas >> /sys/kernel/tracing/set_event"
REM adb shell "echo power:bw_hwmon_update >> /sys/kernel/tracing/set_event"
REM For Systrace
REM Governor trace
REM adb shell "echo power:sugov_util_update >> /sys/kernel/tracing/set_event"
REM adb shell "echo power:sugov_next_freq >> /sys/kernel/tracing/set_event"
REM Sched traces
adb shell "echo sched:sched_switch >> /sys/kernel/tracing/set_event"
REM adb shell "echo sched:* >> /sys/kernel/tracing/set_event"
REM adb shell "echo schedwalt:*  >> /sys/kernel/tracing/set_event"
adb shell "echo power:cpu_frequency >> /sys/kernel/tracing/set_event"
REM adb shell "echo power:cpu_idle >> /sys/kernel/tracing/set_event
adb shell cat /sys/kernel/tracing/set_event
adb shell "echo 50000 > /sys/kernel/tracing/buffer_size_kb"
adb shell "echo 50000 > /sys/kernel/tracing/buffer_size_kb"
adb shell "echo 50000 > /sys/kernel/tracing/buffer_size_kb"
adb shell "echo 50000 > /sys/kernel/tracing/buffer_size_kb"
adb shell "echo 50000 > /sys/kernel/tracing/buffer_size_kb"
adb shell "echo 0 > /sys/kernel/tracing/options/irq-info"
adb shell cat /sys/kernel/tracing/buffer_size_kb
adb shell "echo 1 > /sys/kernel/tracing/tracing_on"
adb shell "sleep 120"
rem adb shell taskset 40 /data/local/tmp/FullRandLat memlat -min-buffer-size-kb 65536 -max-buffer-size-kb 65536
adb shell "sleep 0.2"
adb shell "echo 0 > /sys/kernel/tracing/tracing_on"
adb pull /sys/kernel/tracing/trace trace.txt