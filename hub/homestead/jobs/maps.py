"""Build the offline maps (homestead-maps.service). Needs internet; rerun quarterly.

Three Protomaps layers cut straight from the newest planet build (no planet download):
  detailed  home state + neighboring states, full detail (zoom 15)
  wide      contiguous US + southern Canada, towns and highways (zoom 10)
  world     everything, countries and major cities (zoom 6)
plus the map fonts and icons, and a place-name index (GeoNames) for offline search.
Output: paths.maps/{detailed,wide,world}.pmtiles, assets/, places.sqlite, maps.json
"""
import argparse
import csv
import io
import json
import os
import platform
import sqlite3
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from .. import config
from .common import Job, human

UA = {"User-Agent": "homestead-maps/1.0 (offline preparedness library)"}
BUILDS = "https://build-metadata.protomaps.dev/builds.json"
BUILD_URL = "https://build.protomaps.com/{key}"
PMTILES_RELEASE = "https://api.github.com/repos/protomaps/go-pmtiles/releases/latest"
STATES_GEOJSON = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"
ASSETS = "https://protomaps.github.io/basemaps-assets"
FONTS = ["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"]
GEONAMES = "https://download.geonames.org/export/dump/{}.zip"

WIDE_BBOX = (-125.0, 24.0, -52.0, 55.0)  # contiguous US + southern Canada
LAYERS = {"detailed": 15, "wide": 10, "world": 6}

# Lower 48 + DC: who borders whom (the detailed area is the home state plus these).
NEIGHBORS = {
    "Alabama": ["Florida", "Georgia", "Mississippi", "Tennessee"],
    "Arizona": ["California", "Colorado", "Nevada", "New Mexico", "Utah"],
    "Arkansas": ["Louisiana", "Mississippi", "Missouri", "Oklahoma", "Tennessee", "Texas"],
    "California": ["Arizona", "Nevada", "Oregon"],
    "Colorado": ["Arizona", "Kansas", "Nebraska", "New Mexico", "Oklahoma", "Utah", "Wyoming"],
    "Connecticut": ["Massachusetts", "New York", "Rhode Island"],
    "Delaware": ["Maryland", "New Jersey", "Pennsylvania"],
    "District of Columbia": ["Maryland", "Virginia"],
    "Florida": ["Alabama", "Georgia"],
    "Georgia": ["Alabama", "Florida", "North Carolina", "South Carolina", "Tennessee"],
    "Idaho": ["Montana", "Nevada", "Oregon", "Utah", "Washington", "Wyoming"],
    "Illinois": ["Indiana", "Iowa", "Kentucky", "Missouri", "Wisconsin"],
    "Indiana": ["Illinois", "Kentucky", "Michigan", "Ohio"],
    "Iowa": ["Illinois", "Minnesota", "Missouri", "Nebraska", "South Dakota", "Wisconsin"],
    "Kansas": ["Colorado", "Missouri", "Nebraska", "Oklahoma"],
    "Kentucky": ["Illinois", "Indiana", "Missouri", "Ohio", "Tennessee", "Virginia", "West Virginia"],
    "Louisiana": ["Arkansas", "Mississippi", "Texas"],
    "Maine": ["New Hampshire"],
    "Maryland": ["Delaware", "District of Columbia", "Pennsylvania", "Virginia", "West Virginia"],
    "Massachusetts": ["Connecticut", "New Hampshire", "New York", "Rhode Island", "Vermont"],
    "Michigan": ["Indiana", "Ohio", "Wisconsin"],
    "Minnesota": ["Iowa", "North Dakota", "South Dakota", "Wisconsin"],
    "Mississippi": ["Alabama", "Arkansas", "Louisiana", "Tennessee"],
    "Missouri": ["Arkansas", "Illinois", "Iowa", "Kansas", "Kentucky", "Nebraska", "Oklahoma", "Tennessee"],
    "Montana": ["Idaho", "North Dakota", "South Dakota", "Wyoming"],
    "Nebraska": ["Colorado", "Iowa", "Kansas", "Missouri", "South Dakota", "Wyoming"],
    "Nevada": ["Arizona", "California", "Idaho", "Oregon", "Utah"],
    "New Hampshire": ["Maine", "Massachusetts", "Vermont"],
    "New Jersey": ["Delaware", "New York", "Pennsylvania"],
    "New Mexico": ["Arizona", "Colorado", "Oklahoma", "Texas", "Utah"],
    "New York": ["Connecticut", "Massachusetts", "New Jersey", "Pennsylvania", "Vermont"],
    "North Carolina": ["Georgia", "South Carolina", "Tennessee", "Virginia"],
    "North Dakota": ["Minnesota", "Montana", "South Dakota"],
    "Ohio": ["Indiana", "Kentucky", "Michigan", "Pennsylvania", "West Virginia"],
    "Oklahoma": ["Arkansas", "Colorado", "Kansas", "Missouri", "New Mexico", "Texas"],
    "Oregon": ["California", "Idaho", "Nevada", "Washington"],
    "Pennsylvania": ["Delaware", "Maryland", "New Jersey", "New York", "Ohio", "West Virginia"],
    "Rhode Island": ["Connecticut", "Massachusetts"],
    "South Carolina": ["Georgia", "North Carolina"],
    "South Dakota": ["Iowa", "Minnesota", "Montana", "Nebraska", "North Dakota", "Wyoming"],
    "Tennessee": ["Alabama", "Arkansas", "Georgia", "Kentucky", "Mississippi", "Missouri", "North Carolina", "Virginia"],
    "Texas": ["Arkansas", "Louisiana", "New Mexico", "Oklahoma"],
    "Utah": ["Arizona", "Colorado", "Idaho", "Nevada", "New Mexico", "Wyoming"],
    "Vermont": ["Massachusetts", "New Hampshire", "New York"],
    "Virginia": ["District of Columbia", "Kentucky", "Maryland", "North Carolina", "Tennessee", "West Virginia"],
    "Washington": ["Idaho", "Oregon"],
    "West Virginia": ["Kentucky", "Maryland", "Ohio", "Pennsylvania", "Virginia"],
    "Wisconsin": ["Illinois", "Iowa", "Michigan", "Minnesota"],
    "Wyoming": ["Colorado", "Idaho", "Montana", "Nebraska", "South Dakota", "Utah"],
    "Alaska": [], "Hawaii": [],
}


def get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _coords(geom):
    def walk(c):
        if isinstance(c[0], (int, float)):
            yield c
        else:
            for x in c:
                yield from walk(x)
    return walk(geom["coordinates"])


def state_bboxes() -> dict[str, tuple]:
    gj = json.loads(get(STATES_GEOJSON))
    out = {}
    for f in gj["features"]:
        xs, ys = zip(*((p[0], p[1]) for p in _coords(f["geometry"])))
        out[f["properties"]["name"]] = (min(xs), min(ys), max(xs), max(ys))
    return out


def detailed_area(home: str, boxes: dict) -> tuple[list[str], tuple]:
    if home not in NEIGHBORS:
        raise SystemExit(f"region_state {home!r} isn't a US state name")
    states = [home] + NEIGHBORS[home]
    bs = [boxes[s] for s in states]
    pad = 0.05
    return states, (min(b[0] for b in bs) - pad, min(b[1] for b in bs) - pad,
                    max(b[2] for b in bs) + pad, max(b[3] for b in bs) + pad)


def pmtiles_bin(job: Job) -> str:
    dest = config.path("state") / "bin" / "pmtiles"
    if dest.exists():
        return str(dest)
    rel = json.loads(get(PMTILES_RELEASE))
    arch = "x86_64" if platform.machine() in ("x86_64", "AMD64") else "arm64"
    asset = next(a for a in rel["assets"] if a["name"].endswith(f"_Linux_{arch}.tar.gz"))
    job.log(f"getting pmtiles {rel['tag_name']}")
    with tarfile.open(fileobj=io.BytesIO(get(asset["browser_download_url"]))) as t:
        member = next(m for m in t.getmembers() if m.name.endswith("pmtiles"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(t.extractfile(member).read())
    dest.chmod(0o755)
    return str(dest)


def extract(job: Job, binpath: str, src: str, out: Path, bbox: tuple | None, maxzoom: int):
    tmp = out.with_suffix(".pmtiles.part")
    cmd = [binpath, "extract", src, str(tmp), f"--maxzoom={maxzoom}", "--download-threads=4"]
    if bbox:
        cmd.append("--bbox=" + ",".join(f"{v:.4f}" for v in bbox))
    job.log(f"extracting {out.name} (zoom ≤ {maxzoom})")
    subprocess.run(cmd, check=True)
    os.replace(tmp, out)


def fetch_assets(job: Job, dest: Path):
    """Fonts and icons for the map style, so nothing loads from the internet."""
    sprites = dest / "sprites"
    sprites.mkdir(parents=True, exist_ok=True)
    for f in ("light.json", "light.png", "light@2x.json", "light@2x.png"):
        if not (sprites / f).exists():
            (sprites / f).write_bytes(get(f"{ASSETS}/sprites/v4/{f}"))
    for font in FONTS:
        d = dest / "fonts" / font
        d.mkdir(parents=True, exist_ok=True)
        job.log(f"fonts: {font}")
        for start in range(0, 65536, 256):
            name = f"{start}-{start + 255}.pbf"
            if (d / name).exists():
                continue
            try:
                (d / name).write_bytes(get(f"{ASSETS}/fonts/{urllib.request.quote(font)}/{name}", timeout=60))
            except OSError:
                pass  # a missing range only affects that script's labels


def build_places(job: Job, out: Path, detailed_bbox: tuple):
    """Place-name search index from GeoNames: towns, hospitals, schools, parks, water, peaks."""
    keep = {"P", "S", "L", "H", "T", "A"}  # populated places, spots, parks, water, terrain, admin
    tmp = out.with_suffix(".part")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.execute("CREATE VIRTUAL TABLE places USING fts5(name, kind, admin, lat UNINDEXED, lon UNINDEXED, score UNINDEXED)")
    x0, y0, x1, y1 = detailed_bbox
    for code in ("US", "CA", "cities15000"):
        job.log(f"place names: {code}")
        with zipfile.ZipFile(io.BytesIO(get(GEONAMES.format(code), timeout=600))) as z:
            with z.open(f"{code}.txt") as f:
                rows = []
                for r in csv.reader(io.TextIOWrapper(f, "utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
                    if len(r) < 15 or r[6] not in keep:
                        continue
                    lat, lon, pop = float(r[4]), float(r[5]), int(r[14] or 0)
                    inside = x0 <= lon <= x1 and y0 <= lat <= y1
                    if code != "cities15000" and not inside and r[6] != "P":
                        continue  # outside the home area, keep only towns
                    # higher rank sorts first: home area, then population
                    rank = (1_000_000_000 if inside else 0) + pop
                    rows.append((r[1], r[7], f"{r[10]}, {r[8]}", lat, lon, rank))
                db.executemany("INSERT INTO places VALUES (?,?,?,?,?,?)", rows)
    db.commit()
    db.close()
    os.replace(tmp, out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(LAYERS) + ["assets", "places"], nargs="*")
    args = ap.parse_args(argv)
    cfg = config.load()
    dest = config.path("maps")
    dest.mkdir(parents=True, exist_ok=True)
    want = set(args.only or list(LAYERS) + ["assets", "places"])
    with Job("maps") as job:
        builds = json.loads(get(BUILDS))
        build = builds[-1]["key"]
        src = BUILD_URL.format(key=build)
        states, bbox = detailed_area(cfg["site"]["region_state"], state_bboxes())
        job.status["total"] = len(want)
        info = {"build": build, "home": cfg["site"]["region_state"], "states": states,
                "detailed_bbox": bbox, "wide_bbox": WIDE_BBOX, "maxzoom": LAYERS}
        binpath = pmtiles_bin(job) if want & set(LAYERS) else ""
        for layer, z in LAYERS.items():
            if layer in want:
                extract(job, binpath, src, dest / f"{layer}.pmtiles",
                        bbox if layer == "detailed" else WIDE_BBOX if layer == "wide" else None, z)
                job.item(layer, state="done", size=(dest / f"{layer}.pmtiles").stat().st_size, build=build)
                job.status["done"] += 1
        if "assets" in want:
            fetch_assets(job, dest / "assets")
            job.item("assets", state="done")
            job.status["done"] += 1
        if "places" in want:
            build_places(job, dest / "places.sqlite", bbox)
            job.item("places", state="done", size=(dest / "places.sqlite").stat().st_size)
            job.status["done"] += 1
        (dest / "maps.json").write_text(json.dumps(info, indent=1))
        sizes = {p.name: human(p.stat().st_size) for p in dest.glob("*.pmtiles")}
        job.log(f"done: {', '.join(f'{k} {v}' for k, v in sizes.items())}")


if __name__ == "__main__":
    main()
