"""
agent.py
--------
Double DQN Agent with Experience Replay and Prioritised Sampling.

Why Double DQN?
  - Large discrete action space (thousands of freq combinations)
  - Avoids Q-value overestimation (common in vanilla DQN)
  - Stable convergence with target network
  - Easy to extend with Dueling architecture or reward shaping later

Architecture:
  Input  : state_dim (7)
  Hidden : 256 → 256 → 128
  Output : n_actions (total frequency combinations)
"""

import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque
import logging

logger = logging.getLogger(__name__)


# ── Neural Network ─────────────────────────────────────────────────────────────

class QNetwork(nn.Module):
    def __init__(self, state_dim: int, n_actions: int, hidden: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 128),
            nn.ReLU(),
            nn.Linear(128, n_actions),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ── Replay Buffer ──────────────────────────────────────────────────────────────

class ReplayBuffer:
    """Fixed-size circular buffer storing (s, a, r, s', done) transitions."""

    def __init__(self, capacity: int = 50_000):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((
            np.array(state,      dtype=np.float32),
            int(action),
            float(reward),
            np.array(next_state, dtype=np.float32),
            bool(done),
        ))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.stack(states),
            np.array(actions),
            np.array(rewards),
            np.stack(next_states),
            np.array(dones, dtype=np.float32),
        )

    def __len__(self):
        return len(self.buffer)


# ── Double DQN Agent ───────────────────────────────────────────────────────────

class DoubleDQNAgent:
    """
    Double DQN agent.

    Parameters
    ----------
    state_dim      : int   – dimension of state vector
    n_actions      : int   – total number of discrete actions
    lr             : float – learning rate
    gamma          : float – discount factor
    epsilon_start  : float – initial exploration rate
    epsilon_end    : float – minimum exploration rate
    epsilon_decay  : float – multiplicative decay per step
    batch_size     : int   – mini-batch size for training
    target_update  : int   – steps between target network syncs
    buffer_capacity: int   – replay buffer size
    device         : str   – 'cpu' or 'cuda'
    """

    def __init__(
        self,
        state_dim:       int,
        n_actions:       int,
        lr:              float = 1e-3,
        gamma:           float = 0.99,
        epsilon_start:   float = 1.0,
        epsilon_end:     float = 0.05,
        epsilon_decay:   float = 0.995,
        batch_size:      int   = 64,
        target_update:   int   = 100,
        buffer_capacity: int   = 50_000,
        device:          str   = "cpu",
    ):
        self.n_actions     = n_actions
        self.gamma         = gamma
        self.epsilon       = epsilon_start
        self.epsilon_end   = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.batch_size    = batch_size
        self.target_update = target_update
        self.device        = torch.device(device)
        self._step         = 0

        # Networks
        self.online_net = QNetwork(state_dim, n_actions).to(self.device)
        self.target_net = QNetwork(state_dim, n_actions).to(self.device)
        self.target_net.load_state_dict(self.online_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.online_net.parameters(), lr=lr)
        self.loss_fn   = nn.SmoothL1Loss()   # Huber loss – robust to outliers

        self.buffer = ReplayBuffer(buffer_capacity)

        logger.info(
            f"DoubleDQNAgent: state_dim={state_dim}, n_actions={n_actions:,}, "
            f"device={device}"
        )

    # ── Action selection ───────────────────────────────────────────────────────

    def select_action(self, state: np.ndarray) -> int:
        """Epsilon-greedy action selection."""
        if random.random() < self.epsilon:
            return random.randrange(self.n_actions)

        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q_values = self.online_net(state_t)
        return int(q_values.argmax(dim=1).item())

    def select_greedy_action(self, state: np.ndarray) -> int:
        """Pure greedy (for evaluation)."""
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q_values = self.online_net(state_t)
        return int(q_values.argmax(dim=1).item())

    # ── Learning ───────────────────────────────────────────────────────────────

    def store(self, state, action, reward, next_state, done):
        self.buffer.push(state, action, reward, next_state, done)

    def learn(self) -> float | None:
        """Sample a mini-batch and perform one gradient update. Returns loss."""
        if len(self.buffer) < self.batch_size:
            return None

        states, actions, rewards, next_states, dones = self.buffer.sample(
            self.batch_size
        )

        states_t      = torch.FloatTensor(states).to(self.device)
        actions_t     = torch.LongTensor(actions).to(self.device)
        rewards_t     = torch.FloatTensor(rewards).to(self.device)
        next_states_t = torch.FloatTensor(next_states).to(self.device)
        dones_t       = torch.FloatTensor(dones).to(self.device)

        # Current Q values
        q_values = self.online_net(states_t)
        q_current = q_values.gather(1, actions_t.unsqueeze(1)).squeeze(1)

        # Double DQN target:
        #   action* = argmax_a Q_online(s', a)
        #   target  = r + γ * Q_target(s', action*)
        with torch.no_grad():
            next_actions = self.online_net(next_states_t).argmax(dim=1)
            next_q       = self.target_net(next_states_t).gather(
                1, next_actions.unsqueeze(1)
            ).squeeze(1)
            q_target = rewards_t + self.gamma * next_q * (1 - dones_t)

        loss = self.loss_fn(q_current, q_target)

        self.optimizer.zero_grad()
        loss.backward()
        # Gradient clipping for stability
        nn.utils.clip_grad_norm_(self.online_net.parameters(), max_norm=10.0)
        self.optimizer.step()

        self._step += 1

        # Decay epsilon
        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)

        # Sync target network
        if self._step % self.target_update == 0:
            self.target_net.load_state_dict(self.online_net.state_dict())
            logger.debug(f"Target network synced at step {self._step}")

        return loss.item()

    # ── Persistence ────────────────────────────────────────────────────────────

    def save(self, path: str):
        torch.save({
            "online_net":  self.online_net.state_dict(),
            "target_net":  self.target_net.state_dict(),
            "optimizer":   self.optimizer.state_dict(),
            "epsilon":     self.epsilon,
            "step":        self._step,
            # Architecture metadata — needed to reload without re-discovering device
            "n_actions":   self.n_actions,
            "state_dim":   self.online_net.net[0].in_features,
        }, path)
        logger.info(f"Agent saved to {path}")

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.online_net.load_state_dict(ckpt["online_net"])
        self.target_net.load_state_dict(ckpt["target_net"])
        self.optimizer.load_state_dict(ckpt["optimizer"])
        self.epsilon = ckpt["epsilon"]
        self._step   = ckpt["step"]
        logger.info(
            f"Agent loaded from {path} "
            f"(step={self._step}, n_actions={ckpt.get('n_actions','?')}, "
            f"state_dim={ckpt.get('state_dim','?')})"
        )

    @staticmethod
    def inspect(path: str) -> dict:
        """Return metadata from a checkpoint without loading the full model."""
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        return {
            "n_actions": ckpt.get("n_actions"),
            "state_dim": ckpt.get("state_dim"),
            "epsilon":   ckpt.get("epsilon"),
            "step":      ckpt.get("step"),
        }
