"use strict";
/* Overview and Modes. */
const isRound = t => /^round-\d+$/.test(t);
function releaseTags(r) { return r.rounds.map(x => x.tag); }
/* per release values for one mode: [{tag, win_rate, return, episodes}] in release order */
const isVpt = t => !/^(scratch|openai)-/.test(t);
const isOpenai = t => /^openai-/.test(t);
const rnum = t => { const x = /^(?:round|scratch)-(\d+)$/.exec(t); return x ? +x[1] : null; };
function modeHistory(r, key) { return r.rounds.filter(x => isVpt(x.tag)).map(x => ({ tag: x.tag, ...(x.modes[key] || { win_rate: null, return: null, episodes: 0 }) })); }

/* ---------- comparisons: ours against OpenAI's released models and against the from-scratch track ---------- */
let cmpMetric = "return", cmpView = null;
function compareData(r) {
  const vpt = r.rounds.filter(x => /^round-\d+$/.test(x.tag)), sc = r.rounds.filter(x => /^scratch-\d+$/.test(x.tag)), oa = r.rounds.filter(x => isOpenai(x.tag));
  const vn = new Map(vpt.map(x => [rnum(x.tag), x])), sn = new Map(sc.map(x => [rnum(x.tag), x]));
  const common = [...vn.keys()].filter(n => sn.has(n)).sort((a, b) => b - a);
  const ours = vpt[vpt.length - 1] || null;
  if (common.length) return { vpt, sc, oa, ours, a: vn.get(common[0]), b: sn.get(common[0]), same: true };
  return { vpt, sc, oa, ours, a: ours, b: sc[sc.length - 1] || null, same: false };
}
/* for each mode, the OpenAI release with the highest win rate there (return breaks ties) */
function openaiBest(oa, f) {
  const per = {};
  oa.forEach(rel => Object.entries(rel.modes).forEach(([k, v]) => {
    const cur = per[k];
    const better = !cur || (f === "win_rate" ? (v.win_rate ?? -1) > (cur.v.win_rate ?? -1) || ((v.win_rate ?? -1) === (cur.v.win_rate ?? -1) && (v.return ?? -1e9) > (cur.v.return ?? -1e9)) : (v.return ?? -1e9) > (cur.v.return ?? -1e9));
    if (better) per[k] = { tag: rel.tag, v };
  }));
  const overall = oa.filter(x => x.mean_win_rate != null).sort((x, y) => y.mean_win_rate - x.mean_win_rate)[0] || null;
  return { per, overall };
}
function barRows(keys, mm, A, B, f, tagB) {
  const vals = keys.flatMap(k => [A[k] && A[k][f], B[k] && B[k][f]]).filter(v => v != null);
  const lo = f === "win_rate" ? 0 : Math.min(0, ...vals), hi = f === "win_rate" ? 1 : Math.max(...vals, lo + 1e-9);
  const w = v => v == null ? 0 : Math.max(1, (v - lo) / (hi - lo) * 100), lab = v => v == null ? "-" : f === "win_rate" ? pct(v) : rtPlain(v);
  const ne = (x, y) => x && y && x.episodes !== y.episodes ? `<em class="ep" title="${x.episodes} episode(s) per mode for this one, ${y.episodes} for the other">n=${x.episodes}</em>` : "";
  return `<div class="cmp">${keys.map(k => `<div class="cmp-row"><a href="#/modes/${encodeURIComponent(k)}">${modeIcon(k, 16)} ${esc(mm[k].name)}</a><div class="cmp-b"><div class="cb"><i class="v" style="width:${w(A[k] && A[k][f])}%"></i><span>${ne(A[k], B[k])} ${lab(A[k] && A[k][f])}</span></div><div class="cb"><i class="s" style="width:${w(B[k] && B[k][f])}%"></i><span>${tagB && tagB[k] ? `<em class="tg">${esc(tagB[k])}</em>` : ""}${ne(B[k], A[k])} ${lab(B[k] && B[k][f])}</span></div></div></div>`).join("")}</div>`;
}
function compareHtml(r, mm) {
  const c = compareData(r), f = cmpMetric, isR = f === "return";
  if (!cmpView) cmpView = c.oa.length ? "openai" : "scratch";
  const mean = x => isR ? x.mean_return : x.mean_win_rate, val = v => isR ? rtPlain(v) : pct(v);
  const wins = x => Object.values(x.modes).reduce((a, v) => a + (v.wins || 0), 0);
  const expl = `<p class="cmp-ex"><b>Three tracks.</b> <b>Ours (VPT)</b> starts from OpenAI's VPT model, pretrained on about 70,000 hours of YouTube Minecraft video. <b>From scratch</b> is a small policy of about 5 million parameters, the same architecture family, with no pretraining. <b>OpenAI (released)</b> are OpenAI's own final models, evaluated as references. All three use the same arenas and evaluation; ours and the from-scratch track also share the PPO training loop.</p>
  <p class="cmp-ex"><b>What the numbers mean.</b> Return is the total reward an agent earns in a game: hits and kills raise it, damage taken and dying lower it, so closer to zero is better. Win rate is the share of games won against the scripted arena bots. Nobody has won a game yet, so win rate is 0% everywhere and return is where the differences show.</p>`;
  const labels = {}, s1 = [], s2 = [];
  c.vpt.forEach(x => { const n = rnum(x.tag); labels[n] = "round " + n; if (mean(x) != null) s1.push([n, mean(x)]); });
  c.sc.forEach(x => { const n = rnum(x.tag); labels[n] = "round " + n; if (mean(x) != null) s2.push([n, mean(x)]); });
  const oaPick = c.oa.filter(x => mean(x) != null).sort((x, y) => mean(y) - mean(x))[0] || null, xs = Object.keys(labels).map(Number);
  const series = { "VPT (round-N)": s1, "From scratch (scratch-N)": s2 };
  if (oaPick && xs.length) series["OpenAI best: " + oaPick.tag] = xs.map(n => [n, mean(oaPick)]);
  const chartOpts = { xLabels: labels, yFmt: isR ? rtPlain : v => Math.round(v * 100) + "%" }; if (!isR) chartOpts.yRange = [0, 1];
  const line = s1.length || s2.length || oaPick ? multiChart(series, "Mean " + (isR ? "return" : "win rate") + " per round for the three tracks", chartOpts) : `<div class="empty">Nothing evaluated yet.</div>`;
  let head = "", bars = "";
  if (cmpView === "openai") {
    if (!c.oa.length) bars = `<div class="empty">No OpenAI model has been evaluated yet. The reference comparison appears once <code>openai-rl-2x</code>, <code>openai-2x</code> or <code>openai-3x</code> has results.</div>`;
    else if (!c.ours) bars = `<div class="empty">No round of ours has been evaluated yet.</div>`;
    else {
      const best = openaiBest(c.oa, f), keys = Object.keys(mm).filter(k => c.ours.modes[k] || best.per[k]);
      const B = Object.fromEntries(keys.map(k => [k, best.per[k] && best.per[k].v])), T = Object.fromEntries(keys.map(k => [k, best.per[k] && best.per[k].tag]));
      const noisy = c.oa.filter(x => Object.values(x.modes).some(v => v.episodes !== 3));
      head = `<p class="cmp-head">${isR ? esc(verdict("Ours", "OpenAI's best released model", c.ours.mean_return, oaPick.mean_return, wins(c.ours), wins(oaPick))) : `Ours vs OpenAI's best released model: <b>${pct(c.ours.mean_win_rate)}</b> vs <b>${oaPick ? pct(oaPick.mean_win_rate) : "-"}</b> wins`}</p><p class="upd" style="margin-top:0"><b>${esc(c.ours.tag)}</b> (ours) against <b>${oaPick ? esc(oaPick.tag) : "-"}</b>, the OpenAI model with the best mean ${isR ? "return" : "win rate"}. The bars use the best OpenAI model in each mode, a harder bar, with its name shown.${noisy.length ? ` ${noisy.map(x => esc(x.tag)).join(", ")} ran fewer episodes per mode, so its numbers are noisier; modes where the counts differ are marked n=.` : ""}</p>`;
      bars = `<div class="cmp-legend"><span><i style="background:var(--accent)"></i>Ours ${esc(c.ours.tag)}</span><span><i style="background:var(--accent2)"></i>OpenAI, best per mode</span></div>` + barRows(keys, mm, c.ours.modes, B, f, T);
    }
  } else {
    if (!c.sc.length) bars = `<div class="empty">No from-scratch release has been evaluated yet. The per-mode comparison fills in after <code>scratch-0</code>.</div>`;
    else if (!c.a || !c.b) bars = `<div class="empty">Waiting for a VPT release to compare against.</div>`;
    else {
      const keys = Object.keys(mm).filter(k => c.a.modes[k] || c.b.modes[k]);
      head = `<p class="cmp-head">${isR ? esc(verdict("Ours", "the from-scratch model", c.a.mean_return, c.b.mean_return, wins(c.a), wins(c.b))) : `Ours vs from scratch: <b>${pct(c.a.mean_win_rate)}</b> vs <b>${pct(c.b.mean_win_rate)}</b> wins`}</p><p class="upd" style="margin-top:0">${c.same ? `Both at round ${rnum(c.a.tag)}` : `Newest of each, <b>${esc(c.a.tag)}</b> and <b>${esc(c.b.tag)}</b> (no round number has both yet)`}.</p>`;
      bars = `<div class="cmp-legend"><span><i style="background:var(--accent)"></i>VPT ${esc(c.a.tag)}</span><span><i style="background:var(--accent2)"></i>From scratch ${esc(c.b.tag)}</span></div>` + barRows(keys, mm, c.a.modes, c.b.modes, f, null);
    }
  }
  return `${expl}<div class="grid cols-2"><div class="card chart"><h3>Mean ${isR ? "return" : "win rate"} per round</h3>${line}</div><div class="card"><div class="toolbar" style="margin-top:0"><span class="seg"><button class="chip ${cmpView === "openai" ? "on" : ""}" data-cv="openai">Ours vs OpenAI</button><button class="chip ${cmpView === "scratch" ? "on" : ""}" data-cv="scratch">VPT vs from scratch</button></span><span class="seg"><button class="chip ${isR ? "on" : ""}" data-cm="return">Return</button><button class="chip ${!isR ? "on" : ""}" data-cm="win_rate">Win rate</button></span></div>${head}${bars}</div></div>`;
}
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-cm],[data-cv]"); if (!b || !window.__cmp) return;
  if (b.dataset.cm) cmpMetric = b.dataset.cm; if (b.dataset.cv) cmpView = b.dataset.cv;
  const el = $("#cmpbox"); if (el) { el.innerHTML = compareHtml(window.__cmp.r, window.__cmp.mm); wireMulti(el); }
});
function totalSteps(w) { return w.totals ? w.totals.steps_total : w.workers.reduce((a, x) => a + (x.env_steps || 0), 0); }

/* ---------- overview helpers ---------- */
const rt = v => v == null || !isFinite(v) ? "-" : (v < 0 ? "−" : v > 0 ? "+" : "") + Math.abs(v).toFixed(2);
const rtPlain = v => v == null || !isFinite(v) ? "-" : (v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
function revealIn(root) {
  const els = $$(".rv", root);
  if (reduced || !("IntersectionObserver" in window)) { els.forEach(e => e.classList.add("in")); return; }
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
  els.forEach(e => io.observe(e)); onLeave(() => io.disconnect());
}
/* videos with data-src get their source only when they are about to scroll into view; data-vp videos play while visible */
function lazyVideos(root) {
  const vids = $$("video[data-src]", root);
  if (!("IntersectionObserver" in window)) { vids.forEach(v => { v.preload = "metadata"; v.src = v.dataset.src; }); return; }
  const io = new IntersectionObserver(es => es.forEach(e => { const v = e.target; if (e.isIntersecting) { if (v.dataset.src) { v.preload = "metadata"; v.src = v.dataset.src; delete v.dataset.src; } if (v.hasAttribute("data-vp") && !reduced) v.play().catch(() => {}); } else if (v.hasAttribute("data-vp")) v.pause(); }), { rootMargin: "300px 0px" });
  vids.forEach(v => io.observe(v)); $$("video[data-vp]:not([data-src])", root).forEach(v => io.observe(v)); onLeave(() => io.disconnect());
}
function montage(box, urls) {
  const vs = $$("video", box); let i = 0, cur = 0, stopped = false;
  const load = (v, u) => { v.src = clipSrc(u); v.load(); };
  load(vs[0], urls[0]); vs[0].classList.add("on");
  if (!reduced) { vs[0].play().catch(() => {}); if (urls.length > 1) load(vs[1], urls[1]); }
  const swap = () => {
    i = (i + 1) % urls.length; const a = vs[cur], b = vs[1 - cur]; b.currentTime = 0; b.play().catch(() => {}); b.classList.add("on"); a.classList.remove("on"); cur = 1 - cur;
    setTimeout(() => { if (!stopped && urls.length > 1) { a.pause(); load(a, urls[(i + 1) % urls.length]); } }, 1000);
  };
  vs.forEach(v => v.addEventListener("timeupdate", () => { if (v === vs[cur] && urls.length > 1 && v.currentTime >= 6 && !v.dataset.sw) { v.dataset.sw = "1"; swap(); setTimeout(() => { delete v.dataset.sw; }, 2500); } }));
  vs.forEach(v => v.addEventListener("ended", () => { if (v === vs[cur] && urls.length > 1) swap(); else if (v === vs[cur]) { v.currentTime = 0; v.play().catch(() => {}); } }));
  return () => { stopped = true; vs.forEach(v => { v.pause(); v.removeAttribute("src"); }); };
}
function pickMontage(cloud, latestTag, mm) {
  const m = (cloud.clips || {})[latestTag] || {};
  const pref = ["duels_sword", "bedwars_solo", "the_bridge", "skywars_solo", "kitpvp", "duels_bow", "spleef", "tnt_run", "duels_boxing", "capture_the_wool"];
  const keys = pref.filter(k => m[k]).concat(Object.keys(m).filter(k => !pref.includes(k)).sort());
  return keys.slice(0, 10).map(k => ({ url: m[k], mode: k, name: mm[k] ? mm[k].name : k }));
}
/* The story chart: mean return per round, drawn as you scroll. */
function storyChart(pts, refs) {
  const cp = innerWidth < 640, W = cp ? 420 : 960, H = cp ? 340 : 360, m = cp ? { l: 46, r: 14, t: 34, b: 42 } : { l: 62, r: 30, t: 30, b: 46 };
  const ys = pts.map(p => p.v).concat(refs.map(q => q.v));
  const ticks = niceTicks(Math.min(...ys) - 0.15, Math.max(...ys) + 0.2, 4), lo = ticks[0], hi = ticks[ticks.length - 1];
  const sx = i => m.l + (pts.length < 2 ? .5 : i / (pts.length - 1)) * (W - m.l - m.r), sy = v => H - m.b - (v - lo) / (hi - lo) * (H - m.t - m.b);
  const d = pts.map((p, i) => (i ? "L" : "M") + sx(i).toFixed(1) + " " + sy(p.v).toFixed(1)).join("");
  const grid = ticks.map(v => `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${m.l - 8}" y="${sy(v) + 4}" text-anchor="end">${rtPlain(v)}</text>`).join("");
  const rl = refs.map(q => { const lower = refs.some(o => o !== q && (o.v > q.v || (o.v === q.v && o.cls < q.cls))); return `<line x1="${m.l}" x2="${W - m.r}" y1="${sy(q.v)}" y2="${sy(q.v)}" class="refl ${q.cls}"/><text x="${q.cls === "b" ? m.l + 8 : W - m.r}" y="${sy(q.v) + (lower ? 16 : -6)}" text-anchor="${q.cls === "b" ? "start" : "end"}" class="refT ${q.cls}">${esc(cp ? q.label.replace("baseline VPT", "baseline").replace(/^OpenAI.*/, "OpenAI") : q.label)} ${rtPlain(q.v)}</text>`; }).join("");
  const dots = pts.map((p, i) => `<g class="sdot" data-f="${pts.length < 2 ? 0 : i / (pts.length - 1)}"><circle cx="${sx(i)}" cy="${sy(p.v)}" r="6"/><text x="${sx(i)}" y="${sy(p.v) - 14}" text-anchor="middle" class="sv">${rtPlain(p.v)}</text><text x="${sx(i)}" y="${H - 14}" text-anchor="middle" class="sl">${esc(cp ? p.label.replace("round-", "r") : p.label)}</text></g>`).join("");
  return `<svg class="story ${cp ? "c" : ""}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mean return per game for each training round: ${pts.map(p => p.label + " " + rtPlain(p.v)).join(", ")}">${grid}${rl}<path class="sline" pathLength="1" d="${d}"/>${dots}</svg>`;
}
function bindScrollDraw(box) {
  const path = $(".sline", box), dots = $$(".sdot", box);
  const set = p => { if (path) path.style.strokeDashoffset = String(1 - p); dots.forEach(g => g.classList.toggle("on", p >= +g.dataset.f - 0.001)); };
  if (reduced) { set(1); return; }
  set(0);
  let raf = 0;
  const upd = () => { raf = 0; const r = box.getBoundingClientRect(), vh = innerHeight; set(Math.max(0, Math.min(1, (vh * 0.88 - r.top) / (r.height * 0.9 + vh * 0.1)))); };
  const on = () => { if (!raf) raf = requestAnimationFrame(upd); };
  addEventListener("scroll", on, { passive: true }); addEventListener("resize", on); upd();
  onLeave(() => { removeEventListener("scroll", on); removeEventListener("resize", on); });
}
function versusBars(ours, them, mm) {
  const rows = Object.keys(mm).filter(k => ours.modes[k] && them.modes[k] && ours.modes[k].return != null && them.modes[k].return != null)
    .map(k => ({ k, name: mm[k].name, a: ours.modes[k].return, b: them.modes[k].return, d: ours.modes[k].return - them.modes[k].return })).sort((x, y) => y.d - x.d);
  const mx = Math.max(0.01, ...rows.map(x => Math.abs(x.d)));
  return { rows, html: `<div class="dv" role="list">${rows.map(x => `<div class="dv-row" role="listitem" title="${esc(x.name)}: ours ${rtPlain(x.a)}, theirs ${rtPlain(x.b)}"><a class="dv-n" href="#/modes/${encodeURIComponent(x.k)}">${modeIcon(x.k, 16)}<span>${esc(x.name)}</span></a><div class="dv-bar"><span class="dv-axis"></span><i class="${x.d >= 0 ? "pos" : "neg"}" style="${x.d >= 0 ? "left:50%" : "right:50%"};width:${Math.max(1.5, Math.abs(x.d) / mx * 50)}%"></i></div><b class="dv-v ${x.d >= 0 ? "posc" : "negc"}">${rt(x.d)}</b></div>`).join("")}</div>` };
}
/* a plain sentence for a comparison of mean return */
function verdict(aName, bName, a, b, winsA, winsB) {
  const d = a - b;
  if (winsA > 0 || winsB > 0) return `${aName} ${d >= 0 ? "scores higher" : "scores lower"} than ${bName}: ${rtPlain(a)} against ${rtPlain(b)} mean return`;
  if (d >= 1) return `${aName} loses far less badly than ${bName}: ${rtPlain(a)} vs ${rtPlain(b)}`;
  if (d > 0.2) return `${aName} loses less badly than ${bName}: ${rtPlain(a)} vs ${rtPlain(b)}`;
  if (d >= -0.2) return `${aName} and ${bName} lose about equally badly: ${rtPlain(a)} vs ${rtPlain(b)}`;
  return `${aName} loses more badly than ${bName}: ${rtPlain(a)} vs ${rtPlain(b)}`;
}

pages.overview = async () => {
  const [o, r, w, md, cloud] = await Promise.all([api("/api/overview"), api("/api/rounds"), api("/api/workers"), api("/api/modes"), api("/api/cloud")]);
  const mm = Object.fromEntries(md.modes.map(m => [m.key, m]));
  const vpt = r.rounds.filter(x => /^round-\d+$/.test(x.tag)), oa = r.rounds.filter(x => isOpenai(x.tag) && x.mean_return != null);
  const base = r.rounds.find(x => x.tag === "baseline"), first = vpt[0], last = vpt[vpt.length - 1];
  const bestOa = oa.slice().sort((x, y) => y.mean_return - x.mean_return)[0] || null;
  const sumWins = x => Object.values(x.modes).reduce((a, v) => a + (v.wins || 0), 0), sumEps = x => Object.values(x.modes).reduce((a, v) => a + (v.episodes || 0), 0);
  const games = r.rounds.reduce((a, x) => a + sumEps(x), 0), wins = r.rounds.reduce((a, x) => a + sumWins(x), 0);
  const steps = w.totals ? w.totals.steps_total : totalSteps(w);
  const st = typeof roundState === "function" ? roundState({ workers: w.workers.filter(x => x.track !== "scratch"), cloud: o.cloud, rounds: r }) : null;
  const montageList = last ? pickMontage(cloud, last.tag, mm) : [];
  const pairModes = last && first ? Object.keys(mm).filter(k => ((cloud.clips || {})[first.tag] || {})[k] && ((cloud.clips || {})[last.tag] || {})[k] && first.modes[k] && last.modes[k]) : [];
  pairModes.sort((a, b) => (last.modes[b].return - first.modes[b].return) - (last.modes[a].return - first.modes[a].return));
  const vs = last && bestOa ? versusBars(last, bestOa, mm) : null, ahead = vs ? vs.rows.filter(x => x.d > 0).length : 0;
  const wall = md.modes.filter(m => m.clip && okUrl(m.clip.url));
  const wlast = (m) => { const h = last && last.modes[m.key]; return h ? h.return : null; };
  view.innerHTML = `
  <section class="hero2" id="hero">
    <div class="hv" aria-hidden="true"><video muted playsinline preload="metadata" tabindex="-1"></video><video muted playsinline preload="metadata" tabindex="-1"></video></div>
    <div class="hero-scrim"></div>
    <div class="hero-in">
      <div class="lbslot" id="lbslot"></div>
      <p class="eyebrow">VPT Arena &middot; open research</p>
      <h1>An AI learning to fight in Minecraft.</h1>
      <p class="sub">One network plays ${o.modes} game modes from pixels, with a keyboard and mouse. ${first && last ? `Its average score has gone from ${rt(first.mean_return)} to ${rt(last.mean_return)}. ` : ""}${wins} wins in ${games.toLocaleString()} evaluation games. Yet.</p>
      <div class="cta"><a class="btn primary lg" href="#/live">Watch it live</a><button type="button" class="btn lg glass" id="trailerbtn" hidden>Watch the trailer</button>${pages.simulate ? `<a class="btn lg glass" href="#/simulate">Run a simulation</a>` : ""}</div>
      <div class="hero-cap" id="herocap"></div>
    </div>
  </section>
  <section class="counters rv" aria-label="Headline numbers">
    <div class="ct"><div class="v" data-n="${steps}" data-big="1">-</div><div class="k">Environment steps trained</div></div>
    <div class="ct"><div class="v" data-n="${vpt.length}">-</div><div class="k">Training rounds, all evaluated</div></div>
    <div class="ct"><div class="v" data-n="${o.modes}">-</div><div class="k">Game modes</div></div>
    <div class="ct"><div class="v" data-n="${wins}">-</div><div class="k">Wins in ${games.toLocaleString()} evaluation games</div></div>
  </section>
  ${st ? `<a class="statusband rv" href="#/dashboard"><span class="dot ${st.live ? "on" : ""}"></span><span><b>${esc(st.headline)}.</b> ${esc(st.live ? st.detail : "Training is paused at the free-compute cap.")}</span><span class="go">Dashboard</span></a>` : ""}

  ${first && last && vpt.length > 1 ? `<section class="sec rv"><p class="eyebrow">The story so far</p>
    <h2>It started at ${rt(first.mean_return)}. Round by round it climbed to ${rt(last.mean_return)}.</h2>
    <p class="sec-sub">Return is the total reward an agent earns in one game. Landing hits and kills raise it; taking damage and dying lower it. Closer to zero is better. No model has won a game yet, so return is the clearest sign of progress.</p>
    <div class="card storybox" id="storybox">${storyChart(vpt.map(x => ({ v: x.mean_return, label: x.tag })), [base && { v: base.mean_return, label: "baseline VPT", cls: "b" }, bestOa && { v: bestOa.mean_return, label: "OpenAI " + bestOa.tag.replace("openai-", ""), cls: "o" }].filter(Boolean))}</div>
    <div class="rcards">${vpt.map((x, i) => { const p = vpt[i - 1]; const dlt = p ? x.mean_return - p.mean_return : null; return `<div class="rcard"><b>${esc(x.tag)}</b><span class="rc-v" data-r="${x.mean_return}">${rtPlain(x.mean_return)}</span><span class="rc-d ${dlt == null ? "" : dlt >= 0.02 ? "posc" : dlt <= -0.02 ? "negc" : ""}">${dlt == null ? "start" : Math.abs(dlt) < 0.02 ? "about level" : (dlt >= 0 ? "up " : "down ") + Math.abs(dlt).toFixed(2)}</span><span class="rc-w">${sumWins(x)} wins</span></div>`; }).join("")}</div>
    ${pairModes.length ? `<div class="pair rv" id="pair"><div class="pair-h"><h3>The same mode, ${esc(first.tag)} and ${esc(last.tag)}</h3><label class="fld inl"><span class="sr">Mode</span><select id="pairmode" aria-label="Mode to compare">${pairModes.map(k => `<option value="${esc(k)}">${esc(mm[k].name)}</option>`).join("")}</select></label></div><div class="pair-v" id="pairv"></div></div>` : ""}
  </section>` : ""}

  ${vs && vs.rows.length ? `<section class="sec rv"><p class="eyebrow">Versus</p>
    <h2>${esc(verdict("Ours", "OpenAI's best released model", last.mean_return, bestOa.mean_return, sumWins(last), sumWins(bestOa)))}</h2>
    <p class="sec-sub">${esc(last.tag)} (ours) against ${esc(bestOa.tag)}, the OpenAI release with the best mean return. The bars show the gap in return, per mode: right means ours is better, left means OpenAI's is. Ours is ahead in ${ahead} of ${vs.rows.length} modes. ${sumWins(last) + sumWins(bestOa) === 0 ? "Neither has won a game." : ""}</p>
    <div class="card">${vs.html}<div class="dv-legend"><span><i class="pos"></i>ours is better</span><span><i class="neg"></i>OpenAI is better</span></div></div>
    <p class="upd"><a href="#/dashboard">More comparisons on the Dashboard</a>, including win rate and the from-scratch track.</p></section>` : ""}

  ${wall.length ? `<section class="sec rv"><p class="eyebrow">All ${wall.length} modes</p><h2>Watch it play every one.</h2>
    <p class="sec-sub">Five-second clips from ${esc(last ? last.tag : "the newest release")}. Hover or tap to play, open a mode for its full history.</p>
    <div class="wall">${wall.map(m => `<a class="tile" href="#/modes/${encodeURIComponent(m.key)}" aria-label="${esc(m.name)}"><video muted loop playsinline preload="none" data-src="${esc(clipSrc(m.clip.url))}" data-hover></video><span class="tile-n">${modeIcon(m.key, 16)}${esc(m.name)}</span>${wlast(m) != null ? `<span class="tile-r">${rtPlain(wlast(m))}</span>` : ""}</a>`).join("")}</div></section>` : ""}

  <section class="sec rv"><p class="eyebrow">Where it's at</p><h2>Honest status.</h2>
    <div class="grid cols3 status3">
      <div class="card"><h3>What works</h3><ul><li>${vpt.length} training rounds on free CPU runners, each evaluated on all ${o.modes} modes.</li><li>Average return up from ${first ? rt(first.mean_return) : "-"} to ${last ? rt(last.mean_return) : "-"}${bestOa ? `, against ${rt(bestOa.mean_return)} for OpenAI's best released model` : ""}.</li><li>A from-scratch comparison track, a live stream and a simulation lab.</li></ul></div>
      <div class="card"><h3>What does not</h3><ul><li>${wins} wins in ${games.toLocaleString()} evaluation games, for every model including OpenAI's.</li>${vpt.length > 2 && Math.abs(last.mean_return - vpt[vpt.length - 2].mean_return) < 0.05 ? `<li>Progress has levelled off: ${esc(vpt[vpt.length - 2].tag)} is ${rt(vpt[vpt.length - 2].mean_return)}, ${esc(last.tag)} is ${rt(last.mean_return)}.</li>` : ""}<li>Reward alone is a slow teacher for PvP.</li></ul></div>
      <div class="card"><h3>What is next</h3><ul><li>Data is the bottleneck: it needs PvP demonstrations, from recorded human games.</li><li>A teacher-bot attempt to generate them failed and was stopped.</li><li>Training is paused at the free-compute cap.</li></ul></div>
    </div></section>
  <p class="upd">Built on OpenAI's Video PreTraining model. The numbers on this page come from the published evaluation results; open the <a href="#/dashboard">Dashboard</a> for the details.</p>`;
  $$(".counters .v[data-n]").forEach(el => counter(el, +el.dataset.n, el.dataset.big ? { fmt: big } : {}));
  revealIn(view); lazyVideos(view);
  initTrailer();
  if (typeof mountLiveBadge === "function") mountLiveBadge($("#lbslot"));
  const sb = $("#storybox"); if (sb) bindScrollDraw(sb);
  $$(".rc-v").forEach(el => counter(el, Math.abs(+el.dataset.r), { fmt: v => (+el.dataset.r < 0 ? "−" : "") + v.toFixed(2) }));
  /* hover tiles */
  view.addEventListener("pointerover", e => { const t = e.target.closest && e.target.closest(".tile"); if (t && e.pointerType === "mouse") { const v = $("video", t); if (v && v.src) v.play().catch(() => {}); } });
  view.addEventListener("pointerout", e => { const t = e.target.closest && e.target.closest(".tile"); if (t && !t.contains(e.relatedTarget)) { const v = $("video", t); if (v) { v.pause(); } } });
  view.addEventListener("click", e => { const t = e.target.closest && e.target.closest(".tile"); if (t && matchMedia("(hover:none)").matches) { const v = $("video", t); if (v && v.paused && !t.dataset.tapped) { e.preventDefault(); t.dataset.tapped = "1"; v.play().catch(() => {}); } } });
  /* side-by-side */
  const drawPair = () => {
    const k = $("#pairmode").value, A = cloud.clips[first.tag][k], B = cloud.clips[last.tag][k];
    $("#pairv").innerHTML = [[first, A], [last, B]].map(([x, u], i) => `<figure class="pv"><div class="pv-box"><video muted loop playsinline preload="metadata" data-src="${esc(clipSrc(u))}" data-vp></video></div><figcaption><b>${esc(x.tag)}</b><span class="pv-r">return ${rtPlain(x.modes[k].return)}</span></figcaption></figure>`).join("");
    lazyVideos($("#pairv"));
  };
  if ($("#pairmode")) { $("#pairmode").onchange = drawPair; drawPair(); }
  /* hero background: the live stream when it is up, otherwise a montage of the newest clips */
  const box = $(".hv", $("#hero")), cap = $("#herocap");
  let stopHero = () => {};
  const startMontage = () => { if (!montageList.length) return; stopHero = montage(box, montageList.map(c => c.url)); const vs2 = $$("video", box); let ci = 0; cap.innerHTML = `<span class="tag">${esc(last.tag)}</span> ${esc(montageList[0].name)}`; vs2.forEach(v => v.addEventListener("playing", () => { const idx = montageList.findIndex(c => clipSrc(c.url) === (v.getAttribute("src") || "")); if (idx >= 0) cap.innerHTML = `<span class="tag">${esc(last.tag)}</span> ${esc(montageList[idx].name)}`; })); };
  if (STATIC && !reduced) {
    fetch("/live/status.json", { cache: "no-store" }).then(x => x.json()).then(d => {
      if (d.online && d.status && d.status.hls && typeof playHls === "function") {
        const v = $("video", box); v.classList.add("on"); let failed = false;
        stopHero = playHls(v, "/live/hls/30/index.m3u8", () => { if (failed) return; failed = true; stopHero(); v.classList.remove("on"); startMontage(); });
        cap.textContent = "Live from the cloud arena. The video runs a few seconds behind.";
      } else startMontage();
    }).catch(startMontage);
  } else startMontage();
  onLeave(() => stopHero());
};

/* ---------- modes ---------- */
function modeCard(m, hist) {
  const ours = hist.filter(h => /^round-/.test(h.tag)), rv = ours.map(h => h.return), lastH = [...ours].reverse().find(h => h.return != null), firstH = ours.find(h => h.return != null);
  const evs = Object.entries(m.events), shown = evs.slice(0, 4), wins = lastH ? (lastH.wins || 0) : 0, eps = lastH ? lastH.episodes : 0;
  const gain = lastH && firstH && lastH !== firstH ? lastH.return - firstH.return : null;
  return `<article class="card mode">
    <div class="m-media">${m.clip && okUrl(m.clip.url) ? hoverClip(m.clip.url, m.name + " " + m.clip.tag, modeIcon(m.key, 22), m.clip.url60, true) : noClip(modeIcon(m.key, 40))}</div>
    <div class="m-body">
      <h3><span class="m-ic">${modeIcon(m.key, 20)}</span><a href="#/modes/${encodeURIComponent(m.key)}">${esc(m.name)}</a></h3>
      <div class="tags"><span class="tag ${m.ruleset}">${m.ruleset === "modern" ? "1.9+ cooldown" : "1.8 combat"}</span><span class="tag">team ${m.team_size}</span></div>
      <p>${esc(m.summary)}</p>
      <div class="m-trend"><div>${spark(rv, { w: 110, h: 38 })}</div><div class="m-wr"><b>${rtPlain(lastH ? lastH.return : null)}</b><span>return per game${gain != null ? `, ${gain >= 0 ? "up" : "down"} ${Math.abs(gain).toFixed(2)} since ${esc(firstH.tag)}` : lastH ? ", " + esc(lastH.tag) : ", not evaluated"}</span><span>${lastH ? `${wins} wins in ${eps} games` : ""}</span></div></div>
      <div class="ev">${shown.map(([k, w]) => `<span class="${w < 0 ? "neg" : "pos"}">${esc(k)} <b>${w > 0 ? "+" : ""}${w}</b></span>`).join("")}${evs.length > 4 ? `<span class="more">+${evs.length - 4}</span>` : ""}</div>
    </div></article>`;
}
pages.modes = async args => {
  if (args && args[0]) return pages.modeDetail(args[0]);
  const [d, r] = await Promise.all([api("/api/modes"), api("/api/rounds")]);
  view.innerHTML = `<h1>Modes</h1><p class="lede">${d.modes.length} game modes. The same network plays all of them; a learned embedding tells it which one it is in. Each card shows the mean return per game across our training rounds (closer to zero is better) and how many games were won. Reward events are the game signals that return is built from, with their weights.</p>
  <div class="toolbar"><input type="search" id="q" placeholder="Filter modes" aria-label="Filter modes"><button class="chip on" data-r="">All</button><button class="chip" data-r="modern">Modern</button><button class="chip" data-r="legacy">Legacy</button></div>
  <div class="grid cols modegrid" id="mgrid"></div>`;
  let rs = "", q = "";
  const draw = () => {
    const list = d.modes.filter(m => (!rs || m.ruleset === rs) && (!q || (m.name + m.key + m.summary).toLowerCase().includes(q)));
    $("#mgrid").innerHTML = list.map(m => modeCard(m, modeHistory(r, m.key))).join("") || `<div class="empty">no modes match</div>`;
    lazyVideos($("#mgrid"));
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
    <div class="card stat"><div class="k">Latest return</div><div class="v">${rtPlain([...hist].reverse().find(h => h.return != null && /^round-/.test(h.tag))?.return)}</div><div class="s">mean per game, closer to zero is better</div></div>
    <div class="card stat"><div class="k">Latest win rate</div><div class="v">${pct([...hist].reverse().find(h => h.win_rate != null && /^round-/.test(h.tag))?.win_rate)}</div><div class="s">against the scripted arena bots</div></div>
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

/* ---------- trailer: shown only when the video exists in KV; a cinematic cut appears when its key does ---------- */
let trailerP = null;
function trailerInfo() {
  if (!STATIC) return Promise.resolve(null);
  if (!trailerP) {
    const has = u => fetch(u, { headers: { range: "bytes=0-0" }, cache: "no-store" }).then(r => r.ok || r.status === 206).catch(() => false);
    trailerP = Promise.all([has("/trailer.mp4"), has("/trailer-vertical.mp4"), has("/trailer-60.mp4"), has("/trailer-cinematic.mp4"), has("/trailer-cinematic-60.mp4"), has("/trailer-theatrical.mp4"), has("/trailer-theatrical-60.mp4")])
      .then(([main, vertical, p60, cine, cine60, theat, theat60]) => main || cine || theat ? { main, vertical, p60, cine, cine60, theat, theat60 } : null);
  }
  return trailerP;
}
async function initTrailer() {
  const b = $("#trailerbtn"); if (!b) return;
  const t = await trailerInfo(); if (!t || !b.isConnected) return;
  b.hidden = false; b.onclick = () => openTrailer(t);
}
function openTrailer(t, cut) {
  let ov = $("#trailerbox");
  if (!ov) { ov = document.createElement("div"); ov.id = "trailerbox"; ov.className = "lightbox trl"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true"); ov.setAttribute("aria-label", "Trailer"); document.body.appendChild(ov);
    ov.addEventListener("click", e => { if (e.target === ov || e.target.closest(".lb-close")) { const v = $("video", ov); if (v) v.pause(); ov.hidden = true; } const c = e.target.closest("[data-cut]"); if (c && ov._t) openTrailer(ov._t, c.dataset.cut); });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !ov.hidden) { const v = $("video", ov); if (v) v.pause(); ov.hidden = true; } }); }
  ov._t = t; cut = cut || (t.main ? "standard" : t.cine ? "cinematic" : "theatrical");
  const portrait = innerWidth < innerHeight && innerWidth < 760 && t.vertical && cut === "standard";
  const u30 = cut === "theatrical" ? "/trailer-theatrical.mp4" : cut === "cinematic" ? "/trailer-cinematic.mp4" : portrait ? "/trailer-vertical.mp4" : "/trailer.mp4";
  const u60 = cut === "theatrical" ? (t.theat60 ? "/trailer-theatrical-60.mp4" : "") : cut === "cinematic" ? (t.cine60 ? "/trailer-cinematic-60.mp4" : "") : !portrait && t.p60 ? "/trailer-60.mp4" : "";
  const src = getFps() === 60 && u60 ? u60 : u30;
  const avail = [["standard", "Standard cut", t.main], ["cinematic", "Cinematic cut", t.cine], ["theatrical", "Theatrical trailer", t.theat]].filter(c => c[2]);
  const cuts = avail.length > 1 ? `<div class="cuts" role="group" aria-label="Trailer cut">${avail.map(c => `<button type="button" class="chip ${cut === c[0] ? "on" : ""}" data-cut="${c[0]}">${c[1]}</button>`).join("")}</div>` : "";
  ov.innerHTML = `<button type="button" class="lb-close" aria-label="Close trailer">Close</button>${cuts}<div class="trl-box vbox ${portrait ? "vert" : ""}" data-fsbox data-u30="${u30}" data-u60="${u60}"><video controls playsinline autoplay src="${src}" aria-label="VPT Arena trailer, ${cut} cut"></video><div class="vtools">${fpsBtn(u60)}${fsBtn}</div></div>`;
  ov.hidden = false; lastBox = $(".trl-box", ov); $(".lb-close", ov).focus();
}
