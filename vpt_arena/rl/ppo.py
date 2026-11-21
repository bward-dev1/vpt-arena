"""PPO fine-tuning of the conditioned VPT policy, with a KL pull toward the starting (BC) policy.

This follows the recipe of VPT's own RL stage: recurrent rollouts, GAE,
clipped policy loss, value loss in the value head's normalised space, and a
KL penalty to the frozen pretrained policy so RL doesn't wipe out what BC
taught. The first --vf-warmup iterations train only the value head, because
the pretrained value head knows nothing about arena rewards.

Envs implement reset() -> frame and step(env_action) -> (frame, reward, done, info);
see envs.py (toy envs for tests) and live_env.py (real Minecraft on your server).
"""
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch as th

from .. import games
from ..data import resize_frame
from ..train_bc import detach_state, to_device_state
from ..vpt import ActionCodec

import lib.tree_util as tree_util  # noqa: E402


def masked_logprob(policy, pd, buttons, camera, cam_off):
    """Log-prob of a joint action; the camera head only counts when the camera meta-action is on."""
    lp_b = policy.pi_head["buttons"].logprob(buttons, pd["buttons"])
    lp_c = policy.pi_head["camera"].logprob(camera, pd["camera"])
    return lp_b + lp_c * (~cam_off[buttons[..., 0]]).float()


def masked_entropy(policy, pd, buttons, cam_off):
    e_b = policy.pi_head["buttons"].entropy(pd["buttons"])
    e_c = policy.pi_head["camera"].entropy(pd["camera"])
    return e_b + e_c * (~cam_off[buttons[..., 0]]).float()


class PPO:
    def __init__(self, policy, envs, modes, prior=None, device="cpu", T=64, lr=2e-5, clip=0.2, vf_coef=0.5,
                 ent_coef=0.0, kl_coef=0.2, kl_decay=0.9995, gamma=0.999, lam=0.95, epochs=2, minibatches=1,
                 max_grad=1.0, vf_warmup=0, run=None):
        self.policy, self.prior, self.envs = policy, prior, envs
        self.device = th.device(device)
        self.N, self.T = len(envs), T
        self.cond = th.tensor([games.cond_ids(m) for m in modes], device=self.device)  # (N, 3)
        self.modes = [games.get(m).key for m in modes]
        self.clip, self.vf_coef, self.ent_coef = clip, vf_coef, ent_coef
        self.kl_coef, self.kl_decay = kl_coef, kl_decay
        self.gamma, self.lam, self.epochs, self.minibatches, self.max_grad = gamma, lam, epochs, minibatches, max_grad
        self.vf_warmup = vf_warmup
        self.opt = th.optim.Adam(policy.parameters(), lr=lr)
        self.codec = ActionCodec()
        self.cam_off = th.from_numpy(self.codec.mapper.BUTTON_IDX_TO_CAMERA_META_OFF).to(self.device)
        self.state = to_device_state(policy.initial_state(self.N), self.device)
        self.prior_state = to_device_state(prior.initial_state(self.N), self.device) if prior else None
        self.obs = np.stack([resize_frame(e.reset()) for e in envs])
        self.first = np.ones(self.N, bool)
        self.ep_ret = np.zeros(self.N)
        self.ep_len = np.zeros(self.N, int)
        self.finished = []  # (mode, return, length, won), last 1000 episodes
        self.iter, self.env_steps = 0, 0
        self.run = Path(run) if run else None
        if self.run:
            self.run.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ rollout
    @th.no_grad()
    def collect(self):
        p, N, T, dev = self.policy, self.N, self.T, self.device
        p.eval()
        start_state = tree_util.tree_map(lambda x: x.clone() if isinstance(x, th.Tensor) else x, self.state)
        start_prior = (tree_util.tree_map(lambda x: x.clone() if isinstance(x, th.Tensor) else x, self.prior_state)
                       if self.prior else None)
        buf = defaultdict(list)
        for _ in range(T):
            img = th.from_numpy(self.obs).to(dev)
            first = th.from_numpy(self.first).to(dev)
            obs = {"img": img, "diff_goal": self.cond}
            tok, self.state, res = p.act(obs, first, self.state, stochastic=True, return_pd=True)
            pd = {k: v.unsqueeze(1) for k, v in res["pd"].items()}
            lp = masked_logprob(p, pd, tok["buttons"][:, None], tok["camera"][:, None], self.cam_off)[:, 0]
            if self.prior is not None:
                _, self.prior_state, _ = self.prior.act({"img": img}, first, self.prior_state, stochastic=True)
            actions = self.codec.tokens_to_env({k: v.cpu().numpy() for k, v in tok.items()})
            rew, done = np.zeros(N, np.float32), np.zeros(N, bool)
            nxt = np.empty_like(self.obs)
            for i, (env, a) in enumerate(zip(self.envs, actions)):
                frame, r, d, info = env.step(a)
                rew[i], done[i] = r, d
                self.ep_ret[i] += r
                self.ep_len[i] += 1
                if d:
                    self.finished.append((self.modes[i], float(self.ep_ret[i]), int(self.ep_len[i]),
                                          bool(info.get("won", False))))
                    self.ep_ret[i], self.ep_len[i] = 0, 0
                    frame = env.reset()
                nxt[i] = resize_frame(frame)
            for k, v in (("img", self.obs), ("first", self.first), ("buttons", tok["buttons"].cpu().numpy()),
                         ("camera", tok["camera"].cpu().numpy()), ("logp", lp.cpu().numpy()),
                         ("value", res["vpred"].reshape(-1).cpu().numpy()), ("reward", rew), ("done", done)):
                buf[k].append(v)
            self.obs, self.first = nxt, done.copy()
            self.env_steps += N
        # bootstrap value for the step after the rollout
        _, _, res = p.act({"img": th.from_numpy(self.obs).to(dev), "diff_goal": self.cond},
                          th.from_numpy(self.first).to(dev), tree_util.tree_map(lambda x: x, self.state), stochastic=True)
        last_v = res["vpred"].reshape(-1).cpu().numpy()
        roll = {k: np.stack(v, axis=1) for k, v in buf.items()}  # (N, T, ...)
        adv = np.zeros((N, T), np.float32)
        gae = np.zeros(N, np.float32)
        for t in reversed(range(T)):
            nv = last_v if t == T - 1 else roll["value"][:, t + 1]
            nonterm = 1.0 - roll["done"][:, t].astype(np.float32)
            delta = roll["reward"][:, t] + self.gamma * nv * nonterm - roll["value"][:, t]
            gae = delta + self.gamma * self.lam * nonterm * gae
            adv[:, t] = gae
        roll["adv"], roll["ret"] = adv, adv + roll["value"]
        roll["start_state"], roll["start_prior"] = start_state, start_prior
        return roll

    # ------------------------------------------------------------------ update
    def update(self, roll):
        p, dev = self.policy, self.device
        p.train()
        t = lambda k, dt=None: th.as_tensor(roll[k], device=dev, dtype=dt)  # noqa: E731
        img, first = t("img"), t("first")
        buttons, camera = t("buttons", th.long), t("camera", th.long)
        old_lp, adv, ret = t("logp", th.float32), t("adv", th.float32), t("ret", th.float32)
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        warm = self.iter < self.vf_warmup
        pd_prior = None
        if self.prior is not None and not warm:
            with th.no_grad():
                (pd_prior, _, _), _ = self.prior(obs={"img": img}, first=first, state_in=roll["start_prior"])
        stats = defaultdict(list)
        idx = np.arange(self.N)
        for _ in range(self.epochs):
            np.random.shuffle(idx)
            for mb in np.array_split(idx, self.minibatches):
                mbt = th.as_tensor(mb, device=dev)
                st = tree_util.tree_map(lambda x: x[mbt] if isinstance(x, th.Tensor) and x.dim() > 0 else x,
                                        roll["start_state"])
                (pd, vpred, _), _ = p(obs={"img": img[mbt], "diff_goal": self.cond[mbt, None].expand(-1, self.T, -1)},
                                      first=first[mbt], state_in=st)
                v_loss = p.value_head.loss(vpred, ret[mbt][..., None])
                if warm:
                    loss = self.vf_coef * v_loss
                    pi_loss = ent = kl = th.zeros((), device=dev)
                    ratio = th.ones(1)
                else:
                    lp = masked_logprob(p, pd, buttons[mbt], camera[mbt], self.cam_off)
                    ratio = th.exp(lp - old_lp[mbt])
                    a = adv[mbt]
                    pi_loss = -th.min(ratio * a, th.clamp(ratio, 1 - self.clip, 1 + self.clip) * a).mean()
                    ent = masked_entropy(p, pd, buttons[mbt], self.cam_off).mean()
                    kl = (p.pi_head.kl_divergence({k: v[mbt] for k, v in pd_prior.items()}, pd).mean()
                          if pd_prior is not None else th.zeros((), device=dev))
                    loss = pi_loss + self.vf_coef * v_loss - self.ent_coef * ent + self.kl_coef * kl
                self.opt.zero_grad(set_to_none=True)
                loss.backward()
                th.nn.utils.clip_grad_norm_(p.parameters(), self.max_grad)
                self.opt.step()
                stats["pi_loss"].append(float(pi_loss))
                stats["v_loss"].append(float(v_loss))
                stats["entropy"].append(float(ent))
                stats["kl"].append(float(kl))
                stats["ratio_dev"].append(float((ratio.detach() - 1).abs().mean()))
        self.kl_coef *= self.kl_decay
        self.state = detach_state(self.state)
        return {k: float(np.mean(v)) for k, v in stats.items()}

    def train(self, iters, log_every=1, save_every=50):
        t0 = time.time()
        log = open(self.run / "rl_log.jsonl", "a") if self.run else None
        recs = []
        try:
            for _ in range(iters):
                s0, n0 = self.env_steps, len(self.finished)
                ti = time.time()
                roll = self.collect()
                st = self.update(roll)
                self.iter += 1
                fin = self.finished[n0:] or self.finished[-20:]  # episodes that ended this iteration
                self.finished = self.finished[-1000:]
                by_mode = defaultdict(list)
                for m, r, _, _ in fin:
                    by_mode[m].append(r)
                rec = dict(iter=self.iter, env_steps=self.env_steps,
                           ep_return_mean=float(np.mean([f[1] for f in fin])) if fin else None,
                           ep_len_mean=float(np.mean([f[2] for f in fin])) if fin else None,
                           win_rate=float(np.mean([f[3] for f in fin])) if fin else None,
                           fps=round((self.env_steps - s0) / max(1e-6, time.time() - ti), 1),
                           kl_coef=self.kl_coef, sec=round(time.time() - t0, 1),
                           by_mode={m: float(np.mean(v)) for m, v in by_mode.items()}, **st)
                recs.append(rec)
                if log:
                    log.write(json.dumps(rec) + "\n")
                    log.flush()
                if self.iter % log_every == 0:
                    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in rec.items()
                                      if k != "by_mode"}), flush=True)
                if self.run and self.iter % save_every == 0:
                    self.save()
        finally:
            if log:
                log.close()
        if self.run:
            self.save()
        return recs

    def save(self):
        tmp = self.run / "latest.pt.tmp"
        th.save({"policy": self.policy.state_dict(), "optim": self.opt.state_dict(), "iter": self.iter,
                 "env_steps": self.env_steps, "kl_coef": self.kl_coef}, tmp)
        tmp.replace(self.run / "latest.pt")
        th.save(self.policy.state_dict(), self.run / "policy.weights")

    def finished_episodes(self):
        return list(self.finished)
