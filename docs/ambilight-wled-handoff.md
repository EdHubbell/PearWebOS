# Design: WLED on the board, effects when the TV is off

Written 2026-11-03 from a planning conversation with Eddie, then built the
same day. The outcome is first; the design as approved follows it. Plan:
`docs/superpowers/plans/2026-11-03-ambilight-wled.md`.

## Outcome (2026-11-03)

- WLED 16.0.1 is on the board, configured as below, with the four
  presets; the supply is quiet on all three lit ones.
- **USB did not survive contact with the hardware.** The stock build's
  Adalight over the native USB port gave 16 fps with the first ~56 LEDs
  tracking and the rest flickering rainbows: WLED empties a 256-byte
  receive buffer a byte at a time and the frames overflowed it. The
  custom-build fallback would hit the same buffer. HyperHDR now streams
  UDP to the board (its "wled" driver), 50 fps, clean all round. The TV's
  USB cable carries nothing.
- **The guard was not retired.** HyperHDR's WLED driver locks the board
  "live" with no timeout, so WLED's 2.5 s return-to-effect timer never
  runs, and at power-off the TV died mid-stream with the strip locked on
  black (and the supply whining at the dark strip). Even a clean HyperHDR
  stop leaves the lock set when its last UDP frame lands after its "live
  off" request. `tv/ambilightguard` now stops HyperHDR through the loader
  on "Request Power Off" and sends `{"live":false}` to the board once the
  process is gone; does the same release on the screensaver; and starts
  HyperHDR on "Screen On", because the loader only restarts HyperHDR by
  itself after its own stops. HyperHDR's "restore original state" is on.
- Measured: power-off to Warm glow in about a second, tracking back on
  wake with nothing touched, screensaver to Warm glow and back to
  tracking ~5 s after a key press.
- `pear ambilight pull` exports `ambilight/wled/cfg.json` and
  `presets.json` (network names redacted); `ambilight/hyperk.json` is kept
  for going back; `.pear.json` key `wled` holds the board's address.
- Warm glow is amber (255,147,41 at 128) rather than a gray: with
  auto-white Accurate a gray becomes white-channel only at a fifth of the
  load, below the supply's whine threshold.

## Intent

The ESP32-S3 now runs from the LED supply, so it is on around the clock.
When the TV is off the strip should do something worth looking at, chosen
by whoever is in the room: a warm candle flicker on a winter night, red
and green chases in December, a plain glow the rest of the year. Choosing
happens on a page the board serves itself at its own address
(192.168.8.248 / its mDNS name), from a phone or laptop on the Wi-Fi.
When the TV comes on, the strip tracks the screen as it does now; when the
TV sleeps, it goes back to the chosen effect by itself.

Hyperk 0.0.5 cannot do this. Its idle options are Solid Color and
Rainbow, and its core is a closed binary, so nothing can be added to it.
WLED does all of it as stock behavior, so the board moves to WLED.

## Goals

- Pick an effect, its colors, speed and brightness on the board's own
  page, with a handful of ready-made presets (candle, Christmas, plain
  warm glow, off) on the front of it.
- The TV takes over automatically when HyperHDR streams, and the effect
  comes back by itself within a few seconds of the stream stopping.
- Tracking quality stays what it is today: 214 LEDs at HyperHDR's 50 Hz
  smoothing without visible stutter.
- The LED supply stays quiet: the Mean Well LRS-100-5 whines below about
  15 W of load, so the idle effects must draw at least that. A black
  "off" preset is the one exception and is accepted as noisy.
- Reversible: Hyperk's image and `ambilight/hyperk.json` can put the
  board back the way it was.

## Non-goals

- Choosing effects from the TV remote, Pear's Home, or a schedule. The
  board's page (and WLED's phone app, which talks to the same page) is
  the only control surface for now. WLED has timers if a schedule is
  wanted later; nothing in this design blocks it.
- Any change to PicCap, the HyperHDR loader, Pear, or the level shifter.
- Preserving HyperHDR's RGBW white calibration. Eddie says white is
  mostly there for the tracking look; WLED's own white handling is good
  enough and gets tuned by eye.
- A custom WLED build as the starting point. The stock release binary
  is the target; a custom build is the sanctioned fallback (see "If the
  stock build cannot keep up" below), not a non-goal.

## Anti-goals (what would make this a failure)

- Tracking that stutters or tears where it did not before.
- A strip that freezes on the last TV frame at power-off again.
- A board that needs the TV awake to serve its page.
- Losing the ability to go back to Hyperk.

## Constraints and facts the builder needs

**Hardware (unchanged).** Hosyond ESP32-S3-WROOM-1 N16R8 (DevKitC-1
pinout, 16 MB flash, 8 MB octal PSRAM), two USB-C ports: "COM" (CH343
bridge to UART0) and "USB" (the S3's native USB). Data out on GPIO 4 into
a 74AHCT125 on the PCB, then 214 SK6812 RGBW (56 left, 102 top, 56
right, data entering bottom-left). Board powered from the LED supply's
5 V into its 5V pin; the DevKitC's diode keeps that off the TV's USB.
See `docs/ambilight.md` for the rest.

**WLED release.** v16.0.1 (2026-07-07). The asset for this board is
`WLED_16.0.1_ESP32-S3_16MB_opi.bin` (environment `esp32s3dev_16MB_opi`:
`esp32-s3-devkitc-1`, `qio_opi` memory, 16 MB).

**Which USB port the TV plugs into changes.** That build is compiled
with `ARDUINO_USB_CDC_ON_BOOT=1` (confirmed in WLED's `platformio.ini`;
the UART0 variant is a commented-out line). So WLED's `Serial`, which is
where it listens for Adalight, is the S3's *native* USB, the port marked
"USB" on the board, not the CH343 "COM" port Hyperk used. The TV's cable
moves from COM to USB. Consequences:

- The TV sees an Espressif CDC device (303a:1001) instead of the CH343
  (1a86:55d3). It should still enumerate as `/dev/ttyACM0` through the
  same `cdc_acm` driver, but confirm with `dmesg` on the TV and update
  HyperHDR's output path if the name differs.
- Baud rate is meaningless on native CDC (it is a USB bulk pipe, not a
  UART), so WLED's serial baud setting and HyperHDR's rate only need to
  match on paper. Set both to 1500000, WLED's maximum, to be safe.
- The native CDC port can reset the chip or drop it into the ROM
  bootloader if a host toggles DTR/RTS in the download pattern. HyperHDR
  does not do that, but it is the first thing to suspect if the board
  reboots when HyperHDR opens the port. A fallback exists: a custom build
  with `ARDUINO_USB_CDC_ON_BOOT=0` puts `Serial` back on the COM port.
- The serial-console debugging recipe in `docs/ambilight.md` (ROM
  messages at 115200 on the CH343, DTR/RTS reset from the TV) now needs
  the COM port, which will be free; it still works from a laptop.

**Flashing.** WLED's web installer at https://install.wled.me flashes
the S3 over the "USB" port from Chrome on the laptop, and asks for the
Wi-Fi credentials in the same flow. Eddie does the flash (it is his
board and his Wi-Fi password); the plan tells him exactly which binary
and port. The Hyperk factory image is available from
github.com/awawa-dev/Hyperk for going back.

**Adalight in WLED.** Serial settings live under Config, Sync
Interfaces, Serial: baud rate 115200 to 1500000 (default 115200, "only
sufficient for about 50-100 LEDs"). Adalight and tpm2 are accepted on
`Serial`. Realtime timeout (Sync Interfaces, Realtime) is 1 to 65000 ms:
"Time after which to resume normal mode once a stream has stopped". The
design uses 2500 ms. Realtime streams are subject to the brightness
limiter. **"Force max brightness" (Sync Interfaces, Realtime) is on**, so
the TV's frames ignore WLED's master slider and arrive at the level
HyperHDR sets (its own brightness and the 50 % power limiter). The
slider then only shapes the effects, and each preset stores its own
slider value, so picking Candle sets Candle's brightness. Eddie's
decision 2026-11-03: tracking always at full strength; he has never used
the "lights off while watching" trick and it is dropped from the docs.

**HyperHDR side.** `ambilight/hyperhdr/instance-0/device.json` goes from
Hyperk's checksummed AWA frames to classic Adalight: `awa_mode` false,
`espHandshake` false, `forceSerialDetection` false, `rate` 1500000,
`output` whatever the TV names the new port. `white_channel_calibration`
stays false. HyperHDR's power limiter (Image Processing, Color
Calibration, 50 %) stays as the cap for tracking.

**White channel.** HyperHDR's classic Adalight sends RGB. WLED's LED
output is set to SK6812 RGBW with "Auto-calculate white channel from
RGB" on ("Accurate" is the usual choice; try "Dual" if whites look dim).
Tune by eye against a known white scene.

**If the stock build cannot keep up.** Two failure modes only show up
after the flash: WLED drains the native USB receive buffer once per main
loop while `show()` on 214 RGBW LEDs holds that loop for several ms, so
dropped bytes and skipped frames at 50 Hz are possible; and the S3's
USB-Serial-JTAG peripheral resets the chip in hardware on the DTR/RTS
download pattern, which no setting fixes. Tracking parity outranks
"stock binary". If step 2 shows stutter or resets, the next step is a
PlatformIO build of `esp32s3dev_16MB_opi` with
`ARDUINO_USB_CDC_ON_BOOT=0`, which puts `Serial` back on the CH343 COM
port (a real UART at 1500000, the cable stays where it is today). The
build flags go in the repo under `ambilight/wled/` so it can be rebuilt.
Lowering HyperHDR's update rate below 50 is not an acceptable fix.

**Idle load for the supply.** 214 LEDs at 3 channels, 20 mA each: a
preset averaging about 60/255 per channel across the strip draws ~15 W
and is quiet. Candle and twinkle effects dip below that in their dark
phases; set their brightness so the *average* stays up, and if the
supply still sings, raise it. Coil whine follows the instantaneous load,
so a candle whose dark moments dip under the threshold will whine in
time with the flicker. If a candle bright enough at its dimmest no
longer reads as a candle, the escalation is the 10 Ω 5 W resistor
across the supply output that `docs/ambilight.md` already costs out
(2.6 W, about $4 a year), fitted by Eddie; dropping the effect is the
last resort. Tune first.

**WLED's own current limiter.** LED Preferences, "Maximum PSU Current"
(mA) with 80 mA per LED for SK6812 RGBW full white. Set 8000 mA to match
the "8 A total until the corner feeds are in" rule in `docs/ambilight.md`.
This caps effects *and* realtime, so HyperHDR's 50 % and WLED's 8 A
overlap; that is fine, the lower wins.

## What changes in the repo

- **`tv/ambilightguard`, its hook, `tests/test_ambilightguard.py`, and
  `pear ambilight install|uninstall|status`: retired.** The guard existed
  because the board lost USB power 6 s after the Power press and Hyperk
  needed 6.5 s to fall back. With the board on the supply and WLED's
  timeout at 2.5 s, the strip returns to the effect on its own. `pear
  ambilight uninstall` runs once on the TV to remove the hook and
  `/var/lib/ambilightguard` before the code goes. (Ground rule: Eddie
  says when.)
- **`pear ambilight pull`** keeps exporting HyperHDR and PicCap and
  replaces the Hyperk export with WLED's: `GET http://<board>/cfg.json`
  (settings) and `GET http://<board>/presets.json` (presets) into
  `ambilight/wled/`. Wi-Fi name and password are redacted as
  `hyperk.json` was (`installer/ambilight.py`, `redact`). The board's
  address comes from `.pear.json` key `wled` (or still `hyperk`; pick
  one and migrate), since HyperHDR's discovery no longer names it.
- **`ambilight/hyperk.json`** stays in the repo as the record for going
  back; the docs say so.
- **`installer/ambilight.py`**: `hyperk_for_repo` and `hyperk_address`
  become their WLED equivalents or go; tests follow.
- **`ambilight/hyperhdr/instance-0/device.json`**: the Adalight change
  above, pulled from the TV after it is set in HyperHDR's page.
- **`docs/ambilight.md`**: the "Who does what" table (Hyperk row becomes
  WLED, ambilightguard row goes), "Sleep and wake", the Firmware section
  (WLED setup checklist replaces the Hyperk one), the USB port change,
  and the serial-console recipe's port. The "lights on or off" section
  (HyperHDR's LED switch, PicCap Stop from the remote) goes. Keep the
  Hyperk notes in a short "Going back to Hyperk" section rather than
  deleting them.
- **Memory** (`ambilight-shutdown.md`, `ambilight-serial-link.md` in
  Claude's project memory) updated to say WLED, native USB port, no
  guard.

## Order of work

1. Flash and configure WLED with the TV cable unplugged; bring the page
   up; set LEDs (SK6812 RGBW, 214, GPIO 4, auto-white), the current
   limiter, serial 1500000, realtime timeout 2500; make the presets;
   check the supply is quiet on each. The strip can be verified from the
   page alone.
2. Move the TV's cable to the "USB" port; confirm the device name on the
   TV; change HyperHDR's Adalight settings; confirm tracking, fps and
   stutter over an evening of normal viewing.
3. Power-off test: press Power, the strip should hold the last frame for
   about 2.5 s then show the effect. Screensaver test: same.
4. Retire the guard on the TV, then in the repo. Update `pear ambilight
   pull`, docs, memory. Commit when Eddie says.

## Calls I made (Eddie can overturn any of these)

- Native USB port for the TV cable, stock binary, rather than a custom
  build that keeps the COM port. Reason: stock stays upgradeable from
  WLED's own page.
- 2.5 s realtime timeout. Short enough that a power-off looks deliberate,
  long enough that HyperHDR's occasional slow frame does not flash the
  effect.
- Custom build allowed as a fallback, not as a starting point. Tracking
  parity is what Eddie asked about when weighing the swap; the stock
  binary was my preference for upgradability.
- Dummy-load resistor is the sanctioned escalation for a whining
  candle, after tuning. Eddie already weighed its cost.
- Retire the guard outright instead of adapting it to WLED's API. With
  "Force max brightness" on, nothing needs setting from the TV: the
  board shows the current preset at the preset's own brightness whenever
  the stream stops. Eddie asked whether a TV-side script could set the
  slider at shutdown; it could, through WLED's JSON API
  (`POST http://<board>/json/state {"ps": <preset id>}` applies a
  preset, `{"bri": 128}` sets the slider), and the guard's power-event
  loop is the natural host if a different preset per TV event (power-off
  versus screensaver) is ever wanted. That is a later, small job; the
  docs keep the recipe. Not building it now.
- Keep `ambilight/hyperk.json` and the Hyperk docs as a "going back"
  record rather than deleting history that took days to learn.
- Preset list to start: Candle, Christmas (red/green chase), Warm glow
  (solid, about 60/255 each channel), Off. Eddie adds the rest from the
  page.

## Open questions for Eddie

- None blocking. The flash itself is his to do; the plan gives the
  binary name, port and settings step by step.

## Ground rules

Ask Eddie before: reflashing the board, moving the TV's cable, changing
HyperHDR settings, running `pear ambilight uninstall`, rebooting the TV.
`tv/` scripts (if any remain) are busybox `sh`, POSIX only. Edit in the
repo and push with `./pear sync`, not on the TV.
