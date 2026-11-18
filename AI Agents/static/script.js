const $ = id => document.getElementById(id);
const log = $("log"), msg = $("msg"), send = $("send"), auto = $("auto"), form = $("chat-form");
const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;

let threadId = crypto.randomUUID();
let typing = null;
let last = null; // last request, used by Retry

/* ---------- helpers ---------- */
const esc = s => String(s).replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));

// Small markdown subset: **bold**, `code`, [text](url), bare links, "- " lists
function md(text) {
  const inline = t => t
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/(?<!["'=>])(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  let out = "", list = false;
  for (const line of esc(text).split("\n")) {
    const li = line.match(/^\s*[-*•]\s+(.*)/);
    if (li) {
      if (!list) { out += "<ul>"; list = true; }
      out += `<li>${inline(li[1])}</li>`;
      continue;
    }
    if (list) { out += "</ul>"; list = false; }
    if (line.trim()) out += `<p>${inline(line)}</p>`;
  }
  return out + (list ? "</ul>" : "");
}

const toBottom = () => log.scrollTo({ top: log.scrollHeight, behavior: calm ? "auto" : "smooth" });

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

/* ---------- rendering ---------- */
function addUser(text) {
  const m = el("article", "msg user", `<div class="bubble">${esc(text)}</div>`);
  log.append(m); toBottom();
}

function addBot(text) {
  const m = el("article", "msg bot",
    `<span class="avatar" aria-hidden="true">🌤️</span>
     <div class="stack"><div class="bubble">${md(text)}</div>
     <button class="copy" type="button">Copy</button></div>`);
  m.querySelector(".copy").onclick = async e => {
    try { await navigator.clipboard.writeText(text); e.target.textContent = "Copied"; }
    catch { e.target.textContent = "Copy failed"; }
    setTimeout(() => (e.target.textContent = "Copy"), 1500);
  };
  log.append(m); toBottom();
}

function addError(text, retry) {
  const m = el("div", "err", `<span>${esc(text)}</span>`);
  if (retry) {
    const b = el("button", "", "Try again");
    b.type = "button";
    b.onclick = () => { m.remove(); call(retry.url, retry.body); };
    m.append(b);
  }
  log.append(m); toBottom();
}

function setBusy(on) {
  send.disabled = msg.disabled = on;
  if (on && !typing) {
    typing = el("article", "msg bot",
      `<span class="avatar" aria-hidden="true">🌤️</span>
       <div class="bubble"><span class="dots" role="status"><i></i><i></i><i></i>Checking live data</span></div>`);
    log.append(typing); toBottom();
  } else if (!on && typing) {
    typing.remove(); typing = null;
  }
}

function welcome() {
  const h = new Date().getHours();
  const tod = h < 5 ? "night" : h < 11 ? "morning" : h < 17 ? "day" : h < 20 ? "evening" : "night";
  const hello = { morning: "Good morning.", day: "Good afternoon.", evening: "Good evening.", night: "Still up?" }[tod];
  const prompts = [
    ["Weather in Kolkata", "Temperature and conditions right now", "What's the weather in Kolkata?"],
    ["News in Mumbai", "Today's top local headlines", "Latest news in Mumbai"],
    ["Rain in Delhi?", "Current conditions and chance of rain", "Is it raining in Delhi?"],
    ["Durgapur briefing", "Weather and news together", "Weather and news in Durgapur"]
  ];
  const w = el("section", "welcome",
    `<div class="sky ${tod}" aria-hidden="true"><div class="orb"></div><div class="cloud a"></div><div class="cloud b"></div><div class="cloud c"></div></div>
     <h2>${hello} Which city are you curious about?</h2>
     <p>Ask for the weather, the news, or both. I look up live data before I answer.</p>
     <div class="prompts">${prompts.map(p =>
       `<button class="prompt" type="button" data-q="${esc(p[2])}"><b>${esc(p[0])}</b><span>${esc(p[1])}</span></button>`
     ).join("")}</div>`);
  w.addEventListener("click", e => {
    const b = e.target.closest(".prompt");
    if (b) submit(b.dataset.q);
  });
  log.append(w);
}

/* ---------- server calls ---------- */
async function call(url, body) {
  last = { url, body };
  setBusy(true);
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(`Server returned ${r.status}`);
    setBusy(false);
    handle(await r.json());
  } catch (e) {
    setBusy(false);
    addError(`Could not reach the assistant. ${e.message}`, last);
  } finally {
    if (!msg.disabled) msg.focus();
  }
}

function handle(d) {
  if (d.type === "message") return addBot(d.content || "I didn't get a reply. Try asking again.");
  if (d.type === "error") return addError(d.content || "Something went wrong.", last);
  if (d.type !== "approval") return addError("Unexpected response from the server.", last);

  if (auto.checked) return call("/api/decision", { thread_id: threadId, approve: true });

  const tools = (d.actions || []).map(a => {
    const args = Object.entries(a.args || {}).map(([k, v]) => `${k}: ${v}`).join(", ");
    return `<div class="tool"><code>${esc(a.name)}</code>${args ? `<small>${esc(args)}</small>` : ""}</div>`;
  }).join("");
  const card = el("section", "ask",
    `<h3>Permission needed</h3><p>The assistant wants to run:</p>${tools}
     <div class="row"><button class="yes" type="button">Approve</button><button class="no" type="button">Deny</button></div>`);

  const decide = ok => {
    card.querySelector(".row").replaceWith(el("div", "status", ok ? "Approved" : "Denied"));
    call("/api/decision", { thread_id: threadId, approve: ok });
  };
  card.querySelector(".yes").onclick = () => decide(true);
  card.querySelector(".no").onclick = () => decide(false);
  log.append(card); toBottom();
  card.querySelector(".yes").focus({ preventScroll: true });
}

function submit(text) {
  text = text.trim();
  if (!text || send.disabled) return;
  log.querySelector(".welcome")?.remove();
  addUser(text);
  msg.value = ""; grow();
  call("/api/chat", { thread_id: threadId, message: text });
}

/* ---------- input ---------- */
function grow() {
  msg.style.height = "auto";
  msg.style.height = Math.min(msg.scrollHeight, 140) + "px";
}
msg.addEventListener("input", grow);
msg.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    submit(msg.value);
  }
});
form.addEventListener("submit", e => { e.preventDefault(); submit(msg.value); });

$("reset").onclick = () => {
  threadId = crypto.randomUUID();
  setBusy(false);
  log.innerHTML = "";
  welcome();
  msg.focus();
};

/* ---------- preferences ---------- */
try { auto.checked = localStorage.getItem("auto") === "1"; } catch {}
auto.onchange = () => { try { localStorage.setItem("auto", auto.checked ? "1" : "0"); } catch {} };

welcome();
msg.focus();
