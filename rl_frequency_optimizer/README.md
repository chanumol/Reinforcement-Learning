# RL Frequency Optimizer

A **Double DQN** reinforcement learning agent that discovers the optimal
CPU / DDR / DDRQOS / LLCC frequency combination **and** target CPU for
running `FullRandLat memlat` with minimum memory latency.

All frequency levels are discovered live from the connected Android device —
no hard-coded values, no simulation.

---

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent (Double DQN)                   │
│  state → Q-network → argmax action → epsilon-greedy select  │
└────────────────────────┬────────────────────────────────────┘
                         │ action (freq combo + target CPU)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   AndroidFreqEnv (env.py)                   │
│  1. adb: set CPU governor + freq on all cores               │
│  2. adb: set DDR / DDRQOS / LLCC boost_freq                 │
│  3. adb: taskset <mask> FullRandLat memlat …                │
│  4. parse latency (ns) from output                          │
│  5. reward = -latency_ns / 1_000_000                        │
└─────────────────────────────────────────────────────────────┘
                         │ (next_state, reward, done, info)
                         ▼
              Agent stores transition → learns
```

### Components

| File | Purpose |
|------|---------|
| `freq_space.py` | Discovers all available freq levels from device via adb |
| `env.py` | RL environment — applies configs, runs benchmark, returns reward |
| `agent.py` | Double DQN agent with experience replay |
| `train.py` | Training loop, checkpointing, evaluation |

### Does the agent try all 42,768 combinations?

**No.** Exhaustive search would take ~42,768 runs × ~2 s each ≈ 24 hours.
Instead, Double DQN *learns* which combinations are likely good and focuses
exploration there:

```
Episode 1–50   ε=1.00  Pure random exploration — samples the space broadly
Episode 50–200 ε→0.30  Guided: Q-network starts predicting good actions
Episode 200+   ε→0.05  Mostly exploits learned knowledge, 5% random
```

The **Q-network generalises**: after observing that
`cpu=3475200 kHz + ddr=5333000 kHz` gives low latency on CPU7, it infers
that nearby combinations are also likely good — without testing every one.
In practice the agent converges to a near-optimal configuration after
exploring only a few thousand combinations (not all 42,768).

The `best_config.json` is updated **every time** a new minimum latency is
found, so you always have the best result seen so far, even mid-training.

### Why Double DQN?
- Action space is large but **discrete** (all freq combinations)
- Avoids Q-value overestimation vs vanilla DQN
- Stable with target network + Huber loss
- Easy to extend: add power as a second reward term later

---

## Prerequisites

- Android device connected via `adb` with root access
- `FullRandLat` binary pushed to `/data/local/tmp/FullRandLat`
- Python 3.10+

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
# Start training (device must be connected):
python train.py

# Resume from last checkpoint:
python train.py --resume

# Evaluate the best saved configuration:
python train.py --eval

# Custom episode / step count:
python train.py --episodes 300 --steps 150
```

---

## Output files

| File | Contents |
|------|----------|
| `best_config.json` | Best frequency configuration found |
| `checkpoint.pt` | Agent checkpoint (saved every 50 episodes) |
| `results.jsonl` | Per-episode metrics (JSON lines) |
| `training.log` | Full training log |

### Example `best_config.json`
```json
{
  "cpu_freq":     4435200,
  "ddr_freq":     5333000,
  "ddrqos_freq":  1,
  "llcc_freq":    1350000,
  "target_cpu":   7,
  "taskset_mask": "0x80",
  "latency_ns":   12345
}
```

### Reproduce the best result
After training, `train.py --eval` prints the exact adb commands:

```bash
adb shell echo userspace > /sys/devices/system/cpu/cpu7/cpufreq/scaling_governor
adb shell echo 4435200  > /sys/devices/system/cpu/cpu7/cpufreq/scaling_setspeed
adb shell echo 5333000  > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq
adb shell echo 1        > /sys/devices/system/cpu/bus_dcvs/DDRQOS/boost_freq
adb shell echo 1350000  > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq
adb shell taskset 0x80 /data/local/tmp/FullRandLat memlat \
    -min-buffer-size-kb 65536 -max-buffer-size-kb 65536
```

---

## Extending the reward signal

In `env.py`, the reward is currently:
```python
reward = -latency_ns / 1_000_000
```

To add power as a second objective later, change to:
```python
reward = -latency_ns / 1_000_000  -  alpha * power_mw
```
and read `power_mw` from the device's power rail sensors via adb.