document.write(`<header><b>Scam Interrupt</b>
<a href="/web/bank.html">Mary's bank app</a><a href="/web/phones.html">Phones</a>
<a href="/web/dashboard.html">Bank dashboard</a><a href="/docs" target="_blank">API</a></header>`);
async function api(path, opts = {}) {
  const r = await fetch(path, {headers: {"Content-Type": "application/json"}, ...opts});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
const STATUS = {released: "Sent", cancelled: "Cancelled", awaiting_customer: "Held: safety check",
  awaiting_family: "Held: family check", held_review: "Held: bank review", scoring: "Checking"};
const pill = s => `<span class="pill ${s}">${STATUS[s] || s}</span>`;
const money = n => "$" + Number(n).toLocaleString(undefined, {maximumFractionDigits: 0});
