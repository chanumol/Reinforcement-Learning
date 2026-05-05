"""
predict.py
----------
Use the trained Q-network (checkpoint.pt) to predict the best frequency
configuration without running any benchmarks on the device.

The Q-network scores every action in the 80,784-combination space and
returns the top-N configurations ranked by predicted Q-value (higher = better).

Usage
-----
  # Show top 10 predicted configurations:
  python predict.py

  # Show top 20 and run the best one on the device to verify:
  python predict.py --top 20 --verify

  # Predict for a specific buffer size (runs benchmark to verify):
  python predict.py --buffer-kb 65536 --verify

  # Predict without a connected device (offline, uses cached freq space):
  python predict.py --offline
"""

import argparse
import json
import logging
import os
import sys
import numpy as np
import torch

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("predict")

CHECKPOINT_PATH  = "checkpoint.pt"
BEST_CONFIG_PATH = "best_config.json"
FREQ_CACHE_PATH  = "freq_space_cache.json"

PENALTY_LATENCY_NS = 10_000_000


def parse_args():
    p = argparse.ArgumentParser(description="RL Frequency Predictor")
    p.add_argument("--top",       type=int,   default=10,
                   help="Number of top configurations to show (default: 10)")
    p.add_argument("--verify",    action="store_true",
                   help="Run the top-1 prediction on the device to measure actual latency")
    p.add_argument("--buffer-kb", type=int,   default=40960,
                   help="Buffer size in KB for verification benchmark (default: 40960 = 40 MB)")
    p.add_argument("--offline",   action="store_true",
                   help="Don't connect to device; use cached freq_space_cache.json")
    return p.parse_args()


def load_freq_space(offline: bool):
    """Load FrequencySpace from device or from cache."""
    if offline:
        if not os.path.exists(FREQ_CACHE_PATH):
            logger.error(
                f"No cache found at '{FREQ_CACHE_PATH}'. "
                f"Run once without --offline to create it."
            )
            sys.exit(1)
        with open(FREQ_CACHE_PATH) as f:
            cache = json.load(f)
        logger.info(f"Loaded frequency space from cache: {FREQ_CACHE_PATH}")
        return cache

    from freq_space import FrequencySpace
    fs = FrequencySpace()

    # Save cache for offline use later
    cache = {
        "cpu_freqs":          fs.cpu_freqs,
        "cpu_freqs_per_core": {str(k): v for k, v in fs.cpu_freqs_per_core.items()},
        "ddr_freqs":          fs.ddr_freqs,
        "ddrqos_freqs":       fs.ddrqos_freqs,
        "llcc_freqs":         fs.llcc_freqs,
        "num_cpus":           fs.num_cpus,
        "cpu_masks":          fs.cpu_masks,
    }
    with open(FREQ_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
    logger.info(f"Frequency space cached to {FREQ_CACHE_PATH}")
    return fs


class CachedFreqSpace:
    """Minimal FrequencySpace built from a JSON cache (no adb needed)."""
    def __init__(self, cache: dict):
        self.cpu_freqs          = cache["cpu_freqs"]
        self.cpu_freqs_per_core = {int(k): v for k, v in cache["cpu_freqs_per_core"].items()}
        self.ddr_freqs          = cache["ddr_freqs"]
        self.ddrqos_freqs       = cache["ddrqos_freqs"]
        self.llcc_freqs         = cache["llcc_freqs"]
        self.num_cpus           = cache["num_cpus"]
        self.cpu_masks          = cache["cpu_masks"]

    @property
    def total_combinations(self):
        return (
            len(self.cpu_freqs)
            * len(self.ddr_freqs)
            * len(self.ddrqos_freqs)
            * len(self.llcc_freqs)
            * self.num_cpus
        )

    def valid_freq_for_cpu(self, cpu_freq, cpu_id):
        valid = self.cpu_freqs_per_core.get(cpu_id, self.cpu_freqs)
        candidates = [f for f in valid if f <= cpu_freq]
        return max(candidates) if candidates else min(valid)

    def decode_action(self, action_idx):
        n_cpu    = self.num_cpus
        n_llcc   = len(self.llcc_freqs)
        n_ddrqos = len(self.ddrqos_freqs)
        n_ddr    = len(self.ddr_freqs)

        idx = action_idx
        target_cpu   = idx % n_cpu;    idx //= n_cpu
        llcc_idx     = idx % n_llcc;   idx //= n_llcc
        ddrqos_idx   = idx % n_ddrqos; idx //= n_ddrqos
        ddr_idx      = idx % n_ddr;    idx //= n_ddr
        cpu_freq_idx = idx % len(self.cpu_freqs)

        requested = self.cpu_freqs[cpu_freq_idx]
        actual    = self.valid_freq_for_cpu(requested, target_cpu)

        return {
            "cpu_freq":      actual,
            "ddr_freq":      self.ddr_freqs[ddr_idx],
            "ddrqos_freq":   self.ddrqos_freqs[ddrqos_idx],
            "llcc_freq":     self.llcc_freqs[llcc_idx],
            "target_cpu":    target_cpu,
            "taskset_mask":  str(self.cpu_masks[target_cpu]),
            "_cpu_freq_idx": cpu_freq_idx,
            "_ddr_idx":      ddr_idx,
            "_ddrqos_idx":   ddrqos_idx,
            "_llcc_idx":     llcc_idx,
        }


def load_qnet(checkpoint_path: str, state_dim: int = None, n_actions: int = None):
    """
    Load the online Q-network from checkpoint.
    If state_dim / n_actions are not provided, they are read from the
    checkpoint itself (saved since the latest training run).
    """
    from agent import DoubleDQNAgent
    # Peek at checkpoint metadata first
    meta = DoubleDQNAgent.inspect(checkpoint_path)
    if state_dim is None:
        state_dim = meta.get("state_dim", 7)
    if n_actions is None:
        n_actions = meta.get("n_actions")
        if n_actions is None:
            raise RuntimeError(
                f"Checkpoint '{checkpoint_path}' does not contain n_actions. "
                f"Retrain to generate a new checkpoint, or pass --n-actions manually."
            )
    logger.info(
        f"Checkpoint metadata: state_dim={state_dim}, "
        f"n_actions={n_actions:,}, step={meta.get('step')}, "
        f"epsilon={meta.get('epsilon')}"
    )
    agent = DoubleDQNAgent(
        state_dim=state_dim, n_actions=n_actions,
        lr=1e-3, gamma=0.99,
        epsilon_start=0.0, epsilon_end=0.0, epsilon_decay=1.0,
        batch_size=64, target_update=50,
        buffer_capacity=1, device="cpu",
    )
    agent.load(checkpoint_path)
    agent.epsilon = 0.0   # pure greedy
    return agent


def make_query_state(fs, last_latency_norm: float = 0.5) -> np.ndarray:
    """
    Build a query state for the Q-network.
    We use the midpoint of each dimension as a neutral starting state.
    last_latency_norm: 0.0 = best possible, 1.0 = worst (penalty).
    """
    n_cpu_f  = max(len(fs.cpu_freqs) - 1, 1)
    n_ddr    = max(len(fs.ddr_freqs) - 1, 1)
    n_ddrqos = max(len(fs.ddrqos_freqs) - 1, 1)
    n_llcc   = max(len(fs.llcc_freqs) - 1, 1)
    n_cpus   = max(fs.num_cpus - 1, 1)

    return np.array([
        0.5,                  # cpu_freq_idx midpoint
        0.5,                  # ddr_idx midpoint
        0.5,                  # ddrqos_idx midpoint
        0.5,                  # llcc_idx midpoint
        0.5,                  # target_cpu midpoint
        last_latency_norm,    # last latency (unknown → use midpoint)
        0.0,                  # step 0 (fresh query)
    ], dtype=np.float32)


def rank_all_actions(agent, fs, state: np.ndarray, top_n: int):
    """
    Score all actions with the Q-network and return top_n configs.
    The Q-network outputs Q(s, a) for ALL actions in one forward pass,
    so we just pass the state once and read off all n_actions Q-values.
    """
    n_actions = fs.total_combinations
    state_t   = torch.FloatTensor(state).unsqueeze(0)  # [1, state_dim]

    with torch.no_grad():
        q_vals = agent.online_net(state_t)   # [1, n_actions]
    all_q = q_vals.squeeze(0).cpu().numpy()  # [n_actions]

    # Top-N by Q-value (descending)
    top_indices = np.argsort(all_q)[::-1][:top_n]

    results = []
    for rank, idx in enumerate(top_indices):
        cfg = fs.decode_action(int(idx))
        results.append({
            "rank":       rank + 1,
            "action_idx": int(idx),
            "q_value":    float(all_q[idx]),
            "cpu_freq":   cfg["cpu_freq"],
            "ddr_freq":   cfg["ddr_freq"],
            "ddrqos":     cfg["ddrqos_freq"],
            "llcc_freq":  cfg["llcc_freq"],
            "target_cpu": cfg["target_cpu"],
            "taskset":    cfg["taskset_mask"],
        })
    return results


def print_table(results: list):
    sep = "-" * 90
    logger.info(sep)
    logger.info(
        f"{'Rank':>4}  {'CPU freq (kHz)':>14}  {'DDR (kHz)':>10}  "
        f"{'QoS':>3}  {'LLCC (kHz)':>10}  {'CPU':>3}  {'Q-value':>10}"
    )
    logger.info(sep)
    for r in results:
        logger.info(
            f"{r['rank']:>4}  {r['cpu_freq']:>14,}  {r['ddr_freq']:>10,}  "
            f"{r['ddrqos']:>3}  {r['llcc_freq']:>10,}  "
            f"CPU{r['target_cpu']:>1}  {r['q_value']:>10.4f}"
        )
    logger.info(sep)


def verify_on_device(cfg: dict, buffer_kb: int):
    """Apply the predicted config and run the benchmark to measure actual latency."""
    from freq_space import FrequencySpace
    from env import AndroidFreqEnv

    logger.info(f"\nVerifying top-1 prediction on device (buffer={buffer_kb} KB)...")
    fs  = FrequencySpace()
    env = AndroidFreqEnv(fs)

    # Override benchmark buffer size for this verification
    import env as env_module
    original_args = env_module.BENCHMARK_ARGS
    env_module.BENCHMARK_ARGS = (
        f"memlat -min-buffer-size-kb {buffer_kb} -max-buffer-size-kb {buffer_kb}"
    )

    env._apply_config(cfg)
    latencies = []
    for i in range(5):
        lat = env._run_benchmark(cfg["taskset_mask"])
        latencies.append(lat)
        logger.info(f"  Run {i+1}/5: {lat:,} ns")

    env_module.BENCHMARK_ARGS = original_args

    logger.info(f"\n  Mean : {np.mean(latencies):>10,.0f} ns")
    logger.info(f"  Std  : {np.std(latencies):>10,.0f} ns")
    logger.info(f"  Min  : {np.min(latencies):>10,} ns")
    logger.info(f"  Max  : {np.max(latencies):>10,} ns")


def main():
    args = parse_args()

    if not os.path.exists(CHECKPOINT_PATH):
        logger.error(f"No checkpoint found at '{CHECKPOINT_PATH}'. Run training first.")
        sys.exit(1)

    # Load frequency space
    raw = load_freq_space(args.offline)
    if isinstance(raw, dict):
        fs = CachedFreqSpace(raw)
    else:
        fs = raw

    n_actions = fs.total_combinations
    state_dim = 7

    logger.info(f"Action space: {n_actions:,} combinations")
    logger.info(f"Loading Q-network from {CHECKPOINT_PATH}...")
    # n_actions read from checkpoint metadata — no device needed
    agent = load_qnet(CHECKPOINT_PATH, state_dim=state_dim, n_actions=n_actions)

    # Build query state
    state = make_query_state(fs, last_latency_norm=0.5)

    logger.info(f"\nRanking all {n_actions:,} actions by Q-value...")
    results = rank_all_actions(agent, fs, state, top_n=args.top)

    logger.info(f"\nTop {args.top} predicted configurations:")
    print_table(results)

    # Show best_config.json for comparison
    if os.path.exists(BEST_CONFIG_PATH):
        with open(BEST_CONFIG_PATH) as f:
            best = json.load(f)
        logger.info(
            f"\nBest config from training (actual measured):\n"
            f"  CPU {best['cpu_freq']:,} kHz | DDR {best['ddr_freq']:,} kHz | "
            f"DDRQOS {best['ddrqos_freq']} | LLCC {best['llcc_freq']:,} kHz | "
            f"CPU{best['target_cpu']} | latency={best.get('latency_ns','?')} ns"
        )

    # Optionally verify top-1 on device
    if args.verify:
        top1 = results[0]
        cfg = {
            "cpu_freq":    top1["cpu_freq"],
            "ddr_freq":    top1["ddr_freq"],
            "ddrqos_freq": top1["ddrqos"],
            "llcc_freq":   top1["llcc_freq"],
            "target_cpu":  top1["target_cpu"],
            "taskset_mask": top1["taskset"],
        }
        verify_on_device(cfg, args.buffer_kb)


if __name__ == "__main__":
    main()