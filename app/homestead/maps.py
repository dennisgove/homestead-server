"""Offline maps: three map files at different detail, place-name search, and the builder.

    detailed.pmtiles   home state and its neighbours, every street and trail (zoom 15)
    wide.pmtiles       the contiguous US and southern Canada, towns and highways (zoom 10)
    world.pmtiles      countries and big cities (zoom 6)
    places.sqlite      place names from GeoNames, for the search box
    assets/            the map's fonts and icons

Building needs the internet: map data from Protomaps' daily planet build (only the
areas above are downloaded, not the whole planet), names from GeoNames.
"""
import io
import json
import math
import re
import shutil
import sqlite3
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from . import settings

UA = {"User-Agent": "homestead/1.0 (offline library)"}
PMTILES_CLI = "https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/go-pmtiles_1.31.2_Linux_x86_64.tar.gz"
BUILDS = "https://build-metadata.protomaps.dev/builds.json"
PLANET = "https://build.protomaps.com/{}"
ASSETS = "https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.zip"
STATES = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"
GEONAMES = ["https://download.geonames.org/export/dump/US.zip", "https://download.geonames.org/export/dump/CA.zip",
            "https://download.geonames.org/export/dump/cities15000.zip"]
WIDE = (-125.0, 24.0, -52.0, 55.0)            # contiguous US + southern Canada
ZOOM = {"detailed": 15, "wide": 10, "world": 6}
KEEP_CODES = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLC", "PPLX", "HSP", "SCH", "CH", "PRK", "MT", "LK", "STM", "AIRP",
              "BDG", "DAM", "FRST", "ISL", "RES", "MALL", "PO", "FT", "SPR", "BAY", "BCH"}
KIND = {"PPL": "town", "PPLA": "city", "PPLA2": "town", "PPLA3": "town", "PPLC": "capital", "PPLX": "neighborhood",
        "HSP": "hospital", "SCH": "school", "CH": "church", "PRK": "park", "MT": "mountain", "LK": "lake",
        "STM": "river or stream", "AIRP": "airport", "BDG": "bridge", "DAM": "dam", "FRST": "forest",
        "ISL": "island", "RES": "reservation", "MALL": "shopping", "PO": "post office", "FT": "fort",
        "SPR": "spring", "BAY": "bay", "BCH": "beach"}

# Neighbours of each state (shared border), for the detailed map.
NEIGHBORS = {
    "Alabama": ["Florida", "Georgia", "Mississippi", "Tennessee"], "Arizona": ["California", "Colorado", "Nevada", "New Mexico", "Utah"],
    "Arkansas": ["Louisiana", "Mississippi", "Missouri", "Oklahoma", "Tennessee", "Texas"],
    "California": ["Arizona", "Nevada", "Oregon"], "Colorado": ["Arizona", "Kansas", "Nebraska", "New Mexico", "Oklahoma", "Utah", "Wyoming"],
    "Connecticut": ["Massachusetts", "New York", "Rhode Island"], "Delaware": ["Maryland", "New Jersey", "Pennsylvania"],
    "Florida": ["Alabama", "Georgia"], "Georgia": ["Alabama", "Florida", "North Carolina", "South Carolina", "Tennessee"],
    "Idaho": ["Montana", "Nevada", "Oregon", "Utah", "Washington", "Wyoming"],
    "Illinois": ["Indiana", "Iowa", "Kentucky", "Missouri", "Wisconsin"], "Indiana": ["Illinois", "Kentucky", "Michigan", "Ohio"],
    "Iowa": ["Illinois", "Minnesota", "Missouri", "Nebraska", "South Dakota", "Wisconsin"],
    "Kansas": ["Colorado", "Missouri", "Nebraska", "Oklahoma"],
    "Kentucky": ["Illinois", "Indiana", "Missouri", "Ohio", "Tennessee", "Virginia", "West Virginia"],
    "Louisiana": ["Arkansas", "Mississippi", "Texas"], "Maine": ["New Hampshire"],
    "Maryland": ["Delaware", "Pennsylvania", "Virginia", "West Virginia", "District of Columbia"],
    "Massachusetts": ["Connecticut", "New Hampshire", "New York", "Rhode Island", "Vermont"],
    "Michigan": ["Indiana", "Ohio", "Wisconsin"], "Minnesota": ["Iowa", "North Dakota", "South Dakota", "Wisconsin"],
    "Mississippi": ["Alabama", "Arkansas", "Louisiana", "Tennessee"],
    "Missouri": ["Arkansas", "Illinois", "Iowa", "Kansas", "Kentucky", "Nebraska", "Oklahoma", "Tennessee"],
    "Montana": ["Idaho", "North Dakota", "South Dakota", "Wyoming"],
    "Nebraska": ["Colorado", "Iowa", "Kansas", "Missouri", "South Dakota", "Wyoming"],
    "Nevada": ["Arizona", "California", "Idaho", "Oregon", "Utah"], "New Hampshire": ["Maine", "Massachusetts", "Vermont"],
    "New Jersey": ["Delaware", "New York", "Pennsylvania"], "New Mexico": ["Arizona", "Colorado", "Oklahoma", "Texas", "Utah"],
    "New York": ["Connecticut", "Massachusetts", "New Jersey", "Pennsylvania", "Vermont"],
    "North Carolina": ["Georgia", "South Carolina", "Tennessee", "Virginia"],
    "North Dakota": ["Minnesota", "Montana", "South Dakota"], "Ohio": ["Indiana", "Kentucky", "Michigan", "Pennsylvania", "West Virginia"],
    "Oklahoma": ["Arkansas", "Colorado", "Kansas", "Missouri", "New Mexico", "Texas"], "Oregon": ["California", "Idaho", "Nevada", "Washington"],
    "Pennsylvania": ["Delaware", "Maryland", "New Jersey", "New York", "Ohio", "West Virginia"],
    "Rhode Island": ["Connecticut", "Massachusetts"], "South Carolina": ["Georgia", "North Carolina"],
    "South Dakota": ["Iowa", "Minnesota", "Montana", "Nebraska", "North Dakota", "Wyoming"],
    "Tennessee": ["Alabama", "Arkansas", "Georgia", "Kentucky", "Mississippi", "Missouri", "North Carolina", "Virginia"],
    "Texas": ["Arkansas", "Louisiana", "New Mexico", "Oklahoma"], "Utah": ["Arizona", "Colorado", "Idaho", "Nevada", "New Mexico", "Wyoming"],
    "Vermont": ["Massachusetts", "New Hampshire", "New York"],
    "Virginia": ["Kentucky", "Maryland", "North Carolina", "Tennessee", "West Virginia", "District of Columbia"],
    "Washington": ["Idaho", "Oregon"], "West Virginia": ["Kentucky", "Maryland", "Ohio", "Pennsylvania", "Virginia"],
    "Wisconsin": ["Illinois", "Iowa", "Michigan", "Minnesota"], "Wyoming": ["Colorado", "Idaho", "Montana", "Nebraska", "South Dakota", "Utah"],
    "Alaska": [], "Hawaii": [],
}


def info() -> dict | None:
    try:
        return json.loads((settings.path("maps") / "maps.json").read_text())
    except (OSError, ValueError):
        return None


def layers() -> dict[str, bool]:
    return {n: (settings.path("maps") / f"{n}.pmtiles").is_file() for n in ZOOM}


def places(q: str, limit: int = 10) -> list[dict]:
    """Place names for the search box: whole-name matches first, then bigger places."""
    db = settings.path("maps") / "places.sqlite"
    terms = " ".join(f'"{w}"*' for w in re.findall(r"\w+", q))
    if not db.exists() or not terms:
        return []
    con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    try:
        rows = con.execute("SELECT name, kind, admin, lat, lon, score FROM places WHERE places MATCH ? LIMIT 400",
                           (terms,)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    ql = q.strip().lower()

    def rank(r):
        name, kind, _, _, _, score = r
        town = (kind or "").startswith("PPL") or kind in ("town", "city", "capital")
        return (name.lower() != ql, not town, -float(score or 0))
    rows.sort(key=rank)
    return [{"name": r[0], "kind": KIND.get(r[1], r[1] or "place"), "admin": r[2], "lat": r[3], "lon": r[4]}
            for r in rows[:limit]]


# --- building ------------------------------------------------------------------------------

def _get(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def pmtiles_cli(work: Path) -> Path:
    exe = work / "pmtiles"
    if not exe.exists():
        with tarfile.open(fileobj=io.BytesIO(_get(PMTILES_CLI)), mode="r:gz") as t:
            member = next(m for m in t.getmembers() if m.name.endswith("pmtiles"))
            exe.write_bytes(t.extractfile(member).read())
        exe.chmod(0o755)
    return exe


def state_boxes() -> dict[str, tuple[float, float, float, float]]:
    gj = json.loads(_get(STATES))
    boxes = {}
    for f in gj["features"]:
        pts = []
        def walk(c):
            if c and isinstance(c[0], (int, float)):
                pts.append(c)
            else:
                for x in c:
                    walk(x)
        walk(f["geometry"]["coordinates"])
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        boxes[f["properties"]["name"]] = (min(xs), min(ys), max(xs), max(ys))
    return boxes


def build(region: str, log=print):
    out = settings.path("maps")
    work = out / ".build"
    work.mkdir(parents=True, exist_ok=True)
    exe = pmtiles_cli(work)
    builds = json.loads(_get(BUILDS))
    latest = sorted(b["key"] for b in builds if b["key"].endswith(".pmtiles"))[-1]
    planet = PLANET.format(latest)
    boxes = state_boxes()
    states = [region] + NEIGHBORS.get(region, [])
    bb = [boxes[s] for s in states if s in boxes]
    detailed = (min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb))
    areas = {"detailed": detailed, "wide": WIDE, "world": (-180, -85, 180, 85)}
    for name, box in areas.items():
        log(f"map {name}: {box}, zoom {ZOOM[name]}")
        tmp = work / f"{name}.pmtiles"
        tmp.unlink(missing_ok=True)
        subprocess.run([str(exe), "extract", planet, str(tmp), "--bbox=" + ",".join(f"{v:.5f}" for v in box),
                        f"--maxzoom={ZOOM[name]}", "--download-threads=4"], check=True)
        shutil.move(tmp, out / f"{name}.pmtiles")
    log("map fonts and icons")
    with zipfile.ZipFile(io.BytesIO(_get(ASSETS, 600))) as z:
        for m in z.namelist():
            parts = m.split("/", 1)
            if len(parts) < 2 or not parts[1] or m.endswith("/"):
                continue
            rel = parts[1]
            if rel.startswith("fonts/Noto Sans ") or rel.startswith("sprites/v4/light"):
                dest = out / "assets" / rel.replace("sprites/v4/", "sprites/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(m))
    log("place names")
    build_places(out / "places.sqlite", detailed, log)
    (out / "maps.json").write_text(json.dumps({"build": latest, "home": region, "states": states,
                                               "detailed_bbox": detailed, "wide_bbox": WIDE, "maxzoom": ZOOM}, indent=1))
    shutil.rmtree(work, ignore_errors=True)


def build_places(dest: Path, detailed: tuple, log=print):
    tmp = dest.with_suffix(".new")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute("CREATE VIRTUAL TABLE places USING fts5(name, kind, admin, lat UNINDEXED, lon UNINDEXED, score UNINDEXED)")
    seen = set()
    for url in GEONAMES:
        with zipfile.ZipFile(io.BytesIO(_get(url, 900))) as z:
            name = next(n for n in z.namelist() if n.endswith(".txt") and not n.startswith("readme"))
            rows = []
            for line in io.TextIOWrapper(z.open(name), encoding="utf-8"):
                f = line.rstrip("\n").split("\t")
                if len(f) < 15 or f[0] in seen:
                    continue
                code, lat, lon = f[7], float(f[4]), float(f[5])
                world = "cities15000" in url
                inside = detailed[0] <= lon <= detailed[2] and detailed[1] <= lat <= detailed[3]
                town = code.startswith("PPL")
                if not world and not (town or (inside and code in KEEP_CODES)):
                    continue
                pop = int(f[14] or 0)
                score = math.log10(pop + 1) * 10 + (5 if town else 0) + (3 if inside else 0)
                admin = ", ".join(x for x in (f[10], f[8]) if x)
                rows.append((f[1], code, admin, lat, lon, round(score, 2)))
                seen.add(f[0])
            con.executemany("INSERT INTO places VALUES (?, ?, ?, ?, ?, ?)", rows)
            log(f"  {url.rsplit('/', 1)[1]}: {len(rows)} places")
    con.commit()
    con.execute("INSERT INTO places(places) VALUES ('optimize')")
    con.commit()
    con.close()
    tmp.replace(dest)
