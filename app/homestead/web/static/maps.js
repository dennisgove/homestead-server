// Offline map: three map files, each used at the zoom levels it covers well.
(() => {
  const { layers, info } = window.MAPS;
  const proto = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", proto.tile);
  const files = location.origin + "/files/maps/";
  // world: zoomed out; wide (US + southern Canada) from zoom 5 on (enlarged past its own detail
  // where there's nothing better); detailed (home region) from zoom 9, where it replaces the wide map.
  const bands = { world: [0, 5], wide: [5, 24], detailed: [9, 24] };
  const sources = {}, style = [];
  const flavor = basemaps.namedFlavor("light");
  for (const name of ["world", "wide", "detailed"]) {
    if (!layers[name]) continue;
    sources[name] = { type: "vector", url: `pmtiles://${files}${name}.pmtiles`,
                      attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a>' };
    const [lo, hi] = bands[name];
    for (const l of basemaps.layers(name, flavor, { lang: "en" })) {
      l.id = `${name}-${l.id}`;
      l.minzoom = Math.max(l.minzoom || 0, lo);
      l.maxzoom = Math.min(l.maxzoom || 24, hi);
      style.push(l);
    }
  }
  const home = info && info.detailed_bbox;
  const map = new maplibregl.Map({
    container: "map", hash: true, maxZoom: 18, preserveDrawingBuffer: true,
    center: home ? [(home[0] + home[2]) / 2, (home[1] + home[3]) / 2] : [-96, 39], zoom: home ? 7 : 3,
    style: { version: 8, glyphs: files + "assets/fonts/{fontstack}/{range}.pbf",
             sprite: files + "assets/sprites/light", sources, layers: style },
  });
  // Over the home region, close up, show only the detailed map (no doubled roads and labels).
  const wideIds = style.filter(l => l.id.startsWith("wide-")).map(l => l.id);
  const inHome = () => home && layers.detailed && map.getZoom() >= 9 &&
    (([x, y]) => x >= home[0] && x <= home[2] && y >= home[1] && y <= home[3])(map.getCenter().toArray());
  let wideShown = true;
  const pick = () => {
    const show = !inHome();
    if (show === wideShown) return;
    wideShown = show;
    for (const id of wideIds) map.setLayoutProperty(id, "visibility", show ? "visible" : "none");
  };
  map.on("load", pick);
  map.on("moveend", pick);
  map.addControl(new maplibregl.NavigationControl(), "bottom-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");

  const input = document.getElementById("place"), found = document.getElementById("found");
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = input.value.trim();
      found.innerHTML = "";
      if (q.length < 2) return;
      const r = await fetch("/api/places?q=" + encodeURIComponent(q));
      for (const p of await r.json()) {
        const li = document.createElement("li"), b = document.createElement("button");
        b.type = "button";
        b.textContent = `${p.name} · ${p.kind}${p.admin ? ", " + p.admin : ""}`;
        b.onclick = () => {
          map.flyTo({ center: [p.lon, p.lat], zoom: /town|city|capital/.test(p.kind) ? 13 : 15 });
          new maplibregl.Marker().setLngLat([p.lon, p.lat]).addTo(map);
          found.innerHTML = "";
        };
        li.appendChild(b); found.appendChild(li);
      }
    }, 200);
  });
  document.getElementById("where").addEventListener("submit", ev => { ev.preventDefault(); const b = found.querySelector("button"); if (b) b.click(); });
})();
