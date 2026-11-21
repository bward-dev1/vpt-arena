"""Relay between the public Simulation Lab (Cloudflare KV) and GitHub Actions (simulate.yml).

Every 20 s:
  - read KV `simindex` (written by the worker on submit; one read, no KV list operations)
  - new ids: read `simreq:<id>`, validate the spec again, resolve the model, dispatch simulate.yml,
    write `simstat:<id>` = dispatched
  - dispatched/running ids: check the run; on success download the artifact and write
    `simclip:<id>:<ep>` + `simstat:<id>` = done (with results); on failure write failed
Local state in runs/.sim_relay.json keeps KV writes to state changes only.

    python3 tools/sim_relay.py            # loop
    python3 tools/sim_relay.py --once
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from publish_site import CF  # noqa: E402
from vpt_arena.rl import custom_sim as C  # noqa: E402

REPO = "bward-dev1/vpt-arena"
STATE = ROOT / "runs" / ".sim_relay.json"
MAX_ACTIVE = 4          # concurrent cloud sims (RL rounds use 12 of the 20 free runners)
STALE_S = 75 * 60       # give up on a run after this long


def gh(*args, timeout=120):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout


class KV:
    def __init__(self):
        self.cf = CF()
        self.ns = self.cf.ensure_kv()

    def _path(self, key):
        return f"/accounts/{self.cf.acct}/storage/kv/namespaces/{self.ns}/values/{urllib.parse.quote(key, safe='')}"

    def get_json(self, key):
        try:
            raw = self.cf.call("GET", self._path(key))
        except RuntimeError as e:
            if "404" in str(e) or "10009" in str(e):
                return None
            raise
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    def put_json(self, key, obj):
        self.cf.call("PUT", self._path(key), raw=json.dumps(obj).encode(), ctype="application/json")

    def put_bytes(self, key, data):
        self.cf.call("PUT", self._path(key), raw=data, ctype="application/octet-stream")


def releases():
    try:
        rels = json.loads(gh("release", "list", "-R", REPO, "--json", "tagName", "-L", "100"))
    except RuntimeError:
        return []
    return sorted([r["tagName"] for r in rels if r["tagName"].startswith("round-")],
                  key=lambda t: int(t.split("-")[1]))


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(st):
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(STATE)


def find_run(sim_id):
    runs = json.loads(gh("run", "list", "-R", REPO, "-w", "simulate", "-L", "40", "--json",
                         "databaseId,displayTitle,status,conclusion,url,createdAt"))
    for r in runs:
        if r["displayTitle"] == f"sim {sim_id}":
            return r
    return None


def stat(kv, sim_id, status, **extra):
    obj = {"status": status, "updated": int(time.time() * 1000), **extra}
    kv.put_json(f"simstat:{sim_id}", obj)
    return obj


def tick(kv, st):
    index = kv.get_json("simindex") or []
    rels = releases()
    active = [i for i, s in st.items() if s.get("status") in ("dispatched", "running")]
    # newest last so older requests go first
    for entry in reversed(index[:40]):
        sid = entry.get("id")
        if not sid or sid in st:
            continue
        if len(active) >= MAX_ACTIVE:
            break
        req = kv.get_json(f"simreq:{sid}")
        if not req:
            continue
        try:
            spec = C.validate(req.get("spec") or {}, releases=rels)
            tag = spec["model"]
            if tag == "latest":
                tag = rels[-1] if rels else "baseline"
            spec_json = json.dumps(spec, separators=(",", ":"))
            if len(spec_json) > 60000:
                raise C.SpecError("spec too large")
            gh("workflow", "run", "simulate.yml", "-R", REPO, "-f", f"id={sid}", "-f", f"spec={spec_json}",
               "-f", f"model_tag={tag}")
            st[sid] = {"status": "dispatched", "since": time.time(), "model_tag": tag}
            stat(kv, sid, "dispatched", message=f"Starting a cloud machine with model {tag}", model_tag=tag)
            active.append(sid)
            print(f"dispatched {sid} ({tag}): {C.describe(spec)}", flush=True)
        except C.SpecError as e:
            st[sid] = {"status": "failed"}
            stat(kv, sid, "failed", message=f"Invalid scenario: {e}")
        except RuntimeError as e:
            print(f"dispatch failed for {sid}: {e}", flush=True)
            return
    for sid in list(active):
        s = st[sid]
        try:
            run = find_run(sid)
        except RuntimeError as e:
            print(f"run lookup failed: {e}", flush=True)
            return
        if run is None:
            if time.time() - s["since"] > 600:
                st[sid] = {"status": "failed"}
                stat(kv, sid, "failed", message="The cloud run never started")
            continue
        if run["status"] != "completed":
            if s["status"] != "running" and run["status"] == "in_progress":
                s["status"] = "running"
                stat(kv, sid, "running", message="Minecraft is running the scenario", run_url=run["url"],
                     model_tag=s.get("model_tag"))
            elif time.time() - s["since"] > STALE_S:
                st[sid] = {"status": "failed"}
                stat(kv, sid, "failed", message="Timed out", run_url=run["url"])
            continue
        if run["conclusion"] != "success":
            st[sid] = {"status": "failed"}
            stat(kv, sid, "failed", message=f"The cloud run ended with {run['conclusion']}", run_url=run["url"])
            continue
        tmp = Path(tempfile.mkdtemp(prefix="vpt-sim-"))
        try:
            gh("run", "download", str(run["databaseId"]), "-R", REPO, "-n", f"sim-{sid}", "-D", str(tmp), timeout=300)
            res = json.loads((tmp / "result.json").read_text())
            for i, ep in enumerate(res.get("episodes", [])):
                clip = tmp / f"ep{i}.mp4"
                if clip.exists() and clip.stat().st_size < 20_000_000:
                    kv.put_bytes(f"simclip:{sid}:{i}", clip.read_bytes())
                    ep["clip"] = True
                else:
                    ep["clip"] = False
            res.pop("spec", None)
            st[sid] = {"status": "done"}
            stat(kv, sid, "done", message="Finished", run_url=run["url"], result=res, model_tag=res.get("model_tag"))
            print(f"done {sid}: {[(e['won'], e['return']) for e in res.get('episodes', [])]}", flush=True)
        except Exception as e:
            st[sid] = {"status": "failed"}
            stat(kv, sid, "failed", message=f"Could not collect results: {str(e)[:120]}", run_url=run["url"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    # forget old finished entries
    keep = {e.get("id") for e in index}
    for sid in list(st):
        if sid not in keep and st[sid].get("status") in ("done", "failed"):
            del st[sid]


def main():
    once = "--once" in sys.argv
    kv = KV()
    while True:
        st = load_state()
        try:
            tick(kv, st)
        except Exception as e:
            print(f"tick error: {type(e).__name__}: {str(e)[:200]}", flush=True)
        save_state(st)
        if once:
            break
        time.sleep(20)


if __name__ == "__main__":
    main()
