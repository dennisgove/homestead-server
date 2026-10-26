# Rethink: is there a better way to build this?

Status: **decided** (option C, see [Decisions](#decisions)). Plan only, on branch `plan/rethink-stack`; nothing here is built yet. This is the base that later apps and pages build on, so it's designed to be extended (see [Extending it](#extending-it)).

## What we're actually trying to do

1. **Collect** the most useful offline knowledge (medical, water, food, defense, sustainability, repair, education) while the internet still works, and keep it current until it doesn't.
2. **Collate** it so a stressed, untrained person finds the right page fast: by topic, by search, on paper, and by asking the AI.
3. **Answer questions** with a local AI that's grounded in that library and responds in seconds on this hardware.
4. **Survive**: run on solar, rebuild from a backup drive with no internet, and keep working when parts (the USB library drive, the AI) are missing.
5. **Be boring to run**: one command to build, no clicking, nothing that silently drifts.

## What hurt with the current approach

Most of the problems in this build came from NOMAD, or from running two systems side by side and keeping them from fighting:

| Problem we hit | Cause |
|---|---|
| Installer has to be run by hand; playbook pauses for it | NOMAD's interactive `install_nomad.sh` |
| Its app links all broken (8000-range ports) | NOMAD links apps by backend port; needed a link-fixer timer |
| Two libraries with duplicate ZIMs (essentials vs NOMAD), two copies of Wikipedia (240 GB) | NOMAD manages its own download folder and catalog; ours is separate |
| CPU pinned for hours indexing all of Wikipedia | NOMAD's ingest policy defaulted to "Always"; embedding every ZIM can't finish on this hardware |
| AI chat never answered | NOMAD's chat unloads other models; two chat apps fought over one Ollama |
| NOMAD state hidden in MySQL, Redis, Qdrant | Hard to back up meaningfully, hard to reason about, hard to rebuild declaratively |
| NOMAD's AI tile hidden by redirecting it | No way to switch off parts of NOMAD we don't use |

And two problems that aren't NOMAD's fault, but that a redesign should solve properly:

- **Open WebUI keeps settings in its database**, and its defaults (26 built-in tools, follow-ups, tags) assume a GPU. We now patch these with `homestead-webui-setup`. That works, but it's a patch.
- **Making the AI use the ZIM libraries.** Embedding ZIMs doesn't scale. Full Wikipedia alone is about 19 million articles, which means months of CPU and an index too big for 32 GB.

What NOMAD gives us that we'd have to replace: its web UI (content manager, downloads, the Supply Depot for one-click apps), the maps viewer and map downloads, curated collections, and upstream updates.

## Options

### A. Keep NOMAD, tidy up (status quo)

Keep going as we are: link fixer, AI tile redirected, ingest set to Manual, duplicates cleaned up.

- **For:** works now, no migration, upstream keeps improving NOMAD.
- **Against:** every NOMAD update can change ports, defaults, or behaviour we've patched around (link timer, ingest policy, AI unloads). Two content systems stay. The playbook still pauses for an interactive install. Backups include MySQL and Redis state that we don't control.

### B. Internet-in-a-Box (IIAB)

A long-running open-source project that turns Ubuntu or a Raspberry Pi into an offline "learning hotspot": Wikipedia and other Kiwix content, Kolibri, OpenStreetMap maps, Calibre-Web and about 40 other apps, with a one-line installer and continuous releases ([internet-in-a-box.org](https://internet-in-a-box.org/), [github.com/iiab/iiab](https://awesome.ecosyste.ms/projects/github.com%2Fiiab%2Fiiab)).

- **For:** mature and field-tested in schools and clinics, a broad app catalog, a real offline maps setup, and actively maintained (pushed June 2026).
- **Against:** it's built for classrooms, not grid-down households. It has no local AI. It brings its own conventions (nginx layout, its own admin console, its own content tooling), and our vault, power watchdog, radio, kiosk, hotspot modes and backups would have to be fitted around it. That's the same integration problem we have with NOMAD, with a bigger system.

### C. Our own thin stack, no platform (chosen)

Drop NOMAD and run each component directly from our compose file and Ansible, driven by one content catalog. We already run half of this: Open WebUI, Ollama, the essentials Kiwix, Grocy, Mealie, Paperless, OpenWebRX+, Caddy and the portal are ours, not NOMAD's.

- **For:** one library, one catalog, one AI. No interactive install, no link fixing, no hidden databases. Everything is declared in the repo and rebuilt identically from a backup. Fewer moving parts to break on solar power.
- **Against:** we own the content tooling (we mostly do already, with `fetch_content.py`), and we lose NOMAD's point-and-click content manager and its upstream improvements. A maps viewer has to be added.

### D. A commercial appliance

Several offline "survival computers" sell for roughly $200–700. Search results didn't name them reliably, so I can't compare them here. They're typically a Raspberry Pi with Kiwix and a fixed content set: simpler, but smaller, not extensible, and with no AI to speak of. Not a fit for the scope here.

## Decisions

1. **Option C:** our own stack, no NOMAD.
2. **Content is managed from a web page**, not by editing YAML.
3. **Maps:** detailed for the home state and its neighbors; less detailed for a wider area.
4. **This is the base.** More apps and pages come later, so adding one must be cheap and must not mean touching ten files.

## Design

```
                     ┌─ Caddy (ports 80, 7000-7099) ──────────────────────────────────┐
phones / kiosk ────▶ │ Hub (portal + Library manager + health + future pages)         │
                     │ library  books  learn  videos  maps  AI  radio  pantry  ...    │
                     └────────────────────────────────────────────────────────────────┘
                                         │
             ┌────────── Hub (homestead-hub: small Python web app) ──────────┐
             │ pages: portal, library manager, health, settings; JSON API   │
             │ catalog = repo baseline + local edits (/var/lib/homestead)   │
             └───────┬──────────────────────────────┬───────────────────────┘
                     │ starts jobs (systemd)        │ reads/writes
     homestead-fetch │ homestead-kb-sync │ homestead-books │ homestead-maps
                     ▼
   /srv/core (NVMe, essentials)        /srv/library (USB, everything else)
      zim/  docs/  maps/                  zim/  books/  maps/  video/  kolibri/
                     │
   kiwix library.xml (one library, both disks) · Calibre library · map tiles
   Open WebUI + Ollama (server; Mac mini first when it's on)
      └─ library-search filter: Kiwix full-text search at question time
```

### 1. The Hub: one small web app for our own pages

Today the portal is static HTML, and everything else of ours is scripts. Replace it with **`homestead-hub`**, a small Python web app (FastAPI with server-rendered pages and a sprinkle of htmx: no JavaScript build step, works on old phones, nothing to download from the internet). It serves:
- **the portal** (same look and tiles, now generated from the app registry below);
- **the Library manager** (next section);
- **the library health page** (downloaded, missing, failed, out of date, by-hand checklist);
- **a JSON API** (`/api/catalog`, `/api/apps`, `/api/status`) that future apps and pages use instead of reading files.

It runs as an unprivileged user. It can only start the specific `homestead-*` jobs, through a narrow polkit rule, and never runs anything as root itself. Admin pages sit behind the admin password at Caddy, as now. Future pages are **modules** of the Hub (a folder with routes, templates and a menu entry), so a new page doesn't need a new server, port or login.

Why one app rather than many small ones: one place for the look, navigation, login and the API. And one less thing that can be down on solar power.

### 2. Content managed from a web page: the Library manager

**Where the catalog lives:**
- `content/catalog.yaml` in the repo is the **baseline**: everything recommended (today's manifest, enriched).
- `/var/lib/homestead/catalog.local.yaml` holds **your changes from the web page**: added items, removed items, changed tier or placement. It's backed up by borg, so a rebuild restores your choices.
- The two are merged at run time. An **Export** button turns your local changes into a patch for the repo, so good additions can become baseline.

**What the page does:**
- **Browse and search Kiwix's online catalog** (it publishes an OPDS feed) by language, category and size, and **add** an item in one click, choosing a category, tier and disk (essentials or bulk).
- **Add a PDF or document by URL, or upload a file** (for the by-hand items). The upload goes to the right category folder and is queued for the AI and the books library.
- **Remove** an item: its file is deleted after confirmation, and the space freed is shown.
- Per item: **use in AI** (on or off), **in printed binder** (on or off), **update automatically** (on or off).
- **Space planner:** size of each pending download against free space on each disk, with warnings before anything is queued.
- **Queue and progress:** current download, queue, failures with a retry button, recent checksum results.
- **Updates:** "new release available" per ZIM, from the same catalog feed, with update-all or one at a time.
- **Health:** missing files, duplicates, partial downloads, items in the catalog but not on disk, files on disk but not in the catalog (with an **adopt** button).

**Behind the page:** the existing jobs, reading the merged catalog. Each job writes a small status file that the page reads:
`homestead-fetch` (downloads), `homestead-kb-sync` (AI), `homestead-books` (Calibre import), `homestead-maps` (map extracts), and `homestead-catalog-apply`, which regenerates the Kiwix `library.xml`, the portal topic pages and the binder index.

### 3. Serving

| What | How | Replaces |
|---|---|---|
| All ZIMs | **One `kiwix-serve`** over a single `library.xml` for both disks, plus an **essentials-only** instance that keeps working without the USB drive | NOMAD's Kiwix and our duplicate copies |
| PDFs, EPUBs, purchased books | **Calibre-Web** on a Calibre library that `homestead-books` keeps in sync with `docs/` and `books/` | portal folder listing |
| Maps | see [Maps](#4-maps) | NOMAD maps |
| Courses | **Kolibri** container. Channels are catalog items, imported by a job. | NOMAD Kolibri |
| Video | **Jellyfin** container on `/srv/library/video` | NOMAD Jellyfin |
| Optional tools | CyberChef, IT Tools, Excalidraw, Stirling PDF, Homebox, Vaultwarden as plain containers, switched on in the app registry | Supply Depot |

### 4. Maps

Built from **Protomaps** basemap files (a single PMTiles file per extract, served as a static file with no tile server; see [supabase guide](https://supabase.com/blog/self-host-maps-storage-protomaps), [Bobek](https://www.bobek.cz/til/self-hosting-openstreetmap/), [NPR](https://blog.apps.npr.org/2024/11/26/slippy-maps.html)). The `pmtiles extract` command cuts a region, at a chosen maximum zoom, straight from the published planet build over the internet, with no need to download the whole planet.

| Layer | Area | Detail | Rough size* |
|---|---|---|---|
| **Detailed** | home state plus neighboring states (from `region_state`; for Massachusetts: MA, NH, VT, NY, CT, RI) | full detail (zoom 15: every street, building, trail, POI) | a few GB to ~15 GB |
| **Wide** | contiguous US plus southern Canada | zoom 10 (towns, highways, rivers, county roads) | ~1–3 GB |
| **World** | whole planet | zoom 6 (countries, major cities) | ~100 MB |

\*To be measured when built. Sizes depend on the states.

- **Viewer:** a Hub page with **MapLibre GL**, a Protomaps style, and fonts and icons stored locally, so nothing loads from the internet. It switches automatically from detailed to wide to world as you zoom out or leave the detailed area.
- **Search places offline:** a small place-name index built from the same data (towns, roads, POIs) and served by the Hub API. Typing "Concord" or "hospital" jumps the map there.
- **Printing:** a "print this view" button (the browser prints the current map at page size) for binder maps with routes marked.
- **Phones:** Organic Maps state files on the share, as now.
- **Later, if wanted:** hillshade or topo lines, and USGS topo GeoPDFs for your county as catalog items.
- `homestead-maps` rebuilds the extracts when the catalog's map settings change, and refreshes them from a newer build quarterly while online.

### 5. The AI, grounded in the whole library without indexing it

1. **Curated knowledge bases:** procedure-type PDFs (medical, canning, water, field manuals), embedded once by `homestead-kb-sync`. Which items go in is the **use in AI** switch on the Library manager.
2. **Live library search at question time:** an Open WebUI **filter function**, which runs before the model and sends no tool definitions. The small model turns the question into search terms; Kiwix's full-text search runs across every ZIM; the best two or three article excerpts are added to the prompt with their titles, so the answer cites them. **Nothing has to be indexed**, it covers full Wikipedia and every new ZIM, and it costs one search plus a few hundred tokens per question.
   - MCP servers do the same thing ([OpenZIM MCP](https://glama.ai/mcp/servers/cameronrye/openzim-mcp), [Kiwix Agent](https://mcpmarket.com/server/kiwix-agent)), but through tool calling, which is what made every message cost 5,000+ tokens here. A filter avoids that.
   - Kiwix search is keyword-based ([piefed thread](https://piefed.jeena.net/post/369262)), which is why the small model writes the search terms. Answer quality and speed get measured on real questions before we rely on it (phase 4).
3. **Compute:** the server's Ollama is always on. A Mac mini, if added, is listed first in Open WebUI's connections, with the server as fallback.
4. **Settings:** applied by the playbook (`homestead-webui-setup` plus env), as now.

### 6. What goes away

The NOMAD role and its interactive install; the Command Center with its MySQL, Redis and Qdrant; the link-fixer timer; NOMAD storage bind mounts; duplicate ZIMs and the second Wikipedia; NOMAD's embedding jobs; ports 7000 (read-only NOMAD) and 7090 (Command Center); the static portal files, which the Hub replaces.

## Extending it

The rule: **adding an app or page means adding one entry and, if needed, one role or Hub module. Nothing else gets hand-edited.**

### The app registry

`group_vars/apps.yml` lists every app in one place. One entry declares:

```yaml
apps:
  - id: grocy
    title: Pantry
    icon: "🥫"
    hint: Food storage & expiry
    section: tools              # portal section
    access: public              # public | admin | local (this machine only)
    scheme: http                # https for apps that need a secure context
    backend: 8620               # container port on 127.0.0.1
    port: 7008                  # public port (assigned once, never reused)
    container: homestead-grocy  # compose service (or a role for non-container apps)
    data: [/opt/homestead/data/grocy]   # what backups must include
    power: normal               # normal | eco-stop (stopped in power-saving mode)
    health: /                   # URL checked for the status page
```

Generated from the registry:
- **Caddy** sites (public, admin-password, or local-only);
- **firewall** port sets;
- **portal tiles**, the kiosk's bookmarks, and the binder's app list;
- **backup** include list and database dumps;
- **power-saving** stop list;
- the **status page** (up or down per app, with response time);
- **`/api/apps`**, so Hub pages and future apps can discover each other.

Today all of that is hand-written in six places (Caddyfile, firewall, portal config, Firefox policy, backup script, power script).

### Hub modules

A future page (a family message board, an inventory dashboard, a garden planner, a medication tracker…) is a folder in `hub/modules/<name>/` with its routes, templates, an optional SQLite database under `/var/lib/homestead/<name>/` (backed up automatically), and a menu entry. It gets the Hub's look, login, API and backups for free.

### Shared services future apps can rely on

- **Catalog and library API:** search the library, link to an article or book, check what's on disk.
- **AI API:** a Hub endpoint that asks the planner a question with library search included, so apps don't each wire up Ollama.
- **Events:** when content changes, the jobs signal it (a systemd target, `homestead-content-updated`), so apps can react, for example to re-index.
- **Accounts (later):** today, admin pages use the admin password and Open WebUI has its own users. When apps need per-person accounts, add one sign-in (for example Caddy `forward_auth` to a small identity service) in front of the Hub and the apps. The registry's `access` field is where each app opts in. It's not needed for the base.

### Conventions

- Ports: public 7000–7089 assigned from the registry; admin 7090–7099; backends 8080–8999, never exposed.
- Data: `/opt/homestead/data/<app>` (NVMe), big media on `/srv/library/<kind>`; every path is declared in the registry so backups can't miss it.
- Everything is rebuilt by `bootstrap.sh`. Anything a web page changes lives under `/var/lib/homestead` and is backed up.

## Build plan (keeping everything already downloaded)

| Phase | Work | Downtime |
|---|---|---|
| 1. Registry | `apps.yml`, and generate Caddy, firewall, portal tiles, backup list and power list from it (same result as today, now from one place) | none |
| 2. Catalog | `catalog.yaml` from the manifest plus what's on disk; merged-catalog loader; `homestead-catalog-apply`; health status files | none |
| 3. Hub | `homestead-hub` serving the portal (replacing the static files), health page, JSON API | none |
| 4. One library | Move ZIMs from NOMAD's folder to `/srv/library/zim` (a rename on the same disk), one `kiwix-serve` over both disks, delete duplicates and the second Wikipedia | library for minutes |
| 5. Library manager | Kiwix catalog browse and add, uploads, remove, space planner, queue, updates | none |
| 6. Books | Calibre library and Calibre-Web from `docs/`, `homestead-books` job | none |
| 7. Maps | `homestead-maps` (detailed, wide and world extracts), MapLibre page, place search | none |
| 8. AI library search | Open WebUI filter calling Kiwix search; measure quality and latency | none |
| 9. Apps off NOMAD | Kolibri, Jellyfin and the tools as our containers (move their data folders); registry entries | each app for minutes |
| 10. Remove NOMAD | Stop and remove its containers and role; keep its storage folder until checked | none |
| 11. Docs | INSTALL, RESTORE, binder and README regenerated or updated | none |

Each phase is its own commit on this branch, tested on the server, and leaves the system working. Phases 1–3 lay the extendable base. 4–8 are the features. 9–11 retire NOMAD.

**Risks:**
- **Kiwix search quality** for questions: measured in phase 8. If it's weak, the AI falls back to the curated knowledge bases.
- **Map sizes and build time:** measured in phase 7. The detailed zoom level can be lowered if the extract is too big.
- **The Hub is new code to maintain:** kept small, server-rendered, with no build step and tests for its API.

## Open questions

1. **Hub technology:** Python (FastAPI plus htmx) matches the scripts we already have. Any preference?
2. **Wide map area:** contiguous US plus southern Canada, or just the eastern US (smaller)?
3. **Start with phase 1** (registry) once you're happy with this plan?
