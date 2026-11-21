"use strict";
/* Dashboard: mission control for the training rounds. */
const SETUP_MIN = 10;
/* Where the current round is. s = {workers, cloud, rounds}. Times are unix seconds. */
function roundState(s) {
  const now = Date.now() / 1000, W = s.workers || [], jobs = (s.cloud && s.cloud.jobs) || [];
  const wf = jobs.filter(j => j.platform === "github-actions" && /workflow/i.test(j.name) && j.state === "running");
  const rs = W.filter(w => w.round != null).map(w => w.round), maxR = rs.length ? Math.max(...rs) : -1;
  const cur = W.filter(w => w.round === maxR), running = cur.filter(w => w.state === "running");
  const minutes = (cur.find(w => w.minutes) || {}).minutes || 150;
  const lastStart = cur.length ? Math.max(...cur.map(w => w.started || 0)) : 0;
  const wfStart = wf.length ? Math.max(...wf.map(j => j.started || 0)) : 0;
  const out = { round: maxR, minutes, cur, running, now, live: false, phase: -1, endTs: null, startTs: null, pct: null, headline: "", detail: "", etaLabel: "", next: "" };
  if (running.length) {
    const start = Math.min(...running.map(w => w.started || now));
    const ends = running.map(w => w.minutes_left != null && w.updated ? w.updated + w.minutes_left * 60 : (w.started || start) + (w.minutes || minutes) * 60);
    Object.assign(out, { live: true, phase: 1, startTs: start, endTs: Math.max(...ends), round: maxR });
    out.pct = Math.min(1, (now - start) / (Math.max(...ends) - start));
    out.headline = `Round ${maxR} is training`;
    out.detail = `${running.length} of ${cur.length} workers running. Training ends about ${clock(out.endTs)}.`;
    out.etaLabel = "Training ends in";
    out.next = "The next round starts on its own when this one has been merged and released, a few minutes after training ends.";
  } else if (wf.length && wfStart > lastStart) {
    const rnd = maxR + 1, end = wfStart + (SETUP_MIN + minutes) * 60;
    Object.assign(out, { live: true, phase: 0, round: rnd, startTs: wfStart, endTs: end });
    out.pct = Math.min(1, (now - wfStart) / (end - wfStart));
    out.headline = `Round ${rnd} is starting up`;
    out.detail = `The workers are installing Minecraft and loading the model, about ${SETUP_MIN} minutes. Training then runs ${minutes} minutes.`;
    out.etaLabel = "Training ends in about";
    out.next = "This round's merge and evaluation follow training. The round after it starts automatically.";
  } else if (wf.length) {
    Object.assign(out, { live: true, phase: 2 });
    out.headline = `Round ${maxR} is merging and evaluating`;
    out.detail = "The workers have finished. Their policies are merged into one, released and evaluated on every mode.";
    out.etaLabel = "";
    out.next = "The next round starts automatically as soon as the release is published.";
  } else {
    out.headline = maxR >= 0 ? `Round ${maxR} is the latest` : "No round has run yet";
    out.detail = maxR >= 0 ? "No round is running right now." : "Rounds appear here once the first workers report.";
    out.next = "A new round starts when the training workflow is dispatched.";
  }
  return out;
}
let dashMode = "", dashMetric = "win_rate", dashRel = null, dashSort = { k: "mode", dir: 1 };
const dashOpen = new Set();
const PHASES = ["Setup", "Training", "Merge", "Evaluation"];

function etaHtml(st) {
  if (!st.endTs) return `<div class="eta-l">${esc(st.phase === 2 ? "Merge and evaluation" : "Status")}</div><div class="eta">${st.phase === 2 ? "in progress" : "idle"}</div>`;
  return `<div class="eta-l">${esc(st.etaLabel)}</div><div class="eta" data-eta="${st.endTs}">${span(st.endTs - Date.now() / 1000)}</div>`;
}
function tickEta() { $$("[data-eta]").forEach(el => { const left = +el.dataset.eta - Date.now() / 1000; el.textContent = left > 0 ? span(left) : "any moment"; }); }

function timelineHtml(r, st) {
  const tags = r.rounds.map(x => ({ tag: x.tag, done: true, wr: x.mean_win_rate }));
  const doneRounds = new Set(tags.map(t => t.tag));
  const items = tags.slice();
  if (st.round >= 0 && st.live && !doneRounds.has("round-" + st.round)) items.push({ tag: "round-" + st.round, now: true });
  const nextN = (st.live && !doneRounds.has("round-" + st.round) ? st.round : Math.max(st.round, ...tags.map(t => /round-(\d+)/.test(t.tag) ? +RegExp.$1 : -1))) + 1;
  items.push({ tag: "round-" + nextN, next: true });
  return `<div class="timeline" role="list">${items.map(t => `<div class="tl ${t.done ? "done" : t.now ? "now" : ""}" role="listitem"><i></i><b>${esc(t.tag)}</b><span>${t.done ? (t.wr != null ? pct(t.wr) + " mean win rate" : "released") : t.now ? "in progress" : "next"}</span></div>`).join("")}</div>`;
}
function stepsByRound(w) {
  const by = {};
  w.workers.forEach(x => { if (x.round != null) by[x.round] = (by[x.round] || 0) + (x.env_steps || 0); });
  const keys = Object.keys(by).map(Number).sort((a, b) => a - b), mx = Math.max(1, ...keys.map(k => by[k]));
  if (!keys.length) return `<div class="empty">No worker has reported steps yet.</div>`;
  return `<div class="vbars">${keys.map(k => `<div class="vb" title="Round ${k}: ${by[k].toLocaleString()} steps"><b>${big(by[k])}</b><i style="height:${Math.max(2, by[k] / mx * 100)}%"></i><span>round ${k}</span></div>`).join("")}</div>`;
}
function workerCard(x, mm, frames) {
  const fr = frames.filter(f => f.job === x.job);
  const frac = x.state === "finished" ? 1 : x.minutes && x.minutes_left != null ? Math.max(0, Math.min(1, 1 - x.minutes_left / x.minutes)) : x.minutes && x.started ? Math.max(0, Math.min(1, (Date.now() / 1000 - x.started) / (x.minutes * 60))) : 0;
  const slots = [0, 1].map(i => { const f = fr.find(q => q.slot === i); const mode = x.modes[i]; return f ? `<button type="button" data-zoom="${esc(f.img)}" data-cap="${esc((mm[f.mode] ? mm[f.mode].name : f.mode) + ", " + x.job)}" aria-label="Enlarge frame of ${esc(x.job)}"><img src="${esc(f.img)}" alt="" width="160" height="90"></button>` : `<div class="nof">${mode ? esc(mm[mode] ? mm[mode].name : mode) : "-"}</div>`; }).join("");
  const open = dashOpen.has(x.job);
  return `<article class="card wcard" data-job="${esc(x.job)}"><div class="wf">${slots}</div><div class="wb">
    <div class="wt"><b>${esc(x.job)}</b><span class="tag ${esc(x.state)}">${esc(x.state)}</span></div>
    <div class="pbar" role="progressbar" aria-valuenow="${Math.round(frac * 100)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${Math.round(frac * 100)}%"></i></div>
    <div class="wm"><span>steps <b>${x.env_steps == null ? "-" : Number(x.env_steps).toLocaleString()}</b></span><span>fps <b>${x.fps == null ? "-" : fmtN(x.fps, 1)}</b></span><span><b>${x.minutes_left == null ? (x.state === "finished" ? "done" : "-") : Math.round(x.minutes_left) + " min"}</b> left</span></div>
    ${(x.modes.length ? x.modes : Object.keys(x.per_mode)).map(m => { const v = x.per_mode[m]; return `<div class="wpm"><button type="button" class="linkb" data-mf="${esc(m)}">${esc(mm[m] ? mm[m].name : m)}</button><span>${v ? `return <b>${fmt(v.return, 3)}</b>, win <b>${pct(v.win_rate)}</b>` : "no episodes yet"}</span></div>`; }).join("")}
    <button type="button" class="btn sm ghost wx-t" aria-expanded="${open}" data-wx="${esc(x.job)}">${open ? "Hide curves" : "Show curves"}</button>
    <div class="wx" ${open ? "" : "hidden"}>${open ? '<div class="empty">Loading</div>' : ""}</div></div></article>`;
}
async function fillCurves(card, job) {
  const box = $(".wx", card); if (!box) return;
  try {
    const d = await api("/api/run/" + encodeURIComponent(job));
    const mc = d.mode_curves || {}, ch = Object.fromEntries((d.charts || []).map(c => [c.field, c.points]));
    box.innerHTML = (Object.keys(mc).length ? `<div class="card chart flat"><h3>Return by mode</h3>${multiChart(mc, "Return by mode for " + job, { h: 170 })}</div>` : "") +
      (ch.win_rate ? `<div class="card chart flat"><h3>Win rate</h3>${lineChart(ch.win_rate, "--s2", { label: "win rate" })}</div>` : "") + (ch.ep_return_mean ? `<div class="card chart flat"><h3>Mean return</h3>${lineChart(ch.ep_return_mean, "--s1", { label: "mean return" })}</div>` : "") || `<div class="empty">No curves yet.</div>`;
    wireCharts(box); wireMulti(box);
  } catch (e) { box.innerHTML = `<div class="empty">No curves are published for this worker.</div>`; }
}

function evalTable(r, mm, relIdx) {
  const rel = r.rounds[relIdx], prev = relIdx > 0 ? r.rounds[relIdx - 1] : null;
  let rows = Object.keys(mm).filter(k => rel.modes[k]).map(k => { const v = rel.modes[k], p = prev && prev.modes[k]; return { k, name: mm[k].name, ep: v.episodes, wins: v.wins, wr: v.win_rate, ret: v.return, dw: p && p.win_rate != null && v.win_rate != null ? v.win_rate - p.win_rate : null, dr: p && p.return != null && v.return != null ? v.return - p.return : null }; });
  if (dashMode) rows = rows.filter(x => x.k === dashMode);
  const key = dashSort.k, dir = dashSort.dir;
  rows.sort((a, b) => { const A = a[key === "mode" ? "name" : key], B = b[key === "mode" ? "name" : key]; if (A == null && B == null) return 0; if (A == null) return 1; if (B == null) return -1; return (typeof A === "string" ? A.localeCompare(B) : A - B) * dir; });
  const th = (k, label, n) => `<th class="${n ? "n" : ""} sortable ${dashSort.k === k ? (dir > 0 ? "asc" : "desc") : ""}" data-sort="${k}" tabindex="0" role="button" aria-label="Sort by ${label}">${label}</th>`;
  const dl = v => v == null ? "-" : `<span class="${v >= 0 ? "posc" : "negc"}">${v >= 0 ? "+" : ""}${fmt(v, 3)}</span>`;
  return `<div class="tw"><table class="evt"><thead><tr>${th("mode", "Mode")}${th("ep", "Episodes", 1)}${th("wins", "Wins", 1)}${th("wr", "Win rate", 1)}${th("ret", "Mean return", 1)}${th("dw", "Win rate vs " + (prev ? prev.tag : "previous"), 1)}${th("dr", "Return vs " + (prev ? prev.tag : "previous"), 1)}</tr></thead><tbody>
  ${rows.map(x => `<tr><td><a href="#/modes/${encodeURIComponent(x.k)}">${modeIcon(x.k, 16)} ${esc(x.name)}</a></td><td class="n">${x.ep}</td><td class="n">${x.wins}</td><td class="n"><b>${pct(x.wr)}</b></td><td class="n">${fmt(x.ret, 3)}</td><td class="n">${dl(x.dw)}</td><td class="n">${dl(x.dr)}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">No evaluated modes for this release${dashMode ? " and mode" : ""}.</td></tr>`}
  </tbody></table></div>`;
}
function modeCharts(r, mm) {
  const keys = Object.keys(mm).filter(k => r.rounds.some(x => x.modes[k])).filter(k => !dashMode || k === dashMode);
  if (!keys.length) return `<div class="empty">No release has been evaluated yet. Charts appear after the first evaluation.</div>`;
  const f = dashMetric;
  const lo = f === "win_rate" ? 0 : undefined, hi = f === "win_rate" ? 1 : undefined;
  return `<div class="minis">${keys.map(k => { const vals = r.rounds.map(x => x.modes[k] ? x.modes[k][f] : null), last = [...vals].reverse().find(v => v != null);
    return `<div class="card mini ${dashMode === k ? "sel" : ""}"><h4><button type="button" class="linkb" data-mf="${esc(k)}" title="Filter the dashboard to this mode">${modeIcon(k, 16)} ${esc(mm[k].name)}</button></h4><div class="big">${f === "win_rate" ? pct(last) : fmt(last, 3)}</div>${spark(vals, { lo, hi, w: 200, h: 46 })}<div class="mini-x">${r.rounds.map((x, i) => `<span title="${esc(x.tag)}: ${vals[i] == null ? "-" : f === "win_rate" ? pct(vals[i]) : fmt(vals[i], 3)}">${esc(x.tag.replace("round-", "r"))}</span>`).join("")}</div></div>`; }).join("")}</div>`;
}
function meanChart(r) {
  const labels = {}, wr = [], rt = [];
  r.rounds.forEach((x, i) => { labels[i] = x.tag; if (x.mean_win_rate != null) wr.push([i, x.mean_win_rate]); if (x.mean_return != null) rt.push([i, x.mean_return]); });
  return `<div class="grid cols-2"><div class="card chart"><h3>Mean win rate by release</h3>${wr.length ? multiChart({ "win rate": wr }, "Mean win rate by release", { xLabels: labels, yRange: [0, 1], yFmt: v => Math.round(v * 100) + "%", noLegend: true }) : `<div class="empty">Nothing evaluated yet.</div>`}</div>
  <div class="card chart"><h3>Mean return by release</h3>${rt.length ? multiChart({ "return": rt }, "Mean return by release", { xLabels: labels, noLegend: true }) : `<div class="empty">Nothing evaluated yet.</div>`}</div></div>`;
}

pages.dashboard = async () => {
  const [mmAll, o, r, w] = await Promise.all([modeMap(), api("/api/overview"), api("/api/rounds"), api("/api/workers")]);
  const mm = mmAll;
  let fr = null; try { fr = await api("/api/frames"); } catch (e) { fr = null; }
  const mkState = () => roundState({ workers: w.workers, cloud: o.cloud, rounds: r });
  view.innerHTML = `<div class="dash">
  <div class="dh"><div><h1>Dashboard</h1><p class="lede">The live training view: where the current round is, how every worker is doing and how each release compares. For the project summary see the <a href="#/overview">Overview</a>.</p></div>
    <div class="dh-actions"><span id="lbslot"></span><button type="button" class="btn sm" id="mcbtn">Mission control</button><button type="button" class="btn sm ghost" data-copy="${esc(location.href.split("#")[0])}#/dashboard">Copy link</button></div></div>
  <div id="dyn"></div></div>`;
  mountLiveBadge($("#lbslot"));
  const render = () => {
    const st = mkState();
    const totalNow = st.cur.reduce((a, x) => a + (x.env_steps || 0), 0), fpsv = st.running.filter(x => x.fps != null);
    const frames = (fr && fr.frames) || [];
    if (dashRel == null || dashRel >= r.rounds.length) dashRel = Math.max(0, r.rounds.length - 1);
    const modesPresent = Object.keys(mm);
    const wl = w.workers.filter(x => x.round === (st.round >= 0 ? (st.phase === 0 ? st.round - 1 : st.round) : x.round)).filter(x => !dashMode || x.modes.includes(dashMode) || x.per_mode[dashMode]);
    $("#dyn").innerHTML = `
    <div class="mcb">
      <div class="card mc-main"><p class="kick" style="margin-top:0">Current round</p><h2>${esc(st.headline)}</h2><p class="sub">${esc(st.detail)}</p>
        <div class="etaRow">${etaHtml(st)}</div>
        ${st.pct != null ? `<div class="pbar" style="margin-top:14px" role="progressbar" aria-valuenow="${Math.round(st.pct * 100)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${Math.round(st.pct * 100)}%"></i></div>` : ""}
        <div class="phase" aria-label="Round phases">${PHASES.map((p, i) => `<span class="${i === st.phase || (st.phase === 2 && i === 3 && false) ? "on" : st.phase > i ? "past" : ""}">${p}</span>`).join("")}</div>
        <p class="upd"><b>Next round.</b> ${esc(st.next)}</p></div>
      <div class="card mc-live"><p class="kick" style="margin-top:0">Live preview</p><div id="prevslot"><div class="empty">No live stream at the moment.</div></div></div>
    </div>
    <div class="grid stats">
      <div class="card stat"><div class="k">Steps this round</div><div class="v">${big(totalNow)}</div><div class="s">across ${st.cur.length} workers</div></div>
      <div class="card stat"><div class="k">Steps, all rounds</div><div class="v">${big(totalSteps(w))}</div><div class="s">environment steps trained</div></div>
      <div class="card stat"><div class="k">Workers running</div><div class="v">${st.running.length}<span class="of"> / ${st.cur.length || 12}</span></div><div class="s">${fpsv.length ? "mean " + fmtN(fpsv.reduce((a, x) => a + x.fps, 0) / fpsv.length, 1) + " fps each" : "no fps reported"}</div></div>
      <div class="card stat"><div class="k">Releases evaluated</div><div class="v">${r.rounds.length}</div><div class="s">${r.rounds.length ? esc(r.rounds.map(x => x.tag).join(", ")) : "none yet"}</div></div>
    </div>
    <h2 class="kick">Round timeline</h2><div class="card">${timelineHtml(r, st)}</div>
    <div class="grid cols-2" style="margin-top:14px"><div class="card chart"><h3>Environment steps per round</h3>${stepsByRound(w)}</div><div class="card"><h3>Evaluation setup</h3><p class="upd" style="margin-top:0">Each release is evaluated on all ${modesPresent.length} modes, 3 games each, at a fixed opponent strength of 0.5, against the scripted arena bots. The baseline is the unmodified VPT model.</p></div></div>
    <h2 class="kick">Mode filter</h2>
    <div class="toolbar chips"><button class="chip ${dashMode ? "" : "on"}" data-mf="">All modes</button>${modesPresent.map(k => `<button class="chip ${dashMode === k ? "on" : ""}" data-mf="${esc(k)}">${esc(mm[k].name)}</button>`).join("")}</div>
    <h2 class="kick">Workers${dashMode ? ` playing ${esc(mm[dashMode].name)}` : ""}</h2>
    ${wl.length ? `<div class="wgrid">${wl.map(x => workerCard(x, mm, frames)).join("")}</div>` : `<div class="empty">${w.workers.length ? "No worker in this round plays that mode." : "No workers reported yet. Each round starts 12 workers that train two modes each."}</div>`}
    ${frames.length ? "" : `<p class="upd">Workers write a frame of each simulator every 3 minutes from round 2 onward; the thumbnails above fill in then.</p>`}
    <h2 class="kick">Releases compared</h2>${meanChart(r)}
    <div class="toolbar" style="margin-top:14px"><span class="seg"><button class="chip ${dashMetric === "win_rate" ? "on" : ""}" data-metric="win_rate">Win rate</button><button class="chip ${dashMetric === "return" ? "on" : ""}" data-metric="return">Return</button></span><span class="upd" style="margin:0">per mode, across releases. Click a mode to filter.</span></div>
    ${modeCharts(r, mm)}
    <h2 class="kick">Evaluation table</h2>
    ${r.rounds.length ? `<div class="scrub"><label for="relr">Release</label><input id="relr" type="range" min="0" max="${r.rounds.length - 1}" step="1" value="${dashRel}" aria-valuetext="${esc(r.rounds[dashRel].tag)}"><b id="relname">${esc(r.rounds[dashRel].tag)}</b><span class="upd" style="margin:0">drag to compare releases; the change columns show the difference from the release before</span></div><div id="evalslot">${evalTable(r, mm, dashRel)}</div>` : `<div class="empty">No release has been evaluated yet.</div>`}
    <p class="upd">Snapshot ${o.cloud && o.cloud.updated ? "of the cloud status from " + when(o.cloud.updated) : "has no cloud status yet"}. ${STATIC ? "This page refreshes about once a minute." : ""}</p>`;
    mountLivePreviewOnce();
    tickEta();
    $$(".wcard").forEach(c => { if (dashOpen.has(c.dataset.job)) fillCurves(c, c.dataset.job); });
  };
  let prevMounted = false;
  function mountLivePreviewOnce() {
    // the preview keeps its own timers; re-render must not restart it, so mount once into a persistent node
    const slot = $("#prevslot"); if (!slot) return;
    if (!window.__prevNode) { window.__prevNode = document.createElement("div"); mountLivePreview(window.__prevNode, mm); }
    slot.innerHTML = ""; slot.appendChild(window.__prevNode);
  }
  window.__prevNode = null;
  render();
  every(1000, tickEta);
  every(STATIC ? 30000 : 10000, async () => { try { snapT = 0; const [o2, r2, w2] = await Promise.all([api("/api/overview"), api("/api/rounds"), api("/api/workers")]); Object.assign(o, o2); Object.assign(r, r2); Object.assign(w, w2); try { fr = await api("/api/frames"); } catch (e) { /* keep */ } render(); } catch (e) { /* keep showing */ } });
  const setMission = on => { document.body.classList.toggle("mission", on); const de = document.documentElement; if (on && de.requestFullscreen) de.requestFullscreen().catch(() => {}); if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {}); const b = $("#mcbtn"); if (b) b.textContent = on ? "Exit mission control" : "Mission control"; };
  $("#mcbtn").onclick = () => setMission(!document.body.classList.contains("mission"));
  window.fsHook = () => setMission(!document.body.classList.contains("mission"));
  const fsch = () => { if (!document.fullscreenElement && document.body.classList.contains("mission") && window.__mcFs) setMission(false); window.__mcFs = !!document.fullscreenElement; };
  document.addEventListener("fullscreenchange", fsch);
  onLeave(() => { document.removeEventListener("fullscreenchange", fsch); document.body.classList.remove("mission"); window.__prevNode = null; if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); });
  view.addEventListener("click", e => {
    const t = e.target.closest && e.target.closest("[data-mf]"); if (t) { dashMode = dashMode === t.dataset.mf ? "" : t.dataset.mf; render(); return; }
    const m = e.target.closest("[data-metric]"); if (m) { dashMetric = m.dataset.metric; render(); return; }
    const x = e.target.closest("[data-wx]"); if (x) { const j = x.dataset.wx; if (dashOpen.has(j)) dashOpen.delete(j); else dashOpen.add(j); const card = x.closest(".wcard"), box = $(".wx", card); box.hidden = !dashOpen.has(j); x.textContent = dashOpen.has(j) ? "Hide curves" : "Show curves"; x.setAttribute("aria-expanded", dashOpen.has(j)); if (dashOpen.has(j)) { box.innerHTML = '<div class="empty">Loading</div>'; fillCurves(card, j); } return; }
    const s = e.target.closest("[data-sort]"); if (s) { const k = s.dataset.sort; dashSort = { k, dir: dashSort.k === k ? -dashSort.dir : (k === "mode" ? 1 : -1) }; $("#evalslot").innerHTML = evalTable(r, mm, dashRel); }
  });
  view.addEventListener("input", e => { if (e.target.id === "relr") { dashRel = +e.target.value; $("#relname").textContent = r.rounds[dashRel].tag; e.target.setAttribute("aria-valuetext", r.rounds[dashRel].tag); $("#evalslot").innerHTML = evalTable(r, mm, dashRel); } });
  view.addEventListener("keydown", e => { const s = e.target.closest && e.target.closest("[data-sort]"); if (s && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); s.click(); } });
};
/* copy buttons: any element with data-copy */
document.addEventListener("click", async e => {
  const b = e.target.closest && e.target.closest("[data-copy]"); if (!b) return;
  const text = b.dataset.copy; const old = b.dataset.label || b.textContent; b.dataset.label = old;
  try { await navigator.clipboard.writeText(text); } catch (err) { const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e2) { /* ignore */ } ta.remove(); }
  b.textContent = "Copied"; setTimeout(() => { b.textContent = old; }, 1500);
});
