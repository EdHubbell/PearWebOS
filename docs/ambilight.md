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
| **HyperHDR** | TV | Turns each frame into 214 LED colors and sends them out the USB port | At boot, by its loader service, which stops it on the screensaver and restarts it on wake |
| **Hyperk** | ESP32-S3 | Paints the strip with what HyperHDR sends; shows its own idle color 6.5 s after the stream stops | When the board has power |
| **ambilightguard** | TV | At power-off, has HyperHDR show Hyperk's idle color before the board loses USB power | At boot, by its own Homebrew hook (`./pear ambilight install`) |

**Lights on or off.** HyperHDR's web page, `http://<tv-ip>:8090`, Remote
Control, the "LED device" switch: off blanks the strip, on brings it back at
once. From the TV remote, the PicCap app's Stop and Start do the same and
also save TV CPU. The HyperHDR loader app on the TV never needs opening; its
Reboot button reboots the whole TV.

**Sleep and wake.** On the screensaver the loader stops HyperHDR (it
watches the power state and stops HyperHDR on anything but "Active"), and
starts a fresh one on wake. The board keeps USB power through the
screensaver, so 6.5 s after the stream ends Hyperk shows its own idle color.

Standby is different, and it is why the strip used to freeze on the last
picture (measured 2026-10-31, see `docs/ambilight-shutdown-handoff.md`):

- The power state stays "Active" all through the power-off sequence; the
  "Suspend" state only arrives once the TV is already asleep. So the loader
  never stops HyperHDR at power-off and no black frame is sent.
- The TV cuts the board's USB power about 6 s after the Power press. Hyperk's
  6.5 s idle timer never fires, and SK6812s hold their last frame.

`ambilightguard` closes that gap: it watches the power state and, on
"Request Power Off", tells the still-running HyperHDR to show Hyperk's idle
color (read from the board over Wi-Fi, last value cached). HyperHDR keeps
sending it until the power goes, so the strip holds the idle color. One
color is set in one place, Hyperk's web page. The guard is its own
Homebrew startup hook, nothing of Pear's: `./pear ambilight install`,
`status`, `uninstall`. Source: `tv/ambilightguard`, tests in
`tests/test_ambilightguard.py` (run under `dash`).

Still open: as the USB power dies the ESP32 browns out and sometimes
restarts on the collapsing rail far enough to clear the strip, so the held
color is lost on some power-offs and kept on others. The fix is a voltage
supervisor on EN (see Wiring) and a 10 kΩ pull-down on DIN. Feeding the
board 5 V from the LED supply also cures it, but on this board the strip
flickered with both supplies connected.

**Board hung after a power cut (2026-10-31).** Once, after the strip was
remounted and the TV had been off, the board came back dead: no Wi-Fi, no
`Hyperk-Setup` access point, and HyperHDR logging "Could not detect
HyperSerial". Its console showed the ROM and bootloader run and the app
start, then nothing. Resets through EN (HyperHDR's handshake does one on
every open, and five more by hand) changed nothing, with or without the
data wire on GPIO 4. Unplugging and replugging the USB cable fixed it at
once, config intact. So the brownout can leave the board in a state that
only a full power cycle clears, which is one more reason for the
supervisor on EN. If `hyperk.local` is gone and the board's LED is on:
replug its USB before anything else, then turn HyperHDR's LED device back
on (Remote Control, or `./pear ambilight status` to check).

**After a wake** HyperHDR starts before the board has finished booting. With
"Maximum number of retries" at 0 one failed open switches the LED device off
for good; HyperHDR's Remote Control (or `componentstate` over JSON-RPC) turns
it back on. A retry count of about 10 would cover this.

## Signal chain

```
PicCap (screen capture on the TV)
  → HyperHDR (on the TV, Adalight driver, AWA protocol, 2 Mb)
  → TV USB → ESP32-S3 running Hyperk (HyperSerial on)
  → GPIO 4 → 74AHCT125 level shifter → SK6812 RGBW strip
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
| Layout | 3 sides (top, left, right), 214 LEDs as mounted, ~3.6 m |
| Controller | Hosyond ESP32-S3-WROOM-1 N16R8 (DevKitC-1 pinout) |
| Firmware | Hyperk (HyperSerialESP32 has no S3 build) |
| Level shifter | 74AHCT125 on a small PCB (replaced the TXS0108E on 2026-11-01; see `docs/ambilight-wiring-change-handoff.md`) |
| Power | 5 V, 15–18 A (e.g. Mean Well LRS-100-5), mounted top center |

TV size without stand: about 172 × 99 cm. Strip runs, inset ~5 cm:
top ~162 cm (~97 LEDs), each side ~89 cm (~53 LEDs).

## Wiring

**Data** enters at the bottom of the left side, runs up, across the top
(left to right) and down the right side. One data line. HyperHDR's layout
matches: 56 LEDs up the left, 102 across the top, 56 down the right (214,
as mounted on 2026-11-01; the bench layout was 60/100/60). Hyperk's
`numLeds` is the same 214; the three counts must agree or colors land in
the wrong place.

**ESP32-S3 to TV: use the board's "COM" USB-C port**, the one behind the
CH343 bridge. It shows on the TV as `USB Single Serial`, `/dev/ttyACM0`,
on the TV's built-in `cdc_acm` driver. Hyperk 0.0.5 does not answer
HyperSerial on the native "USB" port: HyperHDR logs "Could not detect
HyperSerial..." then "Timeout writing data". That is Hyperk issue
[#75](https://github.com/awawa-dev/Hyperk/issues/75), a build-flag typo in
0.0.5 that left native USB serial off for the S3; a fixed beta was promised
on 2026-10-18. After reflashing a fixed build, either port should work.

**ESP32-S3**
- Powered from the TV's USB. GPIO 4 → shifter input. GND → common ground.
  Leave the 5V pin unconnected so the LED supply never feeds the TV's USB
  port.
- Avoid GPIO 0, 3, 45, 46 (boot straps), 19/20 (USB), 26–37 (flash and
  octal PSRAM on N16R8), 43/44 (UART), 48 (onboard RGB LED).
- Planned: a voltage supervisor on EN so the board cannot restart as the
  USB power dies and clear the strip (see Sleep and wake). MAX809S, TLV803S
  or APX803L-44 (4.4 V threshold; not the 4.63 V parts, a loaded USB port
  can sit near 4.75 V): VDD to the 5V pin, GND to ground, RESET to EN,
  100 nF across VDD/GND. The board's 10 kΩ pull-up on EN suits the
  open-drain output. The 10 kΩ pull-down on the shifter's input (below)
  already makes a floating GPIO 4 read as "no data".
- Powering the board from the LED supply's 5 V with the USB cable still in
  made the strip flicker (2026-10-31); reverted. A loose ground jumper gives
  the same symptom, single pixels wrong then correcting themselves.
- Hyperk issue #79 (S3 fails to boot after power loss with LEDs on GPIO 4)
  only affected a board flashed over WLED's OTA update. This board was
  flashed with the official installer, so it does not apply.

**74AHCT125** on the PCB, which sits with the ESP32 at the start of the
strip (one gate used; it reads the ESP32's 3.3 V as high and drives the
strip at 5 V, so it needs no 3.3 V supply):

| Pin | Connect to |
|---|---|
| 14 VCC | 5 V from the LED supply, 0.1 µF to GND at the pin |
| 7 GND | Common ground |
| 1 1OE | GND (active low: gate 1 always on) |
| 2 1A | ESP32 GPIO 4, plus 10 kΩ to GND (GPIO 4 floats while the ESP32 boots) |
| 3 1Y | 33–100 Ω in series, then the strip's DIN |
| 4, 10, 13 (unused OE) | 5 V |
| 5, 9, 12 (unused A) | GND |
| 6, 8, 11 (unused Y) | No connection |

The series resistor sits at the chip, not at the strip: it is source
termination for the wire. If the data wire to the strip is long, twist it
with a ground. The TXS0108E it replaced auto-senses direction and drives
weakly, which is a poor match for a long data line.

First power-up of the PCB (2026-11-01): the strip froze half white, half
yellow and ignored every color HyperHDR sent, while the board reported the
stream at 50 fps. Pin 14 to pin 7 read 1 V with the strip connected and
4.5 V without: bad solder joints on the PCB were carrying the strip's
current through a path that could not, and at 1 V the LEDs cannot decode
data, so they held garbage. Reflowing the joints fixed it. The first
measurement to make when the strip ignores data is the 5 V at pin 14 with
the strip connected.

The joints kept failing one after another (2026-11-02) because the PCB
was wired with breadboard jumper wire, whose strands do not wet with
solder. Use tinned 22 to 24 AWG stranded hookup wire, tin the end first,
and leave a loop of slack at each joint. Two more lessons from that night:
with the TV on its screensaver the loader has stopped HyperHDR, so a meter
on GPIO 4 reads about 50 mV (the board idling at 4 fps), not the 0.4 V of a
50 fps stream; and after any power cycle of the board HyperHDR's LED device
is off until someone turns it on (retry count 0).

**Power**, from the supply at top center:
- One 5 V + GND pair of 22 AWG silicone to each top corner (~1 m each),
  each 5 V feed fused at 5 A at the supply. Sides are fed from their top
  corner only. The ground must go to the corners too, or the return current
  runs along the strip's own ground trace and shifts the data reference
  (flicker near the input at high brightness).
- 470–1000 µF / 10 V across 5 V and GND where power enters the strip, on
  the PCB, for the supply's turn-on inrush.
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
3. LED type SK6812 RGBW (neutral), count 220, data pin GPIO 4, driver SPI
   bitbang (DMA) first (RMT can flood interrupts). Serial port speed
   2000000 under Network & Serial.
4. The idle color (`r`, `g`, `b` in its config) is what the strip shows
   whenever no stream is coming in, and what `ambilightguard` hands the
   strip at power-off. Set it once here for a holiday color; `./pear
   ambilight pull` records it in `ambilight/hyperk.json`.

## HyperHDR (on the TV, http://<tv-ip>:8090)

LED Hardware, controller type **adalight** (set 2026-10-30; it was the
debug `file` output before, which is why nothing reached the board):

- Output path `ttyACM0`, baud 2000000
- High-speed serial AWA protocol with data integrity check: on
- ESP8266/ESP32/RP2040/RP2350 handshake: on
- Force HyperSerial detection: on
- RGB byte order rgb; RGBW dithering and white calibration off until the
  strip is wired and can be judged
- Maximum number of retries 0. Too low: after a wake HyperHDR opens the
  port before the board has finished booting, fails once and leaves the
  LED device off (seen 2026-10-31). About 10 would cover it. Until then,
  Remote Control → LED device on, or `./pear ambilight status` to check.

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
   Single pixels wrong then correcting themselves while a solid color is
   up = a loose ground or data jumper, not software. The whole strip
   sitting on Hyperk's idle color (orange here) = the data path works but
   nothing is being sent: HyperHDR's LED device is off, almost always
   after the board was power-cycled with the retry count at 0 (switch it
   on in Remote Control). The strip frozen on garbage that no color
   changes = the LEDs are not getting valid data or enough voltage; put a
   meter on the shifter's 5 V with the strip connected.
5. `./pear ambilight status`: the guard is running and knows the idle
   color. Press Power: the strip turns that color at once and keeps it
   after the board's LED goes out.

Steps 1 to 3 passed on 2026-10-30 with the strip not yet wired; 4 and 5 on
2026-10-31 with the strip on the bench.

Do not `kill -9` HyperHDR on the TV: it leaves `/tmp/hyperhdr-domain`
behind and every HyperHDR after that fails to bind it, so PicCap shows
`"connected": false` and the strip stops tracking. Stop and start it through
the loader (`luna://org.webosbrew.hyperhdr.loader.service/stop` and
`/start`); if it has happened, remove the socket file and restart.

## Debugging the board from the TV

The loader gives HyperHDR no log file. To read its log, stop it through
the loader and run the same binary in the foreground for half a minute:

```sh
L=/var/lib/pearwebos/luna-send-n   # Pear's wrapper; the count goes after -n
S=/media/developer/apps/usr/palm/services/org.webosbrew.hyperhdr.loader.service/hyperhdr
$L -n 1 luna://org.webosbrew.hyperhdr.loader.service/stop '{}'
LD_LIBRARY_PATH=$S HOME=/home/root $S/hyperhdr > /tmp/hhdr.log 2>&1 &
sleep 25; kill $!; sleep 3
$L -n 1 luna://org.webosbrew.hyperhdr.loader.service/start '{}'
grep -a LEDDEVICE /tmp/hhdr.log
```

The board's console is the same port. With HyperHDR stopped, `stty -F
/dev/ttyACM0 115200 raw -echo` and `cat /dev/ttyACM0` shows the ESP32's
boot messages; the TV has Python 2.7, and the DTR/RTS reset the flasher
uses is two `TIOCMSET` ioctls (DTR off and RTS on for 0.25 s, then both
off), which resets the board without touching it. Always put the speed
back (`stty -F /dev/ttyACM0 2000000`) and restart HyperHDR through the
loader afterwards. Do not `pkill -f` by a pattern that is in your own
command line: busybox matches the ssh shell and kills the session.
