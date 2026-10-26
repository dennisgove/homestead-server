// Homestead offline map: three Protomaps layers (world → wide → detailed) by zoom,
// fonts and icons served from this machine, and place search through the Hub.
(function () {
  "use strict";
  const M = window.HOMESTEAD_MAPS;
  const data = location.origin + "/maps/data/";
  const proto = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", proto.tile);
  const flavor = basemaps.namedFlavor("light");

  // Which layer shows at which zoom (each only where its file exists).
  const have = M.layers;
  const bands = [];
  if (have.world) bands.push(["world", 0, have.wide || have.detailed ? 6 : 24]);
  if (have.wide) bands.push(["wide", have.world ? 6 : 0, have.detailed ? 10 : 24]);
  if (have.detailed) bands.push(["detailed", have.wide || have.world ? 10 : 0, 24]);

  const sources = {};
  let layers = [];
  bands.forEach(([name, minz, maxz], i) => {
    sources[name] = { type: "vector", url: `pmtiles://${data}${name}.pmtiles`,
                      attribution: "© OpenStreetMap contributors, Protomaps" };
    basemaps.layers(name, flavor, { lang: "en" }).forEach(l => {
      if (l.type === "background" && i > 0) return; // one background is enough
      layers.push(Object.assign({}, l, {
        id: `${name}-${l.id}`,
        minzoom: Math.max(l.minzoom || 0, minz),
        maxzoom: Math.min(l.maxzoom === undefined ? 24 : l.maxzoom, maxz),
      }));
    });
  });

  const b = M.info && M.info.detailed_bbox;
  const map = new maplibregl.Map({
    container: "map",
    style: { version: 8, glyphs: data + "assets/fonts/{fontstack}/{range}.pbf",
             sprite: location.origin + "/maps/data/assets/sprites/light", sources, layers },
    center: b ? [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] : [-96, 39],
    zoom: b ? 7 : 3, maxZoom: 18, hash: true, preserveDrawingBuffer: true,
  });
  map.addControl(new maplibregl.NavigationControl());
  map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }));

  const hits = document.getElementById("hits");
  let timer;
  document.getElementById("place").addEventListener("input", e => {
    clearTimeout(timer);
    const q = e.target.value.trim();
    timer = setTimeout(async () => {
      hits.innerHTML = "";
      if (q.length < 2) return;
      const r = await fetch("/api/places?q=" + encodeURIComponent(q));
      (await r.json()).forEach(p => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.textContent = `${p.name} · ${p.admin}`;
        btn.onclick = () => { map.flyTo({ center: [p.lon, p.lat], zoom: /^PPL/.test(p.kind) ? 13 : 15 });
                              hits.innerHTML = ""; new maplibregl.Marker().setLngLat([p.lon, p.lat]).addTo(map); };
        li.appendChild(btn);
        hits.appendChild(li);
      });
    }, 250);
  });
  document.getElementById("find").addEventListener("submit", e => {
    e.preventDefault();
    const first = hits.querySelector("button");
    if (first) first.click();
  });
})();
