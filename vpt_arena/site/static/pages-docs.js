"use strict";
/* Training, Data, League and Docs pages. */
function roundsView(r, names) {
  if (!r.rounds.length) return `<div class="empty">No evaluated releases yet. After each round the merged policy is released as round-N and evaluated on every mode, and the baseline VPT model is evaluated the same way. Win rate and return per mode will appear here so rounds can be compared.</div>`;
  const modes = r.modes.filter(k => r.rounds.some(x => x.modes[k]));
  const best = {};
  modes.forEach(k => { const c = r.rounds.filter(x => x.modes[k] && x.modes[k].win_rate != null);
    if (c.length > 1) best[k] = c.reduce((a, b) => { const A = a.modes[k], B = b.modes[k]; return (B.win_rate > A.win_rate || (B.win_rate === A.win_rate && B.return > A.return)) ? b : a; }).tag; });
  return `<p class="upd" style="margin:0 0 8px">Each cell is win rate against the scripted arena bots, with mean return below it. The outlined cell is the best release for that mode. Shading follows win rate.</p>
  <div class="tw"><table class="rounds"><thead><tr><th>Mode</th>${r.rounds.map(x => `<th class="n">${esc(x.tag)}${x.track === "openai" ? `<span class="th-sub">OpenAI</span>` : x.track === "scratch" ? `<span class="th-sub">scratch</span>` : x.tag === "baseline" ? `<span class="th-sub">reference</span>` : ""}</th>`).join("")}</tr></thead><tbody>
  ${modes.map(k => `<tr><td>${esc(names[k] || k)}</td>${r.rounds.map(x => { const v = x.modes[k]; return v ? `<td class="rc ${best[k] === x.tag ? "best" : ""}" style="--w:${v.win_rate || 0}"><b>${pct(v.win_rate)}</b><span>${fmt(v.return, 3)}${v.episodes !== 3 && v.episodes != null ? ` <em class="ep">n=${v.episodes}</em>` : ""}</span></td>` : `<td class="rc none">-</td>`; }).join("")}</tr>`).join("")}
  <tr class="sum"><td>Mean win rate</td>${r.rounds.map(x => `<td class="n"><b>${pct(x.mean_win_rate)}</b></td>`).join("")}</tr>
  <tr class="sum"><td>Mean return</td>${r.rounds.map(x => `<td class="n">${fmt(x.mean_return, 3)}</td>`).join("")}</tr>
  <tr class="sum"><td>Elo vs arena bots</td>${r.rounds.map(x => `<td class="n">${x.elo == null ? "-" : Math.round(x.elo)}</td>`).join("")}</tr>
  </tbody></table></div>`;
}
function workersView(w, names) {
  if (!w.workers.length) return `<div class="empty">No workers reported yet. Each round starts 12 workers that train two modes each; their progress appears here, grouped by round.</div>`;
  const groups = new Map();
  w.workers.forEach(x => { const k = x.round == null ? "other" : (x.track === "scratch" ? "s" : "") + x.round; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(x); });
  return [...groups].map(([k, list]) => {
    const by = {}; list.forEach(x => by[x.state] = (by[x.state] || 0) + 1);
    return `<h3 style="margin:1.2em 0 .5em">${k === "other" ? "Other workers" : String(k).startsWith("s") ? "From-scratch round " + String(k).slice(1) : "VPT round " + k} <small style="color:var(--muted);font-weight:500">${list.length} worker(s): ${Object.entries(by).map(([s, n]) => n + " " + s).join(", ")}</small></h3>
    <div class="tw"><table><thead><tr><th>Worker</th><th>State</th><th class="n">Iter</th><th class="n">Steps</th><th class="n">FPS</th><th class="n">Min left</th><th>Modes: return, win rate</th><th>Updated</th></tr></thead><tbody>
    ${list.map(x => `<tr><td><a href="#/training/${encodeURIComponent(x.job)}">${esc(x.job)}</a></td><td><span class="tag ${x.state}">${esc(x.state)}</span></td><td class="n">${x.iter ?? "-"}</td><td class="n">${x.env_steps == null ? "-" : Number(x.env_steps).toLocaleString()}</td><td class="n">${x.fps == null ? "-" : fmtN(x.fps, 1)}</td><td class="n">${x.minutes_left == null ? "-" : Math.round(x.minutes_left)}</td>
    <td class="wrap">${(x.modes.length ? x.modes : Object.keys(x.per_mode)).map(m => { const v = x.per_mode[m]; return `<div class="pm"><b>${esc(names[m] || m)}</b> ${v ? `return ${fmt(v.return, 3)}, win ${pct(v.win_rate)} <span class="mono">(${v.episodes} ep)</span>` : `<span class="mono">no episodes yet</span>`}</div>`; }).join("")}</td><td>${ago(x.updated)}</td></tr>`).join("")}
    </tbody></table></div>`;
  }).join("");
}


let selRun = null;
pages.training = async () => {
  view.innerHTML = `<h1>Training</h1><p class="lede">Runs under <code>runs/</code>. ${STATIC ? "This public page refreshes about once a minute from a snapshot that is rebuilt every 5 minutes." : "Charts refresh every 10 seconds."}</p>
  <h2>Rounds</h2><div id="rounds"></div>
  <h2>Workers</h2><div id="workers"></div>
  <h2>Run charts</h2><div id="runs" class="runs"></div><div id="detail"></div>`;
  const loadCloud = async () => {
    const [r, w, md] = await Promise.all([api("/api/rounds"), api("/api/workers"), api("/api/modes")]);
    const names = Object.fromEntries(md.modes.map(m => [m.key, m.name]));
    $("#rounds").innerHTML = roundsView(r, names);
    $("#workers").innerHTML = workersView(w, names);
  };
  const load = async () => {
    await loadCloud().catch(e => { $("#rounds").innerHTML = $("#workers").innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; });
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
    if (want && !scrolled) { scrolled = true; $("#detail").scrollIntoView(); }
  };
  let scrolled = false;
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

/* ---------- docs ---------- */
const DOCS = [
 ["intro", "What this is", `
<p>VPT Arena trains one network to play survival Minecraft and the PvP minigames. The network takes 128x128 game frames and outputs keyboard and mouse actions at 20 Hz. It starts from OpenAI's Video PreTraining (VPT) foundation model. A learned embedding for the game mode, the combat ruleset (1.8 or 1.9+) and the team size is added to the model input. The embedding starts at zero.</p>
<div class="note"><b>Server scope.</b> It is for a server you run only. Public servers such as Hypixel ban bots, and nothing in this project deals with anti-cheat. Do not point the live client at a server you do not run.</div>
<p>All phases have code. Each section below says what its command does and how far it has been tested; the Overview page shows the same per phase. So far the real-world checks are the 1x weights on one contractor clip, a short BC fine-tune, and cloud RL in MineStudio (see How cloud RL works). The recorder, live agent and datapack have been tested with fakes only, and the live-server RL path below with a toy environment only.</p>`],
 ["cloud", "How cloud RL works", `
<p>Training that needs real gameplay runs on GitHub Actions in the public repository <a href="${REPO_URL}">bward-dev1/vpt-arena</a>. Each round works like this:</p>
<ul>
<li>12 workers start at the same time. Each worker trains 2 game modes. Workers run MineStudio on Minecraft 1.16.5.</li>
<li>Opponents are armed mobs in sky arenas, standing in for players. There is no live server and no other person involved.</li>
<li>Opponent strength follows a curriculum: round 0 used full-strength opponents; from round 1 they start at 0.45 of full strength (fewer armour pieces, weapons one tier lower) and gain 0.15 per round until full strength.</li>
<li>Training is PPO with a KL penalty that pulls the policy toward the policy the round started from.</li>
<li>When the workers finish, their policies are merged into one by federated averaging, and the result is released as <code>round-N</code>.</li>
<li>Each release is then evaluated on all 23 modes, 3 games each, at a fixed opponent strength of 0.5, against the scripted arena bots, which hold an Elo of 1000. The original VPT foundation model is evaluated the same way and appears as <code>baseline</code>. A short gameplay clip of every mode is attached to the release.</li>
<li>A round takes about 2.5 hours. The runners have no GPU, so the game renders on the CPU at about 20 frames per second per simulation.</li>
</ul>
<p>A script on a local machine reads worker status files and release assets every few minutes and writes the data this site shows: the Dashboard, the Workers and Rounds sections on Training, the League page and the clips (copied to Cloudflare so browsers can play them inline). The Rounds table compares releases per mode so improvement from one round to the next is visible. Source code and releases: <a href="${REPO_URL}">${REPO_URL.replace("https://", "")}</a>.</p>`],
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
<li>It writes <code>live/status.json</code> and <code>live/frame.jpg</code> every second, which the Live page reads (the public site shows them within about a second while a session runs). It needs Accessibility permission.</li>
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
 ["sim", "Simulation Lab", `
<p>The Simulate tab lets anyone design a small custom scenario and watch a trained model play it. The scenario runs in the cloud, not in your browser.</p>
<ul>
<li><b>What you can set.</b> The model (baseline, latest or any released round), the game mode that conditions the policy, the arena (size, floor block, void, lava or ground below, day or night), your loadout (weapon, armor, bow and arrows, blocks, golden apples), up to 4 opponent groups, an optional goal (a bridge to cross or a bed to reach), the length in seconds, the number of episodes, the opponent strength and a random seed.</li>
<li><b>Opponents are mobs.</b> Zombies, skeletons, vindicators and the other mob types stand in for players, the same way they do in training. No real player or server is involved.</li>
<li><b>Where it runs.</b> On a free GitHub Actions CPU runner. The runner has to start Minecraft before the first frame, so a run takes about 6 to 10 minutes. The page shows the state (queued, dispatched, running, done) and updates every 5 seconds.</li>
<li><b>Results.</b> Per episode: won or died, return, damage dealt, kills and length, with a clip of each episode when it was recorded.</li>
<li><b>Limits.</b> 3 simulations per person per hour, 30 a day for the whole lab, and at most 8 waiting or running at once. An arena is 3 to 16 blocks, a run is 10 to 120 seconds, 1 to 3 episodes, and at most 6 opponents in total. Anything outside the limits is refused with a message that says which setting.</li>
<li><b>Sharing.</b> Every run has its own link, <code>#/simulate/&lt;id&gt;</code>. The Recent simulations list shows the latest runs from everyone, with their names and settings. Do not put personal information in a name.</li>
</ul>`],
 ["trailer", "Trailer", `
<p>The project trailer is a short video made from real evaluation clips. It plays from the Overview page (Watch the trailer) and appears there once it has been published. The design notes for it, covering the look, pacing and how the footage was chosen, are in the repository: <a href="${REPO_URL}/blob/main/trailer/DESIGN.md">trailer/DESIGN.md</a>.</p>`],
 ["tracks", "VPT and from-scratch tracks", `
<p>Two tracks train side by side so that the value of pretraining can be measured. The <b>VPT track</b> starts from OpenAI's VPT model, which was pretrained on about 70,000 hours of YouTube Minecraft video. Its workers are named <code>r&lt;round&gt;-w&lt;n&gt;</code>, it releases <code>round-N</code>, and it trains with the image encoder frozen and an adaptive difficulty for each mode. The <b>from-scratch track</b> is a small policy of about 5 million parameters in the same architecture family, trained with no pretraining. It uses 6 workers with 4 modes each, named <code>s&lt;round&gt;-s&lt;n&gt;</code>, and releases <code>scratch-N</code>.</p>
<p>A third group, <b>OpenAI (released)</b>, holds OpenAI's own final models, <code>openai-rl-2x</code>, <code>openai-2x</code> and <code>openai-3x</code>, evaluated the same way as references. The 3x model plays 1 episode per mode because it is slow on CPU, so its numbers are noisier, and the tables mark episode counts that differ. Both training tracks use the same arenas, the same PPO loop and the same evaluation (3 games per mode against the scripted bots). The Dashboard and Overview compare the newest <code>round-N</code> with OpenAI's best released model, and with <code>scratch-N</code> at the same round number. The Simulation Lab can run only the VPT <code>round-N</code> models for now; the 2x and 3x architectures are not supported there.</p>`],
 ["colab", "Colab pipeline", `
<p><code>colab/train.sh</code> runs the full pipeline on a GPU: it downloads the weights, checks them, fetches contractor clips, labels the videos in <code>videos/&lt;mode&gt;/</code> with the IDM, and runs BC.</p>
<p><b>Status:</b> not run. It needs a Colab or similar GPU session, which the maintainer starts by hand.</p>`],
 ["site", "Running this site", `
<pre><code>python -m vpt_arena.site.server --port 7790 --root .</code></pre>
<p>A public copy of this site is a static build of the same pages. The data comes from one snapshot that is rebuilt every 5 minutes; it leaves out player names, server addresses and local paths. The Live page reads the local agent through a temporary tunnel when a session is running.</p>
<p>The local server listens on the loopback interface only, uses the Python standard library, and reads files under the root. It does not start processes. Its only writes are first-frame thumbnails under <code>runs/.site-cache/</code>. Pages are plain HTML, CSS and JavaScript with no external requests.</p>`],
];
pages.docs = async () => {
  view.innerHTML = `<div class="docs"><nav class="toc" aria-label="Docs sections">${DOCS.map(([id, t]) => `<a href="#/docs/${id}">${t}</a>`).join("")}</nav>
  <div class="doc"><h1>Docs</h1>${DOCS.map(([id, t, body]) => `<h2 id="doc-${id}">${t}</h2>${body}`).join("")}</div></div>`;
  const sec = location.hash.split("/")[2];
  if (sec) { const el = document.getElementById("doc-" + sec); if (el) el.scrollIntoView(); }
};

