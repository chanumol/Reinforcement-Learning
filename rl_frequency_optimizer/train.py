"""
train.py
--------
Main training loop for the RL frequency optimizer.

The agent explores all combinations of:
  CPU frequency × DDR boost × DDRQOS boost × LLCC boost × target CPU

and learns — via Double DQN — which combination minimises FullRandLat
memory latency on the connected Android device.

Usage
-----
  # Start training (device must be connected via adb):
  python train.py

  # Resume from last checkpoint:
  python train.py --resume

  # Evaluate the best saved configuration (no training):
  python train.py --eval

  # Override number of episodes / steps:
  python train.py --episodes 300 --steps 150

Output files
------------
  best_config.json   – best frequency configuration found so far
  checkpoint.pt      – agent checkpoint (saved every 50 episodes)
  results.jsonl      – per-episode metrics (JSON lines)
  training.log       – full log
"""

import argparse
import json
import logging
import os
import sys
import numpy as np

# Force UTF-8 on Windows so log file handles Unicode; console uses ASCII-safe messages
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("training.log"),
    ],
)
logger = logging.getLogger("train")

from freq_space import FrequencySpace
from env        import AndroidFreqEnv, PENALTY_LATENCY_NS, BENCHMARK_ARGS
from agent      import DoubleDQNAgent

CHECKPOINT_PATH  = "checkpoint.pt"
BEST_CONFIG_PATH = "best_config.json"
RESULTS_PATH     = "results.jsonl"
FREQ_CACHE_PATH  = "freq_space_cache.json"


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="RL Frequency Optimizer")
    p.add_argument("--resume",   action="store_true",
                   help="Resume training from checkpoint.pt")
    p.add_argument("--eval",     action="store_true",
                   help="Evaluate best_config.json only (no training)")
    p.add_argument("--episodes", type=int, default=200,
                   help="Number of training episodes (default: 200)")
    p.add_argument("--steps",    type=int, default=20,
                   help="Max steps per episode (default: 20)")
    p.add_argument("--debug",    action="store_true",
                   help="Show raw benchmark output for every run (helps diagnose parse errors)")
    p.add_argument("--log-every", type=int, default=1,
                   help="Print episode summary every N episodes (default: 1)")
    return p.parse_args()


# ── Evaluation ─────────────────────────────────────────────────────────────────

def evaluate_best_config(env: AndroidFreqEnv, n_runs: int = 5):
    """Load best_config.json, apply it, and run the benchmark n_runs times."""
    if not os.path.exists(BEST_CONFIG_PATH):
        logger.error(f"No best config found at '{BEST_CONFIG_PATH}'. Run training first.")
        return

    with open(BEST_CONFIG_PATH) as f:
        best = json.load(f)

    sep = "=" * 65
    logger.info(f"\n{sep}")
    logger.info("  BEST CONFIGURATION")
    logger.info(sep)
    logger.info(f"  CPU frequency  : {best['cpu_freq']:>12,} kHz")
    logger.info(f"  DDR boost      : {best['ddr_freq']:>12,} kHz")
    logger.info(f"  DDRQOS boost   : {best['ddrqos_freq']:>12}")
    logger.info(f"  LLCC boost     : {best['llcc_freq']:>12,} kHz")
    logger.info(f"  Target CPU     : CPU{best['target_cpu']}  "
                f"(taskset {best['taskset_mask']})")
    logger.info(f"  Best latency   : {best.get('latency_ns', 'N/A'):>12,} ns")
    logger.info(sep)

    logger.info(f"\nRunning {n_runs} verification benchmarks on device...")
    latencies = []
    for i in range(n_runs):
        env._apply_config(best)
        lat = env._run_benchmark(best["taskset_mask"])
        latencies.append(lat)
        logger.info(f"  Run {i + 1}/{n_runs}: {lat:,} ns")

    logger.info(f"\n  Mean : {np.mean(latencies):>12,.0f} ns")
    logger.info(f"  Std  : {np.std(latencies):>12,.0f} ns")
    logger.info(f"  Min  : {np.min(latencies):>12,} ns")
    logger.info(f"  Max  : {np.max(latencies):>12,} ns")

    # Print the exact adb commands to reproduce the result
    from env import CPU_POLICY_NODES
    logger.info(f"\n{sep}")
    logger.info("  REPRODUCE WITH THESE ADB COMMANDS")
    logger.info(sep)
    # CPU: lock via scaling_min/max_freq on all policy nodes (walt governor)
    for pol in CPU_POLICY_NODES:
        logger.info(f"adb shell echo {best['cpu_freq']} > {pol}/scaling_max_freq")
        logger.info(f"adb shell echo {best['cpu_freq']} > {pol}/scaling_min_freq")
        logger.info(f"adb shell echo {best['cpu_freq']} > {pol}/scaling_max_freq")
        logger.info(f"adb shell echo {best['cpu_freq']} > {pol}/scaling_min_freq")
    # DDR / DDRQOS / LLCC: set floor via boost_freq (bwmon min/max are read-only)
    logger.info(f"adb shell echo {best['ddr_freq']} > /sys/devices/system/cpu/bus_dcvs/DDR/boost_freq")
    logger.info(f"adb shell echo {best['ddrqos_freq']} > /sys/devices/system/cpu/bus_dcvs/DDRQOS/boost_freq")
    logger.info(f"adb shell echo {best['llcc_freq']} > /sys/devices/system/cpu/bus_dcvs/LLCC/boost_freq")
    # Run benchmark
    logger.info(
        f"adb shell taskset {best['taskset_mask']} "
        f"/data/local/tmp/FullRandLat {BENCHMARK_ARGS}"
    )
    logger.info(sep)


# ── Training ───────────────────────────────────────────────────────────────────

def train(args):
    # 1. Discover frequency space from device
    logger.info("Connecting to device and discovering frequency space...")
    fs = FrequencySpace()
    logger.info(str(fs))
    logger.info(f"Total action space : {fs.total_combinations:,} combinations")

    # 2. Save freq space cache so predict.py can run offline later
    freq_cache = {
        "cpu_freqs":          fs.cpu_freqs,
        "cpu_freqs_per_core": {str(k): v for k, v in fs.cpu_freqs_per_core.items()},
        "ddr_freqs":          fs.ddr_freqs,
        "ddrqos_freqs":       fs.ddrqos_freqs,
        "llcc_freqs":         fs.llcc_freqs,
        "num_cpus":           fs.num_cpus,
        "cpu_masks":          fs.cpu_masks,
    }
    with open(FREQ_CACHE_PATH, "w") as f:
        json.dump(freq_cache, f, indent=2)
    logger.info(f"Frequency space cached to {FREQ_CACHE_PATH}")

    # 3. Build environment
    env = AndroidFreqEnv(fs)

    # 4. Build agent
    #    n_actions can be very large (e.g. 24 × 16 × 2 × 8 × 8 = 49,152).
    #    Double DQN handles this well with a shared embedding.
    agent = DoubleDQNAgent(
        state_dim       = env.state_dim,
        n_actions       = env.n_actions,
        lr              = 1e-3,
        gamma           = 0.99,
        epsilon_start   = 1.0,
        epsilon_end     = 0.05,
        epsilon_decay   = 0.997,
        batch_size      = 64,
        target_update   = 50,
        buffer_capacity = 50_000,
        device          = "cpu",
    )

    if args.resume and os.path.exists(CHECKPOINT_PATH):
        agent.load(CHECKPOINT_PATH)
        logger.info(f"Resumed from {CHECKPOINT_PATH}")

    # Enable DEBUG logging to see raw benchmark output when --debug is set
    if args.debug:
        logging.getLogger("env").setLevel(logging.DEBUG)
        logger.info("Debug mode ON: raw benchmark output will be printed.")

    # 4. Training loop
    results_fh  = open(RESULTS_PATH, "a")
    global_step = 0

    logger.info(
        f"\nStarting training: {args.episodes} episodes × "
        f"up to {args.steps} steps each\n"
    )

    for episode in range(1, args.episodes + 1):
        state       = env.reset()
        ep_reward   = 0.0
        ep_losses   = []
        ep_best_lat = PENALTY_LATENCY_NS

        for _ in range(args.steps):
            action = agent.select_action(state)
            next_state, reward, done, info = env.step(action)

            agent.store(state, action, reward, next_state, done)
            loss = agent.learn()
            if loss is not None:
                ep_losses.append(loss)

            ep_reward += reward
            global_step += 1

            if info["latency_ns"] < ep_best_lat:
                ep_best_lat = info["latency_ns"]

            state = next_state
            if done:
                break

        # ── Episode summary ────────────────────────────────────────────────
        mean_loss = float(np.mean(ep_losses)) if ep_losses else 0.0

        record = {
            "episode":         episode,
            "total_reward":    round(ep_reward, 4),
            "best_latency_ns": ep_best_lat,
            "mean_loss":       round(mean_loss, 6),
            "epsilon":         round(agent.epsilon, 4),
            "global_step":     global_step,
        }
        results_fh.write(json.dumps(record) + "\n")
        results_fh.flush()

        if episode % args.log_every == 0 or episode == 1:
            logger.info(
                "Ep %4d/%d | reward=%9.2f | ep_best_lat=%10d ns | "
                "global_best=%10d ns | loss=%.5f | eps=%.3f",
                episode, args.episodes, ep_reward,
                ep_best_lat, int(env._best_latency),
                mean_loss, agent.epsilon,
            )

        # Save checkpoint every 50 episodes
        if episode % 50 == 0:
            agent.save(CHECKPOINT_PATH)

        # Persist best config whenever it improves
        if env._best_config is not None:
            with open(BEST_CONFIG_PATH, "w") as f:
                json.dump(env._best_config, f, indent=2)

    results_fh.close()
    agent.save(CHECKPOINT_PATH)

    if env._best_config is not None:
        with open(BEST_CONFIG_PATH, "w") as f:
            json.dump(env._best_config, f, indent=2)

    logger.info(f"\n{'=' * 65}")
    logger.info("TRAINING COMPLETE")
    logger.info(f"{'=' * 65}")
    logger.info(f"  Total steps      : {global_step:,}")
    logger.info(f"  Global best lat  : {env._best_latency:,} ns")
    logger.info(f"  Best config      : {env._best_config}")
    logger.info(f"  Results log      : {RESULTS_PATH}")
    logger.info(f"  Best config file : {BEST_CONFIG_PATH}")

    # Run verification benchmarks with the best config
    evaluate_best_config(env)

    return env


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()

    if args.eval:
        fs  = FrequencySpace()
        env = AndroidFreqEnv(fs)
        evaluate_best_config(env)
    else:
        train(args)