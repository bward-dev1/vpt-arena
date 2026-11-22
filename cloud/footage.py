"""High-resolution footage for the trailers. The agent still acts on its normal 128x128 view; only the recording is large.

  xvfb-run -a -s "-screen 0 3840x2160x24" python cloud/footage.py probe --out probe --weights round-4:1x:w/round-4.weights
  xvfb-run -a -s "-screen 0 3840x2160x24" python cloud/footage.py shoot --tasks cloud/footage_tasks_a.json --agents round-4:1x:w/round-4.weights --out footage

A task is {"name", "kind": "play"|"dolly", "tag", "mode", "size": [w, h], "steps", "seed"}.
play: the policy plays one episode; every game frame is recorded at `size` (20 per game second) and the per-step log
      (reward, cumulative damage dealt, health, done) is written next to it so highlights can be cut where damage lands.
dolly: no policy. After the arena is built the player goes to spectator mode and `/tp` moves the view along an orbit around
      the arena (an establishing shot).
Outputs per task: <name>.mp4 (20 fps source), <name>-60.mp4 (60 fps, adjacent frames blended: film-like motion blur), <name>.json."""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402


class Rec:
    """Pipes raw RGB frames into ffmpeg at native size (no scaling)."""

    def __init__(self, path, size, fps=20):
        self.size, self.n, self.path = tuple(size), 0, Path(path)
        w, h = self.size
        fast = w >= 3000
        self.p = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-preset", "ultrafast" if fast else "veryfast", "-crf", "16" if fast else "14", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(self.path)], stdin=subprocess.PIPE)

    def add(self, rgb):
        import cv2
        if rgb.shape[1] != self.size[0] or rgb.shape[0] != self.size[1]:
            rgb = cv2.resize(rgb, self.size, interpolation=cv2.INTER_AREA)
        self.p.stdin.write(np.ascontiguousarray(rgb).tobytes())
        self.n += 1

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def blend60(src, dst, crf=17):
    """20 fps -> 60 fps by blending neighbouring frames (cheap, and reads as motion blur on a 20 fps source)."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "framerate=fps=60:scene=100", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], check=False)


def num(v):
    from vpt_arena.rl.sim_env import _num
    return _num(v)


def play(env, agent, task, out):
    frame = env.reset()
    agent.reset()
    rec = Rec(out / f"{task['name']}.mp4", task["size"])
    log, t0 = [], time.time()
    from vpt_arena.rl.sim_env import health
    for i in range(int(task["steps"])):
        a, _ = agent.act(frame)
        frame, r, done, info = env.step(a)
        pov = getattr(env, "last_pov", None)
        if pov is not None:
            rec.add(pov)
        prev = env.prev or {}
        log.append([round(float(r), 3), round(num(prev.get("damage_dealt")), 2), round(health(prev), 1), int(done), int(bool(info.get("won")))])
        if done:
            break
    rec.close()
    blend60(out / f"{task['name']}.mp4", out / f"{task['name']}-60.mp4")
    meta = {"task": task, "frames": rec.n, "seconds_wall": round(time.time() - t0, 1), "fps_wall": round(rec.n / max(1e-6, time.time() - t0), 2), "log": log}
    (out / f"{task['name']}.json").write_text(json.dumps(meta))
    print(f"[play] {task['name']}: {rec.n} frames at {meta['fps_wall']} wall fps, ended={'done' if log and log[-1][3] else 'steps'}", flush=True)
    return meta


def look_at(src, dst):
    dx, dz, dy = dst[0] - src[0], dst[2] - src[2], dst[1] - src[1]
    return -math.degrees(math.atan2(dx, dz)), -math.degrees(math.atan2(dy, math.hypot(dx, dz)))


def dolly(env, task, out):
    """Orbit shot around the arena in spectator mode; the arena and its mobs are built by reset()."""
    env.reset()
    cx, cy, cz = env.origin
    n = int(task["steps"])
    rec = Rec(out / f"{task['name']}.mp4", task["size"])
    env._cmd("/gamemode spectator")
    t0 = time.time()
    a0 = math.radians(task.get("start_deg", 200))
    sweep = math.radians(task.get("sweep_deg", 110))
    r0, r1 = task.get("radius", [22, 16])
    h0, h1 = task.get("height", [9, 4])
    for i in range(n):
        u = i / max(1, n - 1)
        e = u * u * (3 - 2 * u)
        ang = a0 + sweep * e
        rad = r0 + (r1 - r0) * e
        pos = (cx + rad * math.cos(ang), cy + h0 + (h1 - h0) * e, cz + rad * math.sin(ang))
        yaw, pitch = look_at(pos, (cx, cy + 1.2, cz))
        env._cmd(f"/tp @p {pos[0]:.2f} {pos[1]:.2f} {pos[2]:.2f} {yaw:.1f} {pitch:.1f}")
        obs, _, _, _, info = env.sim.step(env._noop())
        pov = info.get("pov")
        if pov is not None:
            rec.add(pov)
    rec.close()
    env._cmd("/gamemode survival")
    blend60(out / f"{task['name']}.mp4", out / f"{task['name']}-60.mp4")
    meta = {"task": task, "frames": rec.n, "seconds_wall": round(time.time() - t0, 1), "fps_wall": round(rec.n / max(1e-6, time.time() - t0), 2)}
    (out / f"{task['name']}.json").write_text(json.dumps(meta))
    print(f"[dolly] {task['name']}: {rec.n} frames at {meta['fps_wall']} wall fps", flush=True)


def load_agents(spec, first_mode):
    from vpt_arena.agent import ArenaAgent
    agents = {}
    for item in [s for s in spec.split(",") if s]:
        tag, arch, path = item.split(":", 2)
        agents[tag] = ArenaAgent(arch, path, first_mode, device="cpu")
    return agents


def shoot(args):
    import torch as th
    from vpt_arena.rl.arena_tasks import TASKS
    from vpt_arena.rl.sim_env import ArenaSimEnv
    th.set_num_threads(3)
    tasks = json.loads(Path(args.tasks).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    agents = load_agents(args.agents, tasks[0]["mode"])
    env, env_size = None, None
    budget = args.max_minutes * 60
    t0 = time.time()
    for task in tasks:
        if time.time() - t0 > budget:
            print("[shoot] time budget reached, stopping", flush=True)
            break
        size = tuple(task["size"])
        if env is None or size != env_size:
            if env is not None:
                env.close()
            env = ArenaSimEnv(task["mode"], seed=int(task.get("seed", 7)), render_size=size, look="cine", difficulty=args.difficulty)
            env_size = size
        env.task, env.mode = TASKS[task["mode"]], task["mode"]
        try:
            if task["kind"] == "dolly":
                dolly(env, task, out)
            else:
                ag = agents[task["tag"]]
                ag.set_mode(task["mode"])
                play(env, ag, task, out)
        except Exception as e:  # one bad shot must not lose the rest
            print(f"[shoot] {task['name']} failed: {type(e).__name__}: {str(e)[:200]}", flush=True)
            env._recover("shot failed")
    if env is not None:
        env.close()


def probe(args):
    import cv2
    import torch as th
    from vpt_arena.rl.sim_env import ArenaSimEnv
    th.set_num_threads(3)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res = {"cpus": os.cpu_count()}
    for label, size, look in (("360p", (640, 360), ""), ("1080p", (1920, 1080), "cine"), ("2160p", (3840, 2160), "cine")):
        try:
            env = ArenaSimEnv("duels_sword", seed=3, render_size=size, look=look)
            t = time.time()
            frame = env.reset()
            t_reset = time.time() - t
            t = time.time()
            n = 80
            for _ in range(n):
                frame, r, done, info = env.step({})
            fps = n / (time.time() - t)
            pov = env.last_pov
            cv2.imwrite(str(out / f"probe-{label}.jpg"), cv2.cvtColor(pov, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])
            res[label] = {"reset_s": round(t_reset, 1), "env_step_fps": round(fps, 2), "pov_shape": list(pov.shape), "agent_view": list(frame.shape)}
            print(label, res[label], flush=True)
            if label == "1080p":  # dolly test: a few spectator frames
                env.reset()
                env._cmd("/gamemode spectator")
                cx, cy, cz = env.origin
                for i, ang in enumerate((200, 250, 300)):
                    a = math.radians(ang)
                    pos = (cx + 18 * math.cos(a), cy + 8, cz + 18 * math.sin(a))
                    yaw, pitch = look_at(pos, (cx, cy + 1.2, cz))
                    env._cmd(f"/tp @p {pos[0]:.2f} {pos[1]:.2f} {pos[2]:.2f} {yaw:.1f} {pitch:.1f}")
                    for _ in range(4):
                        _, _, _, _, info = env.sim.step(env._noop())
                    cv2.imwrite(str(out / f"probe-dolly-{i}.jpg"), cv2.cvtColor(info["pov"], cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
                env._cmd("/gamemode survival")
            env.close()
        except Exception as e:
            res[label] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
            print(label, res[label], flush=True)
    if args.weights:
        try:
            tag, arch, path = args.weights.split(":", 2)
            from vpt_arena.agent import ArenaAgent
            ag = ArenaAgent(arch, path, "duels_sword", device="cpu")
            ag.reset()
            fr = np.random.randint(0, 255, (128, 128, 3), dtype=np.uint8)
            ag.act(fr)
            t = time.time()
            for _ in range(20):
                ag.act(fr)
            res["policy_act_per_s"] = round(20 / (time.time() - t), 2)
        except Exception as e:
            res["policy_act_per_s"] = f"error {type(e).__name__}: {str(e)[:200]}"
    (out / "probe.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "shoot"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks")
    ap.add_argument("--agents", default="")
    ap.add_argument("--weights", default="")
    ap.add_argument("--max-minutes", type=float, default=80)
    ap.add_argument("--difficulty", type=float, default=0.5)
    a = ap.parse_args()
    shoot(a) if a.cmd == "shoot" else probe(a)
