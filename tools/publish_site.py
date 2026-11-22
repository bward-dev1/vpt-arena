#!/usr/bin/env python3
"""Publish the VPT Arena dashboard as a public static site on Cloudflare Pages.

Run with the stdlib only:   ~/homebrew/bin/python3 tools/publish_site.py [--root .]

What it does
  1. Builds dist/ (gitignored): the front end from vpt_arena/site/static plus a worker
     (_worker.js) that serves /data.json from a Workers KV value.
  2. Builds one scrubbed data snapshot from the repo's runs/, data/ and weights/ using the
     same Arena functions the local server uses. No names, paths, servers or frames go in.
  3. Fails if any scrubbed pattern shows up in the output (see FORBIDDEN).
  4. Copies each gameplay clip once from its GitHub release asset into KV (clip:<tag>:<mode>) so the
     site can serve it with Range support, and the list of release tags (models) for the sim form.
  5. Writes the snapshot to KV (one key; skipped when unchanged, refreshed at least hourly).
  6. Deploys the Pages project only when the front-end files changed (content hash).

The worker (_worker.js) is generated here: data.json, /clips/<tag>/<mode>.mp4, and the Simulation Lab
endpoints (/api/sim, /api/sims, /sims/<id>/<ep>.mp4). Its validation rules are validate_spec() below,
mirrored in JS; both read configs/sim_spec.json.

Credentials come from CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_AUTH_EMAIL and
CLOUDFLARE_GLOBAL_API_KEY. They are only sent as request headers, never printed or stored.

Options: --build-only (no network), --force (redeploy and rewrite KV), --project NAME.
"""
import argparse
import base64
import copy
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vpt_arena import games  # noqa: E402
from vpt_arena.site import server as srv  # noqa: E402

STATIC = srv.STATIC
API = "https://api.cloudflare.com/client/v4"
PROJECT = "vpt-arena"
KV_TITLE = "vpt-arena-data"
KV_KEY = "data"
COMPAT_DATE = "2025-01-01"
MAX_RUNS = 30
PUBLIC_POINTS = 120
KV_REFRESH_S = 3600

# Anything matching these in the built files or the snapshot fails the publish.
FORBIDDEN = [
    (re.compile(r"/Users/"), "/Users/ path"),
    (re.compile(r"@gmail", re.I), "gmail address"),
    (re.compile(r"@outlook", re.I), "outlook address"),
    (re.compile(r"192\.168\."), "LAN IP"),
    (re.compile(r"127\.0\.0\.1"), "loopback IP"),
    (re.compile(r"rcon", re.I), "rcon"),
    (re.compile(r"\blocalhost\b", re.I), "localhost"),
]
# Personal words (names, account names) live in a gitignored local file so the public repo doesn't list them:
# configs/scrub.local.json = {"words": ["...", ...]}  (matched as whole words, case-insensitive)
_LOCAL = Path(__file__).resolve().parent.parent / "configs" / "scrub.local.json"
if _LOCAL.exists():
    for _w in json.loads(_LOCAL.read_text()).get("words", []):
        FORBIDDEN.append((re.compile(r"\b" + re.escape(_w) + r"\b", re.I), "a private word from scrub.local.json"))
TEXT_EXT = {".html", ".js", ".css", ".json", ".txt", ".svg", ".md"}

# --------------------------------------------------------------------------- simulation spec

SIM_SPEC_PATH = REPO / "configs" / "sim_spec.json"
SIM_TOP = ("name", "model", "base_mode", "arena", "player", "opponents", "goal", "seconds", "episodes", "difficulty", "seed")
SIM_NAME_RE = re.compile(r"^[A-Za-z0-9 _.,'!()+-]+$")
SIM_STALE_S = 3 * 3600          # a request this old that never finished stops counting toward the queue cap
SIM_LIMITS = {"per_ip_hour": 3, "per_day": 30, "unfinished": 8, "index_max": 60, "list_n": 20}


def load_sim_spec(path=SIM_SPEC_PATH):
    """configs/sim_spec.json plus the base_mode keys from games.py (the one source for form, worker and runner)."""
    spec = json.loads(Path(path).read_text("utf-8"))
    spec["base_modes"] = [m.key for m in games.MODES]
    return spec


def _is_int(v):
    return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v == v and abs(v) != float("inf") and v.is_integer())


def validate_spec(raw, spec, models):
    """Strict check of a simulation request. Returns (normalized_spec_or_None, [errors]).

    Missing fields take their defaults. Unknown keys, wrong types, out-of-range numbers, values outside the
    enums, too many opponents and a model that is not baseline/latest/a known release are errors.
    The JS in the worker (VALIDATE_JS) implements exactly the same rules.
    """
    L, E, D = spec["limits"], spec["enums"], spec["defaults"]
    errs = []

    def isobj(v):
        return isinstance(v, dict)

    def need_int(v, rng, label):
        if not _is_int(v):
            errs.append(f"{label} must be a whole number")
            return None
        if v < rng[0] or v > rng[1]:
            errs.append(f"{label} must be between {rng[0]} and {rng[1]}")
        return int(v)

    def need_enum(v, key, label):
        if not isinstance(v, str) or v not in E[key]:
            errs.append(f"{label} must be one of: {', '.join(E[key])}")
        return v

    def need_bool(v, label):
        if not isinstance(v, bool):
            errs.append(f"{label} must be true or false")
        return v

    def keys_ok(o, allowed, label):
        for k in o:
            if k not in allowed:
                errs.append(f"unknown field {label}{k}")

    if not isobj(raw):
        return None, ["the request must be a JSON object"]
    keys_ok(raw, SIM_TOP, "")
    g = lambda k: raw[k] if k in raw else D[k]   # noqa: E731
    out = {}
    name = g("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > L["name_max"] or not SIM_NAME_RE.match(name.strip()):
        errs.append(f"name must be 1 to {L['name_max']} characters: letters, numbers, spaces and . , ' ! ( ) + - _")
    out["name"] = name.strip() if isinstance(name, str) else name
    model = g("model")
    if not isinstance(model, str) or model not in ("baseline", "latest") and model not in models:
        errs.append("model must be baseline, latest or a published release (" + ", ".join(["baseline", "latest"] + [m for m in models if m not in ("baseline", "latest")]) + ")")
    out["model"] = model
    bm = g("base_mode")
    if not isinstance(bm, str) or bm not in spec["base_modes"]:
        errs.append("base_mode is not a known game mode")
    out["base_mode"] = bm

    a = g("arena")
    if not isobj(a):
        errs.append("arena must be an object")
    else:
        keys_ok(a, ("size", "floor", "hazard", "time"), "arena.")
        da = D["arena"]
        out["arena"] = {"size": need_int(a.get("size", da["size"]), L["arena_size"], "arena.size"),
                        "floor": need_enum(a.get("floor", da["floor"]), "floor", "arena.floor"),
                        "hazard": need_enum(a.get("hazard", da["hazard"]), "hazard", "arena.hazard"),
                        "time": need_enum(a.get("time", da["time"]), "time", "arena.time")}
    p = g("player")
    if not isobj(p):
        errs.append("player must be an object")
    else:
        keys_ok(p, ("weapon", "armor", "bow", "arrows", "blocks", "gapples"), "player.")
        dp = D["player"]
        out["player"] = {"weapon": need_enum(p.get("weapon", dp["weapon"]), "weapon", "player.weapon"),
                         "armor": need_enum(p.get("armor", dp["armor"]), "armor", "player.armor"),
                         "bow": need_bool(p.get("bow", dp["bow"]), "player.bow"),
                         "arrows": need_int(p.get("arrows", dp["arrows"]), L["arrows"], "player.arrows"),
                         "blocks": need_int(p.get("blocks", dp["blocks"]), L["blocks"], "player.blocks"),
                         "gapples": need_int(p.get("gapples", dp["gapples"]), L["gapples"], "player.gapples")}
    ops = g("opponents")
    if not isinstance(ops, list):
        errs.append("opponents must be a list")
    else:
        if len(ops) < L["opponent_groups"][0] or len(ops) > L["opponent_groups"][1]:
            errs.append(f"opponents must have {L['opponent_groups'][0]} to {L['opponent_groups'][1]} groups")
        do = D["opponents"][0]
        outs, total = [], 0
        for i, o in enumerate(ops[:L["opponent_groups"][1] + 1]):
            lab = f"opponents[{i}]."
            if not isobj(o):
                errs.append(f"opponents[{i}] must be an object")
                continue
            keys_ok(o, ("type", "count", "weapon", "armor", "distance"), lab)
            if "type" not in o:
                errs.append(lab + "type is required")
            cnt = need_int(o.get("count", do["count"]), L["opponent_count"], lab + "count")
            total += cnt if cnt is not None else 0
            outs.append({"type": need_enum(o.get("type"), "opponent_type", lab + "type"),
                         "count": cnt,
                         "weapon": need_enum(o.get("weapon", "none"), "weapon", lab + "weapon"),
                         "armor": need_enum(o.get("armor", "none"), "armor", lab + "armor"),
                         "distance": need_int(o.get("distance", do["distance"]), L["opponent_distance"], lab + "distance")})
        if total > L["opponents_total_max"]:
            errs.append(f"opponents total {total} is more than the limit of {L['opponents_total_max']}")
        out["opponents"] = outs
    gl = g("goal")
    if not isobj(gl):
        errs.append("goal must be an object")
    else:
        keys_ok(gl, ("type", "distance"), "goal.")
        dg = D["goal"]
        out["goal"] = {"type": need_enum(gl.get("type", dg["type"]), "goal", "goal.type"),
                       "distance": need_int(gl.get("distance", dg["distance"]), L["goal_distance"], "goal.distance")}
    out["seconds"] = need_int(g("seconds"), L["seconds"], "seconds")
    out["episodes"] = need_int(g("episodes"), L["episodes"], "episodes")
    df = g("difficulty")
    if not isinstance(df, (int, float)) or isinstance(df, bool) or df != df or abs(df) == float("inf"):
        errs.append("difficulty must be a number")
    elif df < L["difficulty"][0] or df > L["difficulty"][1]:
        errs.append(f"difficulty must be between {L['difficulty'][0]} and {L['difficulty'][1]}")
    out["difficulty"] = df
    out["seed"] = need_int(g("seed"), L["seed"], "seed")
    return (None, errs) if errs else (out, [])


# The same rules in JS. Keep the two in step; tests/site_test.py runs both on the same cases when node is installed.
VALIDATE_JS = r"""
const SIM_TOP = ["name", "model", "base_mode", "arena", "player", "opponents", "goal", "seconds", "episodes", "difficulty", "seed"];
const NAME_RE = /^[A-Za-z0-9 _.,'!()+-]+$/;
const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
const isInt = v => typeof v === "number" && Number.isInteger(v);
function validateSpec(raw, models) {
  const L = SPEC.limits, E = SPEC.enums, D = SPEC.defaults, errs = [];
  const needInt = (v, r, label) => {
    if (!isInt(v)) { errs.push(label + " must be a whole number"); return null; }
    if (v < r[0] || v > r[1]) errs.push(label + " must be between " + r[0] + " and " + r[1]);
    return v;
  };
  const needEnum = (v, key, label) => { if (typeof v !== "string" || !E[key].includes(v)) errs.push(label + " must be one of: " + E[key].join(", ")); return v; };
  const needBool = (v, label) => { if (typeof v !== "boolean") errs.push(label + " must be true or false"); return v; };
  const keysOk = (o, allowed, label) => { for (const k of Object.keys(o)) if (!allowed.includes(k)) errs.push("unknown field " + label + k); };
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const pick = (o, k, d) => has(o, k) ? o[k] : d;
  if (!isObj(raw)) return { spec: null, errors: ["the request must be a JSON object"] };
  keysOk(raw, SIM_TOP, "");
  const g = k => pick(raw, k, D[k]);
  const out = {};
  const name = g("name");
  if (typeof name !== "string" || !name.trim() || name.trim().length > L.name_max || !NAME_RE.test(name.trim()))
    errs.push("name must be 1 to " + L.name_max + " characters: letters, numbers, spaces and . , ' ! ( ) + - _");
  out.name = typeof name === "string" ? name.trim() : name;
  const model = g("model");
  if (typeof model !== "string" || (model !== "baseline" && model !== "latest" && !models.includes(model)))
    errs.push("model must be baseline, latest or a published release (" + ["baseline", "latest"].concat(models.filter(m => m !== "baseline" && m !== "latest")).join(", ") + ")");
  out.model = model;
  const bm = g("base_mode");
  if (typeof bm !== "string" || !SPEC.base_modes.includes(bm)) errs.push("base_mode is not a known game mode");
  out.base_mode = bm;
  const a = g("arena");
  if (!isObj(a)) errs.push("arena must be an object");
  else {
    keysOk(a, ["size", "floor", "hazard", "time"], "arena.");
    const da = D.arena;
    out.arena = { size: needInt(pick(a, "size", da.size), L.arena_size, "arena.size"), floor: needEnum(pick(a, "floor", da.floor), "floor", "arena.floor"),
      hazard: needEnum(pick(a, "hazard", da.hazard), "hazard", "arena.hazard"), time: needEnum(pick(a, "time", da.time), "time", "arena.time") };
  }
  const p = g("player");
  if (!isObj(p)) errs.push("player must be an object");
  else {
    keysOk(p, ["weapon", "armor", "bow", "arrows", "blocks", "gapples"], "player.");
    const dp = D.player;
    out.player = { weapon: needEnum(pick(p, "weapon", dp.weapon), "weapon", "player.weapon"), armor: needEnum(pick(p, "armor", dp.armor), "armor", "player.armor"),
      bow: needBool(pick(p, "bow", dp.bow), "player.bow"), arrows: needInt(pick(p, "arrows", dp.arrows), L.arrows, "player.arrows"),
      blocks: needInt(pick(p, "blocks", dp.blocks), L.blocks, "player.blocks"), gapples: needInt(pick(p, "gapples", dp.gapples), L.gapples, "player.gapples") };
  }
  const ops = g("opponents");
  if (!Array.isArray(ops)) errs.push("opponents must be a list");
  else {
    const G = L.opponent_groups;
    if (ops.length < G[0] || ops.length > G[1]) errs.push("opponents must have " + G[0] + " to " + G[1] + " groups");
    const dO = D.opponents[0], outs = [];
    let total = 0;
    ops.slice(0, G[1] + 1).forEach((o, i) => {
      const lab = "opponents[" + i + "].";
      if (!isObj(o)) { errs.push("opponents[" + i + "] must be an object"); return; }
      keysOk(o, ["type", "count", "weapon", "armor", "distance"], lab);
      if (!has(o, "type")) errs.push(lab + "type is required");
      const cnt = needInt(pick(o, "count", dO.count), L.opponent_count, lab + "count");
      total += cnt === null ? 0 : cnt;
      outs.push({ type: needEnum(o.type, "opponent_type", lab + "type"), count: cnt, weapon: needEnum(pick(o, "weapon", "none"), "weapon", lab + "weapon"),
        armor: needEnum(pick(o, "armor", "none"), "armor", lab + "armor"), distance: needInt(pick(o, "distance", dO.distance), L.opponent_distance, lab + "distance") });
    });
    if (total > L.opponents_total_max) errs.push("opponents total " + total + " is more than the limit of " + L.opponents_total_max);
    out.opponents = outs;
  }
  const gl = g("goal");
  if (!isObj(gl)) errs.push("goal must be an object");
  else {
    keysOk(gl, ["type", "distance"], "goal.");
    out.goal = { type: needEnum(pick(gl, "type", D.goal.type), "goal", "goal.type"), distance: needInt(pick(gl, "distance", D.goal.distance), L.goal_distance, "goal.distance") };
  }
  out.seconds = needInt(g("seconds"), L.seconds, "seconds");
  out.episodes = needInt(g("episodes"), L.episodes, "episodes");
  const df = g("difficulty");
  if (typeof df !== "number" || !Number.isFinite(df)) errs.push("difficulty must be a number");
  else if (df < L.difficulty[0] || df > L.difficulty[1]) errs.push("difficulty must be between " + L.difficulty[0] + " and " + L.difficulty[1]);
  out.difficulty = df;
  out.seed = needInt(g("seed"), L.seed, "seed");
  return errs.length ? { spec: null, errors: errs } : { spec: out, errors: [] };
}
"""

WORKER_TEMPLATE = r"""// Generated by tools/publish_site.py. Serves data.json, gameplay clips and the Simulation Lab from Workers KV.
const SPEC = __SPEC__;
const LIMITS = __LIMITS__;
const SALT = "vpt-arena-sim-v1";
const SITE_HOSTS = ["vpt-arena.vercel.app", "vpt-arena.pages.dev"];
const DATA_KEY = "__DATA_KEY__";
__VALIDATE__
const JSON_H = { "content-type": "application/json; charset=utf-8", "x-content-type-options": "nosniff" };
const reply = (obj, status = 200, extra = {}) => new Response(JSON.stringify(obj), { status, headers: { ...JSON_H, "cache-control": "no-store", ...extra } });
const fail = (status, message, extra = {}) => reply({ error: message, ...extra }, status);
const ID_RE = /^[0-9a-z]{10}$/;
const UNFINISHED = ["queued", "dispatched", "running"];
const isUnfinished = (status, created, now) => UNFINISHED.includes(status || "queued") && now - created < LIMITS.stale_s * 1000;

async function readJson(env, key) {
  const t = await env.DATA.get(key);
  if (t === null) return null;
  try { return JSON.parse(t); } catch (e) { return null; }
}
async function ipHash(request) {
  // behind the Vercel proxy cf-connecting-ip is the proxy, so prefer the first x-forwarded-for entry
  const ip = (request.headers.get("x-forwarded-for") || "").split(",")[0].trim() || request.headers.get("cf-connecting-ip") || "unknown";
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ip + SALT));
  return Array.from(new Uint8Array(d)).map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}
function newId() {
  const b = new Uint8Array(10); crypto.getRandomValues(b);
  return Array.from(b).map(x => (x % 36).toString(36)).join("");
}

async function serveVideo(request, env, key) {
  const buf = await env.DATA.get(key, { type: "arrayBuffer", cacheTtl: 60 });
  if (!buf) return new Response("not found", { status: 404, headers: { "cache-control": "no-store", "content-type": "text/plain; charset=utf-8" } });
  const len = buf.byteLength, head = request.method === "HEAD";
  const h = { "content-type": "video/mp4", "accept-ranges": "bytes", "cache-control": "public, max-age=86400", "x-content-type-options": "nosniff" };
  const part = { "cache-control": "no-store" };   // a CDN in front must not keep a partial response as the file
  const rh = request.headers.get("range");
  const m = rh ? /^bytes=(\d*)-(\d*)$/.exec(rh.trim()) : null;     // one range only; anything else gets the whole file
  if (m && (m[1] !== "" || m[2] !== "")) {
    let s, e;
    if (m[1] === "") { const n = Number(m[2]); s = Math.max(0, len - n); e = len - 1; if (n === 0) s = len; }
    else { s = Number(m[1]); e = m[2] === "" ? len - 1 : Math.min(Number(m[2]), len - 1); }
    if (s >= len || s > e) return new Response(null, { status: 416, headers: { ...h, ...part, "content-range": "bytes */" + len } });
    return new Response(head ? null : buf.slice(s, e + 1), { status: 206, headers: { ...h, ...part, "content-range": "bytes " + s + "-" + e + "/" + len, "content-length": String(e - s + 1) } });
  }
  return new Response(head ? null : buf, { status: 200, headers: { ...h, "content-length": String(len) } });
}

async function modelList(env) {
  const m = await readJson(env, "models");
  return Array.isArray(m) ? m.filter(x => typeof x === "string") : [];
}

async function submit(request, env) {
  const origin = request.headers.get("origin");
  if (origin && !SITE_HOSTS.includes(new URL(origin).host) && new URL(origin).host !== new URL(request.url).host) return fail(403, "requests must come from this site");
  const text = await request.text();
  if (text.length > LIMITS.body_max) return fail(413, "the request is too large");
  let body;
  try { body = JSON.parse(text); } catch (e) { return fail(400, "the request body is not valid JSON"); }
  const v = validateSpec(body, await modelList(env));
  if (!v.spec) return fail(400, v.errors[0], { errors: v.errors });
  const spec = v.spec;
  const now = Date.now(), iph = await ipHash(request);
  let idx = await readJson(env, "simindex");
  if (!Array.isArray(idx)) idx = [];
  const mine = idx.filter(e => e.iph === iph && now - e.created < 3600e3);
  if (mine.length >= LIMITS.per_ip_hour) {
    const wait = Math.max(1, Math.ceil((mine[mine.length - 1].created + 3600e3 - now) / 60e3));
    return fail(429, "You can start " + LIMITS.per_ip_hour + " simulations an hour. Try again in about " + wait + " minute(s).", { retry_after_min: wait });
  }
  if (idx.filter(e => now - e.created < 86400e3).length >= LIMITS.per_day)
    return fail(429, "The lab has reached its limit of " + LIMITS.per_day + " simulations for today. Try again tomorrow.");
  const newest = idx.slice(0, LIMITS.unfinished);
  const stats = await Promise.all(newest.map(e => readJson(env, "simstat:" + e.id)));
  const open = newest.filter((e, i) => isUnfinished(stats[i] && stats[i].status, e.created, now)).length;
  if (open >= LIMITS.unfinished)
    return fail(429, "The queue is full: " + LIMITS.unfinished + " simulations are still waiting or running. Try again in a few minutes.");
  const id = newId();
  await env.DATA.put("simreq:" + id, JSON.stringify({ id, spec, created: now, status: "queued" }));
  idx.unshift({ id, created: now, iph, name: spec.name, model: spec.model, base_mode: spec.base_mode });
  await env.DATA.put("simindex", JSON.stringify(idx.slice(0, LIMITS.index_max)));
  return reply({ id, status: "queued" });
}

function merge(req, st) {
  const out = { id: req.id, spec: req.spec, created: req.created, status: (st && st.status) || "queued", updated: (st && st.updated) || null };
  if (st) for (const k of ["message", "run_url", "result"]) if (st[k] !== undefined) out[k] = st[k];
  return out;
}
function summarize(res) {
  if (!res || !Array.isArray(res.episodes)) return null;
  const eps = res.episodes, n = eps.length;
  const num = x => typeof x === "number" && Number.isFinite(x) ? x : 0;
  return { episodes: n, wins: eps.filter(e => e && e.won).length, deaths: eps.filter(e => e && e.died).length,
    mean_return: n ? eps.reduce((a, e) => a + num(e && e.return), 0) / n : null, clips: eps.filter(e => e && e.clip).length };
}

const LIVE = { local: { url: null, at: 0 }, cloud: { url: null, at: 0 } };
async function liveBase(env, which) {
  const c = LIVE[which];
  if (Date.now() - c.at > 30000) {
    try { const v = JSON.parse((await env.DATA.get(which === "local" ? "livetunnel" : "livetunnel_cloud")) || "{}"); c.url = v.url || null; }
    catch (e) { c.url = null; }
    c.at = Date.now();
  }
  return c.url;
}
async function liveFetch(env, which, file) {
  const base = await liveBase(env, which);
  if (!base || !/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(base)) return null;
  const bust = file.endsWith(".ts") ? "" : "?t=" + Date.now();
  try { return await fetch(base + "/" + file + bust, { signal: AbortSignal.timeout(6000), cf: { cacheTtl: 0 } }); }
  catch (e) { return null; }
}
async function liveStatus(env, which) {
  const r = await liveFetch(env, which, "status.json");
  if (!r || !r.ok) return null;
  try { const st = await r.json(); return st && st.state !== "offline" && typeof st.updated === "number" ? st : null; }
  catch (e) { return null; }
}
async function liveHls(env, rate, file, ext) {
  // HLS comes from the cloud stream (the Mac session serves stills only)
  const r = await liveFetch(env, "cloud", "hls/" + rate + "/" + file);
  const h = { "access-control-allow-origin": "*", "cache-control": ext === "m3u8" ? "no-store" : "public, max-age=60",
              "content-type": ext === "m3u8" ? "application/vnd.apple.mpegurl" : "video/mp2t" };
  if (!r || !r.ok) return new Response("", { status: 404, headers: h });
  return new Response(r.body, { headers: h });
}
async function live(env, path, url) {
  const nc = { "cache-control": "no-store", "access-control-allow-origin": "*" };
  const now = Date.now() / 1000;
  // a session on the private machine wins; otherwise the always-on cloud stream
  let src = null, st = await liveStatus(env, "local");
  if (st && now - st.updated <= 10) src = "local";
  else { st = await liveStatus(env, "cloud"); if (st) src = "cloud"; }
  if (path === "/live/frame.jpg") {
    const r = src ? await liveFetch(env, src, "frame.jpg") : null;
    if (!r || !r.ok) return new Response("", { status: 404, headers: nc });
    return new Response(r.body, { headers: { ...nc, "content-type": "image/jpeg" } });
  }
  if (!st) return new Response(JSON.stringify({ online: false, age: null, status: null, frame: false, now, source: null }),
    { headers: { ...nc, "content-type": "application/json" } });
  const age = now - st.updated;
  return new Response(JSON.stringify({ online: age <= 10, age, status: st, frame: true, now, source: src }),
    { headers: { ...nc, "content-type": "application/json" } });
}

async function handle(request, env, url) {
  const path = url.pathname, method = request.method;
  if (path === "/live/status.json" || path === "/live/frame.jpg") return live(env, path, url);
  let hm = /^\/live\/hls\/(30|60)\/([a-z0-9_]{1,40}\.(m3u8|ts))$/.exec(path);
  if (hm) return liveHls(env, hm[1], hm[2], hm[3]);
  if (path === "/api/sim") {
    if (method !== "POST") return fail(405, "use POST", { allow: "POST" });
    return submit(request, env);
  }
  let m = /^\/api\/sim\/([^/]+)$/.exec(path);
  if (m) {
    if (method !== "GET" && method !== "HEAD") return fail(405, "use GET");
    if (!ID_RE.test(m[1])) return fail(404, "no such simulation");
    const [req, st] = await Promise.all([readJson(env, "simreq:" + m[1]), readJson(env, "simstat:" + m[1])]);
    if (!req) return fail(404, "no such simulation");
    return reply(merge(req, st));
  }
  if (path === "/api/sims") {
    if (method !== "GET" && method !== "HEAD") return fail(405, "use GET");
    let idx = await readJson(env, "simindex");
    if (!Array.isArray(idx)) idx = [];
    const list = idx.slice(0, LIMITS.list_n);
    const stats = await Promise.all(list.map(e => readJson(env, "simstat:" + e.id)));
    const sims = list.map((e, i) => { const st = stats[i], sm = summarize(st && st.result);
      return { id: e.id, created: e.created, name: e.name, model: e.model, base_mode: e.base_mode, status: (st && st.status) || "queued",
        message: st && st.message ? st.message : undefined, summary: sm, clips: sm ? sm.clips : 0 }; });
    return reply({ sims, total: idx.length, now: Date.now() });
  }
  m = /^\/sims\/([0-9a-z]{10})\/([0-9]{1,2})\.mp4$/.exec(path);
  if (m) return serveVideo(request, env, "simclip:" + m[1] + ":" + Number(m[2]));
  m = /^\/sims\/([0-9a-z]{10})\/([0-9]{1,2})_60\.mp4$/.exec(path);
  if (m) return serveVideo(request, env, "simclip60:" + m[1] + ":" + Number(m[2]));
  m = /^\/clips(60)?\/([A-Za-z0-9][A-Za-z0-9._-]{0,63})\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\.mp4$/.exec(path);
  if (m) return serveVideo(request, env, (m[1] ? "clip60:" : "clip:") + m[2] + ":" + m[3]);
  const TR = { "/trailer.mp4": "trailer:main", "/trailer-vertical.mp4": "trailer:vertical", "/trailer-60.mp4": "trailer:main60" };
  if (TR[path]) return serveVideo(request, env, TR[path]);
  return null;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/data.json") {
      const body = await env.DATA.get(DATA_KEY, { cacheTtl: 60 });
      const h = { "content-type": "application/json; charset=utf-8", "x-content-type-options": "nosniff", "access-control-allow-origin": "*" };
      if (body === null) return new Response('{"error":"no data published yet"}', { status: 404, headers: { ...h, "cache-control": "no-store" } });
      return new Response(body, { headers: { ...h, "cache-control": "public, max-age=60" } });
    }
    try {
      const r = await handle(request, env, url);
      if (r) return r;
    } catch (e) {
      return fail(500, "something went wrong on the server");
    }
    return env.ASSETS.fetch(request);
  },
};
"""


def worker_js(spec):
    """The generated _worker.js with the sim spec, limits and validator embedded."""
    limits = {"per_ip_hour": SIM_LIMITS["per_ip_hour"], "per_day": SIM_LIMITS["per_day"], "unfinished": SIM_LIMITS["unfinished"],
              "index_max": SIM_LIMITS["index_max"], "list_n": SIM_LIMITS["list_n"], "stale_s": SIM_STALE_S, "body_max": 8192}
    return (WORKER_TEMPLATE.replace("__SPEC__", json.dumps(spec, separators=(",", ":")))
            .replace("__LIMITS__", json.dumps(limits)).replace("__DATA_KEY__", KV_KEY)
            .replace("__VALIDATE__", VALIDATE_JS))


ROUTES_JSON = json.dumps({"version": 1, "include": ["/data.json", "/api/*", "/clips/*", "/clips60/*", "/sims/*", "/live/*", "/trailer*"], "exclude": []})


# --------------------------------------------------------------------------- snapshot

class PublicArena(srv.Arena):
    """Arena with the live view switched off: its status can name a server and frames show players."""

    def api_live(self):
        return {"online": False, "age": None, "status": None, "frame": False, "now": time.time()}


BAD_ARG_KEY = re.compile(r"server|host|user|player|pass|rcon|token|secret|email|addr|port|log|cookie|key", re.I)


def _safe_arg(v):
    if isinstance(v, str):
        if v.startswith(("/", "~")) or "@" in v or "\\" in v or re.search(r"\d+\.\d+\.\d+\.\d+", v):
            return None
        return v
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        out = [_safe_arg(x) for x in v]
        return None if any(x is None and y is not None for x, y in zip(out, v)) else out
    return None


def scrub_args(args):
    out = {}
    for k, v in (args or {}).items():
        if BAD_ARG_KEY.search(str(k)):
            continue
        sv = _safe_arg(v)
        if sv is not None or v is None:
            out[k] = sv
    return out


def thin(points, n=PUBLIC_POINTS):
    return srv.downsample(points, n)


def public_run(detail):
    detail = dict(detail)
    detail["args"] = scrub_args(detail.get("args"))
    detail["charts"] = [{"field": c["field"], "points": thin(c["points"])} for c in detail.get("charts", [])]
    detail["mode_curves"] = {k: thin(v) for k, v in (detail.get("mode_curves") or {}).items()}
    return detail


def anonymize_league(lg):
    names = {}
    n = 0
    for p in lg["players"]:
        if p["kind"] in ("human", "other"):
            n += 1
            names[p["name"]] = f"Human player {n}"
    known = {p["name"] for p in lg["players"]}

    def nm(x):
        if x is None or x == "":
            return x
        if x in names:
            return names[x]
        if x in known or x in ("a", "b", "draw"):
            return x
        names[x] = f"Player {len(names) + 1}"
        return names[x]

    for p in lg["players"]:
        p["name"] = nm(p["name"])
    for m in lg["matches"]:
        for k in ("a", "b", "winner"):
            m[k] = nm(m[k])
    lg["_map"] = dict(names)
    return lg


FRAME_MAX_BYTES = 60_000
DATAURL_RE = re.compile(r"data:image/jpeg;base64,[A-Za-z0-9+/=]+")


def build_frames(root, workers):
    """Latest simulator frames (frame0/frame1.jpg in each worker's run dir) of the newest round, as data: URLs."""
    newest = {}
    for w in workers:
        if w["round"] is not None:
            t = w.get("track", "vpt")
            newest[t] = max(newest.get(t, -1), w["round"])
    out = []
    for w in workers:
        if w["round"] is None or w["round"] != newest.get(w.get("track", "vpt")):
            continue
        for slot in (0, 1):
            f = Path(root) / "runs" / w["job"] / f"frame{slot}.jpg"
            try:
                data = f.read_bytes()
                mt = f.stat().st_mtime
            except OSError:
                continue
            if len(data) > FRAME_MAX_BYTES or data[:2] != b"\xff\xd8":
                continue
            mode = w["modes"][slot] if slot < len(w["modes"]) else None
            pm = w["per_mode"].get(mode) or {}
            out.append({"job": w["job"], "track": w.get("track", "vpt"), "round": w["round"], "state": w["state"], "mode": mode, "slot": slot, "updated": mt,
                        "return": pm.get("return"), "win_rate": pm.get("win_rate"), "episodes": pm.get("episodes"),
                        "img": "data:image/jpeg;base64," + base64.b64encode(data).decode()})
    return {"frames": out}


def _cap_workers(ws, per_track=48):
    out = []
    for trk in ("vpt", "scratch"):
        out += [w for w in ws if w.get("track", "vpt") == trk][:per_track]
    return out


def build_snapshot(root):
    a = PublicArena(root)
    runs = a.api_runs()["runs"][:MAX_RUNS]
    data = a.api_data()
    for it in data["recent"]:
        it.pop("path", None)
    overview = a.api_overview()
    overview["live"] = {"online": False, "state": None, "age": None}
    league = anonymize_league(a.api_league())
    names = league.pop("_map")
    modes = a.api_modes()
    for holder in [overview] + modes["modes"]:
        be = holder.get("best_elo")
        if be and be["name"] in names:
            be["name"] = names[be["name"]]
    return {
        "generated": time.time(),
        "overview": overview,
        "modes": modes,
        "runs": {"runs": runs},
        "run": {r["name"]: public_run(a.api_run(r["name"])) for r in runs if a.api_run(r["name"])},
        "data": data,
        "league": league,
        "cloud": a.api_cloud(),
        "rounds": a.api_rounds(),
        "workers": {"workers": _cap_workers(a.api_workers()["workers"])},
        "frames": build_frames(root, a.api_workers()["workers"]),
        "live": {"online": False, "age": None, "status": None, "frame": False, "now": time.time()},
    }


def snapshot_hash(snap):
    s = {k: v for k, v in snap.items() if k not in ("generated", "live")}
    # drop the volatile ages that Arena computes against the clock
    s["overview"] = {k: v for k, v in s["overview"].items() if k != "live"}
    return hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()


# --------------------------------------------------------------------------- dist

def check_text(label, text):
    bad = []
    for rx, what in FORBIDDEN:
        m = rx.search(text)
        if m:
            ctx = text[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")
            bad.append(f"{label}: {what}: ...{ctx}...")
    return bad


def check_dist(dist, payload):
    bad = []
    for p in sorted(Path(dist).rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_EXT:
            bad += check_text(str(p.relative_to(dist)), p.read_text("utf-8", errors="replace"))
    bad += check_text("data.json", DATAURL_RE.sub("data:image/jpeg;base64,", payload))   # base64 can spell a scrubbed word by chance
    return bad


def build_dist(dist, spec=None):
    dist = Path(dist)
    spec = spec or load_sim_spec()
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for p in STATIC.iterdir():
        if p.is_file():
            shutil.copy2(p, dist / p.name)
    idx = (dist / "index.html").read_text("utf-8")
    marker = '<script src="/app.js"></script>'
    if marker not in idx:
        raise SystemExit("index.html has no app.js script tag to mark static mode")
    sim = {"spec": spec, "limits": {k: SIM_LIMITS[k] for k in ("per_ip_hour", "per_day", "unfinished")}}
    inject = '<script>window.VPT_STATIC=true;window.VPT_EARLY=fetch("/data.json").catch(function(){return null});window.VPT_SIM=' + json.dumps(sim, separators=(",", ":")) + '</script>\n'
    idx = idx.replace(marker, inject + marker)
    (dist / "index.html").write_text(idx, "utf-8")
    (dist / "_worker.js").write_text(worker_js(spec), "utf-8")
    (dist / "_routes.json").write_text(ROUTES_JSON, "utf-8")


def asset_files(dist):
    """Files that go in the Pages manifest (everything except the worker and routes)."""
    return {"/" + p.relative_to(dist).as_posix(): p for p in sorted(Path(dist).rglob("*"))
            if p.is_file() and p.name not in ("_worker.js", "_routes.json", ".DS_Store")}


def frontend_hash(dist):
    h = hashlib.sha256()
    for p in sorted(Path(dist).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(dist).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


# --------------------------------------------------------------------------- Cloudflare

class CF:
    def __init__(self):
        try:
            self.acct = os.environ["CLOUDFLARE_ACCOUNT_ID"]
            self._h = {"X-Auth-Email": os.environ["CLOUDFLARE_AUTH_EMAIL"],
                       "X-Auth-Key": os.environ["CLOUDFLARE_GLOBAL_API_KEY"]}
        except KeyError as e:
            raise SystemExit(f"missing environment variable {e.args[0]}")

    def call(self, method, path, body=None, raw=None, ctype=None, headers=None, url=None):
        h = dict(headers if headers is not None else self._h)
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        elif ctype:
            h["Content-Type"] = ctype
        req = urllib.request.Request(url or (API + path), data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode()
        except urllib.error.HTTPError as e:
            txt = e.read().decode(errors="replace")
            try:
                errs = json.loads(txt).get("errors")
            except ValueError:
                errs = txt[:200]
            raise RuntimeError(f"{method} {path.split('?')[0]} -> HTTP {e.code}: {errs}")
        out = json.loads(txt) if txt else {}
        if isinstance(out, dict) and out.get("success") is False:
            raise RuntimeError(f"{method} {path} failed: {out.get('errors')}")
        return out.get("result") if isinstance(out, dict) and "result" in out else out

    def jwt_call(self, method, path, jwt, body):
        return self.call(method, path, body=body, headers={"Authorization": "Bearer " + jwt})

    # project + KV
    def ensure_project(self, name):
        base = f"/accounts/{self.acct}/pages/projects"
        for cand in [name, name + "-site", name + "-dash"]:
            try:
                return self.call("GET", f"{base}/{cand}")
            except RuntimeError as e:
                if "HTTP 404" not in str(e) and "8000007" not in str(e):
                    raise
            try:
                return self.call("POST", base, {"name": cand, "production_branch": "main"})
            except RuntimeError as e:
                print(f"could not create project {cand}: {e}")
        raise SystemExit("no usable Pages project name")

    def ensure_kv(self):
        base = f"/accounts/{self.acct}/storage/kv/namespaces"
        for ns in self.call("GET", base + "?per_page=100") or []:
            if ns.get("title") == KV_TITLE:
                return ns["id"]
        return self.call("POST", base, {"title": KV_TITLE})["id"]

    def bind_kv(self, project, ns_id):
        cfg = {"kv_namespaces": {"DATA": {"namespace_id": ns_id}}, "compatibility_date": COMPAT_DATE}
        self.call("PATCH", f"/accounts/{self.acct}/pages/projects/{project}",
                  {"deployment_configs": {"production": cfg, "preview": cfg}})

    def kv_put(self, ns_id, key, text):
        self.kv_put_bytes(ns_id, key, text.encode(), "application/json")

    def kv_put_bytes(self, ns_id, key, data, ctype="application/octet-stream"):
        self.call("PUT", f"/accounts/{self.acct}/storage/kv/namespaces/{ns_id}/values/{urllib.parse.quote(key, safe='')}",
                  raw=data, ctype=ctype)

    # deployment (Pages direct upload)
    def deploy(self, project, dist, label):
        files = asset_files(dist)
        info = {}
        for path, p in files.items():
            b = base64.b64encode(p.read_bytes()).decode()
            ext = p.suffix.lstrip(".")
            key = hashlib.sha256((b + ext).encode()).hexdigest()[:32]
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            info[path] = (key, b, ctype)
        tok = self.call("GET", f"/accounts/{self.acct}/pages/projects/{project}/upload-token")["jwt"]
        hashes = [v[0] for v in info.values()]
        missing = self.jwt_call("POST", "/pages/assets/check-missing", tok, {"hashes": hashes}) or []
        todo = [{"key": k, "value": b, "metadata": {"contentType": c}, "base64": True}
                for k, b, c in info.values() if k in set(missing)]
        if todo:
            self.jwt_call("POST", "/pages/assets/upload", tok, todo)
        self.jwt_call("POST", "/pages/assets/upsert-hashes", tok, {"hashes": hashes})
        manifest = {path: v[0] for path, v in info.items()}
        boundary = "----vpt" + uuid.uuid4().hex
        parts = []

        def field(name, value, filename=None, ctype=None):
            disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
            head = f"--{boundary}\r\nContent-Disposition: {disp}\r\n" + (f"Content-Type: {ctype}\r\n" if ctype else "") + "\r\n"
            parts.append(head.encode() + value.encode() + b"\r\n")

        field("manifest", json.dumps(manifest))
        field("branch", "main")
        field("commit_message", label)
        field("_worker.js", (Path(dist) / "_worker.js").read_text(), "_worker.js", "application/javascript+module")
        field("_routes.json", ROUTES_JSON, "_routes.json", "application/json")
        raw = b"".join(parts) + f"--{boundary}--\r\n".encode()
        return self.call("POST", f"/accounts/{self.acct}/pages/projects/{project}/deployments", raw=raw,
                         ctype=f"multipart/form-data; boundary={boundary}")


# --------------------------------------------------------------------------- clips and models

CLIP_MAX_BYTES = 4_000_000
CLIPS_PER_RUN = 30         # new clip copies per publish (KV free tier: 1000 writes a day)
KV_DAILY_BUDGET = 700      # the publisher stops adding clips past this many writes in a day; sims need the rest


def clip_path(tag, mode):
    return f"/clips/{tag}/{mode}.mp4"


def clip_key(tag, mode, fps=30):
    return f"clip:{tag}:{mode}" if fps == 30 else f"clip60:{tag}:{mode}"


def raw_clips(snap, key="clips"):
    """{(tag, mode): github_url} from the snapshot before URLs are rewritten (key "clips60" for the 60 fps files)."""
    out = {}
    for tag, mm in (snap.get("cloud", {}).get(key) or {}).items():
        for mode, url in mm.items():
            out[(tag, mode)] = url
    return out


def rewrite_clips(snap, uploaded=None, uploaded60=None):
    """Point every clip URL at /clips/<tag>/<mode>.mp4 (and /clips60/ for 60 fps). With `uploaded` (a set of
    (tag, mode)), drop clips not copied yet; a 60 fps URL is kept only when that file is in KV too."""
    ok = (lambda t, m: True) if uploaded is None else (lambda t, m: (t, m) in uploaded)
    ok60 = (lambda t, m: True) if uploaded60 is None else (lambda t, m: (t, m) in uploaded60)
    cl = snap.get("cloud") or {}
    has60 = {(t, m) for t, mm in (cl.get("clips60") or {}).items() for m in mm}
    new, new60 = {}, {}
    for tag, mm in (cl.get("clips") or {}).items():
        d = {m: clip_path(tag, m) for m in mm if ok(tag, m)}
        if d:
            new[tag] = d
    for tag, mm in (cl.get("clips60") or {}).items():
        d = {m: f"/clips60/{tag}/{m}.mp4" for m in mm if ok(tag, m) and ok60(tag, m)}
        if d:
            new60[tag] = d
    if "clips" in cl:
        cl["clips"] = new
    if "clips60" in cl:
        cl["clips60"] = new60

    def fix(c):
        if isinstance(c, dict) and "tag" in c and "mode" in c and "url" in c:
            if not ok(c["tag"], c["mode"]):
                return None
            out = {**c, "url": clip_path(c["tag"], c["mode"])}
            out.pop("url60", None)
            if (c["tag"], c["mode"]) in has60 and ok60(c["tag"], c["mode"]):
                out["url60"] = f"/clips60/{c['tag']}/{c['mode']}.mp4"
            return out
        return c
    ov = snap.get("overview") or {}
    if isinstance(ov.get("clips"), list):
        ov["clips"] = [c for c in (fix(c) for c in ov["clips"]) if c]
    if isinstance(ov.get("cloud"), dict) and "clips" in ov["cloud"]:
        ov["cloud"]["clips"] = new
        ov["cloud"]["clips60"] = new60
    for m in (snap.get("modes") or {}).get("modes", []):
        c = m.get("clip")
        if c and "url" in c:
            m["clip"] = fix({**c, "mode": m["key"]})
            if m["clip"]:
                m["clip"].pop("mode", None)
    return snap


def model_tags(snap):
    tags = list(snap.get("cloud", {}).get("releases") or []) + [r["tag"] for r in snap.get("rounds", {}).get("rounds", [])]
    seen, out = set(), []
    for t in tags:
        if t.startswith("scratch-"):
            continue          # the Simulation Lab can only run the 1x round-N models for now
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def download_clip(url):
    """Fetch a release asset (follows GitHub's redirect). Returns bytes, or None when it isn't a small MP4."""
    req = urllib.request.Request(url, headers={"User-Agent": "vpt-arena-publisher"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(CLIP_MAX_BYTES + 1)
    except (urllib.error.URLError, OSError) as e:
        print(f"clip download failed: {e}")
        return None
    if len(data) > CLIP_MAX_BYTES or data[4:8] != b"ftyp":
        return None
    return data


def kv_budget_left(st):
    day = time.strftime("%Y-%m-%d", time.gmtime())
    w = st.setdefault("kv_writes", {})
    if w.get("day") != day:
        w.clear()
        w.update(day=day, n=0)
    return KV_DAILY_BUDGET - w["n"]


def count_write(st, n=1):
    kv_budget_left(st)
    st["kv_writes"]["n"] += n


def sync_clips(cf, st, wanted, state_path, fps=30):
    """Copy each wanted clip into KV once. Returns the set of (tag, mode) that are in KV."""
    sk = "clips" if fps == 30 else "clips60"
    done = st.setdefault(sk, {})
    have = {tuple(k.split(":", 1)) for k in done}
    todo = [(t, m, u) for (t, m), u in sorted(wanted.items()) if f"{t}:{m}" not in done]
    n = 0
    for t, m, u in todo:
        if n >= CLIPS_PER_RUN or kv_budget_left(st) <= 0:
            print(f"clips{fps}: {len(todo) - n} left for the next run")
            break
        data = download_clip(u)
        if data is None:
            continue
        cf.kv_put_bytes(st["kv_ns"], clip_key(t, m, fps), data)
        done[f"{t}:{m}"] = len(data)
        count_write(st)
        save_state(state_path, st)
        have.add((t, m))
        n += 1
    if n:
        print(f"copied {n} {fps} fps clip(s) to KV")
    return {k for k in have if k in wanted}


# --------------------------------------------------------------------------- main

def load_state(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return {}


def save_state(p, st):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(st, indent=1))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vpt-arena-publisher"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode(errors="replace")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Publish the VPT Arena public site")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--build-only", action="store_true", help="build dist/ and run the scrub check; no network")
    ap.add_argument("--force", action="store_true", help="redeploy and rewrite the data value")
    ap.add_argument("--reupload-clips", action="store_true", help="copy every clip to KV again (normally each is copied once)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    dist = root / "dist"
    state_path = root / "runs" / ".publish_state.json"

    spec = load_sim_spec()
    build_dist(dist, spec)
    raw = build_snapshot(root)
    wanted = raw_clips(raw)
    snap = rewrite_clips(copy.deepcopy(raw))          # every clip, for the scrub check and the local preview
    payload = json.dumps(srv._clean(snap), allow_nan=False, separators=(",", ":"))
    bad = check_dist(dist, payload)
    if bad:
        print("PUBLISH BLOCKED: scrubbed patterns found in the output:", file=sys.stderr)
        for b in bad[:20]:
            print("  " + b, file=sys.stderr)
        return 2
    (dist / "data.preview.json").write_text(payload)   # for local inspection only; removed before deploy
    print(f"built dist/ ({len(payload) // 1024} KiB data, scrub check passed)")
    if args.build_only:
        return 0
    (dist / "data.preview.json").unlink()

    st = load_state(state_path)
    cf = CF()
    proj = cf.ensure_project(args.project)
    pname = proj["name"]
    sub = proj.get("subdomain") or f"{pname}.pages.dev"
    if st.get("project") != pname or not st.get("kv_ns"):
        ns = cf.ensure_kv()
        cf.bind_kv(pname, ns)
        st.update(project=pname, kv_ns=ns, frontend=None)
        save_state(state_path, st)

    fh = frontend_hash(dist)
    if args.force or st.get("frontend") != fh:
        d = cf.deploy(pname, dist, "front end " + fh[:8])
        st["frontend"] = fh
        save_state(state_path, st)
        print("deployed front end", fh[:8], (d or {}).get("url", ""))
    else:
        print("front end unchanged, no deployment")

    tags = ["baseline", "latest"] + [t for t in model_tags(raw) if t not in ("baseline", "latest")]
    mh = hashlib.sha256(json.dumps(tags).encode()).hexdigest()
    if args.force or st.get("models") != mh:
        cf.kv_put(st["kv_ns"], "models", json.dumps(tags))
        count_write(st)
        st["models"] = mh
        save_state(state_path, st)
        print("model list written to KV:", ", ".join(tags))

    if args.reupload_clips:
        st["clips"] = {}
        st["clips60"] = {}
    uploaded = sync_clips(cf, st, wanted, state_path)
    uploaded60 = sync_clips(cf, st, raw_clips(raw, "clips60"), state_path, 60)
    snap = rewrite_clips(copy.deepcopy(raw), uploaded, uploaded60)
    payload = json.dumps(srv._clean(snap), allow_nan=False, separators=(",", ":"))
    bad = check_text("data.json", DATAURL_RE.sub("data:image/jpeg;base64,", payload))
    if bad:
        print("PUBLISH BLOCKED: " + bad[0], file=sys.stderr)
        return 2

    sh = snapshot_hash(snap)
    age = time.time() - st.get("kv_time", 0)
    if args.force or st.get("data") != sh or age > KV_REFRESH_S:
        cf.kv_put(st["kv_ns"], KV_KEY, payload)
        count_write(st)
        st.update(data=sh, kv_time=time.time())
        save_state(state_path, st)
        print("data written to KV")
    else:
        print("data unchanged, KV not written")
    print("site: https://" + sub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
