# Backup and restore

**Print this.** You'll need it when the computer is broken.

You need: a backup drive (BACKUP-A or BACKUP-B), the Ventoy rescue stick, and the sealed recovery sheet (root password, borg passphrase, vault passphrase, BIOS password).

## What gets backed up where

Every time a backup drive is plugged in, `homestead-backup` runs by itself and shows a message when it's done:

| On the drive | What | How to use it |
|---|---|---|
| `borg/` | Encrypted, deduplicated archives `system-<date>` (/etc, /home, /root, /opt incl. AI models, /usr/local, essentials library, portal, DB dumps, disk layout) and `vault-<date>` (the vault, still LUKS-encrypted). Keeps 7 daily, 8 weekly, 12 monthly. | `homestead-restore` (below) or `borg` directly |
| `library/` | Plain copy of the LIBRARY drive | Copy back, or plug into any Linux/Kiwix computer and read it directly |
| `library-deleted/<date>/` | Library files that were deleted or replaced | Copy back if a deletion was a mistake |
| `offline/` | Docker images, .deb packages, this repo (without secrets.yml) | Rebuild with no internet |
| `clonezilla/` | Full images of the NVMe (made by hand, monthly) | Bare-metal restore in ~30 min |
| `borg-key.txt`, `LAST-BACKUP*.txt` | Repository key copy, last backup summary | |

The borg key is useless without the **passphrase** on the recovery sheet.

## Clonezilla image (monthly, and after big changes)

1. Plug in the backup drive. If a backup starts, let it finish.
2. Reboot with the Ventoy stick in → **Clonezilla Live**.
3. `device-image` → `local_dev` → choose the backup drive (`BACKUP-A`) → directory `clonezilla/`.
4. `Beginner` → `savedisk` → name it `homestead-YYYY-MM` → disk `nvme0n1` → default compression → **check the saved image: yes**.
5. Keep the last 2–3 images and delete older ones in `clonezilla/`.

The NVMe image is about 100–150GB. The LIBRARY drive isn't imaged; `library/` already mirrors it.

## Scenario 1: a file, note, or app's data was lost or broken

```bash
sudo homestead-restore BACKUP-A list                                  # pick an archive
sudo homestead-restore BACKUP-A files system-2026-11-02T10:00 home/guest/Documents
# restored under /restore/home/guest/Documents - copy back what you need
```
App databases: stop the app, copy its folder back from `/restore/opt/homestead/data/<app>` (or use the consistent copy in `/restore/var/lib/homestead/dumps/sqlite/`), then start it again. NOMAD's database: `sudo homestead-restore BACKUP-A mysql`.

## Scenario 2: the NVMe died, or the system won't boot

1. Fit a new NVMe of the same size or larger.
2. Boot Clonezilla → `device-image` → backup drive → `clonezilla/` → `restoredisk` → newest image → `nvme0n1`.
3. Reboot. The system is back as of that image (≤ 1 month old).
4. Bring it up to date from the newest borg archive:
   ```bash
   sudo homestead-restore BACKUP-A list
   sudo homestead-restore BACKUP-A all system-<newest>
   sudo rsync -a /restore/home/ /home/
   sudo rsync -a /restore/opt/homestead/data/ /opt/homestead/data/   # stop apps first: docker compose -f /opt/homestead/compose.yaml stop
   sudo homestead-restore BACKUP-A mysql
   ```
5. Vault newer than the image? `sudo homestead-restore BACKUP-A vault vault-<newest>`.

## Scenario 3: the LIBRARY drive died

The essentials (medical, water, food, Army manuals, all of Wikipedia as text) are on the NVMe and keep working. To bring back the full library:
```bash
sudo homestead-library-format /dev/sdX                 # the new drive
sudo homestead-restore BACKUP-A library               # copies library/ back (hours), restarts NOMAD
```
No spare drive yet? Any laptop with Kiwix desktop can open the backup drive's `library/nomad/zim/*.zim` files directly.

## Scenario 4: the whole computer is gone

Any 64-bit PC with ≥16GB RAM (32GB for the big AI model):
- **Same-size or larger disk:** Clonezilla restore (Scenario 2) works on different hardware. Ubuntu adapts at boot. Then Scenario 3 for the library.
- **Or rebuild clean, with no internet:**
  1. Install Ubuntu from the Ventoy stick (autoinstall). Mount the backup drive: `sudo mount LABEL=BACKUP-A /mnt`.
  2. `cp -a /mnt/offline/repo ~/homestead-server`. It has no `secrets.yml`; `bootstrap.sh` asks for the passwords again in step 6. When it asks for the borg passphrase, type the one from the recovery sheet.
  3. `sudo apt install /mnt/offline/debs/*.deb` installs Docker, Ansible, borg and the rest from the saved packages.
  4. Load the container images: `for f in /mnt/offline/images/*.tar.zst; do zstd -dc "$f" | sudo docker load; done`
  5. Restore /opt (NOMAD's install, app data, AI models) from borg, as root:
     `cd / && BORG_REPO=/mnt/borg borg extract ::system-<newest> opt`, then `sudo umount /mnt`.
  6. Prepare a new LIBRARY drive and restore it (Scenario 3), then `cd ~/homestead-server && sudo ./bootstrap.sh -e offline=true`.
  7. `sudo homestead-restore BACKUP-A mysql`, then `homestead-restore ... vault` if you use the vault.

## Scenario 5: bad edit to settings

`/etc` and the repo copy in `/opt/homestead/repo` are in every borg archive. `sudo ./bootstrap.sh` from the repo puts all managed configuration back the way the playbook defines it.

## Drill (do this before trusting it, then every 3 months)

1. Take a spare SSD or NVMe (or a USB enclosure with an old disk).
2. Restore the latest Clonezilla image onto it (Scenario 2, target = spare disk).
3. Swap it in, boot, and check: the kiosk comes up, the portal loads, Kiwix searches work, the AI answers, and `homestead-vault open` accepts the passphrase.
4. Restore one file from borg (Scenario 1).
5. Plug BACKUP-B into another computer and open a ZIM from `library/` in Kiwix desktop.
6. Write the date and result on the recovery sheet.

## Drive care

- Plug BACKUP-A in **weekly**. Rotate BACKUP-B **monthly**, and keep it away from the server (another building, or a Faraday container: a steel ammo can lined with cardboard, lid gasket scraped so metal touches metal).
- The portal shows "Last backup …". A desktop warning appears after 8 days without one.
- Replace any drive that the backup reports SMART warnings for.
