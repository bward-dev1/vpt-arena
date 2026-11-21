"use strict";
/* Overview and Modes. */
const isRound = t => /^round-\d+$/.test(t);
function releaseTags(r) { return r.rounds.map(x => x.tag); }
/* per release values for one mode: [{tag, win_rate, return, episodes}] in release order */
function modeHistory(r, key) { return r.rounds.map(x => ({ tag: x.tag, ...(x.modes[key] || { win_rate: null, return: null, episodes: 0 }) })); }
function totalSteps(w) { return w.workers.reduce((a, x) => a + (x.env_steps || 0), 0); }

pages.overview = async () => {
  const [o, r, w, md] = await Promise.all([api("/api/overview"), api("/api/rounds"), api("/api/workers"), api("/api/modes")]);
  const clips = (o.clips || []).filter(c => okUrl(c.url));
  const names = Object.fromEntries(md.modes.map(m => [m.key, m]));
  const done = r.rounds.filter(x => isRound(x.tag)).length;
  const st = typeof roundState === "function" ? roundState({ workers: w.workers, cloud: o.cloud, rounds: r }) : null;
  view.innerHTML = `
  <div class="lbslot" id="lbslot"></div>
  <section class="hero voxel">
    <div class="hero-copy">
      <p class="kick">Open research project</p>
      <h1>An AI that learns to fight in Minecraft.</h1>
      <p class="lede">One neural network plays survival and ${o.modes - 1} PvP and minigame modes. It sees game pixels and presses keys and moves the mouse at 20 Hz, like a player. It starts from OpenAI's Video PreTraining model and improves through reinforcement learning rounds that run in public on free CPU servers.</p>
      <div class="cta"><a class="btn primary" href="#/live">Watch it live</a><button type="button" class="btn" id="trailerbtn" hidden>Watch the trailer</button>${pages.simulate ? `<a class="btn" href="#/simulate">Run a simulation</a>` : ""}${pages.dashboard ? `<a class="btn ghost" href="#/dashboard">Open the dashboard</a>` : ""}</div>
    </div>
    <div class="hero-media">
      ${clips.length ? `<div class="hero-clip"><video id="herov" muted playsinline autoplay ${clips.length === 1 ? "loop" : ""} preload="auto" aria-label="Gameplay clip"></video><div class="hero-cap" id="herocap"></div></div>` : `<div class="hero-clip none"><span class="hc-ic big">${pixelIcon("swords", 64)}</span><span class="hc-none">Gameplay clips appear here after the first evaluation.</span></div>`}
    </div>
  </section>
  <section class="counters" aria-label="Headline numbers">
    <div class="ct"><div class="v" data-n="${done}">-</div><div class="k">Training rounds done</div></div>
    <div class="ct"><div class="v" data-n="${totalSteps(w)}" data-big="1">-</div><div class="k">Environment steps trained</div></div>
    <div class="ct"><div class="v" data-n="${o.modes}">-</div><div class="k">Game modes</div></div>
    <div class="ct"><div class="v" id="simcount">-</div><div class="k">Simulations run</div></div>
  </section>
  ${st ? `<a class="statusband" href="#/dashboard"><span class="dot ${st.live ? "on" : ""}"></span><span><b>${esc(st.headline)}</b> ${esc(st.detail)}</span><span class="go">Dashboard</span></a>` : ""}
  <h2 class="kick">Newest clips</h2>
  ${clips.length ? `<div class="grid cols clipgrid">${clips.map(c => `<article class="card clipcard">${hoverClip(c.url, c.name + " " + c.tag, modeIcon(c.mode, 22), c.url60)}<div class="cc-body"><a class="cc-t" href="#/modes/${encodeURIComponent(c.mode)}">${esc(c.name)}</a><span class="tag">${esc(c.tag)}</span></div></article>`).join("")}</div><p class="upd">Clips are 5-second samples of each release playing the mode. Hover or tap a clip to play it.</p>` : `<div class="empty">No gameplay clips yet. After each training round the agent is evaluated on every mode and a short clip of each is posted here.</div>`}
  <h2 class="kick">What it is</h2>
  <div class="grid cols3 feat">
    <div class="card"><div class="ficon">${pixelIcon("grid", 30)}</div><h3>Learns from pixels</h3><p>The network takes 128 by 128 frames and outputs keyboard and mouse actions at 20 Hz. There is no game API and no hand-written fighting logic.</p></div>
    <div class="card"><div class="ficon">${pixelIcon("swords", 30)}</div><h3>One network, ${o.modes} modes</h3><p>A learned embedding for the mode, the combat ruleset (1.8 or 1.9+) and the team size tells the same network which game it is in.</p></div>
    <div class="card"><div class="ficon">${pixelIcon("cloud", 30)}</div><h3>Trained in public</h3><p>Each round runs 12 workers on GitHub Actions. Results, clips and failures are published here, round by round.</p></div>
  </div>
  <h2 class="kick">Project phases</h2>
  <div class="tw"><table><thead><tr><th>Phase</th><th>What</th><th>Live status</th><th>Tested</th><th>State</th></tr></thead><tbody>
  ${o.phases.map(p => `<tr><td>${p.phase}. ${esc(p.name)}</td><td class="wrap">${esc(p.what)}</td><td class="wrap">${esc(p.status)}</td><td class="wrap">${esc(p.tested)}</td><td><span class="tag ${p.state}">${p.state === "done" ? "has data" : p.state === "active" ? "running" : "empty"}</span></td></tr>`).join("")}
  </tbody></table></div>
  <p class="upd">Status comes from the files on disk (weights, data, runs, live), not from the README. The Tested column is a fixed note on how far each phase has been checked; see Docs.</p>`;
  $$(".counters .v[data-n]").forEach(el => counter(el, +el.dataset.n, el.dataset.big ? { fmt: big } : {}));
  initTrailer();
  if (typeof mountLiveBadge === "function") mountLiveBadge($("#lbslot"));
  const hv = $("#herov");
  if (hv) {
    let i = 0;
    const play = () => { const c = clips[i % clips.length]; hv.src = getFps() === 60 && c.url60 ? c.url60 : c.url; hv.onerror = () => { if (hv.src.includes("/clips60/")) { hv.onerror = null; hv.src = c.url; hv.play().catch(() => {}); } }; $("#herocap").innerHTML = `<b>${esc(c.name)}</b> <span class="tag">${esc(c.tag)}</span>`; hv.play().catch(() => {}); };
    hv.addEventListener("ended", () => { i++; play(); });
    play();
  }
  if (STATIC) fetch("/api/sims", { cache: "no-store" }).then(x => x.json()).then(d => { const el = $("#simcount"); if (el) counter(el, d.total ?? d.sims.length); }).catch(() => { const el = $("#simcount"); if (el) el.textContent = "0"; });
  else { const el = $("#simcount"); if (el) el.textContent = "-"; }
};

/* ---------- modes ---------- */
function modeCard(m, hist) {
  const wr = hist.map(h => h.win_rate), last = [...wr].reverse().find(v => v != null);
  const evs = Object.entries(m.events), shown = evs.slice(0, 4);
  return `<article class="card mode">
    <div class="m-media">${m.clip && okUrl(m.clip.url) ? hoverClip(m.clip.url, m.name + " " + m.clip.tag, modeIcon(m.key, 22), m.clip.url60) : noClip(modeIcon(m.key, 40))}</div>
    <div class="m-body">
      <h3><span class="m-ic">${modeIcon(m.key, 20)}</span><a href="#/modes/${encodeURIComponent(m.key)}">${esc(m.name)}</a></h3>
      <div class="tags"><span class="tag ${m.ruleset}">${m.ruleset === "modern" ? "1.9+ cooldown" : "1.8 combat"}</span><span class="tag">team ${m.team_size}</span></div>
      <p>${esc(m.summary)}</p>
      <div class="m-trend"><div>${spark(wr, { lo: 0, hi: 1 })}</div><div class="m-wr"><b>${pct(last)}</b><span>win rate${hist.filter(h => h.win_rate != null).length > 1 ? " across " + hist.filter(h => h.win_rate != null).length + " releases" : last == null ? ", not evaluated" : ", " + esc(hist.filter(h => h.win_rate != null).pop().tag)}</span></div></div>
      <div class="ev">${shown.map(([k, w]) => `<span class="${w < 0 ? "neg" : "pos"}">${esc(k)} <b>${w > 0 ? "+" : ""}${w}</b></span>`).join("")}${evs.length > 4 ? `<span class="more">+${evs.length - 4}</span>` : ""}</div>
    </div></article>`;
}
pages.modes = async args => {
  if (args && args[0]) return pages.modeDetail(args[0]);
  const [d, r] = await Promise.all([api("/api/modes"), api("/api/rounds")]);
  view.innerHTML = `<h1>Modes</h1><p class="lede">${d.modes.length} game modes. The same network plays all of them; a learned embedding tells it which one it is in. Win rate is against the scripted arena bots, per evaluated release. Reward events are the server signals the RL phase turns into reward, with their weights.</p>
  <div class="toolbar"><input type="search" id="q" placeholder="Filter modes" aria-label="Filter modes"><button class="chip on" data-r="">All</button><button class="chip" data-r="modern">Modern</button><button class="chip" data-r="legacy">Legacy</button></div>
  <div class="grid cols modegrid" id="mgrid"></div>`;
  let rs = "", q = "";
  const draw = () => {
    const list = d.modes.filter(m => (!rs || m.ruleset === rs) && (!q || (m.name + m.key + m.summary).toLowerCase().includes(q)));
    $("#mgrid").innerHTML = list.map(m => modeCard(m, modeHistory(r, m.key))).join("") || `<div class="empty">no modes match</div>`;
  };
  draw();
  $("#q").oninput = e => { q = e.target.value.toLowerCase().trim(); draw(); };
  $$(".chip[data-r]").forEach(b => b.onclick = () => { rs = b.dataset.r; $$(".chip[data-r]").forEach(x => x.classList.toggle("on", x === b)); draw(); });
};

pages.modeDetail = async key => {
  const [d, r, cloud, runsIdx] = await Promise.all([api("/api/modes"), api("/api/rounds"), api("/api/cloud"), api("/api/runs")]);
  const m = d.modes.find(x => x.key === key);
  if (!m) { view.innerHTML = `<div class="nf"><div class="nf-ic">${pixelIcon("grid", 64)}</div><h1>No such mode</h1><p class="lede"><code>${esc(key)}</code> is not a game mode.</p><p><a class="btn" href="#/modes">All modes</a></p></div>`; return; }
  document.title = m.name + " - VPT Arena";
  const hist = modeHistory(r, key);
  const rel = [...cloud.releases, ...Object.keys(cloud.clips).filter(t => !cloud.releases.includes(t))];
  const clips = rel.filter(t => cloud.clips[t] && cloud.clips[t][key]).map(t => ({ tag: t, url: cloud.clips[t][key], url60: ((cloud.clips60 || {})[t] || {})[key], h: hist.find(x => x.tag === t) }));
  const rl = runsIdx.runs.filter(x => x.kind === "rl");
  const curves = {};
  for (const x of rl) { try { const run = await api("/api/run/" + encodeURIComponent(x.name)); const c = (run.mode_curves || {})[key]; if (c && c.length) curves[x.name] = c; } catch (e) { /* skip */ } }
  const idx = d.modes.findIndex(x => x.key === key);
  const labels = {}, wrS = [], retS = [];
  hist.forEach((h, i) => { labels[i] = h.tag; if (h.win_rate != null) wrS.push([i, h.win_rate]); if (h.return != null) retS.push([i, h.return]); });
  view.innerHTML = `<nav class="crumb"><a href="#/modes">Modes</a> / <span>${esc(m.name)}</span></nav>
  <header class="mhead"><div class="mh-ic">${modeIcon(key, 56)}</div><div><h1>${esc(m.name)}</h1><div class="tags"><span class="tag ${m.ruleset}">${m.ruleset === "modern" ? "modern, 1.9+ cooldown" : "legacy, 1.8 combat"}</span><span class="tag">team size ${m.team_size}</span><span class="tag mono">${esc(key)}</span></div><p class="lede">${esc(m.summary)}</p></div></header>
  <div class="grid stats">
    <div class="card stat"><div class="k">Latest win rate</div><div class="v">${pct([...hist].reverse().find(h => h.win_rate != null)?.win_rate)}</div><div class="s">against scripted arena bots</div></div>
    <div class="card stat"><div class="k">Best Elo</div><div class="v">${m.best_elo ? Math.round(m.best_elo.elo) : "-"}</div><div class="s">${m.best_elo ? esc(m.best_elo.name) : "not rated"}</div></div>
    <div class="card stat"><div class="k">Training data</div><div class="v">${fmtH(m.hours)} h</div><div class="s">${m.trajectories} trajectories</div></div>
  </div>
  <h2 class="kick">Clips across releases</h2>
  ${clips.length ? `<div class="grid cols clipgrid">${clips.map(c => `<article class="card clipcard">${hoverClip(c.url, m.name + " " + c.tag, "", c.url60)}<div class="cc-body"><span class="tag">${esc(c.tag)}</span><span class="cc-s">${c.h && c.h.win_rate != null ? pct(c.h.win_rate) + " win, return " + fmt(c.h.return, 3) : "not evaluated"}</span></div></article>`).join("")}</div>` : `<div class="empty">No clips for this mode yet.</div>`}
  <h2 class="kick">Release comparison</h2>
  <div class="grid cols-2"><div class="card chart"><h3>Win rate by release</h3>${wrS.length ? multiChart({ "win rate": wrS }, "Win rate by release", { xLabels: labels, yRange: [0, 1], yFmt: v => Math.round(v * 100) + "%", noLegend: true }) : `<div class="empty">No evaluation yet.</div>`}</div>
  <div class="card chart"><h3>Mean return by release</h3>${retS.length ? multiChart({ "return": retS }, "Return by release", { xLabels: labels, noLegend: true }) : `<div class="empty">No evaluation yet.</div>`}</div></div>
  <h2 class="kick">Training curve</h2>
  ${Object.keys(curves).length ? `<div class="card chart"><h3>Return while training<small>per RL run that trained this mode</small></h3>${multiChart(curves, "Return during training for " + m.name)}</div>` : `<div class="empty">No RL run has trained this mode yet. Curves appear once a worker with this mode reports per-mode returns.</div>`}
  <h2 class="kick">Reward events</h2>
  <div class="tw"><table><thead><tr><th>Event</th><th class="n">Weight</th></tr></thead><tbody>${Object.entries(m.events).map(([k, w]) => `<tr><td>${esc(k)}</td><td class="n ${w < 0 ? "negc" : "posc"}">${w > 0 ? "+" : ""}${w}</td></tr>`).join("")}</tbody></table></div>
  <p class="pager">${idx > 0 ? `<a href="#/modes/${encodeURIComponent(d.modes[idx - 1].key)}">&larr; ${esc(d.modes[idx - 1].name)}</a>` : "<span></span>"}${idx < d.modes.length - 1 ? `<a href="#/modes/${encodeURIComponent(d.modes[idx + 1].key)}">${esc(d.modes[idx + 1].name)} &rarr;</a>` : ""}</p>`;
  wireMulti(view);
};

/* ---------- trailer: shown only when the video exists in KV ---------- */
let trailerP = null;
function trailerInfo() {
  if (!STATIC) return Promise.resolve(null);
  if (!trailerP) {
    const has = u => fetch(u, { headers: { range: "bytes=0-0" }, cache: "no-store" }).then(r => r.ok || r.status === 206).catch(() => false);
    trailerP = Promise.all([has("/trailer.mp4"), has("/trailer-vertical.mp4"), has("/trailer-60.mp4")]).then(([main, vertical, p60]) => main ? { main, vertical, p60 } : null);
  }
  return trailerP;
}
async function initTrailer() {
  const b = $("#trailerbtn"); if (!b) return;
  const t = await trailerInfo(); if (!t || !b.isConnected) return;
  b.hidden = false; b.onclick = () => openTrailer(t);
}
function openTrailer(t) {
  let ov = $("#trailerbox");
  if (!ov) { ov = document.createElement("div"); ov.id = "trailerbox"; ov.className = "lightbox trl"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true"); ov.setAttribute("aria-label", "Trailer"); document.body.appendChild(ov);
    ov.addEventListener("click", e => { if (e.target === ov || e.target.closest(".lb-close")) { const v = $("video", ov); if (v) v.pause(); ov.hidden = true; } });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !ov.hidden) { const v = $("video", ov); if (v) v.pause(); ov.hidden = true; } }); }
  const portrait = innerWidth < innerHeight && innerWidth < 760 && t.vertical;
  const u30 = portrait ? "/trailer-vertical.mp4" : "/trailer.mp4", u60 = !portrait && t.p60 ? "/trailer-60.mp4" : "";
  const src = getFps() === 60 && u60 ? u60 : u30;
  ov.innerHTML = `<button type="button" class="lb-close" aria-label="Close trailer">Close</button><div class="trl-box vbox ${portrait ? "vert" : ""}" data-fsbox data-u30="${u30}" data-u60="${u60}"><video controls playsinline autoplay src="${src}" aria-label="VPT Arena trailer"></video><div class="vtools">${fpsBtn(u60)}${fsBtn}</div></div>`;
  ov.hidden = false; lastBox = $(".trl-box", ov); $(".lb-close", ov).focus();
}
