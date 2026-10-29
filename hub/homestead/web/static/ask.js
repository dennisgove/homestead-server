// The Ask page: streams the answer from /api/ask (NDJSON) and renders it.
(function () {
  const chat = document.getElementById("chat");
  const form = document.getElementById("askform");
  const box = document.getElementById("question");
  const send = document.getElementById("send");
  let history = [];

  function esc(s) {
    return s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // Just enough Markdown for the model's answers: paragraphs, lists, bold, headings, [n] citations.
  function render(md, sources) {
    const lines = esc(md).split("\n");
    let out = "", list = null;
    const inline = s => s
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[(\d+)\]/g, (m, n) => {
        const src = sources.find(x => String(x.n) === n);
        return src ? `<a class="cite" href="${esc(src.url)}" target="_blank" title="${esc(src.title)}">[${n}]</a>` : m;
      });
    for (const raw of lines) {
      const line = raw.trimEnd();
      const ul = line.match(/^\s*[-*•]\s+(.*)/), ol = line.match(/^\s*\d+[.)]\s+(.*)/);
      const want = ul ? "ul" : ol ? "ol" : null;
      if (list && want !== list) { out += `</${list}>`; list = null; }
      if (want) {
        if (!list) { out += `<${want}>`; list = want; }
        out += `<li>${inline((ul || ol)[1])}</li>`;
      } else if (/^#{1,4}\s/.test(line)) {
        out += `<h3>${inline(line.replace(/^#+\s*/, ""))}</h3>`;
      } else if (line.trim()) {
        out += `<p>${inline(line)}</p>`;
      }
    }
    if (list) out += `</${list}>`;
    return out;
  }

  function sourcesHtml(sources) {
    if (!sources.length) return "";
    return "<div class=\"sources\"><b>Sources</b><ol>" + sources.map(s =>
      `<li value="${s.n}"><a href="${esc(s.url)}" target="_blank">${esc(s.title)}</a> <span class="meta">${esc(s.book || "")}</span></li>`
    ).join("") + "</ol></div>";
  }

  async function ask(q) {
    const you = document.createElement("div");
    you.className = "msg you";
    you.textContent = q;
    chat.appendChild(you);
    const bot = document.createElement("div");
    bot.className = "msg bot";
    bot.innerHTML = '<p class="status muted">Searching the library…</p>';
    chat.appendChild(bot);
    bot.scrollIntoView({ behavior: "smooth", block: "end" });
    send.disabled = true;

    let text = "", sources = [], status = bot.querySelector(".status");
    const body = document.createElement("div");
    const srcs = document.createElement("div");
    bot.appendChild(body);
    bot.appendChild(srcs);
    try {
      const r = await fetch("/api/ask", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history })
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, i); buf = buf.slice(i + 1);
          if (!line.trim()) continue;
          const m = JSON.parse(line);
          if (m.status && status) status.textContent = m.status;
          if (m.sources) { sources = m.sources; srcs.innerHTML = sourcesHtml(sources); }
          if (m.t) {
            if (status) { status.remove(); status = null; }
            text += m.t;
            body.innerHTML = render(text, sources);
          }
          if (m.error) {
            if (status) { status.remove(); status = null; }
            body.insertAdjacentHTML("beforeend", `<p class="err">${esc(m.error)}</p>`);
          }
        }
      }
    } catch (e) {
      if (status) status.remove();
      body.insertAdjacentHTML("beforeend", `<p class="err">Couldn't reach the AI (${esc(String(e.message || e))}). Try again in a minute.</p>`);
    }
    send.disabled = false;
    history.push({ role: "user", content: q });
    if (text) history.push({ role: "assistant", content: text });
    box.focus();
  }

  form.addEventListener("submit", ev => {
    ev.preventDefault();
    const q = box.value.trim();
    if (!q || send.disabled) return;
    box.value = "";
    ask(q);
  });
  box.addEventListener("keydown", ev => {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
  });
  document.getElementById("newchat").addEventListener("click", () => { history = []; chat.innerHTML = ""; box.focus(); });
  if (box.value.trim()) form.requestSubmit();
})();
