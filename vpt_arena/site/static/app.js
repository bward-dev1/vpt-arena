"use strict";
/* VPT Arena dashboard. Hash routing, no dependencies. */
const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const PAGES = [["overview", "Overview"], ["modes", "Modes"], ["training", "Training"], ["data", "Data"],
  ["league", "League"], ["live", "Live"], ["docs", "Docs"]];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 3) => v == null || !isFinite(v) ? "-" : Math.abs(v) >= 1000 ? Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 }) : trimZ(Number(v).toPrecision(Math.max(d, 1)));
const fmtN = (v, d = 1) => v == null || !isFinite(v) ? "-" : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtH = h => h == null ? "-" : h >= 10 ? h.toFixed(1) : h >= 0.01 ? h.toFixed(2) : h === 0 ? "0" : Number(h.toPrecision(2)).toString();
const ago = ts => { if (!ts) return "-"; const s = Date.now() / 1000 - ts; if (s < 90) return Math.max(0, Math.round(s)) + " s ago"; if (s < 5400) return Math.round(s / 60) + " min ago"; if (s < 129600) return Math.round(s / 3600) + " h ago"; return new Date(ts * 1000).toLocaleDateString(); };
const SRC_NAMES = { human: "Human", idm: "IDM-labelled", contractor: "Contractor", other: "Other" };

/* Static mode (public site): window.VPT_STATIC is set in dist/index.html and all data
   comes from one snapshot at /data.json instead of /api/*. */
const STATIC = !!window.VPT_STATIC;
let snap = null, snapT = 0;
async function snapshot() {
  if (!snap || Date.now() - snapT > 30000) {
    const r = await fetch("/data.json", { cache: "no-store" });
    if (!r.ok) throw new Error("no data published yet");
    snap = await r.json(); snapT = Date.now();
  }
  return snap;
}
async function api(path) {
  if (STATIC) {
    const s = await snapshot(), name = path.replace(/^\/api\//, "");
    stamp(s.generated);
    if (name.startsWith("run/")) { const r = (s.run || {})[decodeURIComponent(name.slice(4))]; if (!r) throw new Error("no such run"); return r; }
    const v = s[name];
    if (v === undefined) throw new Error("no such data " + name);
    return v;
  }
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(path + " " + r.status);
  stamp(Date.now() / 1000);
  return r.json();
}
const when = ts => ts ? new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "-";
let stampTs = null;
function stamp(ts) {
  stampTs = ts;
  const f = document.getElementById("stamp");
  if (f) f.textContent = ts ? "Last updated " + when(ts) : "";
  paintPill();
}
function paintPill() {
  if (!STATIC) return;
  const p = $("#livepill"); if (!p) return;
  const fresh = stampTs && Date.now() / 1000 - stampTs < 900;
  p.className = "pill " + (fresh ? "on" : "off");
  $("span", p).textContent = stampTs ? "Updated " + ago(stampTs) : "no data yet";
}

let timers = [];
function every(ms, fn) { timers.push(setInterval(fn, ms)); }
function clearTimers() { timers.forEach(clearInterval); timers = []; }

/* ---------- charts ---------- */
const COLORS = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"];
function niceTicks(lo, hi, n = 4) {
  if (lo === hi) { const p = Math.abs(lo) || 1; lo -= p * .5; hi += p * .5; }
  const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
  const a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
  for (let v = a; v <= b + step / 1e6; v += step) t.push(+v.toPrecision(12));
  return t;
}
const trimZ = t => t.includes(".") ? t.replace(/0+$/, "").replace(/\.$/, "") : t;
const tickFmt = v => { const a = Math.abs(v); if (a >= 1e6) return trimZ((v / 1e6).toPrecision(3)) + "M"; if (a >= 1e4) return trimZ((v / 1e3).toPrecision(3)) + "k"; if (a !== 0 && a < 0.001) return v.toExponential(0); return String(+v.toPrecision(4)); };

function lineChart(points, color, opts = {}) {
  const W = 480, H = 200, m = { l: 46, r: 12, t: 10, b: 24 };
  if (!points.length) return `<div class="empty">no data</div>`;
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const xlo = Math.min(...xs), xhi = Math.max(...xs);
  const yt = niceTicks(Math.min(...ys), Math.max(...ys)), ylo = yt[0], yhi = yt[yt.length - 1];
  const sx = x => m.l + (xhi === xlo ? .5 : (x - xlo) / (xhi - xlo)) * (W - m.l - m.r);
  const sy = y => H - m.b - (yhi === ylo ? .5 : (y - ylo) / (yhi - ylo)) * (H - m.t - m.b);
  const xt = niceTicks(xlo, xhi, 4).filter(v => v >= xlo - 1e-9 && v <= xhi + 1e-9);
  let d = points.map((p, i) => (i ? "L" : "M") + sx(p[0]).toFixed(1) + " " + sy(p[1]).toFixed(1)).join("");
  const grid = yt.map(v => `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${m.l - 6}" y="${sy(v) + 4}" text-anchor="end">${tickFmt(v)}</text>`).join("");
  const xl = xt.map(v => `<text x="${sx(v)}" y="${H - 6}" text-anchor="middle">${tickFmt(v)}</text>`).join("");
  const dot = points.length <= 40 ? points.map(p => `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="2.5" fill="var(${color})"/>`).join("") : "";
  const id = "c" + Math.random().toString(36).slice(2, 8);
  return `<svg class="ch" id="${id}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "chart")}" data-pts='${JSON.stringify(points.map(p => [+p[0].toPrecision(8), +p[1].toPrecision(6)]))}' data-geo="${[m.l, W - m.r, m.t, H - m.b, xlo, xhi, ylo, yhi].join(",")}">
    ${grid}${xl}<path class="ln" d="${d}" style="stroke:var(${color})"/>${dot}
    <g class="hv" style="display:none"><line class="gl" y1="${m.t}" y2="${H - m.b}" style="stroke:var(--line2)"/><circle r="4" fill="var(${color})" stroke="var(--panel)" stroke-width="2"/><g class="tip"><rect rx="6" height="22" fill="var(--panel2)" stroke="var(--line2)"/><text y="15" x="8" style="fill:var(--text)"></text></g></g>
    <rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg>`;
}
function wireCharts(root) {
  root.querySelectorAll("svg.ch[data-pts]").forEach(svg => {
    const pts = JSON.parse(svg.dataset.pts), [l, r, t, b, xlo, xhi, ylo, yhi] = svg.dataset.geo.split(",").map(Number);
    const hv = $(".hv", svg), line = $("line", hv), c = $("circle", hv), tipg = $(".tip", hv), rect = $("rect", tipg), txt = $("text", tipg);
    const move = e => {
      const bb = svg.getBoundingClientRect(), vx = (e.clientX - bb.left) / bb.width * 480;
      const x = xlo + (vx - l) / (r - l) * (xhi - xlo);
      let best = pts[0]; for (const p of pts) if (Math.abs(p[0] - x) < Math.abs(best[0] - x)) best = p;
      const px = l + (xhi === xlo ? .5 : (best[0] - xlo) / (xhi - xlo)) * (r - l), py = b - (yhi === ylo ? .5 : (best[1] - ylo) / (yhi - ylo)) * (b - t);
      line.setAttribute("x1", px); line.setAttribute("x2", px); c.setAttribute("cx", px); c.setAttribute("cy", py);
      txt.textContent = `${tickFmt(best[0])}: ${+best[1].toPrecision(4)}`;
      const w = txt.textContent.length * 6.4 + 16; rect.setAttribute("width", w);
      const tx = Math.min(Math.max(px - w / 2, l), r - w); tipg.setAttribute("transform", `translate(${tx},${Math.max(py - 32, 0)})`);
      hv.style.display = "";
    };
    const hit = $(".hit", svg);
    hit.addEventListener("pointermove", move); hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => hv.style.display = "none");
  });
}
function barList(rows, max) {
  return rows.map(([k, v, label]) => `<div style="display:grid;grid-template-columns:minmax(80px,1fr) 2fr auto;gap:10px;align-items:center;margin:6px 0"><span style="overflow-wrap:anywhere">${esc(k)}</span><div class="bar"><i style="width:${Math.max(0, Math.min(100, v / max * 100))}%"></i></div><span class="mono">${esc(label)}</span></div>`).join("");
}

const DASH = ["", "", "", "", "", "", "6 3", "6 3", "6 3", "6 3", "6 3", "6 3", "2 3", "2 3", "2 3", "2 3", "2 3", "2 3"];
function multiChart(series, label) {
  const W = 480, H = 220, m = { l: 46, r: 12, t: 10, b: 24 };
  const names = Object.keys(series).filter(k => series[k].length);
  if (!names.length) return `<div class="empty">No data yet.</div>`;
  const all = names.flatMap(k => series[k]);
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const xlo = Math.min(...xs), xhi = Math.max(...xs);
  const yt = niceTicks(Math.min(...ys), Math.max(...ys)), ylo = yt[0], yhi = yt[yt.length - 1];
  const sx = x => m.l + (xhi === xlo ? .5 : (x - xlo) / (xhi - xlo)) * (W - m.l - m.r);
  const sy = y => H - m.b - (yhi === ylo ? .5 : (y - ylo) / (yhi - ylo)) * (H - m.t - m.b);
  const xt = niceTicks(xlo, xhi, 4).filter(v => v >= xlo - 1e-9 && v <= xhi + 1e-9);
  const grid = yt.map(v => `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${m.l - 6}" y="${sy(v) + 4}" text-anchor="end">${tickFmt(v)}</text>`).join("");
  const xl = xt.map(v => `<text x="${sx(v)}" y="${H - 6}" text-anchor="middle">${tickFmt(v)}</text>`).join("");
  const paths = names.map((k, i) => {
    const pts = series[k];
    const d = pts.map((p, j) => (j ? "L" : "M") + sx(p[0]).toFixed(1) + " " + sy(p[1]).toFixed(1)).join("");
    const dot = pts.length === 1 ? `<circle cx="${sx(pts[0][0])}" cy="${sy(pts[0][1])}" r="3" fill="var(${COLORS[i % 6]})"/>` : "";
    return `<path class="ln" d="${d}" style="stroke:var(${COLORS[i % 6]})" ${DASH[i % 18] ? `stroke-dasharray="${DASH[i % 18]}"` : ""}/>${dot}`;
  }).join("");
  const legend = names.map((k, i) => { const last = series[k][series[k].length - 1][1];
    return `<span class="lg"><i style="background:var(${COLORS[i % 6]})"></i>${esc(k)} <b>${fmt(last, 3)}</b></span>`; }).join("");
  return `<svg class="ch" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">${grid}${xl}${paths}</svg><div class="legend">${legend}</div>`;
}
const placeholderCard = (title, msg) => `<div class="card chart"><h3>${esc(title)}</h3><div class="empty">${esc(msg)}</div></div>`;

function cloudTable(c) {
  if (!c || !c.jobs || !c.jobs.length) return `<div class="empty">No cloud jobs reported yet. Jobs on Colab, Kaggle or other GPU hosts appear here when training starts.</div>`;
  const PF = { colab: "Colab", kaggle: "Kaggle", local: "Local" };
  return `<div class="tw"><table><thead><tr><th>Job</th><th>Platform</th><th>Hardware</th><th>State</th><th>Started</th><th>Updated</th><th>Progress</th><th>Run</th></tr></thead><tbody>${c.jobs.map(j =>
    `<tr><td>${esc(j.name)}</td><td>${PF[j.platform] || esc(j.platform)}</td><td>${esc(j.hardware || "-")}</td><td><span class="tag ${j.state}">${j.state}</span></td><td>${when(j.started)}</td><td>${ago(j.updated)}</td><td class="wrap">${esc(j.progress || "-")}</td><td>${j.run ? `<a href="#/training/${encodeURIComponent(j.run.split("/").pop())}">${esc(j.run.split("/").pop())}</a>` : "-"}</td></tr>`).join("")}</tbody></table></div>`;
}

/* ---------- pages ---------- */
const pages = {};

pages.overview = async () => {
  const o = await api("/api/overview");
  const best = o.best_elo ? `${Math.round(o.best_elo.elo)}` : "-";
  view.innerHTML = `
  <h1>VPT Arena</h1>
  <p class="lede">One network plays survival Minecraft and ${o.modes - 1} PvP and minigame modes. It takes game pixels in and puts keyboard and mouse out at 20 Hz, like a player. It is built on OpenAI's Video PreTraining (VPT) model. A learned game-mode embedding (mode, 1.8 or 1.9+ combat, team size) is added through VPT's <code>diff_obs_process</code> hook. It starts at zero, so before any training the model behaves as VPT does.</p>
  <div class="grid stats">
    <div class="card stat"><div class="k">Training data</div><div class="v">${fmtH(o.hours)} h</div><div class="s">${o.trajectories} trajectories</div></div>
    <div class="card stat"><div class="k">Latest BC eval NLL</div><div class="v">${o.latest_eval_nll == null ? "-" : fmt(o.latest_eval_nll, 4)}</div><div class="s">${o.bc_runs} BC run(s), ${o.rl_runs} RL run(s)</div></div>
    <div class="card stat"><div class="k">Best Elo</div><div class="v">${best}</div><div class="s">${o.best_elo ? esc(o.best_elo.name) : "no league yet"}</div></div>
    <div class="card stat"><div class="k">Live agent</div><div class="v">${o.live.online ? esc(o.live.state || "online") : "offline"}</div><div class="s">${o.live.age == null ? "no status file" : "updated " + Math.round(o.live.age) + " s ago"}</div></div>
  </div>
  <h2>Phases</h2>
  <div class="tw"><table><thead><tr><th>Phase</th><th>What</th><th>Live status</th><th>Tested</th><th>State</th></tr></thead><tbody>
  ${o.phases.map(p => `<tr><td>${p.phase}. ${esc(p.name)}</td><td class="wrap">${esc(p.what)}</td><td class="wrap">${esc(p.status)}</td><td class="wrap">${esc(p.tested)}</td><td><span class="tag ${p.state}">${p.state === "done" ? "has data" : p.state === "active" ? "running" : "empty"}</span></td></tr>`).join("")}
  </tbody></table></div>
  <p style="color:var(--faint);font-size:.85rem">Status comes from the files on disk (weights, data, runs, live), not from the README. The Tested column is a fixed note on how far each phase has been checked; see the Docs page.</p>
  <h2>Cloud</h2>
  ${cloudTable(o.cloud)}
  <p class="upd">${o.cloud && o.cloud.updated ? "Cloud status updated " + when(o.cloud.updated) : "No cloud status file yet."}</p>
  <h2>Data by source</h2>
  <div class="card">${barList(Object.entries(o.by_source).map(([k, v]) => [SRC_NAMES[k], v.hours, `${fmtH(v.hours)} h, ${v.trajectories} traj`]), Math.max(o.hours, 1e-9))}</div>`;
};

pages.modes = async () => {
  const d = await api("/api/modes");
  const maxH = Math.max(...d.modes.map(m => m.hours), 1e-9);
  view.innerHTML = `<h1>Modes</h1><p class="lede">${d.modes.length} game modes. The same network plays all of them; a learned embedding tells it which one it is in. Modern is 1.9+ combat with the attack cooldown. Legacy is 1.8 combat with spam clicking. Reward events are the server signals the RL phase turns into reward, with their weights.</p>
  <div class="toolbar"><input type="search" id="q" placeholder="Filter modes" aria-label="Filter modes"><button class="chip on" data-r="">All</button><button class="chip" data-r="modern">Modern</button><button class="chip" data-r="legacy">Legacy</button></div>
  <div class="grid cols" id="mgrid"></div>`;
  let rs = "", q = "";
  const draw = () => {
    const list = d.modes.filter(m => (!rs || m.ruleset === rs) && (!q || (m.name + m.key + m.summary).toLowerCase().includes(q)));
    $("#mgrid").innerHTML = list.map(m => `<article class="card mode"><h3>${esc(m.name)}<span class="mkey">${esc(m.key)}</span></h3>
      <div class="tags"><span class="tag ${m.ruleset}">${m.ruleset === "modern" ? "modern, 1.9+ cooldown" : "legacy, 1.8 combat"}</span><span class="tag">team size ${m.team_size}</span></div>
      <p>${esc(m.summary)}</p>
      <div class="ev">${Object.entries(m.events).map(([k, w]) => `<span class="${w < 0 ? "neg" : "pos"}">${esc(k)} <b>${w > 0 ? "+" : ""}${w}</b></span>`).join("")}</div>
      <div class="foot2"><span><b>${fmtH(m.hours)}</b> h data (${m.trajectories})</span><span>best Elo <b>${m.best_elo ? Math.round(m.best_elo.elo) : "-"}</b>${m.best_elo ? " " + esc(m.best_elo.name) : ""}</span></div>
    </article>`).join("") || `<div class="empty">no modes match</div>`;
  };
  draw();
  $("#q").oninput = e => { q = e.target.value.toLowerCase().trim(); draw(); };
  document.querySelectorAll(".chip[data-r]").forEach(b => b.onclick = () => { rs = b.dataset.r; document.querySelectorAll(".chip[data-r]").forEach(x => x.classList.toggle("on", x === b)); draw(); });
};

let selRun = null;
pages.training = async () => {
  view.innerHTML = `<h1>Training</h1><p class="lede">Runs under <code>runs/</code>. ${STATIC ? "This public page refreshes about once a minute from a snapshot that is rebuilt every 5 minutes." : "Charts refresh every 10 seconds."}</p><div id="runs" class="runs"></div><div id="detail"></div>`;
  const load = async () => {
    const { runs } = await api("/api/runs");
    if (!runs.length) { $("#runs").innerHTML = `<div class="empty" style="grid-column:1/-1">No training runs yet. Behavior cloning and RL runs appear here as soon as they write a log.</div>`;
      $("#detail").innerHTML = `<div class="grid cols-2">${placeholderCard("Behavior cloning loss", "No runs yet.")}${placeholderCard("Evaluation loss", "No runs yet.")}${placeholderCard("RL return by mode", "No RL runs yet. One line per game mode will be drawn on one chart.")}${placeholderCard("Win rate", "No RL runs yet.")}</div>`; return; }
    const want = decodeURIComponent(location.hash.split("/")[2] || "");
    if (want && runs.some(r => r.name === want)) selRun = want;
    if (!selRun || !runs.some(r => r.name === selRun)) selRun = runs[0].name;
    $("#runs").innerHTML = runs.map(r => `<button class="run ${r.name === selRun ? "on" : ""}" data-n="${esc(r.name)}"><div class="nm">${esc(r.name)}</div><div class="mt"><span class="tag">${r.kind.toUpperCase()}</span> ${esc(r.arch || "")} &middot; ${r.points} pts &middot; ${ago(r.updated)}</div></button>`).join("");
    document.querySelectorAll(".run").forEach(b => b.onclick = () => { selRun = b.dataset.n; load(); });
    const sel = runs.find(r => r.name === selRun);
    const d = await api("/api/run/" + encodeURIComponent(selRun));
    const lastKv = Object.entries(sel.last).slice(0, 8).map(([k, v]) => `<span class="tag">${esc(k)} ${fmt(v, 4)}</span>`).join(" ");
    $("#detail").innerHTML = `<div class="card" style="margin-bottom:14px"><h3>${esc(d.summary.name)} <span class="tag">${d.summary.kind.toUpperCase()}</span></h3>
      <div style="color:var(--muted);font-size:.9rem">started ${d.started ? new Date(d.started * 1000).toLocaleString() : "-"} &middot; arch ${esc(d.arch || "-")} &middot; x axis: ${d.x}</div><div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">${lastKv}</div></div>
      ${Object.keys(d.mode_curves || {}).length ? `<div class="card chart" style="margin-bottom:14px"><h3>Return by mode<small>mean return per game mode</small></h3>${multiChart(d.mode_curves, "Mean return by game mode over training")}</div>` : (d.summary.kind === "rl" ? `<div class="card chart" style="margin-bottom:14px"><h3>Return by mode</h3><div class="empty">This RL log has no per-mode returns yet.</div></div>` : "")}
      ${d.charts.length ? `<div class="grid cols-2">${d.charts.map((c, i) => `<div class="card chart"><h3>${esc(c.field)}<small>${fmt(c.points[c.points.length - 1][1], 4)}</small></h3>${lineChart(c.points, COLORS[i % COLORS.length], { label: c.field })}</div>`).join("")}</div>` : `<div class="empty">The log has no numeric rows yet.</div>`}
      ${Object.keys(d.by_mode).length ? `<h2>Latest return by mode</h2><div class="card">${(() => { const e = Object.entries(d.by_mode).sort((a, b) => b[1] - a[1]); const mx = Math.max(...e.map(x => Math.abs(x[1])), 1e-9); return barList(e.map(([k, v]) => [k, Math.abs(v), fmt(v, 3)]), mx); })()}</div>` : ""}
      <h2>Run settings</h2>${Object.keys(d.args).length ? `<div class="tw"><table><tbody>${Object.entries(d.args).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td class="mono">${esc(typeof v === "object" ? JSON.stringify(v) : v)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">no args recorded</div>`}`;
    wireCharts($("#detail"));
  };
  await load();
  every(STATIC ? 60000 : 10000, () => { snapT = 0; load().catch(() => {}); });
};

pages.data = async () => {
  const d = await api("/api/data");
  const modeNames = Object.fromEntries((await api("/api/modes")).modes.map(m => [m.key, m.name]));
  const mx = Math.max(d.total.hours, 1e-9);
  const rows = o => Object.entries(o).sort((a, b) => b[1].hours - a[1].hours || b[1].trajectories - a[1].trajectories);
  view.innerHTML = `<h1>Data</h1><p class="lede">${d.total.trajectories} trajectories, ${fmtH(d.total.hours)} hours. Hours are recorder lines divided by 20 (fps) and 3600. A trajectory with no meta file counts as survival from the contractor source.</p>
  <div class="grid cols-2">
   <div><h2 style="margin-top:.5em">By source</h2><div class="tw"><table><thead><tr><th>Source</th><th class="n">Trajectories</th><th class="n">Hours</th></tr></thead><tbody>${Object.entries(d.by_source).map(([k, v]) => `<tr><td>${SRC_NAMES[k]}</td><td class="n">${v.trajectories}</td><td class="n">${fmtH(v.hours)}</td></tr>`).join("")}</tbody></table></div></div>
   <div><h2 style="margin-top:.5em">By mode</h2>${Object.keys(d.by_mode).length ? `<div class="tw"><table class="wrapt"><thead><tr><th>Mode</th><th class="n">Traj.</th><th class="n">Hours</th></tr></thead><tbody>${rows(d.by_mode).map(([k, v]) => `<tr><td>${esc(modeNames[k] || k)} <span class="mono" style="color:var(--faint)">${esc(k)}</span></td><td class="n">${v.trajectories}</td><td class="n">${fmtH(v.hours)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">no trajectories found under data/</div>`}</div>
  </div>
  <h2>Most recent trajectories</h2>
  ${d.recent.length && STATIC ? `<div class="tw"><table><thead><tr><th>Mode</th><th>Source</th><th>Ruleset</th><th class="n">Hours</th><th class="n">Frames</th></tr></thead><tbody>${d.recent.map(t => `<tr><td>${esc(t.mode_name)}</td><td>${esc(SRC_NAMES[t.source])}</td><td>${esc(t.ruleset || "-")}</td><td class="n">${fmtH(t.hours)}</td><td class="n">${t.frames}</td></tr>`).join("")}</tbody></table></div>` : d.recent.length ? `<div class="thumbs">${d.recent.map(t => `<div class="thumb"><img loading="lazy" alt="First frame of ${esc(t.path)}" src="/api/thumb?path=${encodeURIComponent(t.path)}" onerror="this.style.visibility='hidden'"><div><b title="${esc(t.path)}">${esc(t.path)}</b>${esc(t.mode_name)}<br>${esc(SRC_NAMES[t.source])}${t.ruleset ? " &middot; " + esc(t.ruleset) : ""}${t.team_size ? " &middot; team " + t.team_size : ""}<br>${fmtH(t.hours)} h &middot; ${t.frames} frames${t.weight != null ? " &middot; w " + t.weight : ""}${t.loss_weight != null ? " / lw " + t.loss_weight : ""}</div></div>`).join("")}</div>` : `<div class="empty">Nothing recorded yet. See Docs for how to add data.</div>`}`;
};

pages.league = async () => {
  const d = await api("/api/league");
  view.innerHTML = `<h1>League</h1><p class="lede">Elo ratings from <code>runs/league.json</code>. Pick a mode to rank by the per-mode rating.</p>
  <div class="toolbar"><label for="lm" style="color:var(--muted)">Mode</label><select id="lm"><option value="">All modes</option>${d.modes.map(k => `<option value="${esc(k)}">${esc(k)}</option>`).join("")}</select></div>
  <h2 style="margin-top:.6em">Ratings</h2><div id="lt"></div><h2>Recent matches</h2><div id="lmx"></div>`;
  const draw = () => {
    const m = $("#lm").value;
    const pl = d.players.map(p => ({ ...p, e: m ? p.by_mode[m] : p.elo })).filter(p => p.e != null).sort((a, b) => b.e - a.e);
    $("#lt").innerHTML = pl.length ? `<div class="tw"><table><thead><tr><th class="n">#</th><th>Name</th><th>Kind</th><th class="n">Elo</th><th class="n">Games</th><th class="n">Wins</th><th class="n">Win %</th></tr></thead><tbody>${pl.map((p, i) => `<tr><td class="n">${i + 1}</td><td>${esc(p.name)}</td><td><span class="tag">${esc(p.kind)}</span></td><td class="n">${Math.round(p.e)}</td><td class="n">${p.games}</td><td class="n">${p.wins}</td><td class="n">${p.win_pct == null ? "-" : p.win_pct.toFixed(1)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">${d.players.length ? "no players rated in this mode" : "No league data yet."}</div>`;
    const mt = d.matches.filter(x => !m || x.mode === m).slice(0, 50);
    $("#lmx").innerHTML = mt.length ? `<div class="tw"><table><thead><tr><th>When</th><th>Mode</th><th>A</th><th>B</th><th>Winner</th><th>Score</th></tr></thead><tbody>${mt.map(x => `<tr><td>${ago(x.t)}</td><td>${esc(x.mode)}</td><td>${esc(x.a)}</td><td>${esc(x.b)}</td><td>${x.winner ? esc(x.winner) : "draw"}</td><td>${esc(x.score ?? "")}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">no matches</div>`;
  };
  $("#lm").onchange = draw; draw();
};

function keyEl(label, on, cls = "") { return `<div class="key ${cls} ${on ? "on" : ""}">${label}</div>`; }
function renderLive(d) {
  const st = d.status || {}, a = st.last_action || {}, cam = Array.isArray(a.camera) ? a.camera : [0, 0];
  const on = !!d.online, hot = [1, 2, 3, 4, 5, 6, 7, 8, 9].filter(i => a["hotbar." + i]);
  const mv = Math.hypot(cam[0] || 0, cam[1] || 0);
  const ang = Math.atan2(cam[0] || 0, cam[1] || 0), len = Math.min(34, mv * 2.2);
  const dx = Math.cos(ang) * len, dy = Math.sin(ang) * len;
  $("#livebody").innerHTML = `
  <div class="grid live">
    <div class="card"><div class="frame"><span>${d.frame ? "" : "no frame yet"}</span>${d.frame && liveSrc ? `<img id="lf" alt="Latest agent view" src="${liveSrc}">` : ""}</div>
      <dl class="kv" style="margin-top:14px"><dt>State</dt><dd>${on ? esc(st.state) : "offline"}${!on && d.age != null ? ` (last update ${Math.round(d.age)} s ago)` : ""}</dd>
      <dt>Mode</dt><dd>${esc(st.mode ?? "-")}</dd><dt>Checkpoint</dt><dd class="mono">${esc(st.checkpoint ?? "-")}</dd><dt>Server</dt><dd class="mono">${esc(st.server ?? "-")}</dd>
      <dt>FPS</dt><dd>${st.fps == null ? "-" : fmtN(st.fps, 1)}</dd><dt>Episode</dt><dd>${st.episode ? `${fmtN(st.episode.t, 1)} s, return ${fmt(st.episode.return, 4)}` : "-"}</dd></dl></div>
    <div class="card"><h3>Last action</h3><div class="keys" style="${on ? "" : "opacity:.45"}" aria-label="Last action">
      <div class="krow">${keyEl("W", a.forward)}</div>
      <div class="krow">${keyEl("A", a.left)}${keyEl("S", a.back)}${keyEl("D", a.right)}</div>
      <div class="krow">${keyEl("Ctrl", a.sprint, "sm")}${keyEl("Shift", a.sneak, "sm")}${keyEl("Space", a.jump, "space")}</div>
      <div class="krow" style="flex-wrap:wrap;justify-content:center">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(i => keyEl(i, a["hotbar." + i], "sm")).join("")}</div>
      <div class="mouse-row" style="margin-top:8px">
        <div class="krow">${keyEl("LMB", a.attack, "sm")}${keyEl("RMB", a.use, "sm")}</div>
        <svg width="96" height="96" viewBox="-48 -48 96 96" role="img" aria-label="Camera movement ${(cam[0] || 0).toFixed(1)} pitch, ${(cam[1] || 0).toFixed(1)} yaw degrees"><circle r="42" fill="var(--panel2)" stroke="var(--line2)"/><line x1="-42" x2="42" stroke="var(--line)"/><line y1="-42" y2="42" stroke="var(--line)"/>
          ${mv > 0.01 ? `<line x1="0" y1="0" x2="${dx}" y2="${dy}" stroke="var(--accent)" stroke-width="3" stroke-linecap="round"/><circle cx="${dx}" cy="${dy}" r="4.5" fill="var(--accent)"/>` : `<circle r="3" fill="var(--faint)"/>`}</svg>
      </div>
      <div class="mono" style="color:var(--muted)">camera pitch ${(cam[0] || 0).toFixed(1)}, yaw ${(cam[1] || 0).toFixed(1)} deg</div></div></div>
  </div>`;
}
let liveSrc = null;
pages.live = async () => {
  liveSrc = null;
  if (STATIC) {
    view.innerHTML = `<h1>Live</h1><p class="lede">The live agent plays in a Minecraft window on a private machine, so its view and keystrokes are not published. On a local copy of this dashboard this page shows the latest game frame and the keys and mouse the agent last pressed.</p>
    <div class="empty">Live view is available only when running the dashboard locally.</div>
    <h2>What the live page shows</h2><ul class="doc" style="color:var(--muted)"><li>State, mode, checkpoint, frames per second and the current episode return.</li><li>The last action as a keyboard and mouse diagram.</li><li>Offline status when the status file is more than 10 seconds old.</li></ul>`;
    return;
  }
  view.innerHTML = `<h1>Live</h1><p class="lede">State of the live agent from <code>live/status.json</code> and the latest view from <code>live/frame.jpg</code>. The agent counts as offline when the status file is more than 10 seconds old.</p><div id="livebody" style="margin-top:16px"></div>`;
  const tick = async () => {
    const d = await api("/api/live");
    renderLive(d);
    if (d.frame) {
      const n = new Image();
      n.onload = () => { liveSrc = n.src; const el = $("#lf"); if (el) el.src = n.src; };
      n.src = "/live/frame.jpg?t=" + Date.now();
    }
  };
  await tick();
  every(1000, () => tick().catch(() => {}));
};

/* ---------- docs ---------- */
const DOCS = [
 ["intro", "What this is", `
<p>VPT Arena trains one network to play survival Minecraft and the PvP minigames. The network takes 128x128 game frames and outputs keyboard and mouse actions at 20 Hz. It starts from OpenAI's Video PreTraining (VPT) foundation model. A learned embedding for the game mode, the combat ruleset (1.8 or 1.9+) and the team size is added to the model input. The embedding starts at zero.</p>
<div class="note"><b>Server scope.</b> It is for a server you run only. Public servers such as Hypixel ban bots, and nothing in this project deals with anti-cheat. Do not point the live client at a server you do not run.</div>
<p>All phases have code. Each section below says what its command does and how far it has been tested; the Overview page shows the same per phase. So far the real-world checks are the 1x weights on one contractor clip and a short BC fine-tune. The recorder, live agent, datapack and RL have been tested with fakes or a toy environment only.</p>`],
 ["format", "Data format", `
<p>Each trajectory is three files with the same stem:</p>
<ul><li><code>&lt;stem&gt;.mp4</code>: video at 20 fps, 640x360.</li><li><code>&lt;stem&gt;.jsonl</code>: one JSON object per frame, in VPT recorder format.</li><li><code>&lt;stem&gt;.meta.json</code> (optional): mode and weighting.</li></ul>
<p>One recorder line, with the fields written by <code>env_action_to_json</code> in <code>vpt_arena/vpt.py</code>:</p>
<pre><code>{"keyboard": {"keys": ["key.keyboard.w", "key.keyboard.space"], "newKeys": [], "chars": ""},
 "mouse": {"dx": 1.2, "dy": -0.4, "buttons": [0], "newButtons": [], "x": 0.0, "y": 0.0, "dwheel": 0.0},
 "hotbar": 0, "isGuiOpen": false, "tick": 0}</code></pre>
<p><code>keys</code> holds names such as <code>key.keyboard.w</code>, <code>.a</code>, <code>.s</code>, <code>.d</code>, <code>.space</code>, <code>.left.shift</code>, <code>.left.control</code>, <code>.1</code> to <code>.9</code>, <code>.e</code>, <code>.q</code>, <code>.f</code> and <code>.escape</code>. <code>mouse.buttons</code> lists pressed buttons: 0 is attack (left), 1 is use (right), 2 is pick item (middle). <code>dx</code> and <code>dy</code> are mouse movement in pixels; the loader multiplies by 360/2400 to get degrees of camera turn.</p>
<p>The meta file:</p>
<pre><code>{"mode": "bedwars_solo", "ruleset": "legacy", "team_size": 1, "source": "human", "weight": 1.0, "loss_weight": 1.0}</code></pre>
<p><code>source</code> is one of human, idm or contractor. <code>weight</code> sets how often the trajectory is sampled and <code>loss_weight</code> scales its loss. With no meta file, a trajectory counts as survival play from the contractor source, which is correct for OpenAI's contractor data. The Data page counts hours as the number of non-empty lines divided by 20 and by 3600.</p>`],
 ["record", "Record your own games", `
<p>Human data goes in <code>data/human/&lt;mode&gt;/</code>. The recorder captures the Minecraft window at 20 fps as 640x360 video, plus the exact keys and mouse, and writes <code>&lt;timestamp&gt;.mp4</code>, <code>.jsonl</code> and <code>.meta.json</code> there.</p>
<pre><code>python -m vpt_arena.live.recorder --mode bedwars_solo [--ruleset legacy] [--team-size N]</code></pre>
<ul>
<li>It records only while Minecraft is the front window. Switching away closes the segment, and segments under 2 seconds are dropped.</li>
<li>F8 pauses and resumes. Ctrl-C stops.</li>
<li>macOS asks for Screen Recording and Input Monitoring permission for the terminal app.</li>
<li>Key bindings and mouse sensitivity are read from <code>configs/controls.json</code>. <code>sensitivity</code> is the slider value, so 0.5 is 100%. <code>bindings</code> maps an action to a key, for example <code>{"sprint": "r"}</code>. Recordings store VPT key names whatever the bindings are.</li>
<li>Suggested game settings: FOV 70, GUI scale 2 at 1280x720, or any 16:9 window.</li>
</ul>
<p><b>Status:</b> tested with fake input and capture backends. It has not been run against a real Minecraft window. Check the first recording on the Data page: it should show a thumbnail, the right mode and a plausible number of hours.</p>`],
 ["idm", "Label videos with the IDM", `
<p>The inverse dynamics model (IDM) predicts the keys and mouse movement between frames, so ordinary PvP videos can become training data. The weights are 1.9 GB; use a GPU machine such as Colab and keep them off the Mac's internal disk.</p>
<pre><code>python -m vpt_arena.idm_label --weights weights/4x_idm.weights \\
    --mode duels_sword --out data/idm/sword videos/*.mp4</code></pre>
<p>Options: <code>--ruleset</code> and <code>--team-size</code> override the mode defaults, <code>--crop x,y,w,h</code> selects the game area in source pixels, <code>--min-conf</code> drops steps the IDM is unsure of, and <code>--loss-weight</code> (default 0.5) scales how much these labels count in training. Output is a recorder-format mp4, JSONL and meta file with source <code>idm</code>.</p>
<p><b>Status:</b> tested on synthetic video only.</p>`],
 ["bc", "Train behavior cloning", `
<p>Sequence BC runs over all data directories at once. Each <code>--data</code> takes a directory and an optional multiplier after a colon. Contractor data keeps the survival skill in the mix.</p>
<pre><code>python -m vpt_arena.train_bc --arch 2x --weights weights/foundation-model-2x.weights \\
    --data data/human:4 --data data/idm:2 --data data/contractor:1 \\
    --run runs/arena-2x --batch 4 --T 64 --accum 4 --ckpt-cnn --steps 20000</code></pre>
<p>The run directory gets <code>run.json</code> (kind, arch, start time, args) and <code>log.jsonl</code> with one line per optimizer step: <code>nll</code>, <code>btn_acc</code>, <code>kl</code>, <code>grad_norm</code>, <code>lr</code>, <code>sec</code>, and every <code>--eval-every</code> steps also <code>eval_nll</code> and <code>eval_btn_acc</code>. The Training page plots these. The camera loss is masked when the camera is off, and training resumes from the run directory. The 2x model has 249M parameters and needs a GPU; 1x has 71M.</p>
<p>Contractor clips come from <code>tools/fetch_contractor.py --index 7 --n N --out data/contractor</code>.</p>
<p><b>Status:</b> tested on synthetic data and on one real contractor clip. A 30-step fine-tune of 1x on that clip ran, and NLL fell from 4.5 to 3.6. Nothing has been trained on human or IDM-labelled PvP data yet.</p>`],
 ["validate", "Check real weights", `
<pre><code>python tools/check_weights.py 2x idm4x
python tools/validate_real.py</code></pre>
<p><code>check_weights.py</code> compares remote weight keys and shapes to the model built here. <code>validate_real.py</code> scores a model on a real OpenAI contractor clip. The pretrained 1x model scores 4.28 NLL per step with 60% button-token accuracy on that clip. A randomly initialised 1x scores 13.14 and 0%.</p>`],
 ["server", "Set up your server", `
<p>The agent and RL read rewards from your Minecraft server log, and RL sends commands over the server's remote console. <code>configs/arenas.json</code> holds the settings:</p>
<ul><li><code>agent_name</code> and <code>opponent_name</code>: the two players.</li>
<li>The remote console address and the <code>server_log</code> path. The remote console password is read from an environment variable, never from the file.</li>
<li>Per mode: start commands, <code>start_event</code>, <code>end_events</code>, <code>max_seconds</code> and chat regex patterns.</li></ul>
<p>Rewards come from the server log: vanilla death messages (kill, death, void_kill) and <code>[ARENA] &lt;event&gt;</code> lines printed with <code>/say</code>.</p>
<p>The duel datapack is made with:</p>
<pre><code>python tools/make_datapack.py --out &lt;world&gt;/datapacks/vpt_arena --format 101</code></pre>
<p>Use the pack format of your server (101 for 26.1). Then run <code>/reload</code> and <code>/function vpt:arena/build</code> once. The kits are sword, classic, uhc, bow, sumo and boxing, and it prints round_start, win, loss, draw and knockoff. Other modes, such as Bed Wars, need a minigame plugin, with its join command and chat patterns filled into <code>arenas.json</code>.</p>
<p><b>Status:</b> the datapack has not been loaded on a real server. After <code>/reload</code>, check the server log for function errors.</p>`],
 ["live", "Run the live agent", `
<pre><code>python -m vpt_arena.live.play --weights &lt;policy.weights&gt; --arch 1x \\
    --mode duels_sword --server &lt;host:port&gt;</code></pre>
<ul>
<li><code>--server</code> must be listed in <code>configs/own_servers.json</code>.</li>
<li>It sends input only while Minecraft is the front window, and releases every key when it is not.</li>
<li>Any key or click from the player stops it, after a 1.5 second grace period for the click that focuses the window.</li>
<li>It writes <code>live/status.json</code> and <code>live/frame.jpg</code> every second, which the Live page reads. It needs Accessibility permission.</li>
<li>With OpenAI's real 1x weights a step takes about 20 ms on the M2 CPU, which is 50 Hz; the game needs 20 Hz. The 2x model needs a GPU.</li>
</ul>
<p>Status file fields: <code>state</code> (idle, playing or recording), <code>mode</code>, <code>checkpoint</code>, <code>server</code>, <code>fps</code>, <code>updated</code> (unix time; the Live page shows offline after 10 seconds), <code>last_action</code> (env button names plus <code>camera</code> as [pitch, yaw] degrees) and <code>episode</code> (<code>t</code>, <code>return</code>).</p>
<p><b>Status:</b> logic tested with fakes. It has not been run in a real game.</p>`],
 ["rl", "Run RL", `
<pre><code>python -m vpt_arena.rl.train_rl --arch 1x \\
    --weights &lt;policy.weights&gt; --mode duels_sword --run runs/rl-sword --iters 200</code></pre>
<p>This is PPO over recurrent rollouts with a KL penalty toward the starting policy and a value-head warm-up (<code>--vf-warmup</code>). It resumes from the run directory. One Minecraft window is one environment running in real time, about 72,000 steps an hour. <code>--toy</code> runs the AttackOnRed test environment instead of Minecraft.</p>
<p>The run writes <code>rl_log.jsonl</code> with one line per iteration: <code>iter</code>, <code>env_steps</code>, <code>ep_return_mean</code>, <code>ep_len_mean</code>, <code>win_rate</code>, <code>kl</code>, <code>pi_loss</code>, <code>v_loss</code>, <code>entropy</code>, <code>fps</code> and <code>by_mode</code>. The Training page plots them.</p>
<p><b>Status:</b> on the toy environment, reward per step went from 0.12 to 0.44 (maximum 0.5), and recomputing a rollout as a sequence matched the step-by-step log-probabilities to 1e-6. The live environment and datapack are tested with fakes only; RL has not been run against a real server.</p>`],
 ["league", "League", `
<pre><code>python -m vpt_arena.league play --weights &lt;w&gt; --name &lt;checkpoint name&gt; \\
    --opponent &lt;player&gt; --opponent-kind human|scripted|checkpoint \\
    --mode duels_sword --games 10
python -m vpt_arena.league table [--mode M]</code></pre>
<p><code>play</code> plays real games and writes <code>runs/league.json</code>; <code>table</code> prints the ratings. Elo uses K=32 and a start of 1000, kept overall and per mode. The League page reads the same file.</p>`],
 ["colab", "Colab pipeline", `
<p><code>colab/train.sh</code> runs the full pipeline on a GPU: it downloads the weights, checks them, fetches contractor clips, labels the videos in <code>videos/&lt;mode&gt;/</code> with the IDM, and runs BC.</p>
<p><b>Status:</b> not run. It needs a Colab or similar GPU session, which the maintainer starts by hand.</p>`],
 ["site", "Running this site", `
<pre><code>python -m vpt_arena.site.server --port 7790 --root .</code></pre>
<p>A public copy of this site is a static build of the same pages. The data comes from one snapshot that is rebuilt every 5 minutes; it leaves out the live view, game frames, player names and private server details.</p>
<p>The local server listens on the loopback interface only, uses the Python standard library, and reads files under the root. It does not start processes. Its only writes are first-frame thumbnails under <code>runs/.site-cache/</code>. Pages are plain HTML, CSS and JavaScript with no external requests.</p>`],
];
pages.docs = async () => {
  view.innerHTML = `<div class="docs"><nav class="toc" aria-label="Docs sections">${DOCS.map(([id, t]) => `<a href="#/docs/${id}">${t}</a>`).join("")}</nav>
  <div class="doc"><h1>Docs</h1>${DOCS.map(([id, t, body]) => `<h2 id="doc-${id}">${t}</h2>${body}`).join("")}</div></div>`;
  const sec = location.hash.split("/")[2];
  if (sec) { const el = document.getElementById("doc-" + sec); if (el) el.scrollIntoView(); }
};

/* ---------- shell ---------- */
$("#nav").innerHTML = PAGES.map(([k, t]) => `<a href="#/${k}" data-k="${k}">${t}</a>`).join("");
let gen = 0;
async function route() {
  clearTimers();
  const my = ++gen;
  const k = (location.hash.split("/")[1] || "overview");
  const key = pages[k] ? k : "overview";
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.k === key));
  document.title = (PAGES.find(p => p[0] === key)[1]) + " - VPT Arena";
  if (!(key === "docs" && document.querySelector(".docs"))) view.innerHTML = `<div class="empty">Loading</div>`;
  try { await pages[key](); if (my !== gen) { return; } if (key !== "docs" || !location.hash.split("/")[2]) window.scrollTo(0, 0); }
  catch (e) { if (my !== gen) return; view.innerHTML = `<div class="empty">Could not load this page: ${esc(e.message)}. ${STATIC ? "Try again in a minute." : "Is the server running?"}</div>`; }
}
window.addEventListener("hashchange", route);
$("#theme").onclick = () => {
  const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  const nx = cur === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = nx;
  try { localStorage.setItem("vpt-theme", nx); } catch (e) {}
};
const pill = async () => {
  try { const d = await api("/api/live"), p = $("#livepill"); p.className = "pill " + (d.online ? "on" : "off"); $("span", p).textContent = d.online ? (d.status.state || "online") : "offline"; }
  catch (e) { /* server away */ }
};
if (STATIC) { paintPill(); setInterval(paintPill, 30000); api("/api/overview").catch(() => {}); }
else { pill(); setInterval(pill, 3000); }
route();
