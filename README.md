# Homestead Server

An offline preparedness server for a grid-down situation: a large library (medical, food and water, defense, sustainability, repair, education), local AI for planning, offline maps, a pantry tracker, an encrypted family document vault, ham radio/SDR/MeshCore comms, battery-aware power management, and full backup/restore to external drives.

It runs on a Dell OptiPlex 3060 Micro (i7-8700T, 32GB, 1TB NVMe, AX210 WiFi) with **Ubuntu 26.04 LTS** and is built on [Project NOMAD](https://github.com/Crosstalk-Solutions/project-nomad).

```
                    ┌──────────── HOMESTEAD-LIBRARY WiFi hotspot / ethernet ────────────┐
 phones, laptops ──▶│  Caddy :80 portal (+ captive portal)   :7000-7010 public apps     │
 kiosk (guest)  ──▶ │                                        :7090-7093 admin (password)│
                    └───────────────────────────────┬───────────────────────────────────┘
                                   firewalled backends (nftables)
  NVMe 1TB ─────────────────────────────────────────┼──────────────── USB LIBRARY drive ──
  /srv/core essentials (67GB): kiwix-core            │   NOMAD storage: Wikipedia full,
    medical, water, food, Army FMs, Wikipedia text   │   Survivor Library, Gutenberg,
  /opt: Ollama + Open WebUI (AI), Grocy, Mealie,     │   StackExchange, Khan Academy,
    NOMAD Command Center + MySQL                     │   maps, Kolibri, Calibre, Jellyfin
  vault (LUKS): Paperless family documents           │
                                                     │
  BACKUP-A / BACKUP-B USB drives: borg (encrypted) + library mirror + offline kit + Clonezilla
```

The external drives can come later. Without a LIBRARY drive, the install uses a temporary 180GB library volume on the NVMe, and `homestead-library-migrate` moves it onto the drive when you get one (docs/INSTALL.md, "Adding the drives later").

The essentials are on the internal disk on purpose. If the USB library drive fails, medical, water, food, survival and Army references, all of Wikipedia (text), the AI and the portal keep working.

## Users

| Account | Role |
|---|---|
| `root` | break-glass console login (sealed password) |
| `dennis` | admin: sudo, Docker, vault, admin web UIs, SSH (ethernet, key-only) |
| `guest` | auto-login kiosk: library, AI, maps, office apps, radio apps; can't change the system |

## Start here

1. [docs/INSTALL.md](docs/INSTALL.md): parts list, BIOS, Ubuntu autoinstall, drives, `sudo ./bootstrap.sh`, content download
2. [docs/GRID-DOWN-RUNBOOK.md](docs/GRID-DOWN-RUNBOOK.md): what to do when the grid goes down
3. [docs/RESTORE.md](docs/RESTORE.md): backups, Clonezilla, every restore scenario, the restore drill
4. [docs/POWER.md](docs/POWER.md), [docs/COMMS.md](docs/COMMS.md), [docs/PRINT-BINDER.md](docs/PRINT-BINDER.md)

## Layout

```
bootstrap.sh                  installs Ansible, creates secrets.yml, runs site.yml (re-run any time)
site.yml, group_vars/all.yml  the playbook and its settings (edit timezone/region first)
autoinstall/autoinstall.yaml  unattended Ubuntu install with the LVM layout
content/manifest.yaml         every ZIM / PDF to download, by tier and category
scripts/fetch_content.py      resumable, checksum-verified downloader
roles/
  base      packages, Docker, SMART, unattended upgrades
  users     root / dennis / guest, SSH hardening
  storage   LIBRARY drive + NOMAD bind mount, hot-plug, vault (homestead-vault)
  nomad     stages NOMAD's installer (you accept its license), checks health
  apps      Ollama, Open WebUI, kiwix-core, Grocy, Mealie, Paperless (vault)
  proxy     Caddy (public + password-protected ports), nftables firewall
  portal    the landing page + emergency page + status strip
  kiosk     guest auto-login, GNOME/Firefox lockdown, polkit
  network   hotspot + captive portal, homestead-mode griddown|gridup
  ai        model pulls, homestead-planner persona, knowledge-base seeding
  radio     Pat/Winlink, JS8Call, Fldigi, Direwolf, SDR, NOAA radio, MeshCore
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
| `sudo scripts/fetch_content.py --tier 3` | download or resume the library |
| `homestead-kb-seed --token …` | load PDFs into the AI's knowledge bases |
| `noaa-weather` | NOAA weather radio through the SDR |
| `sudo homestead-library-format /dev/sdX [LABEL]` | prepare a LIBRARY or BACKUP drive |
| `sudo homestead-library-migrate /dev/sdX` | move the temporary internal library onto a new external drive |

## Ports

Public: 80 portal · 7000 NOMAD (read-only) · 7001 full library · 7002 essentials library · 7004 Kolibri · 7005 Calibre-Web · 7006 Jellyfin · 7007 AI · 7008 Grocy · 7009 Mealie · 7010 notes.
Admin (password): 7090 NOMAD Command Center · 7091 Pat/Winlink · 7092 Paperless · 7093 logs.
All backends (8080–8999, 11434–11435, databases) are blocked from the network and from the guest account.
