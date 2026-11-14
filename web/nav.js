const LOGO = `<svg viewBox="0 0 40 44" aria-hidden="true"><path d="M20 2 L37 8 V21 C37 32 29.5 39.5 20 42 C10.5 39.5 3 32 3 21 V8 Z" style="fill:var(--harbor)"/><rect x="13" y="13" width="5" height="17" rx="2" style="fill:var(--paper)"/><rect x="22" y="13" width="5" height="17" rx="2" style="fill:var(--paper)"/></svg>`;
const FAVICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 44"><path d="M20 2 L37 8 V21 C37 32 29.5 39.5 20 42 C10.5 39.5 3 32 3 21 V8 Z" fill="#1F5566"/><rect x="13" y="13" width="5" height="17" rx="2" fill="#FFFCF6"/><rect x="22" y="13" width="5" height="17" rx="2" fill="#FFFCF6"/></svg>`;
const THEMES = [
  { id: "sand", name: "Sand", a: "#F3ECDF", b: "#1F5566" },
  { id: "sage", name: "Sage", a: "#E8EEE4", b: "#2F6A4D" },
  { id: "bloom", name: "Bloom", a: "#F5E8E4", b: "#8A3A5C" },
  { id: "dusk", name: "Dusk (dark)", a: "#212A31", b: "#7CC4D6" },
  { id: "contrast", name: "High contrast", a: "#FFFFFF", b: "#000000" },
];
const pref = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
document.documentElement.dataset.theme = pref("si-theme") || "sand";
document.documentElement.dataset.size = pref("si-size") || "normal";
function setTheme(id) {
  document.documentElement.dataset.theme = id; pref("si-theme", id);
  document.querySelectorAll(".swatch").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
}
function toggleSize() {
  const big = document.documentElement.dataset.size !== "large";
  document.documentElement.dataset.size = big ? "large" : "normal"; pref("si-size", big ? "large" : "normal");
  document.getElementById("sizeBtn").setAttribute("aria-pressed", String(big));
}
(function () {
  const page = location.pathname.split("/").pop() || "index.html";
  const tab = (href, label) => `<a href="${href}" ${page === href ? 'aria-current="page"' : ""}>${label}</a>`;
  const fav = document.createElement("link"); fav.rel = "icon";
  fav.href = "data:image/svg+xml," + encodeURIComponent(FAVICON);
  document.head.appendChild(fav);
  document.write(`<header class="topbar"><div class="topbar-in">
    <a class="brand" href="index.html">${LOGO}<span><b>Scam Interrupt</b><small>A second voice before the money moves</small></span></a>
    <nav class="tabs" aria-label="Screens">${tab("bank.html", "Mary’s bank")}${tab("phones.html", "Phones")}${tab("dashboard.html", "Bank dashboard")}</nav>
    <div class="chips" id="modes"></div>
    <div class="prefs">
      <div class="swatches" role="group" aria-label="Color theme">${THEMES.map(t =>
        `<button class="swatch" data-id="${t.id}" title="${t.name}" aria-label="${t.name} theme" aria-pressed="${document.documentElement.dataset.theme === t.id}"
          style="--a:${t.a};--b:${t.b}" onclick="setTheme('${t.id}')"></button>`).join("")}</div>
      <button class="size-btn" id="sizeBtn" title="Larger text" aria-label="Larger text" aria-pressed="${document.documentElement.dataset.size === "large"}" onclick="toggleSize()">A+</button>
    </div></div></header>`);
  fetch("/api/health").then(r => r.json()).then(h => {
    const chip = (on, text) => `<span class="chip ${on ? "on" : ""}"><i></i>${text}</span>`;
    document.getElementById("modes").innerHTML =
      chip(h.nessie_mode === "live", "Capital One Nessie " + h.nessie_mode) +
      chip(h.photon_mode === "live", "Photon " + h.photon_mode) +
      chip(h.agent_mode === "deepagents", h.agent_mode === "deepagents" ? "Deep Agents on" : "Fixed pipeline") +
      chip(h.model && h.model !== "rules", h.model === "rules" ? "Rules only" : "AI model on");
  }).catch(() => {});
})();
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
const STATUS = { released: "Sent", cancelled: "Cancelled: nothing was sent", awaiting_customer: "Paused: please answer our message",
  awaiting_family: "Paused: checking with family", held_review: "Paused for review", scoring: "Checking…" };
const STAFF = { released: "Sent", cancelled: "Cancelled", awaiting_customer: "Waiting on customer",
  awaiting_family: "Waiting on family", held_review: "Bank review", scoring: "Checking" };
const stamp = (s, fresh, staff) => `<span class="stamp ${s}${fresh ? " fresh" : ""}">${(staff ? STAFF : STATUS)[s] || s}</span>`;
const money = n => "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
