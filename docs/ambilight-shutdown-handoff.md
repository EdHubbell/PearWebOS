# Handoff: strip stays lit after the TV turns off

From a planning conversation with Claude, for the Claude Code session on this
branch. Written before anything was tried on the TV; the outcome is below,
the plan as handed over follows it.

## Outcome (2026-10-31)

Measured with a power-state logger on the TV and a poller on the board:

- The power state stays `"Active"` through the whole power-off sequence
  (`processing` goes "Request Power Off" → "Request Active Standby" →
  "Prepare Suspend" over 3 s); `"Suspend"` is only reported after the TV is
  asleep. The loader keys on `state` alone, so it never stopped HyperHDR at
  power-off: no black frames, no goodbye. On the screensaver it does.
- The board's USB power is cut 6 to 10 s after the Power press.
- Hyperk falls back to its idle color 6.5 s after the stream ends (README;
  confirmed by stopping HyperHDR through the loader). That is longer than
  the window, so the step 2 plan (send black, or any frame, then wait for
  the idle color) could not win either.
- HyperHDR's `color` command at priority 1 with a `duration` takes 8 ms and
  keeps the stream at 45 fps, so the strip ends up holding that color.

Built: `tv/ambilightguard` (own Homebrew hook, `./pear ambilight install`),
which on "Request Power Off" sends Hyperk's idle color through the running
HyperHDR. The strip turns orange within a fraction of a second of the Power
press. Remaining hardware issue: the ESP32 sometimes restarts on the dying
USB rail far enough to clear the strip; a voltage supervisor on EN is the
fix (`docs/ambilight.md`, Wiring). The step 3 relay is not needed: the
idle color must stay on, so the strip's supply stays on.

PR #1 was closed and its branch deleted before this handoff.

## The problem

When the TV goes to standby the strip keeps showing the last colours it was
sent. The strip has its own 5 V supply, and SK6812s hold their last frame, so
something has to send black before the board loses power.

What we know (docs/ambilight.md, "Who does what" and "Sleep and wake"):

- On standby PicCap stops capturing (its `nopowerstate` is `false`, so it
  watches the power state) and HyperHDR's loader stops HyperHDR.
- The ESP32-S3 is powered from the TV's USB and loses power in standby, but
  Eddie sees it stay powered for a few seconds after PicCap stops.
- So the gap is a final black frame: HyperHDR is stopped, not asked to
  blank, and nothing else talks to the board.
- Hyperk's idle colour was set to black (`r`/`g`/`b` 0 in
  `ambilight/hyperk.json`, commit 13a5dc9). Unknown: whether Hyperk falls back
  to that colour when the serial stream stops, and how fast.
- Hyperk's core is closed source (github.com/awawa-dev/Hyperk-Backend ships a
  binary library), so adding a timeout to the firmware isn't an option.
  HyperSerialESP32 is open (MIT) but has no ESP32-S3 support.

Rejected: a hold-up capacitor on the board. Keeping the ESP32 alive longer
doesn't help when nothing is sending, and a large cap on the TV's USB 5 V
causes inrush. A relay or MOSFET switching the LED supply from the TV's USB
5 V would work and is the hardware fallback (see the end), but Eddie wants a
software fix first.

## Plan, in order

### 1. Measure the window and test Hyperk's own fallback

Read-only; tell Eddie before putting the TV in standby.

- Over SSH, log power events with timestamps while Eddie presses Power:
  ```sh
  luna-send -i luna://com.webos.service.tvpower/power/getPowerState '{"subscribe":true}' |
    while read -r l; do echo "$(date +%T.%N | cut -c1-12) $l"; done
  ```
  In a second session, `dmesg -w | grep -i -e usb -e acm` to see when the
  board drops off. That gap is the time available. Note which state names
  appear first (expected: a `processing` field such as "Request Active
  Standby", then `state` "Active Standby" or "Suspend").
- With the TV on and a colour showing, stop HyperHDR's output without
  sending black (e.g. stop PicCap from its app, or kill HyperHDR) and watch
  the strip: if it fades to Hyperk's black idle colour, note the delay. If
  the delay is shorter than the window, this is solved: done. Also check
  Hyperk's web page (`http://hyperk.local`) for a stream-timeout or relay
  setting.

### 2. If not: a TV-side shutdown hook that sends black itself

Preferred over asking HyperHDR to blank (its JSON-RPC `componentstate`
`LEDDEVICE` false), because the loader is stopping HyperHDR on the same
power event and that would be a race.

Design, as `tv/ambilightguard`, modelled on `tv/homeguard` (busybox `sh`,
POSIX only, check with `dash -n`):

- Subscribe to `com.webos.service.tvpower/power/getPowerState`, re-subscribe
  if the bus drops (same loop shape as homeguard).
- On the first power-off event, write a prebuilt all-black frame straight to
  the serial port, several times over ~2 s so one lands after HyperHDR has
  closed the port:
  ```sh
  stty -F /dev/ttyACM0 2000000 raw -echo 2>/dev/null
  for i in 1 2 3 4 5; do cat "$DIR/ambilight-black.bin" > /dev/ttyACM0; usleep 400000; done
  ```
  Frames interleaved with a dying HyperHDR fail the AWA checksum and are
  dropped by the board, which is why it repeats.
- Do nothing on wake: HyperHDR restarts and takes the port back.
- Log to `$DIR/ambilightguard.log` like homeguard.

The black frame:

- Build it on the laptop in Python (e.g. `installer/ambilight.py`), not in
  sh, and push it with the other TV files (see `build_and_push` in `pear`).
- Format is HyperHDR's Adalight AWA frame for 220 LEDs. Take the exact
  header, byte layout and Fletcher checksums from HyperHDR's source rather
  than from memory (find the Adalight driver under `sources/led-drivers` in
  github.com/awawa-dev/HyperHDR and search for "Awa"): "Awa" vs "AwA" depends on white-channel calibration (off in
  `ambilight/hyperhdr/instance-0/device.json`), and the trailer checksums
  must match what Hyperk verifies. Add a test in `tests/test_ambilight.py`
  that checks the frame against a capture if one can be made, or at least
  its length and header.
- Count comes from `numLeds` in `ambilight/hyperk.json` (220); read it
  there rather than hardcoding.
- Hyperk's handshake: HyperHDR does one at connect ("espHandshake": true).
  Check in step 1 whether the board accepts bare frames without it; if not,
  the hook must replay it.

Start it from the same boot path as homeguard (`pearwebos boot` / `on`),
gated by a setting in `pear.conf` so Pear users without an ambilight don't
get it.

Test: TV on with a bright colour, Power off, strip goes black before the
board loses power. Repeat with the screensaver (board keeps power there, so
nothing should break).

### 3. Hardware fallback

If the window is too short or the board won't take frames, switch the LED
supply from the TV's USB 5 V: a 5 V relay module (10 A, 250 VAC, mechanical,
not a small SSR, because of the Mean Well's inrush) in the live wire of the
supply's AC input, coil fed from a TV USB port. Or a logic-level N-MOSFET
(e.g. IRLB8721) in the strip's ground, gate to USB 5 V through 100 Ω with
10 kΩ to ground. Confirm USB power drops in every off state, including Quick
Start+.

## Housekeeping

- PR #1 (`ambilight-debug`, the boot "latch" fix and `pear doctor`) predates
  the boot fix on main (5385ac7). Check whether any of it is still wanted;
  otherwise it can be closed. Ask Eddie.
- Ask Eddie before rebooting the TV, changing HyperHDR/PicCap settings or
  hooks, or adding a new startup hook.
