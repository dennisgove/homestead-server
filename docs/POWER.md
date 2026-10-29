# Off-grid power for the server

## Load

The OptiPlex 3060 Micro with an i7-8700T (35W TDP) draws roughly:
- idle: 12–18 W (measure yours with a Kill-A-Watt or the SmartShunt and write it here: ____ W)
- normal use: ~20 W average including the USB library drive
- AI answering: 45–65 W while generating
- monitor: 10–25 W more (a small 12V monitor is worth it)

**Plan on about 0.5 kWh/day** for the server and a small monitor in typical use.

## Suggested system

| Part | Size | Why |
|---|---|---|
| Battery | 12V 100Ah LiFePO4 (1.28 kWh) | 2–3 days with no sun; 3000+ cycles; safe indoors |
| Solar | 200–400 W panels | ~0.8–1.6 kWh/day in winter sun (4 peak hours) |
| Charge controller | Victron SmartSolar MPPT 100/20 or 100/30 | efficient; VE.Direct port |
| Battery monitor | Victron SmartShunt 500A | accurate state of charge for the shutdown logic |
| PC supply | 12V→19.5V DC-DC boost converter, ≥90 W, Dell 4.5mm barrel (center pin needed for Dell ID) | skips inverter losses (15–20%) |
| Fusing | Fuse at the battery for every circuit; size it to the wire | fire safety |

Double the battery for a whole household (lights, radios, phone charging).

## How the server uses it

- `homestead-power` reads the Victron over `/dev/victron` every 20s. Values are in `/etc/homestead/power.conf` (from `group_vars/all/settings.yml`).
  - SOC ≤ 35% → **eco**: the AI (Ask page) and Kolibri stop
  - SOC ≥ 45% → back to normal
  - SOC ≤ 15% for 3 readings → clean shutdown
  - MPPT-only setups (no SOC) use voltage: eco 12.9 V, shutdown 12.4 V. LiFePO4 voltage is flat, so a SmartShunt is better.
- BIOS **AC Recovery = Power On** restarts it when power is restored.
- `homestead-powertune` applies powertop's tunings at boot but keeps USB autosuspend off. The library drive and radios don't tolerate it.

## Test it

```bash
echo 30 | sudo tee /etc/homestead/power-override   # eco mode within ~20s; portal shows it
echo 60 | sudo tee /etc/homestead/power-override   # back to normal
sudo rm /etc/homestead/power-override
journalctl -u homestead-power -f
```
(Don't test 14% unless you want it to shut down.)

## UPS instead of / in addition

For a USB UPS: `sudo apt install nut`, set `MODE=standalone` and configure `upsmon` to shut down at low battery. The homestead-power service can run alongside it.
