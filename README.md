# Homestead Server

An offline preparedness server for a grid-down situation: a large library (medical, food and water, defense, sustainability, repair, education), local AI that answers from that library, offline maps, a pantry tracker, an encrypted family document vault, ham radio/SDR/MeshCore comms, battery-aware power management, and full backup/restore to external drives.

It runs on a Dell OptiPlex 3060 Micro (i7-8700T, 32GB, 1TB NVMe, AX210 WiFi) with **Ubuntu 26.04 LTS**, built by one Ansible playbook (`sudo ./bootstrap.sh`).

```
                 ┌──────────── HOMESTEAD-LIBRARY WiFi hotspot / ethernet ──────────────┐
 phones, laptops │  Caddy :80  the website: topics, search, Ask, maps, videos, tools │
 kiosk (guest) ─▶│        :7001-7020 public apps   :7091-7094 admin (password)         │
                 └──────────────────────────────┬──────────────────────────────────────┘
                                 firewalled backends (nftables)
  NVMe 1TB ─────────────────────────────────────┼──────────────── USB LIBRARY drive ──
  /srv/core: essentials (ZIMs, PDFs, maps)       │  zim/  everything else: Wikipedia,
    medical, water, food, Army manuals,          │        StackExchange, Gutenberg...
    all of Wikipedia (text)                      │  video/  kolibri/
  /opt: AI (Ollama), the Hub, pantry (Grocy),    │
    notes, tools...                              │
  vault (LUKS): Paperless family documents       │
  BACKUP-A / BACKUP-B: borg (encrypted) + library mirror + offline rebuild kit + Clonezilla
```

The essentials are on the internal disk on purpose. If the USB library drive fails, medical, water, food, survival and Army references, all of Wikipedia (text), the maps, the AI and the portal keep working.

The external drives can come later. Without a LIBRARY drive, the install uses a temporary 180GB library volume on the NVMe, and `homestead-library-migrate` moves it onto the drive when you get one.

## Users

| Account | Role |
|---|---|
| `root` | break-glass console login (sealed password) |
| `dennis` | admin: sudo, Docker, vault, admin pages (admin web password), SSH (ethernet, key-only) |
| `guest` | auto-login kiosk: library, AI, maps, office apps, radio apps; can't change the system |

## Start here

1. [docs/INSTALL.md](docs/INSTALL.md): parts list, BIOS, Ubuntu autoinstall, drives, `sudo ./bootstrap.sh`
2. [docs/GRID-DOWN-RUNBOOK.md](docs/GRID-DOWN-RUNBOOK.md): what to do when the grid goes down
3. [docs/RESTORE.md](docs/RESTORE.md): backups, Clonezilla, every restore scenario, the restore drill
4. [docs/POWER.md](docs/POWER.md), [docs/COMMS.md](docs/COMMS.md), [docs/SDR-ANTENNA.md](docs/SDR-ANTENNA.md), [docs/PRINT-BINDER.md](docs/PRINT-BINDER.md)
5. [docs/RETHINK.md](docs/RETHINK.md): why it's built this way (and not on Project NOMAD)

## How it fits together

- **The Hub** (`hub/`, a small Python web app) is **the website, on port 80, and nothing on it asks for a login**:
  - **Topics:** every guide, manual and encyclopedia, sorted by topic (medical, water, food…). Split books show as one book with its chapters.
  - **Search:** one box searches the text of every PDF (page by page, with the matching lines) and every encyclopedia.
  - **Ask:** the AI answers from the library and links its sources.
  - **Emergency, Maps, Videos, Tools, Binder, Status.**
  - The **Library manager** (add, remove and download content) is separate, on admin port 7090, and the website doesn't link to it.
  - A JSON API (`/api/apps`, `/api/catalog`, `/api/ask`, `/api/places`, …).
- **The catalog** (`content/catalog.yaml`): every ZIM, document and course the library should hold. The Library manager's edits go on top of it, in `/var/lib/homestead/hub/catalog.local.yaml` (backed up), and **Export my changes** turns them into a patch for this file.
- **The library jobs** (`hub/homestead/jobs`, run as systemd units): `fetch` downloads (resumable, checksum-verified), `fetch-plan` checks sizes and new releases, `catalog-apply` rebuilds the Kiwix library index, `docindex` builds the documents' full-text index (for Search and Ask), `maps` builds the map extracts.
- **The AI** (Ollama, on the Hub's Ask page): for each question it searches the documents' index and every ZIM, gives the best passages to the planner model, and streams the answer with numbered sources. No accounts, and nothing is saved.
- **The app registry** (`group_vars/all/apps.yml`): every app in one list. The containers, proxy sites, firewall, Tools page, status checks and power-saving list are all generated from it. Apps with their own login (Calibre-Web, Open WebUI, Mealie, Homebox, Vaultwarden, Jellyfin) are marked `disabled: true`: not run, not on the website. Their data stays in `/opt/homestead/data`.

## Adding things

- **Content:** the Library manager (http://homestead.local:7090, admin password): search Kiwix's catalog, add a document by link, or upload a file. It shows up under its topic on the website.
- **An app:** one entry in `group_vars/all/apps.yml` (with its container definition), then `sudo ./bootstrap.sh`. It gets a port, a Tools tile, a status check and backups. Only add apps that work without a login.
- **A page:** a Hub module, a folder in `hub/homestead/web/modules/` (copy `example/`). It gets the Hub's look, settings, catalog and API.

## Layout

```
bootstrap.sh                  installs Ansible, creates secrets.yml, runs site.yml (re-run any time)
site.yml, group_vars/         the playbook, its settings (all.yml) and the app registry (apps.yml)
autoinstall/                  unattended Ubuntu install with the LVM layout (+ Ventoy config)
content/catalog.yaml          the library's baseline catalog
hub/                          the Hub (homestead package: web app, catalog, jobs) and its tests
scripts/                      make-secrets.sh; migrate-from-nomad.sh (one-time, for older installs)
roles/
  base      packages, Docker, SMART, unattended upgrades
  users     root / dennis / guest, SSH hardening
  storage   LIBRARY drive, hot-plug, vault (homestead-vault)
  apps      every container in the registry
  proxy     Caddy and nftables, generated from the registry
  hub       the Hub service
  kiosk     guest auto-login, GNOME/Firefox/Chrome lockdown, polkit
  network   hotspot + captive portal, homestead-mode griddown|gridup
  ai        models and the planner persona (Open WebUI extras only if it's re-enabled)
  content   the library jobs and their timers
  radio     Pat/Winlink, JS8Call, Fldigi, Direwolf, SDR (web receiver hand-off), MeshCore
  power     Victron watchdog (eco mode, safe shutdown), power tuning
  backup    homestead-backup (auto on plug-in), homestead-restore, offline kit
```

## Commands on the server

| Command | Does |
|---|---|
| `sudo homestead-mode griddown` / `gridup` | hotspot + captive portal + updates paused / normal |
| `sudo homestead-backup BACKUP-A` | backup (also starts by itself when the drive is plugged in) |
| `sudo homestead-restore BACKUP-A list` | see RESTORE.md |
| `sudo homestead-vault open` / `close` | unlock the family document vault |
| `systemctl status homestead-fetch homestead-docindex` | library download / search index progress (also on the Status page) |
| `sudo systemctl start homestead-maps` | rebuild the offline maps (needs internet) |
| `noaa-weather` | NOAA weather radio through the SDR |
| `sudo homestead-library-format /dev/sdX [LABEL]` | prepare a LIBRARY or BACKUP drive |
| `sudo homestead-library-migrate /dev/sdX` | move the temporary internal library onto a new external drive |

## Ports

Public, no login anywhere: 80 the website (topics, search, Ask, emergency, maps, videos, tools, binder, status) · 7001 full library · 7002 essentials library · 7004 courses (Kolibri, +7034) · 7008 pantry · 7010 notes · 7011 data tools · 7012 PDF tools · 7013 IT tools · 7014 whiteboard · 7020 radio receiver.
HTTPS (local certificate; one browser warning): 7017 MeshCore · 7018 Meshtastic. This machine only: 7027, 7028 (kiosk radio launchers).
Admin (password; not linked from the website): 7090 Library manager · 7091 Winlink · 7092 vault documents · 7093 logs · 7094 file browser.
All backends (8080–8999, 11434–11435, databases) are blocked from the network and from the guest account. The full list is `group_vars/all/apps.yml`.
