# DIY ambilight on the same TV

Notes for the ambient lighting that runs alongside Pear on the 2021 77" LG
OLED (C1). It uses no Pear code, but HyperHDR and PicCap share the TV with
Pear, and their settings live in this repo on the `ambilight` branch. The
first install of HyperHDR and PicCap exposed a Pear boot bug (fixed on main,
commit 5385ac7); the apps themselves were never the problem.

## Who does what

| | Runs on | Job | Starts |
|---|---|---|---|
| **PicCap** | TV | Grabs the picture 30 times a second and hands frames to HyperHDR over a local socket | At boot (its `autostart`) |
| **HyperHDR** | TV | Turns each frame into 200 LED colors and sends them out the USB port | At boot, by its loader service, which stops it when the TV sleeps and restarts it on wake |
| **Hyperk** | ESP32-S3 | Paints the strip with what HyperHDR sends | When the board has power |

**Lights on or off.** HyperHDR's web page, `http://<tv-ip>:8090`, Remote
Control, the "LED device" switch: off blanks the strip, on brings it back at
once. From the TV remote, the PicCap app's Stop and Start do the same and
also save TV CPU. The HyperHDR loader app on the TV never needs opening; its
Reboot button reboots the whole TV.

**Sleep and wake.** On the screensaver and on standby the loader stops
HyperHDR and starts a fresh one on wake, which reopens the serial port and
redoes the handshake within a minute. The board keeps USB power through the
screensaver but loses it in standby, reboots on wake, and is ready before
HyperHDR asks for it. No manual step is needed in either case (tested
2026-10-30).

## Signal chain

```
PicCap (screen capture on the TV)
  → HyperHDR (on the TV, Adalight driver, AWA protocol, 2 Mb)
  → TV USB → ESP32-S3 running Hyperk (HyperSerial on)
  → GPIO 4 → TXS0108E level shifter → SK6812 RGBW strip
```

## Settings in this repo

`./pear ambilight pull` (Windows: `python3 pear ambilight pull`) copies the
live settings into `ambilight/` as sorted JSON, so `git diff` shows what
changed on the TV since the last pull:

- `ambilight/hyperhdr/global/*.json` and `instance-0/*.json`: one file per
  HyperHDR settings section, read from its SQLite database on the TV
  (`/home/root/.config/HyperHDR/db/hyperhdr.db`). Filled-in password fields
  are written as `<redacted>`; the table of login hashes and API tokens is
  never read.
- `ambilight/hyperk.json`: the board's config from its web API, Wi-Fi name
  redacted. The board's address is found through HyperHDR's device
  discovery and remembered as `hyperk` in `.pear.json`.
- `ambilight/piccap.json`: PicCap's `config.json`.

Pull only, for now. To put a setting back, change it in HyperHDR's web page
(its admin API needs the web login) or Hyperk's.

## Hardware

| Part | Choice |
|---|---|
| LEDs | SK6812 RGBW, 5 V, neutral white, 60/m |
| Layout | 3 sides (top, left, right), about 200 LEDs, ~3.4 m |
| Controller | Hosyond ESP32-S3-WROOM-1 N16R8 (DevKitC-1 pinout) |
| Firmware | Hyperk (HyperSerialESP32 has no S3 build) |
| Level shifter | TXS0108E (a 74AHCT125 is the fallback if it glitches) |
| Power | 5 V, 15–18 A (e.g. Mean Well LRS-100-5), mounted top center |

TV size without stand: about 172 × 99 cm. Strip runs, inset ~5 cm:
top ~162 cm (~97 LEDs), each side ~89 cm (~53 LEDs).

## Wiring

**Data** enters at the bottom of the left side, runs up, across the top
(left to right) and down the right side. One data line. HyperHDR's layout
matches: 50 LEDs up the left, 100 across the top, 50 down the right.

**ESP32-S3 to TV: use the board's "COM" USB-C port**, the one behind the
CH343 bridge. It shows on the TV as `USB Single Serial`, `/dev/ttyACM0`,
on the TV's built-in `cdc_acm` driver. Hyperk 0.0.5 does not answer
HyperSerial on the native "USB" port: HyperHDR logs "Could not detect
HyperSerial..." then "Timeout writing data". That is Hyperk issue
[#75](https://github.com/awawa-dev/Hyperk/issues/75), a build-flag typo in
0.0.5 that left native USB serial off for the S3; a fixed beta was promised
on 2026-10-18. After reflashing a fixed build, either port should work.

**ESP32-S3**
- Powered from the TV's USB. GPIO 4 → shifter. GND → common ground. Leave
  the 5V pin unconnected so the LED supply never feeds the TV's USB port.
- Avoid GPIO 0, 3, 45, 46 (boot straps), 19/20 (USB), 26–37 (flash and
  octal PSRAM on N16R8), 43/44 (UART), 48 (onboard RGB LED).
- Hyperk issue #79 (S3 fails to boot after power loss with LEDs on GPIO 4)
  only affected a board flashed over WLED's OTA update. This board was
  flashed with the official installer, so it does not apply.

**TXS0108E**, mounted at the strip's data input, not by the ESP32:
- VCCA → ESP32 3V3; VCCB → 5 V; OE → VCCA; GND → common.
- A1 ← GPIO 4 (3.3 V signal run down the wire, twisted with a ground);
  B1 → strip DIN, a few cm. No series resistor (the TXS drive is weak).
- Unused A pins to GND. 0.1 µF on each supply pin.

**Power**, from the supply at top center:
- One pair of 22 AWG silicone to each top corner (~1 m each), each fused
  at 5 A. Sides are fed from their top corner only.
- Cap HyperHDR at about 4 A per corner (8 A total). Two pairs per corner
  only for uncapped full white.
- Trim the supply to ~5.1–5.2 V to offset drop; never above 5.3 V.
- Corners: solder 5 V, GND and data jumpers between sections; check the
  arrows on the strip.
- Common ground: supply, strip, shifter and ESP32.

## Firmware: Hyperk

1. Flash from Chrome or Edge at https://hyperk.hyperhdr.org, using the
   board's COM/UART port, ESP32-S3 build.
2. Join it to Wi-Fi and open its web page (`http://hyperk.local`).
3. LED type SK6812 RGBW (neutral), count 200, data pin GPIO 4, driver SPI
   bitbang (DMA) first (RMT can flood interrupts). Serial port speed
   2000000 under Network & Serial.

## HyperHDR (on the TV, http://<tv-ip>:8090)

LED Hardware, controller type **adalight** (set 2026-10-30; it was the
debug `file` output before, which is why nothing reached the board):

- Output path `ttyACM0`, baud 2000000
- High-speed serial AWA protocol with data integrity check: on
- ESP8266/ESP32/RP2040/RP2350 handshake: on
- Force HyperSerial detection: on
- RGB byte order rgb; RGBW dithering and white calibration off until the
  strip is wired and can be judged
- Maximum number of retries 0. The loader's restart on wake covers sleep;
  a small retry count would also cover a board hiccup mid-session.

## Is it working?

1. On the TV: `ls /dev/ttyACM*` after plugging the board in. No tty means
   the cable is in the wrong port or the board has no power.
2. HyperHDR Logs: `DETECTED DEVICE USING ... FIRMWARE (Hyperk HyperSerial
   interface ...)`.
3. Hyperk's Stats page (`http://hyperk.local/stats.html`): Color stream
   "Serial port", about 50 FPS. Its `/api/stats` says the same as JSON
   (`LIVE` 2).
4. HyperHDR Remote Control: set a solid color. Strip lights = HyperHDR →
   ESP32 → LEDs works. Solid color works but video doesn't = PicCap side.

Steps 1 to 3 passed on 2026-10-30 with the strip not yet wired.
