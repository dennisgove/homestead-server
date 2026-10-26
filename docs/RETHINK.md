# Rethink: is there a better way to build this?

Status: proposal, on branch `plan/rethink-stack`. Nothing here is built yet.

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

### C. Our own thin stack, no platform (recommended)

Drop NOMAD and run each component directly from our compose file and Ansible, driven by one content catalog. We already run half of this: Open WebUI, Ollama, the essentials Kiwix, Grocy, Mealie, Paperless, OpenWebRX+, Caddy and the portal are ours, not NOMAD's.

- **For:** one library, one catalog, one AI. No interactive install, no link fixing, no hidden databases. Everything is declared in the repo and rebuilt identically from a backup. Fewer moving parts to break on solar power.
- **Against:** we own the content tooling (we mostly do already, with `fetch_content.py`), and we lose NOMAD's point-and-click content manager and its upstream improvements. A maps viewer has to be added.

### D. A commercial appliance

Several offline "survival computers" sell for roughly $200–700. Search results didn't name them reliably, so I can't compare them here. They're typically a Raspberry Pi with Kiwix and a fixed content set: simpler, but smaller, not extensible, and with no AI to speak of. Not a fit for the scope here.

## Recommended design (option C)

```
                      ┌─ Caddy (ports 80, 7000-7099) ─────────────────────────────┐
 phones / kiosk ────▶ │ portal  library  books  learn  videos  maps  AI  radio ...│
                      └───────────────────────────────────────────────────────────┘
 content/catalog.yaml ─▶ homestead-fetch ─▶ /srv/core (NVMe)  +  /srv/library (USB)
        (one source)          │                 essentials          everything else
                              ├─▶ kiwix library.xml (one library, both disks)
                              ├─▶ Calibre library (PDFs, EPUBs, books)
                              ├─▶ portal pages + printed binder index
                              └─▶ AI knowledge bases (curated PDFs)
 Open WebUI ─▶ Ollama (server, or Mac mini when it's on)
     └─ library-search filter: asks Kiwix full-text search at question time
```

### 1. One catalog drives everything

Replace `content/manifest.yaml` with a richer `content/catalog.yaml`. Each item records its title, source, category, tier, **where it lives** (essentials on the NVMe, or bulk on the USB drive), licence, whether the AI should index it, and whether it belongs in the printed binder. From that one file we generate:
- the Kiwix library (`library.xml`) and the portal's topic pages;
- the Calibre book library (PDFs and EPUBs get search, covers and categories in Calibre-Web, instead of the folder listing);
- the binder index (`PRINT-BINDER.md` generated, not hand-written);
- the AI knowledge-base membership;
- a **library health page** on the portal: what's downloaded, what's missing, what failed its checksum, what's out of date, and the by-hand checklist with a drop folder.

No item exists twice. Essentials live on the NVMe, everything else on the USB drive.

### 2. Serving

| What | How | Replaces |
|---|---|---|
| All ZIMs | **One `kiwix-serve`** over a single `library.xml` covering both disks, plus the essentials-only instance that keeps working without the USB drive | NOMAD's Kiwix + our kiwix-core duplicates |
| PDFs, EPUBs, purchased books | **Calibre-Web** on a Calibre library built by `homestead-fetch` | portal folder listing |
| Maps | **Protomaps PMTiles** extract for your state and its neighbors (cut from the planet build with the `pmtiles` CLI), plus a **MapLibre** viewer page in the portal. It's a static file with no tile server: anything that supports HTTP range requests can serve it ([supabase guide](https://supabase.com/blog/self-host-maps-storage-protomaps), [Bobek](https://www.bobek.cz/til/self-hosting-openstreetmap/), [NPR](https://blog.apps.npr.org/2024/11/26/slippy-maps.html)). Organic Maps files on the share for phones. | NOMAD maps |
| Courses | **Kolibri** container, with channels listed in the catalog and imported by the playbook | NOMAD Kolibri |
| Video | **Jellyfin** container | NOMAD Jellyfin |
| Optional tools | CyberChef, IT Tools, Excalidraw and Stirling PDF as plain containers, listed in group_vars | Supply Depot |

### 3. The AI, grounded in the whole library without indexing it

Two layers:
1. **Curated knowledge bases** (as now): the procedure-type PDFs (medical, canning, water, field manuals), embedded once, which is small enough to do on the CPU or the Mac mini.
2. **Live library search, at question time.** An Open WebUI **filter function** (it runs before the model, with no tool definitions sent) takes the question, queries **Kiwix's full-text search** across every ZIM, pulls the best two or three article excerpts, and adds them to the prompt with their titles, so the answer cites them. **Nothing has to be indexed**, it covers full Wikipedia and every new ZIM automatically, and it costs one search plus a few hundred tokens per question.
   - The same idea exists as **MCP servers** (for example OpenZIM MCP and Kiwix Agent: [glama](https://glama.ai/mcp/servers/cameronrye/openzim-mcp), [mcpmarket](https://mcpmarket.com/server/kiwix-agent)), but those work through tool calling, which is exactly what made every message cost 5,000+ tokens here. A filter avoids that.
   - Kiwix's own search is keyword-based and community users call it "questionable" ([piefed](https://piefed.jeena.net/post/369262)). The filter would first have the small model turn the question into good search terms, which is cheap.

Settings are applied entirely by the playbook (`homestead-webui-setup` plus env), as now.

**Compute:** the server's Ollama is always on. When the Mac mini is on the network, Open WebUI uses it first (Open WebUI supports several Ollama connections), and falls back to the server when it's off.

### 4. What goes away

The NOMAD role and its interactive install, the Command Center and its MySQL, Redis and Qdrant, the link-fixer timer, NOMAD storage bind mounts, the duplicate ZIM copies, the second Wikipedia, NOMAD's embedding jobs, and ports 7000 (read-only NOMAD) and 7090 (Command Center).

## Migration (keeping everything already downloaded)

| Phase | Work | Downtime |
|---|---|---|
| 1. Catalog | Write `catalog.yaml` from the manifest plus what's on disk now; generate the health page. No behaviour change. | none |
| 2. One library | Move ZIMs out of `/opt/project-nomad/storage/zim` into `/srv/library/zim` (same disk, so a rename, not a copy); one `kiwix-serve` over both disks; delete duplicates | library for minutes |
| 3. Books and maps | Calibre library from `/srv/core/docs`; PMTiles extract plus MapLibre page | none |
| 4. Library-search filter | Open WebUI filter calling Kiwix search; measure answer quality and latency on real questions | none |
| 5. Apps off NOMAD | Kolibri, Jellyfin, tools as our containers (move their data folders); switch portal links | each app for minutes |
| 6. Remove NOMAD | Stop and remove its containers and role; keep its storage folder until we've checked nothing's missing | none |
| 7. Docs | INSTALL, RESTORE and the binder regenerated from the catalog | none |

Each phase is its own commit and can be stopped after. Phases 1–4 are worth doing even if we keep NOMAD.

**Effort:** phases 1–4 are the bulk (the catalog generator, Calibre import, the maps page, the filter). 5–7 are mostly moving things.

**Risks:**
- **Kiwix search quality:** if keyword search turns out poor for questions, the filter can fall back to the curated knowledge bases only. We'd measure that in phase 4 before relying on it.
- **Maps:** PMTiles needs a planet build download (big) to cut the state extract from. Phones still have Organic Maps either way.
- **Losing NOMAD's UI:** content changes then happen through the catalog file, not a web page. The health page shows status, but adding an item means editing YAML.

## Decisions for you

1. **Go with option C**, or stay on A and only take phases 1–4 (catalog, one library, books and maps, live library search) alongside NOMAD?
2. **Content editing:** is editing `catalog.yaml` (with me) acceptable, or do you want a web page for adding and removing items?
3. **Maps:** state plus neighboring states, or wider?
