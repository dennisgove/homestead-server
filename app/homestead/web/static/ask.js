// Ask: sends the question, then shows the answer as it streams in (JSON lines from /api/ask).
(() => {
  const talk = document.getElementById("talk");
  const form = document.getElementById("askform");
  const box = document.getElementById("question");
  const send = document.getElementById("send");
  let history = [];

  const esc = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // Enough Markdown for the answers: paragraphs, lists, headings, bold, [n] citations as links.
  function render(md, sources) {
    let out = "", list = null;
    const inline = s => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[(\d+)\]/g, (m, n) => {
        const src = sources.find(x => String(x.n) === n);
        return src ? `<a class="cite" href="${esc(src.url)}" target="_blank" title="${esc(src.title)}">[${n}]</a>` : m;
      });
    for (const raw of esc(md).split("\n")) {
      const line = raw.trimEnd();
      const ul = line.match(/^\s*[-*•]\s+(.*)/), ol = line.match(/^\s*\d+[.)]\s+(.*)/);
      const want = ul ? "ul" : ol ? "ol" : null;
      if (list && want !== list) { out += `</${list}>`; list = null; }
      if (want) { if (!list) { out += `<${want}>`; list = want; } out += `<li>${inline((ul || ol)[1])}</li>`; }
      else if (/^#{1,4}\s/.test(line)) out += `<h3>${inline(line.replace(/^#+\s*/, ""))}</h3>`;
      else if (line.trim()) out += `<p>${inline(line)}</p>`;
    }
    return list ? out + `</${list}>` : out;
  }

  const sourcesHtml = s => !s.length ? "" : "<div class=\"sources\"><b>Sources</b><ol>" +
    s.map(x => `<li value="${x.n}"><a href="${esc(x.url)}" target="_blank">${esc(x.title)}</a></li>`).join("") + "</ol></div>";

  async function ask(q) {
    const me = document.createElement("div");
    me.className = "say me"; me.textContent = q; talk.appendChild(me);
    const it = document.createElement("div");
    it.className = "say it"; it.innerHTML = '<p class="meta wait">Looking it up in the library…</p>';
    const body = document.createElement("div"), srcs = document.createElement("div");
    it.append(body, srcs); talk.appendChild(it);
    it.scrollIntoView({ behavior: "smooth", block: "end" });
    send.disabled = true;
    let text = "", sources = [], wait = it.querySelector(".wait");
    const unwait = () => { if (wait) { wait.remove(); wait = null; } };
    try {
      const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: JSON.stringify({ question: q, history }) });
      if (!r.ok) throw new Error("the server said " + r.status);
      const reader = r.body.getReader(), dec = new TextDecoder();
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
          if (m.status && wait) wait.textContent = m.status;
          if (m.sources) { sources = m.sources; srcs.innerHTML = sourcesHtml(sources); }
          if (m.t) { unwait(); text += m.t; body.innerHTML = render(text, sources); }
          if (m.error) { unwait(); body.insertAdjacentHTML("beforeend", `<p class="err">${esc(m.error)}</p>`); }
        }
      }
    } catch (e) {
      unwait();
      body.insertAdjacentHTML("beforeend", `<p class="err">Couldn't get an answer (${esc(String(e.message || e))}). Try again in a minute.</p>`);
    }
    send.disabled = false;
    history.push({ role: "user", content: q });
    if (text) history.push({ role: "assistant", content: text });
    box.focus();
  }

  form.addEventListener("submit", ev => {
    ev.preventDefault();
    const q = box.value.trim();
    if (q && !send.disabled) { box.value = ""; ask(q); }
  });
  box.addEventListener("keydown", ev => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); } });
  document.getElementById("again").addEventListener("click", () => { history = []; talk.innerHTML = ""; box.focus(); });
  if (box.value.trim()) form.requestSubmit();
})();
