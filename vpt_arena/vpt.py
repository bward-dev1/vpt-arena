"""Glue around OpenAI's VPT code (third_party/vpt, MIT licence).

- builds the policy / IDM from configs/vpt_models.json (no pickle loading)
- adds the game-mode conditioner through VPT's own `diff_obs_process` hook
- converts actions between recorder JSON, env dicts and the policy's tokens
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch as th
from torch import nn

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "third_party" / "vpt", ROOT / "vpt_arena" / "_shims"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gym3.types import DictType  # noqa: E402  (shim)
from lib.action_mapping import CameraHierarchicalMapping, IDMActionMapping  # noqa: E402
from lib.actions import ActionTransformer, Buttons  # noqa: E402
from lib.policy import InverseActionPolicy, MinecraftAgentPolicy  # noqa: E402

from . import games  # noqa: E402

MODEL_CONFIGS = json.loads((ROOT / "configs" / "vpt_models.json").read_text())
AGENT_RESOLUTION = (128, 128)
N_CAMERA_BINS = 11
ACTION_TRANSFORMER_KWARGS = dict(camera_binsize=2, camera_maxval=10, camera_mu=10, camera_quantization_scheme="mu_law")
# Mouse pixels -> degrees, from MineRL's Java code (recorded at the contractors' sensitivity).
CAMERA_SCALER = 360.0 / 2400.0

WEIGHT_URLS = {
    "1x": "https://openaipublic.blob.core.windows.net/minecraft-rl/models/foundation-model-1x.weights",
    "2x": "https://openaipublic.blob.core.windows.net/minecraft-rl/models/foundation-model-2x.weights",
    "3x": "https://openaipublic.blob.core.windows.net/minecraft-rl/models/foundation-model-3x.weights",
    "2x-early-game": "https://openaipublic.blob.core.windows.net/minecraft-rl/models/bc-early-game-2x.weights",
    "2x-rl-early-game": "https://openaipublic.blob.core.windows.net/minecraft-rl/models/rl-from-early-game-2x.weights",
    "idm4x": "https://openaipublic.blob.core.windows.net/minecraft-rl/idm/4x_idm.weights",
}
# Which architecture each published weights file belongs to.
WEIGHT_ARCH = {"1x": "1x", "2x": "2x", "3x": "3x", "2x-early-game": "2x", "2x-rl-early-game": "2x", "idm4x": "idm4x"}


# --------------------------------------------------------------------------- conditioning

class GameConditioner(nn.Module):
    """(mode, ruleset, team size) -> a vector added to the image features.

    The output projection starts at zero, so a freshly attached conditioner
    leaves the pretrained network's behaviour exactly as it was.
    """

    def __init__(self, hidsize, dim=256):
        super().__init__()
        self.mode = nn.Embedding(len(games.MODES), dim)
        self.ruleset = nn.Embedding(len(games.RULESETS), dim)
        self.team = nn.Embedding(len(games.TEAM_SIZES), dim)
        self.mlp = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, dim), nn.GELU())
        self.out = nn.Linear(dim, hidsize)
        nn.init.zeros_(self.out.weight)
        nn.init.zeros_(self.out.bias)

    def forward(self, ids):  # ids: (B, T, 3) long
        ids = ids.long()
        h = self.mode(ids[..., 0]) + self.ruleset(ids[..., 1]) + self.team(ids[..., 2])
        return self.out(self.mlp(h))


# --------------------------------------------------------------------------- building

def _net_kwargs(arch):
    cfg = MODEL_CONFIGS[arch]
    return dict(cfg["net"]), dict(cfg["pi_head"])


def build_policy(arch="2x", conditioned=True, net_overrides=None):
    """A VPT policy with the conditioner attached. `net_overrides` is for tests (tiny nets)."""
    net_kwargs, head_kwargs = _net_kwargs(arch)
    net_kwargs.update(net_overrides or {})
    mapper = CameraHierarchicalMapping(n_camera_bins=N_CAMERA_BINS)
    policy = MinecraftAgentPolicy(
        action_space=DictType(**mapper.get_action_space_update()),
        policy_kwargs=net_kwargs,
        pi_head_kwargs=head_kwargs,
    )
    if conditioned:
        policy.net.diff_obs_process = GameConditioner(net_kwargs["hidsize"])
    return policy


def build_idm(arch="idm4x", net_overrides=None):
    net_kwargs, head_kwargs = _net_kwargs(arch)
    net_kwargs.update(net_overrides or {})
    mapper = IDMActionMapping(n_camera_bins=N_CAMERA_BINS)
    return InverseActionPolicy(
        idm_net_kwargs=net_kwargs,
        pi_head_kwargs=head_kwargs,
        action_space=DictType(**mapper.get_action_space_update()),
    )


class _PassFeatures(nn.Module):
    """Wraps the image stage: real frames go through it (and the output is remembered); precomputed
    features (B, T, hidsize floats) pass straight through. Lets RL reuse rollout features in the update."""

    def __init__(self, inner, hidsize):
        super().__init__()
        self.inner, self.hidsize, self.last = inner, hidsize, None

    def forward(self, x):
        if x.dim() == 3 and x.is_floating_point() and x.shape[-1] == self.hidsize:
            return x
        out = self.inner(x)
        self.last = out.detach()
        return out


class _PassPre(nn.Module):
    def __init__(self, inner):
        super().__init__()
        self.inner = inner

    def forward(self, x):
        return x if x.dim() == 3 and x.is_floating_point() else self.inner(x)


def freeze_image_encoder(policy):
    """Freeze VPT's image CNN and let callers feed cached features instead of frames (state_dict keys unchanged)."""
    net = policy.net
    if isinstance(net.img_process, _PassFeatures):
        return policy
    for p in net.img_process.parameters():
        p.requires_grad_(False)
    hid = net.hidsize
    pre, proc = net.img_preprocess, net.img_process
    # keep the original modules registered under their own names so weights load/save unchanged
    object.__setattr__(net, "_img_preprocess_raw", pre)
    object.__setattr__(net, "_img_process_raw", proc)
    net._modules["img_preprocess"] = _PassPre(pre)
    net._modules["img_process"] = _PassFeatures(proc, hid)
    return policy


def state_dict_plain(policy):
    """state_dict with the original key names even when freeze_image_encoder wrapped the image stage."""
    sd = policy.state_dict()
    out = {}
    for k, v in sd.items():
        k2 = k.replace("img_process.inner.", "img_process.").replace("img_preprocess.inner.", "img_preprocess.")
        out[k2] = v
    return out


def load_weights(model, path, device="cpu"):
    """Load VPT .weights or one of our checkpoints. Reports anything that didn't match."""
    sd = th.load(path, map_location=device, weights_only=True)
    if isinstance(sd, dict) and "policy" in sd and isinstance(sd["policy"], dict):
        sd = sd["policy"]
    # OpenAI's RL checkpoints carry an auxiliary value head used only during their RL training
    sd = {k: v for k, v in sd.items() if not k.startswith("aux_value_head.")}
    if not any("diff_obs_process" in k for k in model.state_dict()):
        # an unconditioned model (e.g. the KL prior) loading a conditioned checkpoint: drop the conditioner
        sd = {k: v for k, v in sd.items() if "diff_obs_process" not in k}
    missing, unexpected = model.load_state_dict(sd, strict=False)
    # The conditioner is ours and absent from OpenAI's files; anything else missing is a real mismatch.
    real_missing = [k for k in missing if "diff_obs_process" not in k]
    if real_missing or unexpected:
        raise RuntimeError(f"weights mismatch for {path}: missing={real_missing[:8]} unexpected={list(unexpected)[:8]}")
    return model


def default_device():
    if th.cuda.is_available():
        return "cuda"
    if th.backends.mps.is_available():
        return "mps"
    return "cpu"


# VPT's torch_util picks "cuda" whenever torch was *built* with CUDA, even with no GPU present,
# and creates the transformer memory there. Point it at a device that exists. States are moved
# to the policy's device by callers anyway, so cpu is a safe default.
import lib.torch_util as _tu  # noqa: E402
_tu.set_default_torch_device("cuda" if th.cuda.is_available() else "cpu")


# --------------------------------------------------------------------------- actions

KEYBOARD_BUTTON_MAPPING = {  # recorder key name -> env button (from VPT's run_inverse_dynamics_model.py)
    "key.keyboard.escape": "ESC", "key.keyboard.s": "back", "key.keyboard.q": "drop", "key.keyboard.w": "forward",
    **{f"key.keyboard.{i}": f"hotbar.{i}" for i in range(1, 10)},
    "key.keyboard.e": "inventory", "key.keyboard.space": "jump", "key.keyboard.a": "left", "key.keyboard.d": "right",
    "key.keyboard.left.shift": "sneak", "key.keyboard.left.control": "sprint", "key.keyboard.f": "swapHands",
}
BUTTON_TO_KEY = {v: k for k, v in KEYBOARD_BUTTON_MAPPING.items()}
ENV_BUTTONS = ["ESC", "attack", "back", "drop", "forward", *[f"hotbar.{i}" for i in range(1, 10)], "inventory",
               "jump", "left", "pickItem", "right", "sneak", "sprint", "swapHands", "use"]


def noop_env_action():
    a = {k: 0 for k in ENV_BUTTONS}
    a["camera"] = np.zeros(2, dtype=np.float64)
    return a


def json_to_env_action(step):
    """One recorder JSON line -> (env action, is_null). Same rules as VPT's loader."""
    a = noop_env_action()
    null = True
    for key in step["keyboard"]["keys"]:
        if key in KEYBOARD_BUTTON_MAPPING:
            a[KEYBOARD_BUTTON_MAPPING[key]] = 1
            null = False
    mouse = step["mouse"]
    a["camera"][0] = mouse["dy"] * CAMERA_SCALER
    a["camera"][1] = mouse["dx"] * CAMERA_SCALER
    if mouse["dx"] != 0 or mouse["dy"] != 0:
        null = False
    else:
        a["camera"][np.abs(a["camera"]) > 180] = 0
    for b, name in ((0, "attack"), (1, "use"), (2, "pickItem")):
        if b in mouse["buttons"]:
            a[name] = 1
            null = False
    return a, null


def env_action_to_json(a, hotbar, gui_open=False, extra=None):
    """Inverse of json_to_env_action, for writing IDM labels and live recordings in recorder format."""
    keys = [BUTTON_TO_KEY[b] for b in BUTTON_TO_KEY if a.get(b, 0)]
    buttons = [i for i, name in enumerate(("attack", "use", "pickItem")) if a.get(name, 0)]
    cam = np.asarray(a["camera"], dtype=np.float64)
    step = {
        "keyboard": {"keys": keys, "newKeys": [], "chars": ""},
        "mouse": {"dx": float(cam[1] / CAMERA_SCALER), "dy": float(cam[0] / CAMERA_SCALER), "buttons": buttons,
                  "newButtons": [], "x": 0.0, "y": 0.0, "dwheel": 0.0},
        "hotbar": int(hotbar), "isGuiOpen": bool(gui_open), "tick": 0,
    }
    if extra:
        step.update(extra)
    return step


class ActionCodec:
    """Env action dicts <-> the policy's joint (buttons, camera) tokens."""

    def __init__(self):
        self.mapper = CameraHierarchicalMapping(n_camera_bins=N_CAMERA_BINS)
        self.transformer = ActionTransformer(**ACTION_TRANSFORMER_KWARGS)
        self.camera_zero_bin = self.transformer.camera_zero_bin()

    def env_to_tokens(self, env_actions):
        """List of env actions -> dict of (N, 1) int arrays, plus a null mask (VPT drops null steps)."""
        batch = {k: np.array([a.get(k, 0) for a in env_actions]) for k in Buttons.ALL}
        batch["camera"] = np.stack([np.asarray(a["camera"], dtype=np.float64) for a in env_actions])
        fac = self.transformer.env2policy(batch)
        null = np.all(fac["buttons"] == 0, axis=1) & np.all(fac["camera"] == self.camera_zero_bin, axis=1)
        tok = self.mapper.from_factored(fac)
        return tok, null

    def tokens_to_env(self, tokens):
        """dict of (N, 1) tokens (numpy or torch) -> list of env actions."""
        tokens = {k: (v.detach().cpu().numpy() if isinstance(v, th.Tensor) else np.asarray(v)) for k, v in tokens.items()}
        fac = self.mapper.to_factored(tokens)
        env = self.transformer.policy2env(fac)
        n = env["camera"].shape[0]
        out = []
        for i in range(n):
            a = noop_env_action()
            for k in Buttons.ALL:
                a[k] = int(env[k][i])
            a["camera"] = np.asarray(env["camera"][i], dtype=np.float64)
            out.append(a)
        return out

    def camera_active(self, button_tokens):
        """True where the joint button token has the camera meta-action on (camera head is used)."""
        idx = np.asarray(button_tokens).reshape(-1)
        return ~self.mapper.BUTTON_IDX_TO_CAMERA_META_OFF[idx]


def idm_tokens_to_env(pred):
    """IDM output (factored buttons (N,20), camera bins (N,2)) -> list of env actions."""
    tr = ActionTransformer(**ACTION_TRANSFORMER_KWARGS)
    pred = {k: (v.detach().cpu().numpy() if isinstance(v, th.Tensor) else np.asarray(v)) for k, v in pred.items()}
    env = tr.policy2env({"buttons": pred["buttons"].reshape(-1, len(Buttons.ALL)), "camera": pred["camera"].reshape(-1, 2)})
    out = []
    for i in range(env["camera"].shape[0]):
        a = noop_env_action()
        for k in Buttons.ALL:
            a[k] = int(env[k][i])
        a["camera"] = np.asarray(env["camera"][i], dtype=np.float64)
        out.append(a)
    return out
