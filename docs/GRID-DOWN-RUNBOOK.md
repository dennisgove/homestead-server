# Grid-down runbook

**Print this.** Short version first.

## When the internet/grid goes down

1. **Switch to grid-down mode** (dennis, in a terminal or over SSH on ethernet):
   ```bash
   sudo homestead-mode griddown
   ```
   The WiFi becomes the **HOMESTEAD-LIBRARY** hotspot, phones that join get the library page automatically, and updates pause.
2. Tape up the **WiFi sign** (`/srv/core/share/print/wifi-sign.html`, also in the binder).
3. Check the status strip on the portal: battery, full library online, last backup.
4. Plug in BACKUP-A once (fresh backup), then put it back in its safe place.

## Daily

- Look at the battery % on the portal. Below 35% the AI and videos pause automatically. Below 15% the server shuts itself down and starts again when the battery recovers (BIOS AC Recovery). With the DC-DC converter it starts as soon as voltage comes back.
- Run heavy AI planning sessions in the **middle of the day**, when solar is producing.
- Weekly: plug in BACKUP-A.

## Power budget (12V, see POWER.md)

| State | Draw | 100Ah LiFePO4 lasts |
|---|---|---|
| Idle, screen off | ~12–18 W | 3–4 days |
| Normal use, screen on | ~20–30 W | ~2 days |
| AI answering | 45–65 W | (bursts only) |

Turning the monitor off saves 10–20W. Phones and laptops on the hotspot cost the server almost nothing.

## Who can do what

| Person | Account | Can |
|---|---|---|
| Anyone at the keyboard | `guest` (auto-login; password on the sign) | Library, AI, maps, notes, pantry, office apps, radio apps, USB sticks, shut down |
| Anyone on the WiFi | (browser) | Same web apps; AI needs an approved account |
| dennis | `dennis` | Everything: Library manager (http://library.lan:7090), vault, Winlink, `sudo` |
| Break-glass | `root` | Console login with the sealed password |

## Common problems

| Problem | Fix |
|---|---|
| Portal says "Full library drive missing" | Re-seat the LIBRARY USB cable; it comes back automatically. The essentials keep working without it. |
| AI doesn't answer | Battery-saving mode? (portal says so). Otherwise: `docker compose -f /opt/homestead/compose.yaml restart ollama open-webui` |
| Phones can't see the WiFi | `sudo homestead-mode status`; then `sudo homestead-mode griddown` again. Range is about one house. For more, plug a 12V travel router into the ethernet port. |
| Phone joins but no page opens | Browse to `http://library.lan` (or `http://10.42.0.1`) |
| Screen black | Move the mouse. The power button gives a shutdown menu, so don't hold it down. |
| Won't boot | RESTORE.md, Scenario 2 |
| Forgot a password | Recovery sheet. root can reset others: `passwd dennis` |

## When the grid comes back

```bash
sudo homestead-mode gridup
sudo apt update && sudo apt upgrade        # then reboot
sudo systemctl start homestead-fetch-plan homestead-fetch   # refresh content (or: Library manager → Updates)
```
