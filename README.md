# Homestead Server

An offline library and preparedness server for when the grid and the internet are down. It holds
medical, water, food, security, survival, power and repair guides, encyclopedias and courses, plus
maps, a local AI, and radio and mesh tools. It runs on a Dell OptiPlex 3060 Micro (i7-8700T, 32GB,
1TB NVMe, AX210 WiFi) with **Ubuntu 26.04 LTS**, and one Ansible playbook builds it all
(`sudo ./bootstrap.sh`).

```
 phones, laptops, the kiosk          http://library.lan  (hotspot)  ·  http://homestead.local  ·  by IP
              │
              ▼
   Caddy :80 ─── the website (app/) ── reads the library's files directly, no other programs:
              │       topics · search · Ask (AI) · emergency · maps · learn · videos · tools · print · status
              │
              ├── :7008-7020  tools: pantry, notes, PDF/data/IT tools, whiteboard, radio receiver, mesh
              └── :7091-7092  admin: Winlink, vault documents (admin password)

  NVMe: /srv/core     essentials: documents, essential encyclopedias, maps   (always there)
  USB:  /srv/library  everything else: big encyclopedias, Khan Academy, videos
  backups: BACKUP-A / BACKUP-B (borg + library mirror + offline rebuild kit) · vault: LUKS
```

## The website

**One address, no logins, everything in one place.** The website is one program (`app/homestead`)
that reads the library's files itself:

- **Topics:** Medical, Water, Food & farming, Survival, Security, Power, Repair, Comms, Learning,
  Reference, Family documents. Each topic lists its guides and manuals, its encyclopedias and its
  courses. A book that comes as one PDF per chapter shows as one book, with each chapter named from
  its own first page.
- **Search:** one box on every page. It searches the text of every document (page by page, with
  links straight to the page), every encyclopedia, every lesson, and map places. Documents and
  lessons are found by their words and by their meaning, so a page that answers the question in
  other words still comes up. Words listed as meaning the same thing
  (`app/homestead/synonyms.txt`) find each other everywhere, encyclopedias included.
- **Ask:** the AI answers in plain words from the library and links the pages it used.
- **Encyclopedias** (Wikipedia, WikiMed, WikEM, Army manuals, StackExchange, Gutenberg, iFixit,
  and more) are read straight from their ZIM files, inside the website.
- **Learn:** Khan Academy's lessons and videos, browsed and played inside the website.
- **Print:** any document, some of a book's chapters, or a few pages, sent to a printer the
  server can see (CUPS) or opened as one PDF to print from your own phone or laptop.
- **Emergency, Maps, Videos, Tools, Status.**

Every link on it is relative, so it works by whatever name or address you reach it by.

**The library manager** (add and remove things, start downloads) is at **http://localhost:8701** on
the server itself. It answers only there, so it needs no password; from another computer use
`ssh -L 8701:localhost:8701 dennis@homestead.local` and open the same address.

## What's in the library

`library.yaml` lists everything, by topic: encyclopedias (Kiwix ZIM names), documents and ebooks
(links), books published one PDF per chapter (a page and a pattern), and course channels. The
download job fetches anything missing, updates encyclopedias to their newest release (and deletes
the old one), checks every download, and skips what won't fit. Add things in the manager, with
`homestead add …`, or by editing the list. Documents you copy into `/srv/core/docs/<topic>/` show up too.

## Users

| Account | Role |
|---|---|
| `root` | break-glass console login (sealed password) |
| `dennis` | admin: sudo, Docker, vault, admin pages, SSH (ethernet, key only) |
| `guest` | auto-login kiosk with the website open; can't change the system |

## Start here

1. [docs/INSTALL.md](docs/INSTALL.md): parts, BIOS, Ubuntu autoinstall, drives, `sudo ./bootstrap.sh`
2. [docs/GRID-DOWN-RUNBOOK.md](docs/GRID-DOWN-RUNBOOK.md): what to do when the grid goes down
3. [docs/RESTORE.md](docs/RESTORE.md): backups, Clonezilla, every restore case, the restore drill
4. [docs/POWER.md](docs/POWER.md), [docs/COMMS.md](docs/COMMS.md), [docs/SDR-ANTENNA.md](docs/SDR-ANTENNA.md), [docs/PRINT-BINDER.md](docs/PRINT-BINDER.md)

## Layout

```
bootstrap.sh            installs Ansible, makes secrets.yml, runs site.yml (safe to re-run)
site.yml                the playbook          group_vars/all/   settings.yml, website.yml
library.yaml            what the library holds, by topic
app/homestead/          the program: website, manager, search, Ask, downloads, maps   (app/tests: its tests)
autoinstall/            unattended Ubuntu install (+ Ventoy config)
roles/
  base      packages, Docker, SMART, updates          users    root / dennis / guest, SSH
  storage   LIBRARY drive, hot-plug, the vault          homestead the website, library jobs, tools, AI, Caddy, firewall
  kiosk     guest auto-login, browser lockdown          network  hotspot + captive portal, griddown / gridup
  radio     Pat/Winlink, JS8Call, Fldigi, SDR, mesh    power    battery watchdog, power saving
  backup    automatic backups, restore, offline kit
```

## On the server

| Command | Does |
|---|---|
| `homestead status` | what's here, what's missing, disk space, the jobs |
| `sudo homestead fetch` | download and update the library now (needs internet; weekly by itself) |
| `sudo homestead add zim NAME --topic medical` | add an encyclopedia (`homestead find WORDS` to look one up) |
| `sudo homestead add pdf URL --title "…" --topic food` | add a document |
| `sudo homestead index` | update search after copying documents in by hand |
| `sudo homestead maps` | rebuild the maps (needs internet; quarterly by itself) |
| `sudo homestead-mode griddown` / `gridup` | hotspot + captive portal + updates paused / normal |
| `sudo homestead-backup BACKUP-A` | backup (also starts when the drive is plugged in) |
| `sudo homestead-vault open` / `close` | the family document vault |
| `noaa-weather` | NOAA weather radio through the SDR |

## Ports

The website: **80**. Tools (no login): 7008 pantry · 7010 notes · 7011 data tools · 7012 PDF tools ·
7013 IT tools · 7014 whiteboard · 7020 radio receiver · 7017 MeshCore and 7018 Meshtastic (HTTPS,
one certificate warning). Admin (password): 7091 Winlink · 7092 vault documents. The library manager
(8701) and everything else behind Caddy are blocked from the network and from the guest account.
