"use strict";
/* Start-up: nav, theme, header pill, first route. */
$("#nav").innerHTML = PAGES.filter(([k]) => pages[k]).map(([k, t]) => `<a href="#/${k}" data-k="${k}">${t}</a>`).join("");
window.addEventListener("hashchange", route);
$("#theme").onclick = () => {
  const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  const nx = cur === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = nx;
  try { localStorage.setItem("vpt-theme", nx); } catch (e) { /* private mode */ }
  const m = $('meta[name="theme-color"]'); if (m) m.content = nx === "dark" ? "#0c0f14" : "#f4f5f2";
};
const pill = async () => {
  try { const d = await api("/api/live"), p = $("#livepill"); p.className = "pill " + (d.online ? "on" : "off"); $("span", p).textContent = d.online ? (d.status.state || "online") : "offline"; }
  catch (e) { /* server away */ }
};
if (STATIC) { paintPill(); setInterval(paintPill, 30000); api("/api/overview").catch(() => {}); }
else { pill(); setInterval(pill, 3000); }
route();
