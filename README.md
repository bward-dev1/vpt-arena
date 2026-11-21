# VPT Arena

One network that plays survival Minecraft and the PvP minigames: duels (sword, classic, UHC, NoDebuff, sumo, boxing, bow, combo), Build UHC, Bed Wars (solo, doubles, squads), SkyWars, The Bridge, UHC, Survival Games, KitPvP, Capture the Wool, Spleef, TNT Run and parkour races.

It's built on OpenAI's [Video PreTraining (VPT)](https://github.com/openai/Video-Pre-Training) (MIT). The agent sees 128x128 game frames and outputs keyboard and mouse at 20 Hz, like a player. A learned game-mode embedding (mode, 1.8 or 1.9+ combat, team size) is added through VPT's own `diff_obs_process` hook. It starts at zero, so before any training the model is exactly VPT.

Actions use VPT's recorder JSONL format, so recordings from other tools that write it can be used directly.

## Where it plays

It's for your own server. Public servers like Hypixel ban bots, and nothing here deals with anti-cheat.

## How it gets good

| Phase | What | Status |
|---|---|---|
| 0 | VPT foundation 2x (or RL early-game 2x) | weights match key for key (`tools/check_weights.py`); real 1x on a contractor clip: 4.28 NLL/step, 60% button accuracy vs 13.14 / 0% random (`tools/validate_real.py`) |
| 1 | Record your own games: screen + exact keys/mouse | `live/recorder.py`, tested with fake backends |
| 2 | Label PvP videos with VPT's IDM | `idm_label.py`, tested on synthetic video |
| 3 | Sequence BC over all modes + contractor rehearsal | `train_bc.py`, tested on synthetic data and a 30-step real 1x fine-tune |
| 4 | Live agent on his server | `live/play.py`, tested with fakes; real 1x steps in 20 ms on the M2 CPU |
| 5 | RL on his server, reward from game events, KL to BC | `rl/`, PPO learns the toy env (0.12 -> 0.44 reward/step of 0.5 max); LiveEnv + datapack tested with fakes |
| - | Elo league | `league.py`, writes `runs/league.json` |
| - | Site | `site/`, local dashboard + docs on 127.0.0.1:7790 |

Not done yet: anything trained on real Minecraft data, and a run against a real Minecraft window or server.

Compute: IDM labelling, 2x BC and fast RL need a GPU (`colab/train.sh`, not run yet). The 2x model is 249M parameters (1x is 71M), and the IDM weights are 1.9 GB.

## Data format

Each trajectory is `<stem>.mp4` (20 fps, 640x360), `<stem>.jsonl` (one VPT recorder line per frame) and an optional `<stem>.meta.json`:

```json
{"mode": "bedwars_solo", "ruleset": "legacy", "team_size": 1, "source": "human", "weight": 1.0, "loss_weight": 1.0}
```

With no meta file, a trajectory counts as survival play. That's right for OpenAI's contractor data.

## Commands

```bash
.venv/bin/python -m vpt_arena.site.server                      # site on http://127.0.0.1:7790
.venv/bin/python -m vpt_arena.live.recorder --mode duels_sword  # record your own games (F8 pause)
.venv/bin/python -m vpt_arena.live.play --weights runs/x/policy.weights --arch 1x --mode duels_sword --server localhost:25565
python -m vpt_arena.idm_label --weights weights/4x_idm.weights --mode duels_sword --out data/idm/sword videos/*.mp4
python -m vpt_arena.train_bc --arch 2x --weights weights/foundation-model-2x.weights \
    --data data/human:4 --data data/idm:2 --data data/contractor:1 --run runs/arena-2x --ckpt-cnn
VPT_RCON_PASSWORD=... python -m vpt_arena.rl.train_rl --arch 1x --weights runs/x/policy.weights --mode duels_sword --run runs/rl-sword
python -m vpt_arena.league play --weights runs/x/policy.weights --name x --opponent Steve --opponent-kind human --mode duels_sword
python tools/make_datapack.py --out <world>/datapacks/vpt_arena --format 101
python tools/fetch_contractor.py --index 7 --n 50 --out data/contractor
```

Tests (CPU, tiny random nets): `tests.smoke` (18 checks), `tests.live_test`, `tests.rl_test`, `tests.server_test`, `tests.site_test`.

Config: `configs/controls.json` (bindings, sensitivity), `configs/own_servers.json` (where the agent may play), `configs/arenas.json` (RCON, server log, per-mode round commands and chat patterns).

Weights: see `WEIGHT_URLS` in `vpt_arena/vpt.py`. Don't download them to the Mac's internal disk.

## Layout

- `vpt_arena/vpt.py`: builds the policy and IDM from `configs/vpt_models.json` (no pickle loading), adds the conditioner, converts actions
- `vpt_arena/games.py`: the 23 modes, their defaults and their reward events
- `vpt_arena/data.py`: trajectory reader (VPT's loader fixes) and B-stream sequence loader
- `vpt_arena/train_bc.py`: sequence BC, TBPTT memory carry, camera loss masked when the camera is off, KL to prior, resume
- `vpt_arena/idm_label.py`: any video -> 20 fps recorder-format training data
- `vpt_arena/agent.py`: stateful agent (frames in, actions out)
- `vpt_arena/live/`: macOS capture and input (Quartz), recorder, play loop, controls mapping
- `vpt_arena/rl/`: PPO, toy envs, LiveEnv, server log events and RCON, RL CLI
- `vpt_arena/league.py`: Elo league
- `vpt_arena/site/`: dashboard and docs
- `tools/`: weight check, real-weights validation, contractor download, datapack
- `colab/train.sh`: GPU pipeline
- `third_party/vpt/`: OpenAI's code, unmodified; `vpt_arena/_shims/` replaces `gym3.types` and `minerl` so they aren't installed

## Setup

The `.venv` was removed on 2026-11-21 (twice) to keep the Mac from running out of disk. To rebuild it (about 870 MB), put it on the T7 or use Colab:

```bash
python3 -m venv .venv && .venv/bin/pip install --no-cache-dir torch numpy opencv-python-headless attrs
```
