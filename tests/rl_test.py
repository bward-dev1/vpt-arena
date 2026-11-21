"""RL checks with a tiny policy on the AttackOnRed toy env (CPU, a few minutes).

The tiny policy is first behaviour-cloned to press "forward" or "forward +
attack" at random, ignoring colour. That mirrors the real setup (RL starts
from a peaked VPT/BC policy, not a uniform one over 8641 button combos); RL
then has to learn *when* to attack.

1. Recomputing log-probs over the whole rollout sequence gives the same values
   as the step-by-step rollout (the PPO ratio starts at 1).
2. PPO learns the rule: return per step rises well above the random level.

    .venv/bin/python -m tests.rl_test
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch as th

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vpt_arena import games  # noqa: E402
from vpt_arena.rl.envs import AttackOnRed  # noqa: E402
from vpt_arena.rl.ppo import PPO, masked_logprob  # noqa: E402
from vpt_arena.seqfwd import segmented_forward  # noqa: E402
from vpt_arena.train_bc import bc_terms, seq_forward  # noqa: E402
from vpt_arena.vpt import ActionCodec, build_policy, noop_env_action  # noqa: E402

TINY = dict(hidsize=64, impala_width=1, attention_heads=4, n_recurrence_layers=1, attention_memory_size=32, timesteps=16)


def bc_prior(policy, steps=150):
    """BC on colour-blind demos: forward, or forward + attack, 50/50."""
    codec = ActionCodec()
    a0, a1 = noop_env_action(), noop_env_action()
    a0["forward"] = a1["forward"] = a1["attack"] = 1
    tok, _ = codec.env_to_tokens([a0, a1])
    cam_off = th.from_numpy(codec.mapper.BUTTON_IDX_TO_CAMERA_META_OFF)
    env = AttackOnRed(seed=99)
    opt = th.optim.Adam(policy.parameters(), lr=1e-3)
    for _ in range(steps):
        img = np.stack([np.stack([env._frame() for _ in range(16)]) for _ in range(4)])
        img = np.stack([[np.resize(f, (128, 128, 3)) for f in row] for row in img]).astype(np.uint8)
        pick = np.random.randint(0, 2, (4, 16))
        tb = dict(img=th.from_numpy(img), first=th.zeros((4, 16), dtype=th.bool),
                  cond=th.tensor(games.cond_ids("duels_sword")).expand(4, 16, 3),
                  buttons=th.from_numpy(tok["buttons"][pick]), camera=th.from_numpy(tok["camera"][pick]))
        pd, _ = seq_forward(policy, tb, policy.initial_state(4))
        lp, _ = bc_terms(policy, pd, tb, cam_off)
        opt.zero_grad()
        (-lp.mean()).backward()
        opt.step()
    print(f"BC prior nll {float(-lp.mean()):.3f} (ln 2 = 0.693 is perfect for a 50/50 demo)")


def main():
    th.manual_seed(0)
    np.random.seed(0)
    policy = build_policy("1x", net_overrides=TINY)
    bc_prior(policy)
    prior = build_policy("1x", conditioned=False, net_overrides=TINY)
    prior.load_state_dict({k: v for k, v in policy.state_dict().items() if "diff_obs_process" not in k}, strict=False)
    prior.eval().requires_grad_(False)
    envs = [AttackOnRed(seed=i, episode_len=11 if i % 2 else 32) for i in range(8)]  # resets mid-rollout
    run = Path(tempfile.mkdtemp(prefix="vpt-arena-rl-"))
    ppo = PPO(policy, envs, ["duels_sword"] * 8, prior=prior, T=16, lr=3e-4, ent_coef=0.003, kl_coef=0.01,
              epochs=3, minibatches=2, gamma=0.9, lam=0.9, vf_warmup=2, run=run)

    # 1. sequence recompute == rollout log-probs
    roll = ppo.collect()
    policy.eval()
    with th.no_grad():
        (pd, _), _ = segmented_forward(policy, {"img": th.as_tensor(roll["img"]),
                                                "diff_goal": ppo.cond[:, None].expand(-1, 16, -1)},
                                       th.as_tensor(roll["first"]), roll["start_state"])
        assert bool(th.as_tensor(roll["first"])[:, 1:].any()), "test needs a mid-rollout episode start"
        lp = masked_logprob(policy, pd, th.as_tensor(roll["buttons"]), th.as_tensor(roll["camera"]), ppo.cam_off)
    diff = float((lp - th.as_tensor(roll["logp"])).abs().max())
    print(f"max |logp(seq) - logp(rollout)| = {diff:.2e}")
    assert diff < 1e-3, "sequence recompute disagrees with rollout"
    ppo.update(roll)
    ppo.iter += 1

    # 2. learning
    def per_step(recs):
        r = [x["ep_return_mean"] / x["ep_len_mean"] for x in recs if x["ep_return_mean"] is not None]
        return float(np.mean(r)) if r else float("nan")

    recs = ppo.train(40, log_every=10)
    early, late = per_step(recs[:5]), per_step(recs[-5:])
    print(f"return per step: first iters {early:.3f}, last iters {late:.3f}")
    assert (run / "rl_log.jsonl").exists() and (run / "policy.weights").exists()
    assert late > early + 0.1 and late > 0.25, "PPO did not learn AttackOnRed"
    print("rl checks passed")


if __name__ == "__main__":
    main()
