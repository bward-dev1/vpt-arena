"use strict";
/* Simulation Lab: a visual scenario builder, status view and results. The spec comes from configs/sim_spec.json (window.VPT_SIM). */
const FLOOR_COL = { smooth_stone: "#9aa0a8", white_wool: "#eef0f2", grass_block: "#5f9b4a", snow_block: "#e4eef5", quartz_block: "#e8e1d6", end_stone: "#d9d68d", white_concrete: "#d0d6d9", oak_planks: "#b08a52", obsidian: "#2a1d3d" };
const MOB_COL = { zombie: "#6aa84f", husk: "#b59a6a", drowned: "#3d8f8f", skeleton: "#cfd2d6", stray: "#9fc3d9", vindicator: "#7a8a96", pillager: "#6f7c8a", spider: "#4a3b3b", witch: "#8a4fb3", piglin_brute: "#d98f6a", wither_skeleton: "#3b3b45", creeper: "#5fcf5f", iron_golem: "#c8c2b6" };
const human = s => String(s).replace(/_/g, " ");
const clone = o => JSON.parse(JSON.stringify(o));
const SIMS = () => window.VPT_SIM && window.VPT_SIM.spec;

function presetDefs(S) {
  const D = clone(S.defaults);
  const mk = (name, base_mode, patch) => { const x = clone(D); x.name = name; x.base_mode = base_mode; for (const k in patch) { if (patch[k] && typeof patch[k] === "object" && !Array.isArray(patch[k])) Object.assign(x[k], patch[k]); else x[k] = patch[k]; } return x; };
  return [
    { id: "sword", icon: "sword", title: "Sword duel", text: "One zombie in iron armor, iron swords, over the void.", spec: mk("Sword duel", "duels_sword", {}) },
    { id: "bow", icon: "bow", title: "Bow duel", text: "Bow and 24 arrows against a skeleton at range.", spec: mk("Bow duel", "duels_bow", { arena: { size: 12 }, player: { weapon: "stone_sword", armor: "leather", bow: true, arrows: 24 }, opponents: [{ type: "skeleton", count: 1, weapon: "none", armor: "iron", distance: 12 }] }) },
    { id: "sumo", icon: "ring", title: "Sumo", text: "A small wool ring, no weapons. Push the opponent off.", spec: mk("Sumo", "duels_sumo", { arena: { size: 4, floor: "white_wool" }, player: { weapon: "none", armor: "none" }, opponents: [{ type: "zombie", count: 1, weapon: "none", armor: "none", distance: 4 }], seconds: 45 }) },
    { id: "bed", icon: "bed", title: "Bed Wars rush", text: "Blocks in hand, two guards, a bed island 18 blocks away.", spec: mk("Bed Wars rush", "bedwars_solo", { arena: { size: 12 }, player: { weapon: "stone_sword", armor: "chainmail", blocks: 48 }, opponents: [{ type: "zombie", count: 2, weapon: "stone_sword", armor: "leather", distance: 10 }], goal: { type: "bed", distance: 18 }, seconds: 90 }) },
    { id: "bridge", icon: "bridge", title: "Bridge race", text: "Bridge 24 blocks to the goal while a vindicator guards the start.", spec: mk("Bridge race", "the_bridge", { arena: { size: 6 }, player: { weapon: "iron_sword", armor: "iron", blocks: 64 }, opponents: [{ type: "vindicator", count: 1, weapon: "iron_axe", armor: "none", distance: 8 }], goal: { type: "bridge", distance: 24 }, seconds: 90 }) },
    { id: "wave", icon: "swords", title: "Wave defence", text: "Six mobs from three sides on solid ground, golden apples to heal.", spec: mk("Wave defence", "kitpvp", { arena: { size: 12, hazard: "ground", floor: "grass_block" }, player: { weapon: "diamond_sword", armor: "iron", gapples: 4 }, opponents: [{ type: "zombie", count: 2, weapon: "none", armor: "none", distance: 8 }, { type: "skeleton", count: 2, weapon: "none", armor: "none", distance: 12 }, { type: "spider", count: 2, weapon: "none", armor: "none", distance: 10 }], seconds: 90, episodes: 2 }) },
    { id: "night", icon: "heart", title: "Survival night", text: "Free play after dark with a mixed group closing in.", spec: mk("Survival night", "survival", { arena: { size: 14, hazard: "ground", floor: "grass_block", time: "night" }, player: { weapon: "stone_sword", armor: "leather", gapples: 2 }, opponents: [{ type: "zombie", count: 2, weapon: "none", armor: "none", distance: 9 }, { type: "skeleton", count: 1, weapon: "none", armor: "none", distance: 13 }, { type: "creeper", count: 1, weapon: "none", armor: "none", distance: 11 }], seconds: 120 }) },
  ];
}

/* ----- the mini-map ----- */
function defaultAngles(n) { return Array.from({ length: n }, (_, i) => -Math.PI / 2 + i * 2 * Math.PI / Math.max(n, 1)); }
function mapSvg(sp, angles, interactive) {
  const a = sp.arena, goal = sp.goal, ops = sp.opponents;
  const reach = Math.max(a.size, ...ops.map(o => o.distance + 1.6), goal.type !== "none" ? goal.distance + 3 : 0) + 2, R = Math.ceil(reach);
  const hz = a.hazard === "void" ? "#080b11" : a.hazard === "lava" ? "#b6460f" : "#3d6a38", night = a.time === "night";
  const floor = FLOOR_COL[a.floor] || "#999";
  let g = `<rect x="${-R}" y="${-R}" width="${2 * R}" height="${2 * R}" fill="${hz}"/>`;
  if (a.hazard === "void") { let l = ""; for (let i = -R; i <= R; i += 2) l += `M${i} ${-R}V${R}M${-R} ${i}H${R}`; g += `<path d="${l}" stroke="#1b2230" stroke-width=".06" fill="none"/>`; }
  g += `<rect x="${-a.size}" y="${-a.size}" width="${2 * a.size}" height="${2 * a.size}" fill="${floor}" stroke="rgba(0,0,0,.35)" stroke-width=".15"/>`;
  let gl = ""; for (let i = -a.size + 1; i < a.size; i++) gl += `M${i} ${-a.size}V${a.size}M${-a.size} ${i}H${a.size}`;
  g += `<path d="${gl}" stroke="rgba(0,0,0,.12)" stroke-width=".05" fill="none"/>`;
  if (goal.type !== "none") {
    const gx = 0, gy = goal.distance;
    if (goal.type === "bridge") g += `<path d="M0 ${a.size}V${gy - 1.5}" stroke="#d9b36a" stroke-width="1.1" stroke-dasharray=".7 .5"/>`;
    g += `<rect x="${gx - 2}" y="${gy - 2}" width="4" height="4" fill="${goal.type === "bed" ? "#7b5a8f" : "#6fa75b"}" stroke="rgba(0,0,0,.4)" stroke-width=".15"/><text x="${gx}" y="${gy + .5}" text-anchor="middle" font-size="1.5" fill="#fff" font-weight="700">${goal.type === "bed" ? "BED" : "GOAL"}</text>`;
  }
  ops.forEach((o, i) => {
    const ang = angles[i] ?? 0, cx = Math.cos(ang) * o.distance, cy = Math.sin(ang) * o.distance, col = MOB_COL[o.type] || "#c55";
    g += `<circle r="${o.distance}" fill="none" stroke="rgba(255,255,255,.28)" stroke-width=".08" stroke-dasharray=".4 .4"/>`;
    g += `<g class="mk" data-gi="${i}" transform="translate(${cx.toFixed(2)} ${cy.toFixed(2)})" ${interactive ? 'style="cursor:grab" tabindex="0" role="slider" aria-label="Opponent group ' + (i + 1) + ' distance"' : ""}><circle r="2.2" fill="transparent"/>`;
    for (let k = 0; k < o.count; k++) { const t = k * 2 * Math.PI / o.count, rr = o.count > 1 ? 1 : 0; g += `<circle cx="${(Math.cos(t) * rr).toFixed(2)}" cy="${(Math.sin(t) * rr).toFixed(2)}" r=".75" fill="${col}" stroke="#111" stroke-width=".16"/>`; }
    g += `<text y="-1.5" text-anchor="middle" font-size="1.25" fill="#fff" stroke="#000" stroke-width=".25" paint-order="stroke" font-weight="700">${o.count}x ${esc(human(o.type))} ${o.distance}</text></g>`;
  });
  g += `<circle r="1" fill="var(--accent)" stroke="#111" stroke-width=".18"/><text y=".35" text-anchor="middle" font-size="1" fill="#06140d" font-weight="800">P</text>`;
  if (night) g += `<rect x="${-R}" y="${-R}" width="${2 * R}" height="${2 * R}" fill="#0a1440" opacity=".42" pointer-events="none"/>`;
  return `<svg class="simmap" viewBox="${-R} ${-R} ${2 * R} ${2 * R}" role="img" aria-label="Top-down map of the scenario: arena, you, opponents and goal">${g}</svg>`;
}
function summaryText(sp, mm) {
  const a = sp.arena, p = sp.player, bm = mm && mm[sp.base_mode] ? mm[sp.base_mode].name : human(sp.base_mode);
  const gear = (w, ar) => [w !== "none" ? human(w) : "no weapon", ar !== "none" ? human(ar) + " armor" : "no armor"].join(", ");
  const extras = [p.bow ? `a bow with ${p.arrows} arrows` : null, p.blocks ? `${p.blocks} blocks` : null, p.gapples ? `${p.gapples} golden apples` : null].filter(Boolean);
  const opp = sp.opponents.length ? sp.opponents.map(o => `${o.count} ${human(o.type)}${o.count > 1 ? "s" : ""} (${gear(o.weapon, o.armor)}) ${o.distance} blocks away`).join("; ") : "no opponents";
  const goal = sp.goal.type === "none" ? "There is no goal; the aim is to win the fight." : sp.goal.type === "bed" ? `The aim is to reach the bed island ${sp.goal.distance} blocks away.` : `The aim is to bridge ${sp.goal.distance} blocks to the goal.`;
  return `The ${sp.model === "latest" ? "latest model" : sp.model === "baseline" ? "baseline model" : sp.model} plays ${bm} for ${sp.seconds} seconds, ${sp.episodes} episode${sp.episodes > 1 ? "s" : ""}. The arena reaches ${a.size} blocks from the centre, ${human(a.floor)} over ${a.hazard === "ground" ? "solid ground" : a.hazard}, by ${a.time}. You have ${gear(p.weapon, p.armor)}${extras.length ? ", " + extras.join(", ") : ""}. Against you: ${opp}. ${goal} Opponent strength is ${Math.round(sp.difficulty * 100)} percent.`;
}
function problems(sp, S) {
  const out = [], t = sp.opponents.reduce((a, o) => a + o.count, 0);
  if (t > S.limits.opponents_total_max) out.push(`There are ${t} opponents; the limit is ${S.limits.opponents_total_max}.`);
  if (!sp.name.trim()) out.push("Give the scenario a name.");
  return out;
}

/* ----- recent list ----- */
function recentHtml(list) {
  if (!list.length) return `<div class="empty">No simulations yet. The first one will show up here.</div>`;
  return `<div class="recent">${list.map(s => `<a class="rc-row" href="#/simulate/${esc(s.id)}"><b>${esc(s.name)}</b><span class="tag ${esc(s.status)}">${esc(s.status)}</span><span class="m">${esc(s.model)}${s.summary ? ` &middot; ${s.summary.wins}/${s.summary.episodes} won` : ""}</span><span class="m">${ago(s.created / 1000)}</span></a>`).join("")}</div>`;
}
async function loadSims() { const r = await fetch("/api/sims", { cache: "no-store" }); if (!r.ok) throw new Error("sims " + r.status); return r.json(); }

pages.simulate = async args => {
  const S = SIMS();
  if (!S) { view.innerHTML = `<h1>Simulate</h1><div class="empty">The Simulation Lab runs on the public site, where the cloud runner is connected.</div>`; return; }
  if (args && args[0]) return simStatus(args[0], S);
  const [mm, cloud] = await Promise.all([modeMap(), api("/api/cloud")]);
  const models = ["baseline", "latest", ...cloud.releases.filter(t => t !== "baseline" && t !== "latest")];
  let sim = clone(S.defaults), angles = defaultAngles(sim.opponents.length), presetOn = "sword";
  try { const c = sessionStorage.getItem("vpt-sim-clone"); if (c) { sim = JSON.parse(c); sessionStorage.removeItem("vpt-sim-clone"); angles = defaultAngles(sim.opponents.length); presetOn = ""; } } catch (e) { /* ignore */ }
  const P = presetDefs(S), E = S.enums, L = S.limits;
  const opt = (arr, v, f = human) => arr.map(x => `<option value="${esc(x)}" ${x === v ? "selected" : ""}>${esc(f(x))}</option>`).join("");
  const fld = (label, inner, hint) => `<label class="fld"><span>${label}</span>${inner}${hint ? `<span class="hint">${hint}</span>` : ""}</label>`;
  const rng = (path, lo, hi, step, v, unit = "") => `<input type="range" data-p="${path}" min="${lo}" max="${hi}" step="${step}" value="${v}"><output data-o="${path}">${v}${unit}</output>`;
  view.innerHTML = `<h1>Simulate</h1><p class="lede">Design a small scenario and a trained model plays it in the cloud. Pick a preset, change anything, and watch the map and summary update. A run takes about 6 to 10 minutes because a cloud machine has to start Minecraft.</p>
  <h2 class="kick">Presets</h2><div class="presets">${P.map(p => `<button type="button" class="preset ${p.id === presetOn ? "on" : ""}" data-preset="${p.id}"><span class="pi">${pixelIcon(p.icon, 26)}</span><b>${esc(p.title)}</b><span>${esc(p.text)}</span></button>`).join("")}</div>
  <div class="sim"><form id="simform" autocomplete="off" novalidate></form>
  <aside class="sim-side"><div class="card mapbox"><div id="mapslot"></div><div class="map-cap"><span><i style="background:var(--accent)"></i>You</span><span><i style="background:#c55"></i>Opponents (drag to move)</span><span><i style="background:#7b5a8f"></i>Goal</span></div></div>
  <div class="card"><h3>What will run</h3><p class="sumtxt" id="sumtxt"></p></div><div id="errslot"></div>
  <div class="card"><button class="btn primary" id="go" type="button" style="width:100%;justify-content:center">Run simulation</button><p class="upd" id="limits">Limits: ${window.VPT_SIM.limits.per_ip_hour} per person per hour, ${window.VPT_SIM.limits.per_day} a day for everyone, ${window.VPT_SIM.limits.unfinished} waiting or running at once.</p></div></aside></div>
  <h2 class="kick">Recent simulations</h2><div id="recent"><div class="skel sk-box"></div></div>`;
  const form = $("#simform");
  function oppRow(o, i) {
    return `<div class="opp" data-i="${i}"><div class="opp-h"><span>Group ${i + 1}</span><button type="button" class="btn sm ghost danger" data-del="${i}">Remove</button></div><div class="frow">
      ${fld("Mob", `<select data-p="opponents.${i}.type">${opt(E.opponent_type, o.type)}</select>`)}${fld("Count", `<input type="number" data-p="opponents.${i}.count" min="${L.opponent_count[0]}" max="${L.opponent_count[1]}" value="${o.count}">`)}
      ${fld("Weapon", `<select data-p="opponents.${i}.weapon">${opt(E.weapon, o.weapon)}</select>`)}${fld("Armor", `<select data-p="opponents.${i}.armor">${opt(E.armor, o.armor)}</select>`)}
      ${fld("Distance from you", rng(`opponents.${i}.distance`, L.opponent_distance[0], L.opponent_distance[1], 1, o.distance, " blocks"))}</div></div>`;
  }
  function buildForm() {
    form.innerHTML = `<fieldset class="fs"><legend>Scenario</legend><div class="frow">
      ${fld("Name", `<input type="text" data-p="name" maxlength="${L.name_max}" value="${esc(sim.name)}">`)}
      ${fld("Model", `<select data-p="model">${opt(models, sim.model, x => x === "latest" ? "latest (newest round)" : x)}</select>`)}
      ${fld("Game mode it was trained on", `<select data-p="base_mode">${spec_modes()}</select>`, "Conditions the policy; it does not change the arena.")}
      ${fld("Episodes", rng("episodes", L.episodes[0], L.episodes[1], 1, sim.episodes))}${fld("Length of each", rng("seconds", L.seconds[0], L.seconds[1], 5, sim.seconds, " s"))}
      ${fld("Opponent strength", rng("difficulty", 0, 1, 0.05, sim.difficulty))}${fld("Seed", `<input type="number" data-p="seed" min="${L.seed[0]}" max="${L.seed[1]}" value="${sim.seed}">`)}</div></fieldset>
    <fieldset class="fs"><legend>Arena</legend><div class="frow">${fld("Size (blocks from centre to edge)", rng("arena.size", L.arena_size[0], L.arena_size[1], 1, sim.arena.size))}
      ${fld("Floor", `<select data-p="arena.floor">${opt(E.floor, sim.arena.floor)}</select>`)}${fld("Below the arena", `<select data-p="arena.hazard">${opt(E.hazard, sim.arena.hazard, x => x === "ground" ? "solid ground" : x)}</select>`)}${fld("Time", `<select data-p="arena.time">${opt(E.time, sim.arena.time)}</select>`)}</div></fieldset>
    <fieldset class="fs"><legend>You</legend><div class="frow">${fld("Weapon", `<select data-p="player.weapon">${opt(E.weapon, sim.player.weapon)}</select>`)}${fld("Armor", `<select data-p="player.armor">${opt(E.armor, sim.player.armor)}</select>`)}
      <label class="fld chk"><input type="checkbox" data-p="player.bow" ${sim.player.bow ? "checked" : ""}> Bow</label>${fld("Arrows", `<input type="number" data-p="player.arrows" min="${L.arrows[0]}" max="${L.arrows[1]}" value="${sim.player.arrows}">`)}
      ${fld("Blocks", `<input type="number" data-p="player.blocks" min="${L.blocks[0]}" max="${L.blocks[1]}" value="${sim.player.blocks}">`)}${fld("Golden apples", `<input type="number" data-p="player.gapples" min="${L.gapples[0]}" max="${L.gapples[1]}" value="${sim.player.gapples}">`)}</div></fieldset>
    <fieldset class="fs"><legend>Opponents <span class="upd" style="margin:0" id="otot"></span></legend><div id="opps">${sim.opponents.map(oppRow).join("")}</div>
      <button type="button" class="btn sm" id="addopp" ${sim.opponents.length >= L.opponent_groups[1] ? "disabled" : ""}>Add opponent group</button></fieldset>
    <fieldset class="fs"><legend>Goal</legend><div class="frow">${fld("Type", `<select data-p="goal.type">${opt(E.goal, sim.goal.type, x => x === "none" ? "none, just win the fight" : x)}</select>`)}${fld("Distance", rng("goal.distance", L.goal_distance[0], L.goal_distance[1], 1, sim.goal.distance, " blocks"))}</div></fieldset>`;
  }
  function spec_modes() { return S.base_modes.map(k => `<option value="${esc(k)}" ${k === sim.base_mode ? "selected" : ""}>${esc(mm[k] ? mm[k].name : k)}</option>`).join(""); }
  const refresh = () => {
    $("#mapslot").innerHTML = mapSvg(sim, angles, true);
    $("#sumtxt").textContent = summaryText(sim, mm);
    const tot = sim.opponents.reduce((a, o) => a + o.count, 0); const ot = $("#otot"); if (ot) ot.textContent = `${tot} of ${L.opponents_total_max} opponents`;
    const pr = problems(sim, S); $("#errslot").innerHTML = pr.length ? `<div class="errbox"><ul>${pr.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""; $("#go").disabled = pr.length > 0;
    $$("[data-o]", form).forEach(o => { const v = getP(o.dataset.o); o.textContent = (o.dataset.o === "difficulty" ? Math.round(v * 100) + "%" : v) + (/distance|size/.test(o.dataset.o) && !/arena/.test(o.dataset.o) ? " blocks" : o.dataset.o === "seconds" ? " s" : ""); });
    const gd = $('[data-p="goal.distance"]', form); if (gd) gd.disabled = sim.goal.type === "none";
  };
  const getP = path => path.split(".").reduce((o, k) => o[k], sim);
  const setP = (path, v) => { const ks = path.split("."), last = ks.pop(); ks.reduce((o, k) => o[k], sim)[last] = v; };
  buildForm(); refresh();
  form.addEventListener("input", e => {
    const el = e.target.closest("[data-p]"); if (!el) return;
    let v = el.type === "checkbox" ? el.checked : (el.type === "number" || el.type === "range") ? (el.value === "" ? 0 : Number(el.value)) : el.value;
    setP(el.dataset.p, v); presetOn = ""; $$(".preset").forEach(b => b.classList.remove("on")); refresh();
  });
  form.addEventListener("click", e => {
    const d = e.target.closest("[data-del]"); if (d) { const i = +d.dataset.del; sim.opponents.splice(i, 1); angles.splice(i, 1); buildForm(); refresh(); return; }
    if (e.target.closest("#addopp") && sim.opponents.length < L.opponent_groups[1]) { sim.opponents.push({ type: "zombie", count: 1, weapon: "none", armor: "none", distance: 8 }); angles = defaultAngles(sim.opponents.length); buildForm(); refresh(); }
  });
  $$(".preset").forEach(b => b.onclick = () => { const p = P.find(x => x.id === b.dataset.preset); sim = clone(p.spec); sim.model = $('[data-p="model"]', form) ? sim.model : sim.model; angles = defaultAngles(sim.opponents.length); presetOn = p.id; $$(".preset").forEach(x => x.classList.toggle("on", x === b)); buildForm(); refresh(); });
  /* drag opponents on the map; distance and direction follow the pointer, the form follows the map */
  let drag = null;
  const mapEl = $("#mapslot");
  mapEl.addEventListener("pointerdown", e => { const g = e.target.closest(".mk"); if (!g) return; drag = +g.dataset.gi; g.setPointerCapture && g.setPointerCapture(e.pointerId); e.preventDefault(); });
  mapEl.addEventListener("pointermove", e => {
    if (drag == null) return; const svg = $("svg", mapEl), pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; const q = pt.matrixTransform(svg.getScreenCTM().inverse());
    angles[drag] = Math.atan2(q.y, q.x); const o = sim.opponents[drag]; o.distance = Math.max(L.opponent_distance[0], Math.min(L.opponent_distance[1], Math.round(Math.hypot(q.x, q.y))));
    const inp = $(`[data-p="opponents.${drag}.distance"]`, form); if (inp) inp.value = o.distance;
    $("#mapslot").innerHTML = mapSvg(sim, angles, true); $("#sumtxt").textContent = summaryText(sim, mm); $$("[data-o]", form).forEach(x => { if (x.dataset.o === `opponents.${drag}.distance`) x.textContent = o.distance + " blocks"; });
  });
  const endDrag = () => { if (drag != null) { drag = null; presetOn = ""; } };
  mapEl.addEventListener("pointerup", endDrag); mapEl.addEventListener("pointercancel", endDrag);
  mapEl.addEventListener("keydown", e => { const g = e.target.closest && e.target.closest(".mk"); if (!g) return; const i = +g.dataset.gi, o = sim.opponents[i], dd = e.key === "ArrowUp" || e.key === "ArrowRight" ? 1 : e.key === "ArrowDown" || e.key === "ArrowLeft" ? -1 : 0; if (!dd) return; e.preventDefault(); o.distance = Math.max(L.opponent_distance[0], Math.min(L.opponent_distance[1], o.distance + dd)); const inp = $(`[data-p="opponents.${i}.distance"]`, form); if (inp) inp.value = o.distance; refresh(); const ng = $(`.mk[data-gi="${i}"]`, mapEl); if (ng) ng.focus(); });
  $("#go").onclick = async () => {
    const b = $("#go"); b.disabled = true; b.textContent = "Submitting"; $("#errslot").innerHTML = "";
    try {
      const r = await fetch("/api/sim", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(sim) });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.id) { location.hash = "#/simulate/" + d.id; return; }
      const list = d.errors && d.errors.length > 1 ? d.errors : null;
      $("#errslot").innerHTML = `<div class="errbox"><b>${esc(d.error || "The request was refused (" + r.status + ").")}</b>${list ? `<ul>${list.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>`;
    } catch (e) { $("#errslot").innerHTML = `<div class="errbox">Could not reach the lab: ${esc(e.message)}. Check your connection and try again.</div>`; }
    b.disabled = false; b.textContent = "Run simulation";
  };
  const loadRecent = async () => { try { const d = await loadSims(); $("#recent").innerHTML = recentHtml(d.sims); } catch (e) { const el = $("#recent"); if (el) el.innerHTML = `<div class="empty">Could not load recent simulations.</div>`; } };
  loadRecent(); every(15000, loadRecent);
};

/* ----- status and results ----- */
const STEPS = [["queued", "Queued"], ["dispatched", "Sent to a runner"], ["running", "Running"], ["done", "Done"]];
async function simStatus(id, S) {
  const mm = await modeMap(), cloud = await api("/api/cloud");
  const models = ["baseline", "latest", ...cloud.releases.filter(t => t !== "baseline" && t !== "latest")];
  view.innerHTML = `<nav class="crumb"><a href="#/simulate">Simulate</a> / <span class="mono">${esc(id)}</span></nav><div id="sbody"><div class="skel sk-box"></div></div><h2 class="kick">Recent simulations</h2><div id="recent"></div>`;
  let last = null, list = [];
  const draw = d => {
    const sp = d.spec, st = d.status, idx = STEPS.findIndex(x => x[0] === st), failed = st === "failed";
    const elapsed = (Date.now() - d.created) / 1000;
    const ahead = list.filter(s => s.created < d.created && ["queued", "dispatched", "running"].includes(s.status)).length;
    const r = d.result, eps = r && r.episodes || [];
    const wins = eps.filter(e => e.won).length;
    $("#sbody").innerHTML = `<div class="dh"><div><h1>${esc(sp.name)}</h1><div class="tags"><span class="tag ${esc(st)}">${esc(st)}</span><span class="tag">${esc(sp.model)}</span><span class="tag">${esc(mm[sp.base_mode] ? mm[sp.base_mode].name : sp.base_mode)}</span><span class="tag">${sp.episodes} episode${sp.episodes > 1 ? "s" : ""}, ${sp.seconds} s</span></div></div>
      <div class="dh-actions"><button type="button" class="btn sm" data-copy="${esc(location.href.split("#")[0])}#/simulate/${esc(id)}">Copy link</button><button type="button" class="btn sm ghost" id="cloneb">Edit a copy</button></div></div>
    ${failed ? "" : `<div class="steps" role="list">${STEPS.map((x, i) => `<div class="stp ${i < idx ? "done" : i === idx ? "cur" : ""}" role="listitem"><i></i>${x[1]}</div>`).join("")}</div>`}
    ${failed ? `<div class="errbox"><b>The run failed.</b> ${esc(d.message || "The runner reported an error.")}</div>` : `<div class="card"><p class="sumtxt"><b>${esc({ queued: "Waiting in the queue.", dispatched: "A cloud machine has been asked to run this.", running: "Running on a cloud machine.", done: "Finished." }[st] || st)}</b> ${esc(d.message || "")}</p>
      ${st !== "done" ? `<p class="upd">Submitted ${span(elapsed)} ago${st === "queued" ? (ahead ? `, ${ahead} run${ahead > 1 ? "s" : ""} ahead of it` : ", first in line") : ""}. A run takes about 6 to 10 minutes because a cloud machine has to start Minecraft. This page checks every 5 seconds.${st === "queued" && elapsed > 900 ? " It has been queued for a while, so the runner may be offline. The request is saved and runs when the runner is back." : ""}</p>` : ""}
      ${d.run_url && String(d.run_url).startsWith("https://github.com/") ? `<p class="upd"><a href="${esc(d.run_url)}" rel="noopener">View the run on GitHub</a></p>` : ""}</div>`}
    ${st === "done" && r ? `<h2 class="kick">Results</h2><div class="grid stats"><div class="card stat"><div class="k">Won</div><div class="v">${wins} / ${eps.length}</div><div class="s">${esc(r.model_tag || sp.model)} on ${esc(r.base_mode || sp.base_mode)}</div></div><div class="card stat"><div class="k">Mean return</div><div class="v">${fmt(eps.reduce((a, e) => a + (e.return || 0), 0) / Math.max(eps.length, 1), 3)}</div></div><div class="card stat"><div class="k">Simulated</div><div class="v">${fmtN(r.seconds_simulated, 0)} s</div></div></div>
      <div class="tw"><table><thead><tr><th>Episode</th><th>Outcome</th><th class="n">Return</th><th class="n">Damage dealt</th><th class="n">Kills</th><th class="n">Length</th></tr></thead><tbody>${eps.map((e, i) => `<tr><td>${i + 1}</td><td class="${e.won ? "res-ok" : "res-bad"}">${e.won ? "Won" : e.died ? "Died" : "Time up"}</td><td class="n">${fmt(e.return, 3)}</td><td class="n">${fmt(e.damage_dealt, 3)}</td><td class="n">${e.kills ?? "-"}</td><td class="n">${e.steps != null ? fmtN(e.steps / 20, 1) + " s" : "-"}</td></tr>`).join("")}</tbody></table></div>
      ${eps.some(e => e.clip) ? `<h2 class="kick">Episode clips</h2><div class="eps">${eps.map((e, i) => e.clip ? clipHtml({ tag: "episode " + (i + 1), url: `/sims/${id}/${i}.mp4`, url60: `/sims/${id}/${i}_60.mp4` }, e.won ? "won" : e.died ? "died" : "time up") : "").join("")}</div>` : `<p class="upd">No clips were recorded for this run.</p>`}` : ""}
    <h2 class="kick">Scenario</h2><div class="sim"><div class="card"><p class="sumtxt">${esc(summaryText(sp, mm))}</p></div><div class="card mapbox">${mapSvg(sp, defaultAngles(sp.opponents.length), false)}</div></div>
    <h2 class="kick">Run with another model</h2><div class="toolbar"><select id="othermodel" aria-label="Model">${models.map(m => `<option ${m === sp.model ? "selected" : ""}>${esc(m)}</option>`).join("")}</select><button class="btn" id="rerun" type="button">Run this scenario with that model</button><span id="rerr" class="upd" style="margin:0"></span></div>`;
    $("#cloneb").onclick = () => { try { sessionStorage.setItem("vpt-sim-clone", JSON.stringify(sp)); } catch (e) { /* ignore */ } location.hash = "#/simulate"; };
    $("#rerun").onclick = async () => {
      const b = $("#rerun"); b.disabled = true; const nx = { ...sp, model: $("#othermodel").value };
      try { const rr = await fetch("/api/sim", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(nx) }); const j = await rr.json().catch(() => ({})); if (rr.ok && j.id) { location.hash = "#/simulate/" + j.id; return; } $("#rerr").textContent = j.error || "Refused (" + rr.status + ")."; } catch (e) { $("#rerr").textContent = "Could not reach the lab."; }
      b.disabled = false;
    };
  };
  const load = async () => {
    try {
      const [rr, ls] = await Promise.all([fetch("/api/sim/" + encodeURIComponent(id), { cache: "no-store" }), loadSims().catch(() => ({ sims: list }))]);
      list = ls.sims; $("#recent").innerHTML = recentHtml(list);
      if (rr.status === 404) { $("#sbody").innerHTML = `<div class="nf"><div class="nf-ic">${pixelIcon("grid", 64)}</div><h1>No such simulation</h1><p class="lede">There is no simulation with this id. It may have been mistyped, or it is older than the lab keeps.</p><p><a class="btn" href="#/simulate">Start a new one</a></p></div>`; return "gone"; }
      if (!rr.ok) throw new Error("status " + rr.status);
      const d = await rr.json(), key = JSON.stringify([d.status, d.updated, d.message]);
      if (key !== last || d.status === "queued" || d.status === "running" || d.status === "dispatched") { const keep = window.scrollY; last = key; draw(d); window.scrollTo(0, keep); }
      return d.status;
    } catch (e) { return null; }
  };
  const first = await load();
  if (first && !["done", "failed", "gone"].includes(first)) every(5000, async () => { const s = await load(); if (s && ["done", "failed", "gone"].includes(s)) clearTimers(); });
  else if (first === null) every(5000, load);
}
