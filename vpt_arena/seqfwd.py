"""Sequence forward that respects episode starts anywhere in a chunk.

VPT's masked attention only honours `first=True` on the first timestep of a
chunk (see MaskedAttention's docstring). When an episode or trajectory starts
mid-chunk, a plain sequence forward lets the new episode attend to the old
one. Step-by-step rollouts don't have that problem, so the PPO ratio and BC
targets would be computed on a different model than the one that acted.

This splits each batch row at its `first` flags and runs each piece as its
own chunk, carrying the memory from piece to piece. Since a piece that starts
with first=True masks all earlier memory, the result equals step-by-step
processing.
"""
import torch as th

import lib.tree_util as tree_util  # noqa: E402  (on sys.path via vpt)


def _row(state, b):
    return tree_util.tree_map(lambda x: x[b:b + 1] if isinstance(x, th.Tensor) else x, state)


def _cat(states):
    """Stack per-row states (all with the same structure) back into one batched state."""
    first = states[0]
    if isinstance(first, th.Tensor):
        return th.cat(states, 0)
    if first is None:
        return None
    if isinstance(first, (list, tuple)):
        out = [_cat([s[i] for s in states]) for i in range(len(first))]
        return type(first)(out) if isinstance(first, tuple) else out
    raise TypeError(f"unexpected state element {type(first)}")


def segmented_forward(policy, obs, first, state):
    """policy(obs, first, state) over (B, T) but splitting rows at mid-chunk episode starts.

    Returns ((pd, vpred), state_out) like the policy's own forward, with pd a dict of (B, T, ...) tensors
    and vpred (B, T, 1) or None.
    """
    B, T = first.shape
    if not bool(first[:, 1:].any()):  # fast path: no mid-chunk starts
        (pd, vpred, _), st = policy(obs=obs, first=first, state_in=state)
        return (pd, vpred), st
    pds, vps, sts = [], [], []
    for b in range(B):
        st = _row(state, b)
        starts = [0] + [t for t in range(1, T) if bool(first[b, t])]
        ends = starts[1:] + [T]
        row_pd, row_v = [], []
        for s, e in zip(starts, ends):
            o = {k: v[b:b + 1, s:e] for k, v in obs.items()}
            (pd, vpred, _), st = policy(obs=o, first=first[b:b + 1, s:e], state_in=st)
            row_pd.append(pd)
            row_v.append(vpred)
        pds.append({k: th.cat([p[k] for p in row_pd], 1) for k in row_pd[0]})
        vps.append(th.cat(row_v, 1) if row_v[0] is not None else None)
        sts.append(st)
    pd = {k: th.cat([p[k] for p in pds], 0) for k in pds[0]}
    vpred = th.cat(vps, 0) if vps[0] is not None else None
    return (pd, vpred), _cat(sts)
