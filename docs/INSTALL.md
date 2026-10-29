# Install guide

Do the whole thing **while the internet still works**. Allow a weekend for setup and several days of background downloads.

## 0. Parts

| Item | Notes |
|---|---|
| OptiPlex 3060 Micro, i7-8700T, 32GB, 1TB NVMe, AX210 | the server |
| **LIBRARY drive**: USB 3 portable HDD, **2TB minimum** (4–5TB if you'll add video) | measured Oct 2026: essentials 67GB on the NVMe; the full library about 800GB on the USB drive |
| **BACKUP-A, BACKUP-B**: USB 3 portable HDD, **4–5TB each** | each one holds the library mirror + encrypted system backups + Clonezilla images. Start with one; add the second later. |
| 32GB+ USB stick | Ventoy rescue/installer stick |
| Victron SmartShunt (or MPPT) + VE.Direct USB cable | battery-aware shutdown |
| 12V→19.5V DC-DC converter, ≥90W, Dell 4.5mm plug | run the PC directly off the battery |
| RTL-SDR Blog V4 + dipole kit; Digirig + your radio; 2+ MeshCore nodes | comms (optional, can come later) |

Portable 5TB drives have historically been about $100–130. SMR drives are fine here because the library is written once and then mostly read.

## 1. Before you wipe anything

The install erases the NVMe, including whatever is on it now. Copy off anything you want to keep.

**Make the temporary password hash.** The installer creates `dennis` with a temporary password for the first login (`bootstrap.sh` replaces it later). It needs that password as a SHA-512 hash. macOS's `openssl` can't make one, so do this on the OptiPlex's current Ubuntu, or any Linux machine:
```bash
openssl passwd -6        # type a temporary password twice; copy the $6$... line it prints
```
Put it in `autoinstall/autoinstall.yaml` as `password: "$6$..."`, replacing the `CHANGE-ME` placeholder, and set `timezone:`. **Don't skip this.** With the placeholder, no password works and you'd have to reinstall.

## 2. BIOS (F2 at power-on)

- Update the BIOS first (Dell's site, while online).
- **Power Management → AC Recovery: Power On**, so it boots by itself when power returns.
- Deep Sleep Control: Disabled. Wake on LAN: LAN only (optional).
- **System Configuration → USB Configuration:** check **Enable Boot Support** and Enable USB 3.0 Controller, or the stick won't appear in the boot menu.
- Secure Boot **on** (Ubuntu supports it; Ventoy needs a one-time key enrollment, step 4).
- Set a BIOS admin password and write it on the recovery sheet.

The boot order can wait until after the install (step 4). To boot the stick, use the one-time menu: **F12** at power-on.

## 3. Rescue / installer stick

Ventoy has no macOS version, so make the stick on Linux (the OptiPlex's current Ubuntu is fine) or Windows.

1. Download the latest `ventoy-*-linux.tar.gz` from https://github.com/ventoy/Ventoy/releases.
2. Install it on the stick. **This erases the stick**, so check the device name first:
   ```bash
   tar xzf ventoy-*-linux.tar.gz && cd ventoy-*/
   lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS   # the stick shows TRAN=usb; NOT nvme0n1
   sudo umount /dev/sdX?*                      # Ubuntu auto-mounts it; Ventoy refuses a mounted disk
   sudo sh Ventoy2Disk.sh -i -s /dev/sdX       # -s = Secure Boot support; use -I to redo an existing Ventoy stick
   ```
   (Or `sudo ./VentoyGUI.x86_64`, with Options → Secure Boot Support checked.)
3. Unplug the stick and plug it back in. It now has a big partition named **Ventoy**, which is where everything goes, and a small **VTOYEFI** partition you leave alone.
4. Download the ISOs:
   - Ubuntu 26.04 LTS Desktop, `ubuntu-26.04-desktop-amd64.iso`, from https://ubuntu.com/download/desktop
   - Clonezilla Live, the stable amd64 ISO, from https://clonezilla.org/downloads.php
   - Memtest86+ (optional), the ISO from https://www.memtest.org (unzip it if it comes zipped)
5. Copy to the top of the **Ventoy** partition: the three ISOs (any filenames; Ventoy lists every `.iso`), this repo folder named `homestead-server` (after making the step 1 edits), and the `autoinstall/ventoy` folder:
   ```bash
   cp ~/Downloads/*.iso /Volumes/Ventoy/                 # Mac; on Ubuntu: /media/$USER/Ventoy/
   cp -R ~/dev/homestead-server /Volumes/Ventoy/
   cp -R ~/dev/homestead-server/autoinstall/ventoy /Volumes/Ventoy/
   ```
   The stick should end up like this:
   ```
   ubuntu-26.04-desktop-amd64.iso
   clonezilla-live-...-amd64.iso
   mt86plus_..._x86_64.iso
   homestead-server/      (autoinstall/autoinstall.yaml has your hash)
   ventoy/ventoy.json     (makes autoinstall.yaml the Ubuntu ISO's install template)
   ```
   `ventoy.json` names the Ubuntu ISO as `/ubuntu-26.04-desktop-amd64.iso`. If yours is called something else (a point release, say), rename the ISO or edit `image` in `ventoy.json` to match.
6. Eject the stick properly before unplugging it.

## 4. Install Ubuntu 26.04 (wipes the NVMe)

1. **Connect the network first.** Plug in ethernet, or join WiFi from the top-right menu once the live desktop is up. The install downloads packages; without a connection it fails.
2. Plug in the stick, power on, tap **F12**, and pick the USB stick (by its brand name, e.g. "UEFI: SanDisk").
3. **First time only, with Secure Boot on:** a "Verification failed" message appears. Press OK, then any key for MOK management → **Enroll key from disk** → `VTOYEFI` → `ENROLL_THIS_KEY_IN_MOKMANAGER.cer` → Continue → Yes → Reboot. Press F12 and pick the stick again. (If that screen never appears, turn Secure Boot off for the install and back on afterwards.)
4. In the Ventoy menu, pick the Ubuntu ISO, then the **autoinstall.yaml** template when asked.
5. At Ubuntu's menu, choose **Try or Install Ubuntu**.
6. The install runs by itself. Confirm the disk wipe if asked. If you get the normal installer screens instead, the template wasn't picked up: click through to "How do you want to install Ubuntu?", choose **Automated installation**, and give it a URL for the file. To serve it from the Mac on the same network:
   ```bash
   cd ~/dev/homestead-server/autoinstall && python3 -m http.server 8000   # then use http://<mac-ip>:8000/autoinstall.yaml
   ipconfig getifaddr en0                                                 # the Mac's IP
   ```
   Don't choose **Interactive installation**: it doesn't create the disk layout below, and the playbook's storage step would fail.
7. When it says so, remove the stick and reboot.
8. Optional: F2 → **General → Boot Sequence**. Put **ubuntu** first, and delete or uncheck old **Windows Boot Manager** entries (leftovers; the wipe made them useless).

**If the install fails:** before rebooting, open a terminal (Ctrl+Alt+T) and look at the end of `/var/log/installer/curtin-install.log` and `subiquity-server-debug.log` (`sudo tail -40 ...`). The most common cause is no network.

The NVMe gets this layout:

| LV | Size | Mount |
|---|---|---|
| lv_root | 120G | / |
| lv_home | 60G | /home |
| lv_opt | 250G | /opt (apps, the Hub, AI models) |
| lv_core | 150G | /srv/core (essentials library) |
| lv_swap | 16G | swap |
| lv_vault | 50G | encrypted vault (set up later) |
| free | ~280G | snapshots, growth |

## 5. Copy the repo onto the server

The installer installs only Ubuntu, so the repo isn't on the disk yet. Log in as **dennis** with the temporary password from step 1, connect to the internet (`bootstrap.sh` needs it), and copy the repo from the stick:
```bash
cp -r /media/dennis/Ventoy/homestead-server ~/      # `ls /media/dennis/` if the name differs
```
Or from the Mac: `scp -r ~/dev/homestead-server dennis@homestead.local:` (or use the server's IP from `ip -4 addr`).

## 6. Prepare the external drives (optional now)

**No drives yet? Skip this step.** With no LIBRARY drive attached, the playbook creates a 180GB temporary library volume in the NVMe's spare space (`library_temp_size` in `group_vars/all/settings.yml`), and everything installs and works. The portal shows "Library on internal disk (temporary)" until you move it. See [Adding the drives later](#adding-the-drives-later).

Log in as dennis, plug in each drive **one at a time**, and use `lsblk` to identify it (for example `/dev/sda`). Make sure it's the USB drive and not the NVMe.

```bash
cd ~/homestead-server            # the repo, copied from the stick
sudo bash roles/storage/files/homestead-library-format /dev/sdX            # -> LIBRARY
sudo bash roles/storage/files/homestead-library-format /dev/sdY BACKUP-A
sudo bash roles/storage/files/homestead-library-format /dev/sdZ BACKUP-B
```
Leave LIBRARY plugged in permanently, and unplug the backup drives.

## 7. Settings, then the playbook

```bash
cd ~/homestead-server
nano group_vars/all/settings.yml          # timezone, region_state, hotspot name...
sudo ./bootstrap.sh              # asks for passwords, writes secrets.yml, runs Ansible
```
It asks for:
- the root password (break-glass, goes on the recovery sheet)
- the dennis password (replaces the temporary one)
- the guest password (simple; it will be posted)
- the admin web password (the admin pages only: Library manager, vault documents, Winlink, logs, file browser, radio receiver settings). The website itself never asks for one.
- your SSH public key (on the Mac: `cat ~/.ssh/id_ed25519.pub`; blank to skip)
- the hotspot WiFi password
- the borg passphrase: **leave it blank on a first install**, and it generates one. On a rebuild, type the one from the recovery sheet.

**Write down the borg passphrase it prints** and put it in the sealed envelope. It isn't saved on the backup drives, so without it they can't be restored onto a new machine.

After the first run, the firewall allows SSH only from **wired ethernet** (never from the hotspot). An SSH session that's already open keeps working.

To update the server from the Mac later, copy the folder again and re-run `bootstrap.sh`. That keeps the existing passwords and passphrase (`/opt/homestead/repo/secrets.yml`).

The first run takes a while (container images, AI models). Everything after it happens in the background: the library download, the maps, the books library and the AI's knowledge bases. Watch it on the **Library manager** page.

**Upgrading an older install that used Project NOMAD?** Run `sudo scripts/migrate-from-nomad.sh` once, before this step. It moves NOMAD's ZIMs, courses, videos and app data into the new layout (renames on the same disk, so it's quick) and retires NOMAD.

## 8. The Library manager (http://homestead.local:7090; dennis + admin web password)

Everything about the library's content, from a web page:
- **Overview:** what's downloaded, disk space (including whether pending downloads will fit), the jobs and their progress, with **Run now** buttons.
- **Add from Kiwix:** search Kiwix's online catalog (needs internet) and add an item in one click: category, tier, and which disk (essentials on the NVMe, or the USB drive).
- **Add a document:** by link, or upload a file (the by-hand items). Choose its category, and whether the AI uses it and it goes in the printed binder.
- **All items:** change category, tier or disk, switch "use in AI", "in binder" and "updates" per item, download or remove (optionally deleting the files).
- **Updates:** newer releases of what you have (checked weekly, or **Check now**).
- **Health & checklist:** what isn't downloaded yet, duplicates, unfinished downloads, files on disk that aren't in the catalog (**Adopt** them), and the list of things to get by hand.
- **Export my changes:** your edits as a YAML patch for `content/catalog.yaml`, so a rebuild starts from them too. (They're also backed up.)

## 9. Content and maps (automatic; days)

`bootstrap.sh` indexes what's on disk, then starts the download in the background, and it repeats weekly to resume and pick up new releases. It fetches tiers 1–3 (`content_tier` in `group_vars/all/settings.yml`) and skips anything that won't fit, so it's safe with the temporary internal library too. The **maps** are built once in the background (needs internet; refreshed quarterly):
- **detailed:** your state and its neighbors (`region_state`), every street, building and trail;
- **wide:** the contiguous US and southern Canada, towns and highways;
- **world:** countries and major cities;

plus offline place search. Open them at http://homestead.local/maps.

```bash
systemctl status homestead-fetch homestead-maps   # or the Library manager's Overview
```

Some documents have no download link: **Health & checklist** lists them. Upload them there once you have them.

Phone apps (Kiwix, Organic Maps + map files, MeshCore, F-Droid) go into `/srv/core/share/apps/`.

## 10. Search and AI (automatic)

Nothing to click, and nobody needs an account:
- **Search** (the box on every page of http://homestead.local) looks through the text of every PDF, page by page, and every encyclopedia. The documents' index (`homestead-docindex`) is rebuilt after each library change, in under a minute.
- **Ask** (http://homestead.local/ask): the AI searches the same way, gives the planner model the best passages, and streams the answer with numbered links to its sources. It runs on this CPU: the answer starts after 10–30 seconds (a couple of minutes if the model has to load first). Nothing is saved on the server.

```bash
systemctl status homestead-docindex        # journalctl -u homestead-docindex to see what it read
```

## 11. Vault

```bash
sudo homestead-vault init      # pick a strong passphrase -> recovery sheet
sudo homestead-vault open      # Paperless at http://localhost:7092; create its admin:
docker exec -it homestead-paperless python3 manage.py createsuperuser
sudo homestead-vault close
```
Scan IDs, deeds, insurance, prescriptions, vaccination records and the like into Paperless's consume folder (`/srv/vault/paperless/consume`) or through its web UI.

## 12. Comms (when you have the hardware)

See [COMMS.md](COMMS.md): `pat configure` (callsign, grid), Digirig audio levels, `noaa-weather`, MeshCore companion setup.

## 13. Finish

1. Plug in BACKUP-A. The first backup starts automatically and takes many hours. Then do BACKUP-B. (No backup drive yet? The portal shows "Last backup never". The daily desktop reminder only starts after the first backup. Until then you have **no backup**.)
2. Make the first **Clonezilla image** (RESTORE.md §Clonezilla).
3. Do the **restore drill** (RESTORE.md §Drill) before you rely on it.
4. Print the binder: http://homestead.local/binder lists everything marked **in binder** (set in the Library manager), by tab ([PRINT-BINDER.md](PRINT-BINDER.md)). Also the WiFi sign (`/srv/core/share/print/wifi-sign.html`).
5. Test `sudo homestead-mode griddown` with a phone, then `gridup`.

## Adding the drives later

**Library drive** (moves the temporary internal library onto it; the library apps are down only for the final copy pass):
```bash
lsblk                                         # find the new USB drive, e.g. /dev/sda
sudo homestead-library-migrate /dev/sdX       # erases it, copies, swaps labels
# check the website and the Library manager, then free the NVMe space:
sudo lvremove vg_sys/lv_library
sudo systemctl start --no-block homestead-fetch   # now download the rest (also happens weekly on its own)
```

**Backup drive:**
```bash
sudo homestead-library-format /dev/sdY BACKUP-A
```
Unplug it and plug it back in. The first backup starts on its own. Then make the first Clonezilla image (RESTORE.md).
