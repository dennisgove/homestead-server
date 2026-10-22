// Homestead portal. No frameworks, no network beyond this box.
(function () {
  "use strict";
  var C = window.HOMESTEAD;
  var host = location.hostname || "library.lan";

  function url(port, path) {
    return "http://" + host + ":" + port + (path || "/");
  }

  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) {
      if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { e.appendChild(c); });
    return e;
  }

  function tile(t) {
    var href = t.port ? url(t.port, t.path) : t.href;
    return el("a", { "class": "tile", href: href }, [
      el("span", { "class": "icon", text: t.icon || "" }),
      el("span", { "class": "label", text: t.label }),
      el("span", { "class": "hint", text: t.hint || "" })
    ]);
  }

  function fill(id, list) {
    var box = document.getElementById(id);
    if (!box) return;
    list.forEach(function (t) { box.appendChild(tile(t)); });
  }

  // Searches go to the essentials library (on the internal disk, always up).
  function searchUrl(q) {
    return url(C.ports.core_library, "/search?pattern=" + encodeURIComponent(q));
  }
  C.emergency.forEach(function (t) { t.href = searchUrl(t.q); });

  fill("topics", C.topics.map(function (t) {
    t.href = t.q ? searchUrl(t.q) : t.href; return t;
  }));
  fill("tools", C.tools);
  fill("admin", C.admin);
  fill("em", C.emergency);

  var ssid = document.getElementById("ssid");
  if (ssid) ssid.textContent = C.ssid;

  var form = document.getElementById("search");
  if (form) form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var q = document.getElementById("q").value.trim();
    if (q) location.href = searchUrl(q);
  });

  // PDFs pulled by fetch_content.py, grouped by category.
  function loadDocs() {
    var box = document.getElementById("docs");
    if (!box) return;
    var only = box.getAttribute("data-category");
    fetch("data/docs.json", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (docs) {
        box.innerHTML = "";
        var cats = {};
        docs.forEach(function (d) {
          if (only && d.category !== only) return;
          (cats[d.category] = cats[d.category] || []).push(d);
        });
        Object.keys(cats).sort().forEach(function (cat) {
          var ul = el("ul");
          cats[cat].sort(function (a, b) { return a.title.localeCompare(b.title); })
            .forEach(function (d) {
              ul.appendChild(el("li", {}, [el("a", { href: "/docs/" + d.path, text: d.title })]));
            });
          var det = el("details", only ? { open: "" } : {}, [
            el("summary", { text: (C.categories[cat] || cat) + " (" + cats[cat].length + ")" }), ul
          ]);
          box.appendChild(det);
        });
        if (!box.children.length) box.appendChild(el("p", { "class": "muted", text: "No guides downloaded yet." }));
      })
      .catch(function () {
        box.innerHTML = "";
        box.appendChild(el("p", { "class": "muted", text: "Guide list unavailable. Browse /docs/ directly." }));
      });
  }

  function pill(text, cls) { return el("span", { "class": "pill " + (cls || ""), text: text }); }

  function loadStatus() {
    var box = document.getElementById("status");
    if (!box) return;
    fetch("status/status.json", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (s) {
        box.innerHTML = "";
        if (s.power && s.power.soc != null) {
          var soc = s.power.soc;
          box.appendChild(pill("Battery " + soc + "%", soc < C.power.shutdown ? "bad" : soc < C.power.eco ? "warn" : "good"));
        } else if (s.power && s.power.volts != null) {
          box.appendChild(pill("Battery " + s.power.volts.toFixed(2) + " V"));
        }
        if (s.eco) box.appendChild(pill("Power saving: AI & video paused", "warn"));
        if (s.library_temp) box.appendChild(pill("Library on internal disk (temporary)", "warn"));
        else box.appendChild(pill(s.library ? "Full library online" : "Full library drive missing - essentials only", s.library ? "good" : "bad"));
        if (s.clients != null) box.appendChild(pill(s.clients + " on WiFi"));
        if (s.last_backup) box.appendChild(pill("Last backup " + s.last_backup, s.backup_stale ? "warn" : ""));
        box.appendChild(pill("Up " + s.uptime));
      })
      .catch(function () {});
  }

  loadDocs();
  loadStatus();
  setInterval(loadStatus, 60000);
})();
