"""A stateful agent: game frames in, env actions out, with the transformer memory kept between calls."""
import numpy as np
import torch as th

from . import games
from .data import resize_frame
from .vpt import ActionCodec, build_policy, default_device, load_weights

import lib.tree_util as tree_util  # noqa: E402


class ArenaAgent:
    def __init__(self, arch="2x", weights=None, mode="survival", ruleset=None, team_size=None, device=None,
                 stochastic=True, net_overrides=None, policy=None):
        self.device = th.device(device or default_device())
        self.policy = policy if policy is not None else build_policy(arch, net_overrides=net_overrides)
        if weights:
            load_weights(self.policy, weights)
        self.policy.to(self.device).eval()
        self.codec = ActionCodec()
        self.stochastic = stochastic
        self.set_mode(mode, ruleset, team_size)
        self.reset()

    def set_mode(self, mode, ruleset=None, team_size=None):
        self.mode = games.get(mode)
        self.cond = th.tensor([games.cond_ids(self.mode, ruleset, team_size)], device=self.device)  # (1, 3)

    def reset(self):
        st = self.policy.initial_state(1)
        self.state = tree_util.tree_map(lambda x: x.to(self.device) if isinstance(x, th.Tensor) else x, st)
        self.first = True

    @th.no_grad()
    def act(self, frame_rgb):
        """frame_rgb: HxWx3 uint8 game frame (any size). Returns (env action dict, info)."""
        if frame_rgb.shape[:2] != (128, 128):
            frame_rgb = resize_frame(frame_rgb)
        obs = {"img": th.from_numpy(np.ascontiguousarray(frame_rgb))[None].to(self.device), "diff_goal": self.cond}
        first = th.tensor([self.first], device=self.device)
        tok, self.state, res = self.policy.act(obs, first, self.state, stochastic=self.stochastic)
        self.first = False
        action = self.codec.tokens_to_env({k: v.cpu().numpy() for k, v in tok.items()})[0]
        return action, {"log_prob": float(res["log_prob"][0]), "value": float(res["vpred"][0]),
                        "tokens": {k: int(v[0, 0]) for k, v in tok.items()}}
