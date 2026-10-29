# Comms

The server is a radio workstation: **receive** weather and news, **send** email over radio (Winlink), keyboard-to-keyboard chat (JS8Call/Fldigi), and run **MeshCore** LoRa text messaging for family and neighbors. Transmitting on ham bands needs a license (Technician for VHF/UHF, General for most HF). Listening and MeshCore (license-free ISM band) don't.

## Web radio receiver (OpenWebRX+)

http://homestead.local:7020 (or **Radio receiver** on the website's Tools page): a radio receiver in the browser, for anyone on the WiFi. Pick a band from the profile list (NOAA weather, 2m/70cm ham repeaters, APRS, FRS/GMRS, marine, airband, FM, aircraft ADS-B map, shortwave and 40m/80m ham), then click a signal in the waterfall or a bookmark. Several people can listen at once, to different signals inside the band on screen.

Settings (bands, gain, bookmarks, background decoders): the gear icon, then the admin web password, then OpenWebRX's own login, user `dennis`, password from `sudo cat /etc/homestead/openwebrx-admin`.

It holds the dongle while it runs. The desktop radio apps below take the dongle when you start them (the web receiver goes offline) and give it back about 15 seconds after you close them. `homestead-sdr status` shows who has it.

The band is shared: if someone switches to FM, it stays on FM for everyone. Once nobody has the page open for about 5 minutes, it goes back to NOAA by itself.

## NOAA weather radio (RTL-SDR)

Plug in the RTL-SDR and put the antenna up high, by a window at least.
```bash
noaa-weather          # scans the 7 NOAA channels, plays the strongest
noaa-weather 1        # WX1 162.550 MHz
```
There's also a desktop launcher. **GQRX** gives a full scanner/receiver GUI (local public-safety, aircraft, marine, FM broadcast, shortwave with an upconverter).

Weather satellites: **SatDump** decodes Meteor-M LRPT images (137 MHz, needs a V-dipole or QFH antenna). The NOAA APT satellites were retired in 2025. `rtl_433` reads nearby wireless weather stations and sensors.

## Winlink email over radio (Pat)

1. Get a callsign and register it at winlink.org **while online**: `pat` → account / or use the web UI.
2. `pat configure` (as dennis): set `mycall`, `locator` (Maidenhead grid), `secure_login_password`, and your radio's Hamlib rig.
3. `sudo systemctl start pat-http`. The web UI is on admin port **7091**.
4. Transports: `telnet` (internet, for testing), `ardop`/`vara` over HF, `ax25`/packet over VHF via Direwolf.
5. Download the RMS gateway list **while online**: `pat rmslist -s` and save it. Print the nearby gateways for the binder.

## JS8Call / Fldigi

- **Digirig**: one USB cable gives a sound card plus CAT/PTT. It shows up as `/dev/serial/by-id/usb-Silicon_Labs_CP2102...` and as the "USB Audio" sound device.
- **JS8Call**: weak-signal keyboard chat that can store and forward messages through other stations. A good grid-down network tool.
- **Fldigi + Flmsg**: PSK/Olivia/MT63, and ICS-213 forms for ARES/RACES nets.
- **Direwolf**: APRS and packet TNC (`direwolf -c ~/direwolf.conf`).
- Program radios with CHIRP (download the chirp-next wheel while online into `/srv/core/share/radio` and `pipx install` it).

## MeshCore (LoRa mesh text)

- Nodes: Heltec V3, RAK4631, LilyGo T-Deck, and similar. Flash **companion** firmware for handhelds paired to phones, **repeater** firmware for hilltop or roof relays, and **room server** firmware for a neighborhood bulletin board.
- **Flash while online** from the MeshCore web flasher, and save the firmware .bin files for every board you own into `/srv/core/share/meshcore/`. Offline flashing: `esptool.py --chip esp32s3 write_flash 0x0 firmware.bin` (ESP32 boards). nRF boards (RAK) take a UF2 file drag-and-drop.
- On the server: `meshcore-cli -s /dev/ttyUSB0 infos` (companion node on USB). MeshCore Web (port 7017) gives a chat UI in the browser via Web Serial or Bluetooth. It needs Chrome or Edge (Firefox and Safari can't talk to radios). On the server's screen use the **MeshCore radio** launcher, which opens it in Chrome; from a laptop with Chrome, use https://homestead.local:7017. Meshtastic nodes: the **Meshtastic radio** launcher, or https://homestead.local:7018.
- Phones: install the MeshCore app APK from the website's Tools page (downloads).
- Decide family channel names and keys now and write them on the recovery sheet.

## Plan to print

- Family comms plan: who calls whom, on what, when (for example: MeshCore channel "family", check-ins at 08:00 and 20:00; ham simplex frequency; rally points).
- Local repeaters, NOAA frequency for your county, nearby Winlink gateways, ARES net times.
