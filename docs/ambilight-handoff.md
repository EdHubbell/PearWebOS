# Handoff: TV ambilight + PearWebOS crosstalk

Context from a planning conversation with Claude, for a Claude Code session.
Eddie is building a DIY ambilight on his rooted LG TV, and installing
HyperHDR + PicCap for it stopped his custom Home (PearWebOS) from appearing.

## The TV

- LG OLED77C1 (2021, 77"), webOS 6, rooted with Homebrew Channel, SSH on.
- Size without stand: ~172 × 99 × 5.6 cm (67.8 × 39.1 × 2.2").
- Runs Eddie's fork of PearWebOS: https://github.com/EdHubbell/PearWebOS
  (Apple TV style Home that bind-mounts patched QML over LG Home).

## Ambilight design (decided)

**Signal chain**

```
PicCap (screen capture, on TV)
  → HyperHDR (on TV, Adalight driver)
  → TV USB → ESP32-S3 running Hyperk (HyperSerial)
  → GPIO 4 → TXS0108E level shifter → SK6812 RGBW strip
```

**Parts**

| Part | Choice |
|---|---|
| LEDs | SK6812 RGBW, 5 V, neutral white (~4000K), 60 LEDs/m |
| Layout | 3 sides (top + left + right), ~200 LEDs, ~3.4 m |
| Runs | top ~162 cm (~97 LEDs), each side ~89 cm (~53 LEDs), ~5 cm inset |
| Controller | Hosyond ESP32-S3-WROOM-1 N16R8 (ESP32-S3-DevKitC-1 pinout, two USB-C) |
| Firmware | Hyperk, not HyperSerialESP32 (HyperSerialESP32 has no S3 build) |
| Level shifter | TXS0108E (Eddie's choice; 74AHCT125 is the fallback if it glitches) |
| Power | 5 V 15–18 A (e.g. Mean Well LRS-100-5), mounted top center |
| Wire | 22 AWG silicone |

**Why these choices**
- 5 V, not 12 V: 12 V SK6812 groups 3 LEDs per pixel.
- 60/m: ~8 ms per frame on one data line at 200 LEDs; no multi-segment needed.
- Worst case at full white is ~12–16 A; the supply is oversized on purpose,
  so fuse every feed.

**Data path**
- Data enters at the bottom of the left side, runs up, across the top
  left-to-right, and down the right side. One data line.
- Starting data at a corner would need HyperSerial-style two-segment mode;
  rejected as needless complexity.

**ESP32-S3 (Hosyond N16R8)**
- Powered from the TV's USB via the native "USB"/"OTG" port (GPIO 19/20),
  which enumerates as `/dev/ttyACM0` and needs `cdc_acm` in the TV kernel.
  The "COM"/"UART" port goes through a CH343 bridge; use it for flashing.
- Data on GPIO 4. GND to common ground. Leave the board's 5V pin unconnected
  (keeps the LED supply from back-feeding the TV's USB port).
- Avoid: GPIO 0, 3, 45, 46 (strapping), 19/20 (native USB), 26–32 (flash),
  33–37 (octal PSRAM on N16R8), 43/44 (UART0), 48 (onboard RGB LED).

**TXS0108E** (mount it at the strip's data input, not by the ESP32)
- VCCA → ESP32 3V3; VCCB → 5 V; OE → VCCA (active high); GND → common.
- A1 ← GPIO 4. Run the 3.3 V signal down the ~0.8 m wire, twisted with a
  ground, plus a 3V3/GND pair for VCCA.
- B1 → strip DIN, a few cm. No series resistor (TXS drive is weak).
- Unused A pins to GND. 0.1 µF on each supply pin.
- Why at the strip: the TXS0108E uses weak auto-direction outputs and
  misbehaves driving long wires. If it still glitches, swap in a 74AHCT125:
  VCC (pin 14) 5 V with 0.1 µF, GND pin 7, 1OE (pin 1) GND, 1A (pin 2) ←
  GPIO, 1Y (pin 3) → 33–100 Ω → DIN; unused OE to 5 V, unused A to GND,
  unused Y open. It needs no 3.3 V supply.

**Power distribution**
- Supply at top center. One pair of 22 AWG to each top corner (~1 m each),
  each fused at 5 A. Sides are fed from their top corner only; the top is fed
  from both ends.
- Voltage drop, one pair: ~0.8 V at 7.5 A full white, ~0.42 V at 4 A.
- Cap HyperHDR at ~4 A per corner (8 A total). Use two pairs per corner only
  for uncapped full white.
- Trim the supply to ~5.1–5.2 V; never above 5.3 V (SK6812 max at idle).
- Corners: solder 5 V, GND and data jumpers between sections; follow the
  strip's arrows.
- The shifter needs 5 V at the bottom: run a thin 5 V/GND pair, or tap the
  strip's start pad. Strip GND, shifter GND, ESP32 GND and supply GND all tie
  together.

**Hyperk setup**
1. Flash from Chrome/Edge at https://hyperk.hyperhdr.org (COM port,
   ESP32-S3 build).
2. Join Wi-Fi, open the board's web page.
3. SK6812 RGBW neutral, ~200 LEDs, data GPIO 4, driver SPI bitbang (DMA)
   first (RMT can flood interrupts), enable HyperSerial.
4. Wi-Fi mode is a fallback if the TV's USB serial driver is a problem.

**HyperHDR (Adalight driver), at http://<tv-ip>:8090**
- Port `/dev/ttyACM0`, baud 2000000
- High-speed AWA protocol with data integrity check: on
- ESP8266/ESP32/RP2040/RP2350 handshake: on
- Force HyperSerial detection: on
- Layout: 3 sides, starting bottom of left side, clockwise
- Current limit per the power notes

**Bring-up checks**
1. On the TV: `dmesg | tail -20`, `ls /dev/ttyACM* /dev/ttyUSB*`. A USB
   device with no tty means a missing kernel module.
2. HyperHDR System → Log: detected a HyperSerial device.
3. HyperHDR Remote Control: solid colour lights the strip.
4. PicCap shows connected to 127.0.0.1; HyperHDR live preview mirrors the
   screen. Solid colour works but video doesn't = PicCap side.

## PearWebOS crosstalk (in progress)

Symptom: after installing HyperHDR + PicCap, the TV shows LG's Home, not Pear.

Work so far is on branch `ambilight-debug`, PR:
https://github.com/EdHubbell/PearWebOS/pull/1 (not yet tested on the TV).

**Leading hypothesis:** `tv/pearwebos boot` cold-starts LG Home with Pear
mounted, then waited ~38 s for the app manager's CRIU snapshot. A late
snapshot (busy boot with HyperHDR/PicCap starting, or low memory) was
treated as a Pear failure: back to stock, and `touch
/var/lib/pearwebos/disabled`, which keeps Pear off at every later boot.

**What the branch changes**
- Late/missing snapshot with Home still running keeps Pear; next boot
  rebuilds it. Boot waits up to 90 s.
- Real failure (Home died with Pear mounted) is appended to
  `/var/lib/pearwebos/failed`; boot retries until 3 in a row. `disabled` now
  only means `pear off`. `pear on` clears both.
- Failure log lines include free memory and running HyperHDR/PicCap.
- `pear status` reports which state Pear is in.
- New `./pear doctor`: read-only report (logs, init.d hooks, mounts over
  Home, foreground app, memory, OOM kills, USB serial), saved to
  `.cache/doctor.txt`.
- Added `CLAUDE.md` (repo guide, safe vs. ask-first commands) and
  `docs/ambilight.md`.
- Verified: `dash -n` on the scripts, and a stubbed simulation of boot
  outcomes. Not run on real hardware.

**Next steps**
1. `git checkout ambilight-debug`, then `./pear doctor`. Look in
   `pearwebos.log` for "Home did not stay up with Pear; back to stock" and
   for a `disabled` file: both mean the latch fired.
2. `./pear sync` (installs fixed scripts), then `./pear on` (clears the latch).
3. Ask Eddie before rebooting the TV. After reboot, wait ~2 min, run
   `./pear doctor` again. Expect "boot: Pear Home up" or "no snapshot after
   90s; keeping Pear".
4. If that isn't it, other suspects:
   - PicCap autostart launching its app into the foreground, so Home is
     covered and `open_home` is skipped (check doctor's foreground section
     and init.d hooks).
   - OOM kills of `com.webos.app.home` with HyperHDR + PicCap + Pear
     together (doctor's dmesg and biggest-processes sections).
   - Another mount over LG Home's QML.
   - A later init.d hook restarting the app manager or Home.
5. Once confirmed, merge the PR.

**Ground rules (also in the repo's CLAUDE.md)**
- `tv/` scripts are busybox `sh`: POSIX only, check with `dash -n`.
- Edit in the repo and push with `./pear sync`, not on the TV.
- Ask Eddie before: `pear uninstall`, rebooting the TV, touching other
  apps' init.d hooks, changing HyperHDR/PicCap settings, or anything near
  firmware updates or the read-only system partition.
