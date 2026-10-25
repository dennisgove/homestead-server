# SDR antenna setup (listening)

A roof antenna for NOAA weather radio and the rest of VHF/UHF, with lightning protection, plus optional extra dongles. From the basement the RTL-SDR hears almost nothing; this gets the antenna up and outside.

## Shopping list

| # | Qty | Item | Why this one | Link |
|---|---|---|---|---|
| 1 | **1** | **Comet DS-150S discone** | Covers NOAA and everything else on VHF/UHF (2m/70cm, GMRS, aircraft, marine). Comes with **65 ft RG-58 coax** (PL-259 both ends) and mast hardware. | https://www.amazon.com/Comet-Monitoring-Stainless-Directional-Installation/dp/B08FLYL4J5 |
| 2 | **1** | **Proxicast ANT-233-002 lightning arrestor** | SO-239 on both ends, rated 0–3 GHz (covers all the SDR bands), grounding lug, under 0.2 dB loss. | https://www.amazon.com/Proxicast-Lightning-Arrester-Suppressor-Connectors/dp/B0CBW6J6YW |
| 3 | **1** | **3 ft PL-259 jumper** (arrestor to server) | Joins the arrestor to the pigtail below. | https://www.amazon.com/Antenna-Jumper-Coaxial-Connector-Analyzer/dp/B086T2LBFQ |
| 4 | **1** | **Bingfu SMA male to SO-239 pigtail** (2 ft RG-58) | Connects the jumper's PL-259 plug to the V4's SMA socket. A flexible pigtail puts no strain on the dongle's socket, unlike a rigid adapter. | https://www.amazon.com/Bingfu-Antenna-Adapter-Handheld-Receiver/dp/B08BDHHDQD |
| 5 | **2** (optional) | **RTL-SDR Blog V4 with dipole antenna kit**, one per extra dongle | The same dongle as the first. The kit's antennas are enough for nearby 433/915 MHz sensors or a window-mounted ADS-B antenna. | https://www.amazon.com/RTL-SDR-Blog-RTL2832U-Software-Defined/dp/B0CD7558GT |
| 6 | **1** (optional) | **Sabrent HB-UMP3 powered USB hub**, only if you add dongles | Each dongle draws real power, so a powered hub keeps them stable. Per-port switches turn a dongle off without unplugging it. | https://www.amazon.com/sabrent-individual-switches-included-hb-ump3/dp/b00tpmeoym |

Two extra dongles gives the full setup: the one you have for the web receiver, one for home sensors, one for ADS-B or a second band. Skip items 5 and 6 for NOAA alone.

**Also needed, from a hardware store:**

| Qty | Item |
|---|---|
| 1 | #10 AWG (or thicker) bare or green copper ground wire, long enough to reach the house ground rod from where the coax enters |
| 1 | Ground rod clamp (acorn clamp), for the wire at the rod |
| 1 roll | Self-amalgamating (self-fusing) tape, to seal the coax connector at the antenna |
| as needed | Coax clips or UV-rated cable ties, to secure the 65 ft cable on the way down |

The dongle on its own, without antennas: https://www.amazon.com/RTL-SDR-Blog-RTL2832U-Software-Defined/dp/B0CD745394. One listing showed it as currently unavailable. Buy from the **RTL-SDR Blog** seller; there are knock-off "SDR-V4" listings.

Check the connector types and what's in the box on each listing before ordering, and buy from Amazon or the brand rather than third-party sellers. These details came from the listings' search snippets (Oct 2026).

## How to connect it

```
 ROOF / ATTIC                      OUTSIDE WALL                      BASEMENT
 Comet DS-150S ──65 ft coax──▶ [Proxicast arrestor] ──3 ft PL-259 jumper──▶ [SO-239→SMA pigtail] ──▶ RTL-SDR V4 ──USB──▶ server
  (SO-239)      (PL-259 both ends)    │ ground lug                                                        (or the powered hub)
                                      └──#10 copper wire──▶ house electrical ground rod
```

1. **Mount the discone** as high as you can, on a roof mast or chimney mount, or in the attic as a second choice. Keep it clear of metal gutters and wires. Seal the coax connector at the antenna with self-amalgamating tape.
2. **Run the 65 ft cable** down and to the point where it enters the house, with a drip loop: a small downward U before it goes in, so water runs off.
3. **Put the arrestor where the coax enters** (outside, or just inside the wall). Antenna cable in, jumper out.
4. **Ground the arrestor:** run heavy copper wire (#10 AWG or thicker) from its lug to the house's **electrical ground rod**, as short and straight as possible. If you add a separate ground rod, bond it to the house ground. An unbonded rod is a shock hazard.
5. **Inside:** jumper, then the pigtail (its SO-239 end takes the jumper's PL-259 plug), then the pigtail's SMA end onto the dongle. Hand-tighten the SMA only.
6. **During thunderstorms,** unplug the coax from the dongle. The arrestor helps, but a direct strike will get through anything.

## Extra dongles

Plug them into the powered hub, which goes into the server. A second dongle's dipole kit antenna can sit on a basement window sill for nearby 433/915 MHz sensors. ADS-B wants its own small antenna outside as well. Splitting the discone between dongles costs signal, so give each dongle its own antenna where you can. Each new dongle then needs adding to OpenWebRX+ and `rtl_433`.

## Checking it works

Open http://homestead.local:7020 on the NOAA band. Lines in the waterfall at 162.4–162.55 MHz mean you're receiving. From the basement before the antenna (Oct 2026), all 7 NOAA channels were within 0.4 dB of the noise floor; compare against that.

## Sources

[Comet DS-150S](https://www.amazon.com/Comet-Monitoring-Stainless-Directional-Installation/dp/B08FLYL4J5) · [Proxicast arrestor](https://www.amazon.com/Proxicast-Lightning-Arrester-Suppressor-Connectors/dp/B0CBW6J6YW) · [RFAdapter PL-259 jumper](https://www.amazon.com/Antenna-Jumper-Coaxial-Connector-Analyzer/dp/B086T2LBFQ) · [Bingfu pigtail](https://www.amazon.com/Bingfu-Antenna-Adapter-Handheld-Receiver/dp/B08BDHHDQD) · [RTL-SDR Blog V4 kit](https://www.amazon.com/RTL-SDR-Blog-RTL2832U-Software-Defined/dp/B0CD7558GT) · [RTL-SDR Blog V4 dongle only](https://www.amazon.com/RTL-SDR-Blog-RTL2832U-Software-Defined/dp/B0CD745394) · [Sabrent HB-UMP3](https://www.amazon.com/sabrent-individual-switches-included-hb-ump3/dp/b00tpmeoym)
