"""Toy environments with the same interface as the live one, for testing the RL code quickly.

AttackOnRed: each frame is red or blue. Attacking on red earns +1, attacking
on blue costs 0.5. An agent that learns the rule averages about +0.5 per step
(half the frames are red); attacking at random averages about 0.125.
"""
import numpy as np


class AttackOnRed:
    def __init__(self, episode_len=32, seed=0, size=(64, 64)):
        self.len, self.size = episode_len, size
        self.rng = np.random.default_rng(seed)
        self.t = 0
        self.red = False

    def _frame(self):
        self.red = bool(self.rng.random() < 0.5)
        f = np.zeros((*self.size, 3), np.uint8)
        f[..., 0 if self.red else 2] = 220
        f += self.rng.integers(0, 30, f.shape, dtype=np.uint8)
        return f

    def reset(self):
        self.t = 0
        return self._frame()

    def step(self, action):
        attack = bool(action.get("attack", 0))
        r = (1.0 if self.red else -0.5) if attack else 0.0
        self.t += 1
        done = self.t >= self.len
        return self._frame(), r, done, {"won": False}
