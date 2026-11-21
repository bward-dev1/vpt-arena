"use strict";
/* Live: HLS video of the cloud agent (or a local session) with 30/60 fps, key/mouse diagram, theatre mode, cloud worker frames. */
const HLS_JS = { src: "https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js", integrity: "sha384-9v3HcdYrO3D+OPDTjZ40RXocgE4GtXVCd3/mCS62JsM93JXgI1afJVuwjFvsu6ni" };
let hlsJsP = null;
function loadHlsJs() {
  if (window.Hls) return Promise.resolve(window.Hls);
  if (!hlsJsP) hlsJsP = new Promise((ok, no) => {
    const s = document.createElement("script"); s.src = HLS_JS.src; s.integrity = HLS_JS.integrity; s.crossOrigin = "anonymous";
    s.onload = () => window.Hls ? ok(window.Hls) : no(new Error("hls.js did not load")); s.onerror = () => { hlsJsP = null; no(new Error("hls.js blocked")); };
    document.head.appendChild(s);
  });
  return hlsJsP;
}
function keyEl(label, on, cls = "") { return `<div class="key ${cls} ${on ? "on" : ""}">${label}</div>`; }
function keysHtml(d, compact) {
  const st = d.status || {}, a = st.last_action || {}, cam = Array.isArray(a.camera) ? a.camera : [0, 0], on = !!d.online;
  const mv = Math.hypot(cam[0] || 0, cam[1] || 0), ang = Math.atan2(cam[0] || 0, cam[1] || 0), len = Math.min(34, mv * 2.2);
  const dx = Math.cos(ang) * len, dy = Math.sin(ang) * len;
  return `<div class="keys ${compact ? "compact" : ""}" style="${on ? "" : "opacity:.45"}" aria-label="Last action">
      <div class="krow">${keyEl("W", a.forward)}</div>
      <div class="krow">${keyEl("A", a.left)}${keyEl("S", a.back)}${keyEl("D", a.right)}</div>
      <div class="krow">${keyEl("Ctrl", a.sprint, "sm")}${keyEl("Shift", a.sneak, "sm")}${keyEl("Space", a.jump, "space")}</div>
      <div class="krow" style="flex-wrap:wrap;justify-content:center">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(i => keyEl(i, a["hotbar." + i], "sm")).join("")}</div>
      <div class="mouse-row">
        <div class="krow">${keyEl("LMB", a.attack, "sm")}${keyEl("RMB", a.use, "sm")}</div>
        <svg width="${compact ? 64 : 96}" height="${compact ? 64 : 96}" viewBox="-48 -48 96 96" role="img" aria-label="Camera movement ${(cam[0] || 0).toFixed(1)} pitch, ${(cam[1] || 0).toFixed(1)} yaw degrees"><circle r="42" fill="var(--panel2)" stroke="var(--line2)"/><line x1="-42" x2="42" stroke="var(--line)"/><line y1="-42" y2="42" stroke="var(--line)"/>
          ${mv > 0.01 ? `<line x1="0" y1="0" x2="${dx}" y2="${dy}" stroke="var(--accent)" stroke-width="3" stroke-linecap="round"/><circle cx="${dx}" cy="${dy}" r="4.5" fill="var(--accent)"/>` : `<circle r="3" fill="var(--faint)"/>`}</svg>
      </div>
      ${compact ? "" : `<div class="mono" style="color:var(--muted)">camera pitch ${(cam[0] || 0).toFixed(1)}, yaw ${(cam[1] || 0).toFixed(1)} deg</div>`}</div>`;
}
const liveName = (d, mm) => { const st = d.status || {}; return st.mode_name || (mm && mm[st.mode] && mm[st.mode].name) || st.mode || "a mode"; };

/* One live view: <div class="lvp"> with video + still + badge + overlay. Returns {update(d), stop()}. */
function livePlayerHtml(id, opts = {}) {
  return `<div class="lvp vbox ${opts.cls || ""}" id="${id}" data-fsbox data-pfsonly="1"><video muted autoplay playsinline aria-label="Live video of the agent"></video><img class="lv-still" alt="Latest view of the agent" hidden>
    <div class="lv-badge"><span class="livebadge on"><i></i>LIVE <b class="lv-fps">${getFps()}</b> fps</span></div>
    <div class="vtools"><button type="button" class="vbtn fps-live" aria-label="Toggle 30 or 60 fps" title="Frame rate">${getFps()}</button>${fsBtn}</div>
    <div class="lv-ov"><div class="lv-ov-info"></div><div class="lv-ov-keys"></div></div></div>`;
}
function liveController(box, mm) {
  const video = $("video", box), still = $(".lv-still", box);
  let rate = getFps(), stopHls = null, failed = { 30: false, 60: false }, started = "", ok = false, idleT = 0, stillBusy = false;
  const setOk = v => { ok = v; box.classList.toggle("hlsok", v); still.hidden = v || !still.src; };
  const setRateLabel = r => { $$(".lv-fps", box).forEach(e => e.textContent = r); $$(".fps-live", box).forEach(e => e.textContent = r); };
  const stopPlayer = () => { if (stopHls) { try { stopHls(); } catch (e) { /* ignore */ } } stopHls = null; started = ""; setOk(false); };
  function startHls() {
    const r = rate === 60 && !failed[60] ? 60 : 30;
    if (started === String(r)) return;
    stopPlayer(); started = String(r); setRateLabel(r);
    const url = `/live/hls/${r}/index.m3u8`;
    const fail = () => { if (started !== String(r)) return; failed[r] = true; stopPlayer(); if (r === 60 && !failed[30]) { startHls(); } };
    video.onplaying = () => { if (started === String(r)) setOk(true); };
    video.onerror = fail;
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url; video.play().catch(() => {});
      stopHls = () => { video.onerror = null; video.removeAttribute("src"); video.load(); };
    } else {
      let hls = null, dead = false;
      stopHls = () => { dead = true; if (hls) hls.destroy(); video.removeAttribute("src"); };
      loadHlsJs().then(Hls => {
        if (dead) return;
        if (!Hls.isSupported()) return fail();
        hls = new Hls({ liveSyncDurationCount: 3, maxBufferLength: 12, manifestLoadingMaxRetry: 2, levelLoadingMaxRetry: 2, fragLoadingMaxRetry: 2 });
        hls.on(Hls.Events.ERROR, (e, data) => { if (data.fatal) fail(); });
        hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
        hls.loadSource(url); hls.attachMedia(video);
      }).catch(fail);
    }
  }
  const onFps = e => { rate = e.detail; if (box.dataset.hls === "1") { started = ""; startHls(); } setRateLabel(started || rate); };
  document.addEventListener("vpt-fps", onFps);
  const btn = $(".fps-live", box);
  btn.addEventListener("click", () => { const nx = getFps() === 60 ? 30 : 60; lsSet("vpt-fps", String(nx)); $$(".fps-btn").forEach(b => { if (!b.disabled) b.textContent = nx; }); document.dispatchEvent(new CustomEvent("vpt-fps", { detail: nx })); });
  const wake = () => { box.classList.remove("idle"); clearTimeout(idleT); idleT = setTimeout(() => box.classList.add("idle"), 3000); };
  ["pointermove", "pointerdown", "touchstart", "keydown"].forEach(ev => box.addEventListener(ev, wake, { passive: true }));
  wake();
  function loadStill() {
    if (stillBusy) return; stillBusy = true;
    const n = new Image();
    n.onload = () => { still.src = n.src; if (!ok) still.hidden = false; stillBusy = false; };
    n.onerror = () => { stillBusy = false; };
    n.src = "/live/frame.jpg?t=" + Date.now();
  }
  return {
    update(d) {
      const st = d.status || {};
      const hasHls = !!(st.hls && (st.hls["30"] || st.hls["60"]));
      box.dataset.hls = hasHls ? "1" : "0";
      if (hasHls) startHls(); else { stopPlayer(); setRateLabel("1"); }
      if (!ok && d.frame) loadStill();
      $(".lv-badge .lv-fps", box).textContent = hasHls && started ? started : "still";
      const info = $(".lv-ov-info", box);
      if (info) info.innerHTML = `<b>${esc(liveName(d, mm))}</b>${st.checkpoint ? `<span>${esc(st.checkpoint)}</span>` : ""}<span>${st.fps == null ? "" : fmtN(st.fps, 1) + " fps sim"}</span>${st.episode ? `<span>${fmtN(st.episode.t, 1)} s</span><span>return ${fmt(st.episode.return, 3)}</span>` : ""}`;
      const kk = $(".lv-ov-keys", box); if (kk && (box.classList.contains("pfs") || document.fullscreenElement === box)) kk.innerHTML = keysHtml(d, true);
    },
    stop() { clearTimeout(idleT); document.removeEventListener("vpt-fps", onFps); stopPlayer(); },
  };
}
/* Small live preview for other pages (Dashboard). Hidden until the stream is online. */
function mountLivePreview(slot, mm) {
  if (!slot) return;
  const EMPTY = `<div class="empty">No live stream at the moment.</div>`;
  slot.innerHTML = EMPTY;
  let ctl = null, busy = false;
  const tick = async () => {
    if (busy || document.hidden || !slot.isConnected) return; busy = true;
    try {
      const d = await (await fetch(STATIC ? "/live/status.json" : "/api/live", { cache: "no-store" })).json();
      if (d.online) {
        if (!ctl) { slot.innerHTML = livePlayerHtml("lvp-mini", { cls: "mini" }) + `<div class="lvp-cap"></div>`; ctl = liveController($("#lvp-mini", slot), mm); }
        ctl.update(d);
        const st = d.status || {};
        $(".lvp-cap", slot).innerHTML = `<a href="#/live"><b>${esc(liveName(d, mm))}</b></a>${st.checkpoint ? ` <span class="tag">${esc(st.checkpoint)}</span>` : ""} <span class="cc-s">${st.episode ? fmtN(st.episode.t, 1) + " s, return " + fmt(st.episode.return, 3) : ""}</span>`;
      } else if (ctl) { ctl.stop(); ctl = null; slot.innerHTML = EMPTY; }
    } catch (e) { /* keep */ } finally { busy = false; }
  };
  tick(); every(1000, tick);
  onLeave(() => { if (ctl) ctl.stop(); });
}

let agentFilter = "";
function cloudAgents(fr, mm, md) {
  let list = (fr && fr.frames) || [];
  if (list.length) {
    const modes = [...new Set(list.map(f => f.mode))];
    if (agentFilter && !modes.includes(agentFilter)) agentFilter = "";
    const shown = agentFilter ? list.filter(f => f.mode === agentFilter) : list;
    return `<div class="toolbar chips"><button class="chip ${agentFilter ? "" : "on"}" data-af="">All modes</button>${modes.map(k => `<button class="chip ${agentFilter === k ? "on" : ""}" data-af="${esc(k)}">${esc(mm[k] ? mm[k].name : k)}</button>`).join("")}</div>
    <div class="grid cols agents">${shown.map(f => `<figure class="card agent">
      <button class="ag-img" data-zoom="${esc(f.img)}" data-cap="${esc((mm[f.mode] ? mm[f.mode].name : f.mode) + ", " + f.job)}" aria-label="Enlarge view of ${esc(f.job)}"><img src="${esc(f.img)}" alt="What ${esc(f.job)} sees in ${esc(mm[f.mode] ? mm[f.mode].name : f.mode)}" width="320" height="180" loading="lazy"></button>
      <figcaption><div class="ag-t">${modeIcon(f.mode, 18)} <b>${esc(mm[f.mode] ? mm[f.mode].name : f.mode)}</b></div>
      <div class="ag-m"><span>${esc(f.job)}</span><span>round ${f.round ?? "-"}</span><span>frame ${ago(f.updated)}</span></div>
      <div class="ag-m"><span>return <b>${fmt(f.return, 3)}</b></span><span>win <b>${pct(f.win_rate)}</b></span><span class="tag ${esc(f.state)}">${esc(f.state)}</span></div></figcaption></figure>`).join("")}</div>`;
  }
  const clips = (md.clips || []).filter(c => okUrl(c.url));
  return `<div class="note slim">The cloud workers write a frame of each simulator every 3 minutes from round 2 onward. No frames have been published yet, so these are the newest evaluation clips.</div>` +
    (clips.length ? `<div class="grid cols clipgrid">${clips.map(c => `<article class="card clipcard">${hoverClip(c.url, c.name + " " + c.tag, modeIcon(c.mode, 22), c.url60)}<div class="cc-body"><a class="cc-t" href="#/modes/${encodeURIComponent(c.mode)}">${esc(c.name)}</a><span class="tag">${esc(c.tag)}</span></div></article>`).join("")}</div>` : `<div class="empty">No clips or frames yet.</div>`);
}

pages.live = async () => {
  const [mm, ov] = await Promise.all([modeMap(), api("/api/overview")]);
  let fr = null; try { fr = await api("/api/frames"); } catch (e) { fr = null; }
  view.innerHTML = `<h1>Live</h1><p class="lede">Watch the agent play. The newest trained model plays random arena modes in the cloud around the clock. The video runs a few seconds behind; the keys and mouse diagram beside it are live. The cloud workers that train it are below.</p>
  <div id="liveslot"></div>
  <h2 class="kick">What the cloud agents see right now</h2><div id="cloudslot">${cloudAgents(fr, mm, ov)}</div>`;
  const offlineHtml = `<div class="card offline"><div class="off-ic">${pixelIcon("ring", 40)}</div><div><h3>Live stream restarting</h3><p>It comes back within a few minutes. This page checks again every few seconds and switches over by itself. The cloud agents below are still training.</p></div></div>`;
  let ctl = null, online = false, busy = false, n = 0;
  const slot = () => $("#liveslot");
  const head = (d, st) => d.source === "cloud" ? `Live: the <b>${esc(st.checkpoint || "latest")}</b> model playing <b>${esc(liveName(d, mm))}</b> in the cloud arena` : d.source === "local" ? `Live session on a private server: <b>${esc(liveName(d, mm))}</b>` : `Live: <b>${esc(liveName(d, mm))}</b>`;
  const showOffline = () => { if (ctl) { ctl.stop(); ctl = null; } online = false; const s = slot(); if (s && !s.dataset.off) { s.innerHTML = offlineHtml; s.dataset.off = "1"; } };
  const tick = async () => {
    if (busy || document.hidden) return; busy = true;
    try {
      const d = await (await fetch(STATIC ? "/live/status.json" : "/api/live", { cache: "no-store" })).json();
      const s = slot(); if (!s) return;
      if (!d.online) { showOffline(); return; }
      online = true; const st = d.status || {};
      if (!ctl) {
        s.innerHTML = `<div class="livehead"><span class="livebadge on"><i></i>LIVE</span><h2 id="lv-h"></h2><button type="button" class="btn sm" id="lv-theatre">Theatre mode</button></div>
        <div class="grid live"><div class="card">${livePlayerHtml("lvp")}<dl class="kv" id="lv-kv" style="margin-top:14px"></dl></div><div class="card"><h3>Last action</h3><div id="lv-keys"></div></div></div>`;
        delete s.dataset.off; ctl = liveController($("#lvp"), mm);
        $("#lv-theatre").onclick = () => toggleFullscreen($("#lvp"));
        window.fsHook = () => toggleFullscreen($("#lvp"));
      }
      $("#lv-h").innerHTML = head(d, st);
      $("#lv-kv").innerHTML = `<dt>State</dt><dd>${esc(st.state || "-")}${d.age != null ? ` (updated ${Math.round(d.age)} s ago)` : ""}</dd><dt>Mode</dt><dd>${esc(liveName(d, mm))}</dd>${st.checkpoint ? `<dt>Model</dt><dd>${esc(st.checkpoint)}</dd>` : ""}<dt>Simulator</dt><dd>${st.fps == null ? "-" : fmtN(st.fps, 1) + " fps"}</dd><dt>Episode</dt><dd>${st.episode ? `${fmtN(st.episode.t, 1)} s, return ${fmt(st.episode.return, 4)}` : "-"}</dd>`;
      $("#lv-keys").innerHTML = keysHtml(d, false);
      ctl.update(d);
    } catch (e) { showOffline(); } finally { busy = false; }
  };
  await tick();
  if (!online) showOffline();
  every(1000, () => { n++; if (online || n % 3 === 0) tick(); });
  every(60000, async () => { try { snapT = 0; const f = await api("/api/frames").catch(() => null); const o = await api("/api/overview"); const c = $("#cloudslot"); if (c) c.innerHTML = cloudAgents(f, mm, o); } catch (e) { /* keep */ } });
  onLeave(() => { if (ctl) ctl.stop(); });
  view.addEventListener("click", e => { const b = e.target.closest("[data-af]"); if (!b) return; agentFilter = b.dataset.af; api("/api/frames").catch(() => null).then(f => { const c = $("#cloudslot"); if (c) c.innerHTML = cloudAgents(f, mm, ov); }); });
};

/* "LIVE" badge for other pages: shown only while the stream is online. */
async function mountLiveBadge(el) {
  if (!el) return;
  try {
    const r = await fetch(STATIC ? "/live/status.json" : "/api/live", { cache: "no-store" }), d = await r.json();
    if (!d.online || !el.isConnected) return;
    const mm = await modeMap().catch(() => ({}));
    el.innerHTML = `<a class="livebadge on" href="#/live"><i></i>LIVE <span>${esc(liveName(d, mm))}</span></a>`;
  } catch (e) { /* no badge */ }
}
