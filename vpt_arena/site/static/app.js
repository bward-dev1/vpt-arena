"use strict";
/* VPT Arena site core: helpers, data access, charts, icons, clips, router. Pages live in pages-*.js, start-up in boot.js. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const view = $("#view");
const PAGES = [["overview", "Overview"], ["dashboard", "Dashboard"], ["simulate", "Simulate"], ["training", "Training"], ["modes", "Modes"],
  ["league", "League"], ["data", "Data"], ["live", "Live"], ["docs", "Docs"]];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const trimZ = t => t.includes(".") ? t.replace(/0+$/, "").replace(/\.$/, "") : t;
const fmt = (v, d = 3) => v == null || !isFinite(v) ? "-" : Math.abs(v) >= 1000 ? Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 }) : trimZ(Number(v).toPrecision(Math.max(d, 1)));
const fmtN = (v, d = 1) => v == null || !isFinite(v) ? "-" : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtH = h => h == null ? "-" : h >= 10 ? h.toFixed(1) : h >= 0.01 ? h.toFixed(2) : h === 0 ? "0" : Number(h.toPrecision(2)).toString();
const big = v => v == null || !isFinite(v) ? "-" : Math.abs(v) >= 1e6 ? trimZ((v / 1e6).toFixed(2)) + "M" : Math.abs(v) >= 1e4 ? trimZ((v / 1e3).toFixed(1)) + "k" : Math.round(v).toLocaleString();
const pct = v => v == null ? "-" : Math.round(v * 100) + "%";
const ago = ts => { if (!ts) return "-"; const s = Date.now() / 1000 - ts; if (s < 90) return Math.max(0, Math.round(s)) + " s ago"; if (s < 5400) return Math.round(s / 60) + " min ago"; if (s < 129600) return Math.round(s / 3600) + " h ago"; return new Date(ts * 1000).toLocaleDateString(); };
const when = ts => ts ? new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "-";
const clock = ts => ts ? new Date(ts * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "-";
const span = sec => { sec = Math.max(0, Math.round(sec)); const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60; return h ? `${h} h ${String(m).padStart(2, "0")} min` : m ? `${m} min ${String(s).padStart(2, "0")} s` : `${s} s`; };
const SRC_NAMES = { human: "Human", idm: "IDM-labelled", contractor: "Contractor", other: "Other" };
const REPO_URL = "https://github.com/bward-dev1/vpt-arena";

/* ---------- data: one snapshot on the public site, /api/* locally ---------- */
const STATIC = !!window.VPT_STATIC;
let snap = null, snapT = 0, snapP = null;
async function snapshot(force) {
  if (snap && !force && Date.now() - snapT < 30000) return snap;
  if (!snapP) snapP = (async () => {
    let r = null;
    if (window.VPT_EARLY) { try { r = await window.VPT_EARLY; } catch (e) { r = null; } window.VPT_EARLY = null; }
    if (!r || !r.ok) r = await fetch("/data.json", { cache: "no-store" });
    if (!r.ok) throw new Error("no data published yet");
    snap = await r.json(); snapT = Date.now(); return snap;
  })().finally(() => { snapP = null; });
  return snapP;
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
let stampTs = null;
function stamp(ts) {
  stampTs = ts;
  const f = $("#stamp");
  if (f) f.textContent = ts ? "Data updated " + when(ts) : "";
  paintPill();
}
function paintPill() {
  if (!STATIC) return;
  const p = $("#livepill"); if (!p) return;
  const fresh = stampTs && Date.now() / 1000 - stampTs < 900;
  p.className = "pill " + (fresh ? "on" : "off");
  $("span", p).textContent = stampTs ? "Updated " + ago(stampTs) : "no data yet";
}
let timers = [], cleanups = [];
function every(ms, fn) { timers.push(setInterval(fn, ms)); }
function onLeave(fn) { cleanups.push(fn); }
function clearTimers() { timers.forEach(clearInterval); timers = []; cleanups.forEach(f => { try { f(); } catch (e) { /* ignore */ } }); cleanups = []; window.fsHook = null; }
const modeMap = async () => Object.fromEntries((await api("/api/modes")).modes.map(m => [m.key, m]));
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- pixel icons (one bitmap per mode family; # = ink, a = accent, b = warm) ---------- */
const BITMAPS = {
  sword: ["......##", ".....###", "....###.", "#..###..", ".####...", "..##....", ".b.#....", "b......."],
  swords: ["#......#", "##....##", ".##..##.", "..####..", "..####..", ".##..##.", "bb....bb", "b......b"],
  heart: [".##..##.", "########", "########", "########", ".######.", "..####..", "...##...", "........"],
  apple: ["....a...", "...a....", ".##.##..", "######..", "######..", "######..", ".####...", "..##...."],
  potion: ["..####..", "...##...", "...##...", "..####..", ".######.", ".#aaaa#.", ".######.", "..####.."],
  ring: ["..####..", ".#....#.", "#......#", "#..aa..#", "#..aa..#", "#......#", ".#....#.", "..####.."],
  glove: ["..####..", ".######.", "########", "########", "########", ".#####..", "..bbbb..", "..bbbb.."],
  bow: ["###.....", "..##....", "...#.#..", "...#..#.", "...#..#.", "...#.#..", "..##....", "###....."],
  bolt: ["....###.", "...###..", "..###...", ".######.", "...###..", "..##....", ".##.....", "##......"],
  block: ["########", "#......#", "#.####.#", "#.#aa#.#", "#.#aa#.#", "#.####.#", "#......#", "########"],
  bed: ["........", ".aa.....", ".aa.....", "########", "########", "########", "#......#", "#......#"],
  cloud: ["........", "...###..", "..#####.", ".#######", "########", ".######.", "..b..b..", ".b..b..."],
  bridge: ["........", "........", "########", "########", ".#....#.", ".#....#.", ".#....#.", ".#....#."],
  crown: ["#..#..#.", "##.##.##", "########", "########", ".######.", "........", "........", "........"],
  flag: ["#.......", "#aaaaaa.", "#aaaaa..", "#aaaaaa.", "#.......", "#.......", "#.......", "#......."],
  shovel: [".....###", "....###.", "...##...", "..##....", ".##.....", "###.....", "##b.....", "........"],
  tnt: [".....a..", "....a...", "########", "#......#", "#.#.#.##", "#......#", "#######.", "........"],
  boot: [".####...", ".####...", ".####...", ".####...", ".####...", ".#######", "########", "########"],
  grid: ["#.#.#.#.", ".#.#.#.#", "#.#.#.#.", ".#.#.#.#", "#.#.#.#.", ".#.#.#.#", "#.#.#.#.", ".#.#.#.#"],
};
const MODE_ICON = { survival: "heart", duels_sword: "sword", duels_classic: "swords", duels_uhc: "apple", duels_nodebuff: "potion", duels_sumo: "ring",
  duels_boxing: "glove", duels_bow: "bow", duels_combo: "bolt", build_uhc: "block", bedwars_solo: "bed", bedwars_doubles: "bed", bedwars_squads: "bed",
  skywars_solo: "cloud", skywars_doubles: "cloud", the_bridge: "bridge", uhc: "apple", survival_games: "crown", kitpvp: "swords",
  capture_the_wool: "flag", spleef: "shovel", tnt_run: "tnt", parkour_duel: "boot" };
const ICON_CACHE = {};
function pixelIcon(name, size = 28) {
  const bm = BITMAPS[name] || BITMAPS.grid, h = bm.length, w = bm[0].length, key = name + size;
  if (ICON_CACHE[key]) return ICON_CACHE[key];
  const g = { "#": "", a: "", b: "" };
  bm.forEach((row, y) => [...row].forEach((c, x) => { if (g[c] !== undefined) g[c] += `M${x} ${y}h1v1h-1z`; }));
  const out = `<svg class="px" width="${size}" height="${size}" viewBox="0 0 ${w} ${h}" shape-rendering="crispEdges" aria-hidden="true"><path d="${g["#"]}" fill="currentColor"/><path d="${g.a}" fill="var(--accent)"/><path d="${g.b}" fill="var(--warn)"/></svg>`;
  return (ICON_CACHE[key] = out);
}
const modeIcon = (key, size) => pixelIcon(MODE_ICON[key] || "grid", size);

/* ---------- charts (hand-written SVG) ---------- */
const COLORS = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"];
function niceTicks(lo, hi, n = 4) {
  if (lo === hi) { const p = Math.abs(lo) || 1; lo -= p * .5; hi += p * .5; }
  const sp = hi - lo, raw = sp / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
  const a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
  for (let v = a; v <= b + step / 1e6; v += step) t.push(+v.toPrecision(12));
  return t;
}
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
  const d = points.map((p, i) => (i ? "L" : "M") + sx(p[0]).toFixed(1) + " " + sy(p[1]).toFixed(1)).join("");
  const area = d + `L${sx(xhi).toFixed(1)} ${sy(ylo).toFixed(1)}L${sx(xlo).toFixed(1)} ${sy(ylo).toFixed(1)}Z`;
  const grid = yt.map(v => `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${m.l - 6}" y="${sy(v) + 4}" text-anchor="end">${tickFmt(v)}</text>`).join("");
  const xl = xt.map(v => `<text x="${sx(v)}" y="${H - 6}" text-anchor="middle">${tickFmt(v)}</text>`).join("");
  const dot = points.length <= 40 ? points.map(p => `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="2.5" fill="var(${color})"/>`).join("") : "";
  return `<svg class="ch" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "chart")}" data-pts='${JSON.stringify(points.map(p => [+p[0].toPrecision(8), +p[1].toPrecision(6)]))}' data-geo="${[m.l, W - m.r, m.t, H - m.b, xlo, xhi, ylo, yhi].join(",")}">
    ${grid}${xl}<path class="ar" d="${area}" style="fill:var(${color})"/><path class="ln" pathLength="1" d="${d}" style="stroke:var(${color})"/>${dot}
    <g class="hv" style="display:none"><line class="gl" y1="${m.t}" y2="${H - m.b}" style="stroke:var(--line2)"/><circle r="4" fill="var(${color})" stroke="var(--panel)" stroke-width="2"/><g class="tip"><rect rx="6" height="22" fill="var(--panel2)" stroke="var(--line2)"/><text y="15" x="8" style="fill:var(--text)"></text></g></g>
    <rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg>`;
}
function wireCharts(root) {
  $$("svg.ch[data-pts]", root).forEach(svg => {
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
  return rows.map(([k, v, label]) => `<div class="bl"><span>${esc(k)}</span><div class="bar"><i style="width:${Math.max(0, Math.min(100, v / max * 100))}%"></i></div><span class="mono">${esc(label)}</span></div>`).join("");
}
const DASH = ["", "", "", "", "", "", "6 3", "6 3", "6 3", "6 3", "6 3", "6 3", "2 3", "2 3", "2 3", "2 3", "2 3", "2 3"];
/* series: {name: [[x,y],...]} with numeric x. opts.xLabels maps x to a label (categorical axes). Hover shows every series at the nearest x. */
function multiChart(series, label, opts = {}) {
  const W = 480, H = opts.h || 220, m = { l: 46, r: 14, t: 10, b: 26 };
  const names = Object.keys(series).filter(k => series[k].length);
  if (!names.length) return `<div class="empty">No data yet.</div>`;
  const all = names.flatMap(k => series[k]);
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const xlo = Math.min(...xs), xhi = Math.max(...xs);
  const yt = opts.yRange ? niceTicks(opts.yRange[0], opts.yRange[1]) : niceTicks(Math.min(...ys), Math.max(...ys)), ylo = yt[0], yhi = yt[yt.length - 1];
  const sx = x => m.l + (xhi === xlo ? .5 : (x - xlo) / (xhi - xlo)) * (W - m.l - m.r);
  const sy = y => H - m.b - (yhi === ylo ? .5 : (y - ylo) / (yhi - ylo)) * (H - m.t - m.b);
  const xt = opts.xLabels ? Object.keys(opts.xLabels).map(Number) : niceTicks(xlo, xhi, 4).filter(v => v >= xlo - 1e-9 && v <= xhi + 1e-9);
  const yf = opts.yFmt || tickFmt;
  const grid = yt.map(v => `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${m.l - 6}" y="${sy(v) + 4}" text-anchor="end">${yf(v)}</text>`).join("");
  const xl = xt.map(v => `<text x="${sx(v)}" y="${H - 7}" text-anchor="middle">${opts.xLabels ? esc(opts.xLabels[v]) : tickFmt(v)}</text>`).join("");
  const paths = names.map((k, i) => {
    const pts = series[k], c = COLORS[i % 6];
    const d = pts.map((p, j) => (j ? "L" : "M") + sx(p[0]).toFixed(1) + " " + sy(p[1]).toFixed(1)).join("");
    const dots = pts.length <= 12 ? pts.map(p => `<circle cx="${sx(p[0]).toFixed(1)}" cy="${sy(p[1]).toFixed(1)}" r="3" fill="var(${c})"/>`).join("") : "";
    return `<path class="ln" ${DASH[i % 18] ? "" : 'pathLength="1"'} d="${d}" style="stroke:var(${c})" ${DASH[i % 18] ? `stroke-dasharray="${DASH[i % 18]}"` : ""}/>${dots}`;
  }).join("");
  const legend = opts.noLegend ? "" : `<div class="legend">${names.map((k, i) => `<span class="lg"><i style="background:var(${COLORS[i % 6]})"></i>${esc(k)} <b>${yf(series[k][series[k].length - 1][1])}</b></span>`).join("")}</div>`;
  const data = JSON.stringify({ names, series: names.map(k => series[k].map(p => [+p[0].toPrecision(8), +p[1].toPrecision(6)])), g: [m.l, W - m.r, m.t, H - m.b, xlo, xhi, ylo, yhi], xl: opts.xLabels || null });
  return `<div class="mc"><svg class="ch mch" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}" data-mc='${data.replace(/'/g, "&#39;")}'>${grid}${xl}${paths}<line class="mcl gl" y1="${m.t}" y2="${H - m.b}" style="display:none;stroke:var(--line2)"/><rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg><div class="mtip" hidden></div></div>${legend}`;
}
function wireMulti(root) {
  $$("svg.mch", root).forEach(svg => {
    const d = JSON.parse(svg.dataset.mc), [l, r, t, b, xlo, xhi] = d.g, line = $(".mcl", svg), tip = svg.parentElement.querySelector(".mtip");
    const allx = [...new Set(d.series.flat().map(p => p[0]))].sort((a, c) => a - c);
    const move = e => {
      const bb = svg.getBoundingClientRect(), vx = (e.clientX - bb.left) / bb.width * 480;
      const x = xlo + (vx - l) / (r - l) * (xhi - xlo);
      let best = allx[0]; for (const v of allx) if (Math.abs(v - x) < Math.abs(best - x)) best = v;
      const px = l + (xhi === xlo ? .5 : (best - xlo) / (xhi - xlo)) * (r - l);
      line.setAttribute("x1", px); line.setAttribute("x2", px); line.style.display = "";
      const rows = d.names.map((n, i) => { const p = d.series[i].find(q => q[0] === best); return p ? `<div><i style="background:var(${COLORS[i % 6]})"></i>${esc(n)} <b>${+p[1].toPrecision(4)}</b></div>` : ""; }).join("");
      tip.innerHTML = `<div class="th">${d.xl && d.xl[best] != null ? esc(d.xl[best]) : tickFmt(best)}</div>${rows}`;
      tip.hidden = false;
      const frac = px / 480; tip.style.left = Math.min(Math.max(frac * 100, 18), 82) + "%";
    };
    const hit = $(".hit", svg);
    hit.addEventListener("pointermove", move); hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => { line.style.display = "none"; tip.hidden = true; });
  });
}
/* tiny trend line for cards */
function spark(vals, opts = {}) {
  const W = opts.w || 120, H = opts.h || 34, p = 4, pts = vals.map((v, i) => v == null ? null : [i, v]);
  const ok = pts.filter(Boolean);
  if (!ok.length) return `<svg class="spark" viewBox="0 0 ${W} ${H}" aria-hidden="true"><line x1="${p}" x2="${W - p}" y1="${H / 2}" y2="${H / 2}" stroke="var(--line2)" stroke-dasharray="3 4"/></svg>`;
  const lo = opts.lo ?? Math.min(...ok.map(q => q[1])), hi = opts.hi ?? Math.max(...ok.map(q => q[1])), n = Math.max(vals.length - 1, 1);
  const sx = i => p + (n ? i / n : .5) * (W - 2 * p), sy = v => H - p - (hi === lo ? .5 : (v - lo) / (hi - lo)) * (H - 2 * p);
  const d = ok.map((q, j) => (j ? "L" : "M") + sx(q[0]).toFixed(1) + " " + sy(q[1]).toFixed(1)).join("");
  const last = ok[ok.length - 1];
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" aria-hidden="true">${ok.length > 1 ? `<path d="${d}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>` : ""}${ok.map(q => `<circle cx="${sx(q[0]).toFixed(1)}" cy="${sy(q[1]).toFixed(1)}" r="${q === last ? 3.2 : 2}" fill="${q === last ? "var(--accent)" : "var(--panel)"}" stroke="var(--accent)" stroke-width="1.5"/>`).join("")}</svg>`;
}
const placeholderCard = (title, msg) => `<div class="card chart"><h3>${esc(title)}</h3><div class="empty">${esc(msg)}</div></div>`;

/* ---------- clips: 30 and 60 fps, hover/tap play, fullscreen ---------- */
const okUrl = u => typeof u === "string" && (u.startsWith("/clips/") || u.startsWith("/clips60/") || u.startsWith("/sims/") || u.startsWith("https://github.com/"));
const clipSrc = u => u + (u.includes("#") ? "" : "#t=0.1");
const lsGet = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } };
const getFps = () => lsGet("vpt-fps", "30") === "60" ? 60 : 30;
const FS_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>`;
const fsBtn = `<button type="button" class="vbtn fs-btn" aria-label="Fullscreen" title="Fullscreen (f)">${FS_ICON}</button>`;
const fpsBtn = (u60) => u60 ? `<button type="button" class="vbtn fps-btn" aria-label="Toggle 30 or 60 fps" title="Frame rate">${getFps()}</button>` : "";
function clipHtml(c, title) {
  const u = getFps() === 60 && c.url60 ? c.url60 : c.url;
  return `<figure class="clipfig"><div class="clip vbox" data-u30="${esc(c.url)}" data-u60="${esc(c.url60 || "")}"><video controls muted playsinline preload="metadata" src="${esc(clipSrc(u))}" aria-label="${esc(title)}"></video><div class="vtools">${fpsBtn(c.url60)}${fsBtn}</div></div><figcaption><span class="tag">${esc(c.tag)}</span> ${esc(title)}</figcaption></figure>`;
}
/* Card clip: first frame shown, plays on hover or tap, loops while active. */
function hoverClip(url, label, icon, url60) {
  const u = getFps() === 60 && url60 ? url60 : url;
  return `<div class="hclip vbox" data-play data-u30="${esc(url)}" data-u60="${esc(url60 || "")}"><video muted loop playsinline preload="metadata" src="${esc(clipSrc(u))}" aria-label="${esc(label)}"></video><span class="hc-ic">${icon || ""}</span><button type="button" class="hc-btn" aria-label="Play ${esc(label)}"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor"/></svg></button><div class="vtools">${fpsBtn(url60)}${fsBtn}</div></div>`;
}
const noClip = (icon, text = "No clip yet") => `<div class="hclip empty-clip"><span class="hc-ic big">${icon || ""}</span><span class="hc-none">${esc(text)}</span></div>`;
let lastBox = null;
function setClipFps(box, fps) {
  const v = $("video", box), u = fps === 60 && box.dataset.u60 ? box.dataset.u60 : box.dataset.u30;
  if (!v || !u) return;
  const t = v.currentTime, was = !v.paused;
  v.onerror = () => { if (fps === 60) { v.onerror = null; v.src = clipSrc(box.dataset.u30); const b = $(".fps-btn", box); if (b) { b.textContent = "30"; b.disabled = true; } } };
  v.src = clipSrc(u);
  v.addEventListener("loadedmetadata", () => { try { v.currentTime = t; } catch (e) { /* ignore */ } if (was) v.play().catch(() => {}); }, { once: true });
}
/* Fullscreen: the Fullscreen API where it exists, the video element's own on iOS, otherwise a fixed-position fallback. */
function toggleFullscreen(el) {
  const cur = document.fullscreenElement || document.webkitFullscreenElement;
  if (cur || el.classList.contains("pfs")) { (document.exitFullscreen || document.webkitExitFullscreen || (() => {})).call(document); el.classList.remove("pfs"); document.body.classList.remove("nofs"); return; }
  const rq = el.requestFullscreen || el.webkitRequestFullscreen;
  if (rq) { Promise.resolve(rq.call(el)).catch(() => pseudoFs(el)); return; }
  const v = $("video", el);
  if (el.dataset.pfsonly) { pseudoFs(el); return; }
  if (v && v.webkitEnterFullscreen) { try { v.webkitEnterFullscreen(); return; } catch (e) { /* fall through */ } }
  pseudoFs(el);
}
function pseudoFs(el) { el.classList.add("pfs"); document.body.classList.add("nofs"); }
document.addEventListener("click", e => {
  const t = e.target;
  if (!t.closest) return;
  const fb = t.closest(".fs-btn");
  if (fb) { e.preventDefault(); toggleFullscreen(fb.closest(".vbox") || fb.closest("[data-fsbox]")); return; }
  const pb = t.closest(".fps-btn");
  if (pb) { e.preventDefault(); const nx = getFps() === 60 ? 30 : 60; lsSet("vpt-fps", String(nx)); $$(".fps-btn").forEach(b => { if (!b.disabled) b.textContent = nx; }); $$(".vbox").forEach(bx => { if (bx.dataset.u60) setClipFps(bx, nx); }); document.dispatchEvent(new CustomEvent("vpt-fps", { detail: nx })); return; }
  const b = t.closest(".hc-btn, .hclip video");
  if (b) { const box = b.closest(".hclip"), v = $("video", box); if (!v) return; lastBox = box; if (v.paused) v.play().catch(() => {}); else v.pause(); }
});
document.addEventListener("play", e => { const bx = e.target.closest && e.target.closest(".hclip"); if (bx) { bx.classList.add("on"); lastBox = bx; } }, true);
document.addEventListener("pause", e => { const bx = e.target.closest && e.target.closest(".hclip"); if (bx) bx.classList.remove("on"); }, true);
document.addEventListener("pointerover", e => {
  if (e.pointerType !== "mouse") return;
  const box = e.target.closest && e.target.closest(".vbox");
  if (box) lastBox = box;
  const h = e.target.closest && e.target.closest(".hclip");
  if (h && !h.classList.contains("on") && $("video", h)) $("video", h).play().catch(() => {});
});
document.addEventListener("pointerout", e => {
  if (e.pointerType !== "mouse") return;
  const box = e.target.closest && e.target.closest(".hclip");
  if (box && !box.contains(e.relatedTarget) && $("video", box)) { const v = $("video", box); v.pause(); v.currentTime = 0.1; }
});

/* ---------- lightbox ---------- */
function openLightbox(src, cap) {
  const lb = $("#lightbox"); $("img", lb).src = src; $("img", lb).alt = cap || ""; $(".lb-cap", lb).textContent = cap || "";
  lb.hidden = false; $(".lb-close", lb).focus();
}
$("#lightbox").addEventListener("click", e => { if (e.target.id === "lightbox" || e.target.classList.contains("lb-close")) $("#lightbox").hidden = true; });
document.addEventListener("keydown", e => { if (e.key === "Escape") $("#lightbox").hidden = true; });
document.addEventListener("click", e => {
  const f = e.target.closest && e.target.closest("[data-zoom]");
  if (f) openLightbox(f.dataset.zoom, f.dataset.cap);
});

/* ---------- skeletons, empty states ---------- */
const skel = (kind = "page") => ({
  page: `<div class="skel-page" aria-busy="true"><div class="skel sk-h"></div><div class="skel sk-p"></div><div class="skel sk-p short"></div><div class="grid cols" style="margin-top:22px">${'<div class="skel sk-card"></div>'.repeat(6)}</div></div>`,
  list: `<div class="skel-page" aria-busy="true"><div class="skel sk-h"></div><div class="skel sk-box"></div><div class="skel sk-box"></div></div>`,
}[kind]);
const counter = (el, to, opts = {}) => {
  const fmtF = opts.fmt || (v => Math.round(v).toLocaleString());
  if (reduced || to == null || !isFinite(to) || to < 2) { el.textContent = to == null ? "-" : fmtF(to); return; }
  const t0 = performance.now(), D = 900;
  const step = t => { const k = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - k, 3); el.textContent = fmtF(to * e); if (k < 1 && el.isConnected) requestAnimationFrame(step); };
  requestAnimationFrame(step);
};

/* ---------- router ---------- */
const pages = {};
let gen = 0;
function segs() { return location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent); }
async function route() {
  clearTimers();
  const my = ++gen, s = segs(), k = s[0] || "overview";
  const key = pages[k] ? k : null;
  $$("#nav a").forEach(a => a.classList.toggle("on", a.dataset.k === key || (key === "modes" && a.dataset.k === "modes")));
  const entry = PAGES.find(p => p[0] === key);
  document.title = (entry ? entry[1] : "Page not found") + " - VPT Arena";
  if (!key) { view.innerHTML = `<div class="nf"><div class="nf-ic">${pixelIcon("grid", 64)}</div><h1>Page not found</h1><p class="lede">There is no page at <code>${esc(location.hash || "/")}</code>.</p><p><a class="btn" href="#/overview">Back to the overview</a> <a class="btn ghost" href="#/modes">Browse modes</a></p></div>`; window.scrollTo(0, 0); return; }
  if (!(key === "docs" && $(".docs"))) view.innerHTML = skel(key === "overview" ? "page" : "list");
  try {
    await pages[key](s.slice(1));
    if (my !== gen) return;
    view.classList.remove("rise"); void view.offsetWidth; view.classList.add("rise");
    if (key !== "docs" || !s[1]) window.scrollTo(0, 0);
  } catch (e) {
    if (my !== gen) return;
    view.innerHTML = `<div class="empty">Could not load this page: ${esc(e.message)}. ${STATIC ? "Try again in a minute." : "Is the server running?"}</div>`;
  }
}

/* ---------- chart fullscreen ---------- */
const chartObs = new MutationObserver(() => {
  $$(".card.chart:not([data-xb])", view).forEach(c => {
    if (!c.querySelector("svg.ch")) return;
    c.dataset.xb = "1";
    const b = document.createElement("button"); b.type = "button"; b.className = "xb"; b.setAttribute("aria-label", "Open chart fullscreen"); b.title = "Open fullscreen"; b.innerHTML = FS_ICON;
    c.appendChild(b);
  });
});
chartObs.observe(view, { childList: true, subtree: true });
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest(".xb");
  if (!b) return;
  let ov = $("#chartfs");
  if (!ov) { ov = document.createElement("div"); ov.id = "chartfs"; ov.className = "chartfs"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true"); ov.dataset.fsbox = "1"; document.body.appendChild(ov); }
  const card = b.closest(".card").cloneNode(true);
  $$(".xb", card).forEach(x => x.remove());
  ov.innerHTML = `<button type="button" class="lb-close" aria-label="Close">Close</button><div class="cfs-body"></div>`;
  $(".cfs-body", ov).appendChild(card);
  ov.hidden = false; wireCharts(ov); wireMulti(ov);
  const rq = ov.requestFullscreen || ov.webkitRequestFullscreen; if (rq) Promise.resolve(rq.call(ov)).catch(() => {});
  $(".lb-close", ov).focus();
});
document.addEventListener("click", e => {
  const ov = $("#chartfs");
  if (ov && !ov.hidden && e.target.closest && (e.target === ov || e.target.closest(".lb-close") && ov.contains(e.target))) {
    ov.hidden = true; if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  }
});

/* ---------- keyboard: shortcuts overlay, g-then-key navigation, f for fullscreen ---------- */
const GO = { o: "overview", d: "dashboard", s: "simulate", t: "training", m: "modes", l: "league", a: "data", v: "live", h: "docs" };
let gArmed = 0;
function helpOverlay(show) {
  let ov = $("#kbhelp");
  if (!ov) {
    ov = document.createElement("div"); ov.id = "kbhelp"; ov.className = "lightbox kb"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-label", "Keyboard shortcuts"); ov.hidden = true;
    ov.innerHTML = `<div class="kbcard"><h3>Keyboard shortcuts</h3><dl><dt><kbd>?</kbd></dt><dd>Show or hide this list</dd><dt><kbd>g</kbd> then <kbd>o</kbd></dt><dd>Overview</dd><dt><kbd>g</kbd> then <kbd>d</kbd></dt><dd>Dashboard</dd><dt><kbd>g</kbd> then <kbd>s</kbd></dt><dd>Simulate</dd><dt><kbd>g</kbd> then <kbd>t</kbd></dt><dd>Training</dd><dt><kbd>g</kbd> then <kbd>m</kbd></dt><dd>Modes</dd><dt><kbd>g</kbd> then <kbd>l</kbd></dt><dd>League</dd><dt><kbd>g</kbd> then <kbd>a</kbd></dt><dd>Data</dd><dt><kbd>g</kbd> then <kbd>v</kbd></dt><dd>Live</dd><dt><kbd>g</kbd> then <kbd>h</kbd></dt><dd>Docs</dd><dt><kbd>f</kbd></dt><dd>Fullscreen: the video under the pointer, or this page's main view (Live, Dashboard)</dd><dt><kbd>t</kbd></dt><dd>Switch light and dark</dd><dt><kbd>/</kbd></dt><dd>Focus the search box</dd><dt><kbd>Esc</kbd></dt><dd>Close a dialog or leave fullscreen</dd></dl><button class="btn sm" type="button">Close</button></div>`;
    document.body.appendChild(ov);
    ov.addEventListener("click", e => { if (e.target === ov || e.target.closest("button")) ov.hidden = true; });
  }
  ov.hidden = show === undefined ? !ov.hidden : !show;
}
document.addEventListener("keydown", e => {
  const t = e.target, typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
  if (e.metaKey || e.ctrlKey || e.altKey || typing) return;
  const k = e.key;
  if (k === "Escape") { const h = $("#kbhelp"); if (h) h.hidden = true; const c = $("#chartfs"); if (c) c.hidden = true; $$(".pfs").forEach(x => x.classList.remove("pfs")); document.body.classList.remove("nofs"); return; }
  if (k === "?") { e.preventDefault(); helpOverlay(); return; }
  if (gArmed && Date.now() - gArmed < 1500) { gArmed = 0; if (GO[k] && pages[GO[k]]) { e.preventDefault(); location.hash = "#/" + GO[k]; } return; }
  if (k === "g") { gArmed = Date.now(); return; }
  if (k === "/") { const q = $("input[type=search]"); if (q) { e.preventDefault(); q.focus(); } return; }
  if (k === "t") { $("#theme").click(); return; }
  if (k === "f") {
    e.preventDefault();
    const hover = $(".vbox:hover"), el = hover || lastBoxIfVisible();
    if (document.fullscreenElement || document.webkitFullscreenElement) { toggleFullscreen(document.fullscreenElement || document.webkitFullscreenElement); return; }
    if (hover) { toggleFullscreen(hover); return; }
    if (window.fsHook) { window.fsHook(); return; }
    if (el) toggleFullscreen(el);
  }
});
function lastBoxIfVisible() { return lastBox && lastBox.isConnected ? lastBox : null; }
