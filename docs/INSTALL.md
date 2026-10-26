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
| lv_opt | 250G | /opt (NOMAD, apps, AI models) |
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

**No drives yet? Skip this step.** With no LIBRARY drive attached, the playbook creates a 180GB temporary library volume in the NVMe's spare space (`library_temp_size` in `group_vars/all.yml`), and everything installs and works. The portal shows "Library on internal disk (temporary)" until you move it. See [Adding the drives later](#adding-the-drives-later).

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
nano group_vars/all.yml          # timezone, region_state, hotspot name...
sudo ./bootstrap.sh              # asks for passwords, writes secrets.yml, runs Ansible
```
It asks for:
- the root password (break-glass, goes on the recovery sheet)
- the dennis password (replaces the temporary one)
- the guest password (simple; it will be posted)
- the admin web password (Command Center, Paperless, Pat)
- your SSH public key (on the Mac: `cat ~/.ssh/id_ed25519.pub`; blank to skip)
- the hotspot WiFi password
- the borg passphrase: **leave it blank on a first install**, and it generates one. On a rebuild, type the one from the recovery sheet.

**Write down the borg passphrase it prints** and put it in the sealed envelope. It isn't saved on the backup drives, so without it they can't be restored onto a new machine.

After the first run, the firewall allows SSH only from **wired ethernet** (never from the hotspot). An SSH session that's already open keeps working.

To update the server from the Mac later, copy the folder again and re-run `bootstrap.sh`. That keeps the existing passwords and passphrase (`/opt/homestead/repo/secrets.yml`).

The playbook stops at the NOMAD step on purpose:
```bash
sudo homestead-install-nomad     # read and accept the NOMAD license when asked
sudo ./bootstrap.sh              # continue; re-running is always safe
```

## 8. Inside the NOMAD Command Center (http://localhost:7090 on the server, or http://homestead.local:7090 from another computer; dennis + web password)

1. Run the **Easy Setup** wizard. Pick Wikipedia "Complete (Full)" plus the **Comprehensive** tier (on the temporary internal library: the Essential/Standard tiers for now) of Medicine, Survival, Agriculture, DIY and Education. Our manifest skips anything NOMAD already downloaded.
   **AI:** on the wizard's first step (Core Capabilities), select the **AI Assistant** card, check **Use remote Ollama instance** in the box that appears under it, and enter `http://host.docker.internal:11435`. NOMAD then uses our Ollama (already tuned for this CPU and loaded with the models) instead of installing a second one, which would double the RAM and disk the models use.
2. **Maps**: download your state and the neighboring states (see `region_state`).
3. Install from the app catalog (Supply Depot): **Kolibri, Calibre-Web, Jellyfin, FlatNotes, MeshCore Web, CyberChef, Stirling PDF**. Don't install NOMAD's own Ollama from there.
4. In Kolibri, import channels: Khan Academy (English), CK-12, and whatever suits the kids' ages.

**Setting the AI later, or changing it:** open http://homestead.local:7090/settings/models directly (the Settings menu hides this link until the AI is set up, and the page may warn that the AI's dependencies aren't installed; ignore that). Under **Remote Connection**, enter the URL in **Remote Ollama/OpenAI API URL** and click **Save & Test**.

If it can't connect, use `http://172.17.0.1:11435` (the server's Docker address) instead. To check that our Ollama is running: `curl http://127.0.0.1:11435/api/version` on the server should print a version.

## 9. Content downloads (days; run in tmux)

```bash
tmux new -s fetch
sudo scripts/fetch_content.py --list --tier 3     # see sizes first
sudo scripts/fetch_content.py --tier 1            # critical content first
sudo scripts/fetch_content.py --tier 3            # then everything else
```
Then fetch the **manual** items it lists (Hesperian books, TCCC, the canning guide, your state extension guides, manuals for your own gear) into `/srv/core/docs/<category>/` and run `sudo scripts/fetch_content.py --docs-index`.

Phone apps (Kiwix, Organic Maps + map files, MeshCore, F-Droid) go into `/srv/core/share/apps/`.

With the temporary internal library, run `--tier 1` and NOMAD's Essential/Standard tiers for now. The downloader skips anything that won't fit, so nothing breaks. Run `--tier 3` after the external drive is in.

## 10. AI

1. Open http://localhost:7007 and create the first account. **It becomes the Open WebUI admin, so make it dennis.**
2. Admin Panel → Settings → enable API keys. Then profile → Settings → Account → create an API key.
3. `homestead-webui-setup --token <key>` applies the settings that keep chat fast on this CPU (built-in tools off, background jobs on the small model) and sets up the model menu. **Without it, every message waits minutes before an answer starts.** Then `homestead-kb-seed --token <key>` uploads the essentials PDFs into knowledge bases (Medical, Food & Agriculture, ...).
4. In Workspace → Models, edit `homestead-planner` (answers directly, the default) and `homestead-thinker` (reasons step by step first: slower, for hard planning questions) and attach the knowledge bases. Family members sign up, and dennis approves them (Admin → Users).

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
