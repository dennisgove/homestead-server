# Install guide

Do the whole thing **while the internet still works**. Allow a weekend for setup and several days of background downloads.

## 0. Parts

| Item | Notes |
|---|---|
| OptiPlex 3060 Micro, i7-8700T, 32GB, 1TB NVMe, AX210 | the server |
| **LIBRARY drive**: USB 3 portable HDD, **2TB minimum** (4–5TB if you'll add video) | measured Oct 2026: essentials 67GB on the NVMe, full library ~750GB + NOMAD collections + maps |
| **BACKUP-A, BACKUP-B**: USB 3 portable HDD, **4–5TB each** | each one holds the library mirror + encrypted system backups + Clonezilla images. Start with one; add the second later. |
| 32GB+ USB stick | Ventoy rescue/installer stick |
| Victron SmartShunt (or MPPT) + VE.Direct USB cable | battery-aware shutdown |
| 12V→19.5V DC-DC converter, ≥90W, Dell 4.5mm plug | run the PC directly off the battery |
| RTL-SDR Blog V4 + dipole kit; Digirig + your radio; 2+ MeshCore nodes | comms (optional, can come later) |

Portable 5TB drives have historically been about $100–130. SMR drives are fine here because the library is written once and then mostly read.

## 1. BIOS (F2 at power-on)

- Update the BIOS first (Dell's site, while online).
- **Power Management → AC Recovery: Power On**, so it boots by itself when power returns.
- Deep Sleep Control: Disabled. Wake on LAN: LAN only (optional).
- Boot: UEFI, Secure Boot **on** (Ubuntu supports it), boot order NVMe then USB.
- Set a BIOS admin password and write it on the recovery sheet.

## 2. Rescue / installer stick

1. Install [Ventoy](https://www.ventoy.net) on the USB stick.
2. Copy these to it: `ubuntu-26.04-desktop-amd64.iso`, `clonezilla-live-*-amd64.iso`, `memtest86+`, and this repo folder.
3. Edit `autoinstall/autoinstall.yaml`: replace the password hash (`openssl passwd -6`) and timezone. Save it to the stick and set it as the Ubuntu ISO's auto-install template in Ventoy's `ventoy/ventoy.json`:
   ```json
   { "auto_install": [ { "image": "/ubuntu-26.04-desktop-amd64.iso", "template": "/homestead-server/autoinstall/autoinstall.yaml" } ] }
   ```
   (Without Ventoy: the Ubuntu desktop installer also offers "Automated install" and accepts the file from a URL or second USB stick.)

## 3. Install Ubuntu 26.04 (wipes the NVMe)

Boot the stick, pick the Ubuntu ISO, and choose the autoinstall template. The NVMe gets this layout:

| LV | Size | Mount |
|---|---|---|
| lv_root | 120G | / |
| lv_home | 60G | /home |
| lv_opt | 250G | /opt (NOMAD, apps, AI models) |
| lv_core | 150G | /srv/core (essentials library) |
| lv_swap | 16G | swap |
| lv_vault | 50G | encrypted vault (set up later) |
| free | ~280G | snapshots, growth |

## 4. Prepare the external drives (optional now)

**No drives yet? Skip this step.** With no LIBRARY drive attached, the playbook creates a 180GB temporary library volume in the NVMe's spare space (`library_temp_size` in `group_vars/all.yml`), and everything installs and works. The portal shows "Library on internal disk (temporary)" until you move it. See [Adding the drives later](#adding-the-drives-later).

Log in as dennis, plug in each drive **one at a time**, and use `lsblk` to identify it (for example `/dev/sda`). Make sure it's the USB drive and not the NVMe.

```bash
cd ~/homestead-server            # the repo, copied from the stick
sudo bash roles/storage/files/homestead-library-format /dev/sdX            # -> LIBRARY
sudo bash roles/storage/files/homestead-library-format /dev/sdY BACKUP-A
sudo bash roles/storage/files/homestead-library-format /dev/sdZ BACKUP-B
```
Leave LIBRARY plugged in permanently, and unplug the backup drives.

## 5. Settings, then the playbook

```bash
nano group_vars/all.yml          # timezone, region_state, hotspot name...
sudo ./bootstrap.sh              # asks for passwords, writes secrets.yml, runs Ansible
```
**Write down the borg passphrase it prints** and put it in the sealed envelope.

The playbook stops at the NOMAD step on purpose:
```bash
sudo homestead-install-nomad     # read and accept the NOMAD license when asked
sudo ./bootstrap.sh              # continue; re-running is always safe
```

## 6. Inside the NOMAD Command Center (http://localhost:7090, dennis + web password)

1. Run the **Easy Setup** wizard. Pick Wikipedia "Complete (Full)" plus the **Comprehensive** tier of Medicine, Survival, Agriculture, DIY and Education. Our manifest skips anything NOMAD already downloaded.
2. **Maps**: download your state and the neighboring states (see `region_state`).
3. Install from the app catalog (Supply Depot): **Kolibri, Calibre-Web, Jellyfin, FlatNotes, MeshCore Web, CyberChef, Stirling PDF**. Do **not** install NOMAD's own *AI Assistant/Ollama* container. Instead, go to **AI settings → remote Ollama URL = `http://host.docker.internal:11435`** (our tuned Ollama). If NOMAD insists on its own container, it can stay installed, but then point Open WebUI at whichever one you keep.
4. In Kolibri, import channels: Khan Academy (English), CK-12, and whatever suits the kids' ages.

## 7. Content downloads (days; run in tmux)

```bash
tmux new -s fetch
sudo scripts/fetch_content.py --list --tier 3     # see sizes first
sudo scripts/fetch_content.py --tier 1            # critical content first
sudo scripts/fetch_content.py --tier 3            # then everything else
```
Then fetch the **manual** items it lists (Hesperian books, TCCC, the canning guide, your state extension guides, manuals for your own gear) into `/srv/core/docs/<category>/` and run `sudo scripts/fetch_content.py --docs-index`.

Phone apps (Kiwix, Organic Maps + map files, MeshCore, F-Droid) go into `/srv/core/share/apps/`.

## 8. AI

1. Open http://localhost:7007 and create the first account. **It becomes the Open WebUI admin, so make it dennis.**
2. Admin Panel → Settings → enable API keys. Then profile → Settings → Account → create an API key.
3. `homestead-kb-seed --token <key>` uploads the essentials PDFs into knowledge bases (Medical, Food & Agriculture, ...).
4. In Workspace → Models, edit `homestead-planner` and attach the knowledge bases. Family members sign up, and dennis approves them (Admin → Users).

## 9. Vault

```bash
sudo homestead-vault init      # pick a strong passphrase -> recovery sheet
sudo homestead-vault open      # Paperless at http://localhost:7092; create its admin:
docker exec -it homestead-paperless python3 manage.py createsuperuser
sudo homestead-vault close
```
Scan IDs, deeds, insurance, prescriptions, vaccination records and the like into Paperless's consume folder (`/srv/vault/paperless/consume`) or through its web UI.

## 10. Comms (when you have the hardware)

See [COMMS.md](COMMS.md): `pat configure` (callsign, grid), Digirig audio levels, `noaa-weather`, MeshCore companion setup.

With the temporary internal library, run `--tier 1` and NOMAD's Essential/Standard tiers for now. The downloader skips anything that won't fit, so nothing breaks. Run `--tier 3` after the external drive is in.

## 11. Finish

1. Plug in BACKUP-A. The first backup starts automatically and takes many hours. Then do BACKUP-B. (No backup drive yet? The portal shows "Last backup never". The daily desktop reminder only starts after the first backup. Until then you have **no backup**.)
2. Make the first **Clonezilla image** (RESTORE.md §Clonezilla).
3. Do the **restore drill** (RESTORE.md §Drill) before you rely on it.
4. Print the binder ([PRINT-BINDER.md](PRINT-BINDER.md)) and the WiFi sign (`/srv/core/share/print/wifi-sign.html`).
5. Test `sudo homestead-mode griddown` with a phone, then `gridup`.

## Adding the drives later

**Library drive** (moves the temporary internal library onto it; NOMAD is down only for the final copy pass):
```bash
lsblk                                         # find the new USB drive, e.g. /dev/sda
sudo homestead-library-migrate /dev/sdX       # erases it, copies, swaps labels
# check the portal and the Command Center, then free the NVMe space:
sudo lvremove vg_sys/lv_library
tmux new -s fetch 'sudo /opt/homestead/repo/scripts/fetch_content.py --tier 3'   # now download the rest
```

**Backup drive:**
```bash
sudo homestead-library-format /dev/sdY BACKUP-A
```
Unplug it and plug it back in. The first backup starts on its own. Then make the first Clonezilla image (RESTORE.md).
