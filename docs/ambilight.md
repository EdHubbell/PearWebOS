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
| **HyperHDR** | TV | Turns each frame into 214 LED colors and sends them to the board over Wi-Fi (UDP) | At boot, by its loader service, which stops it on the screensaver and restarts it on wake |
| **WLED** | ESP32-S3 | Paints the strip with what HyperHDR sends; runs its own effects, chosen on its page, whenever nothing is streaming | Always: the board runs from the LED supply |
| **ambilightguard** | TV | At power-off stops HyperHDR cleanly and hands the strip back to WLED; on the screensaver does the hand-back; on wake starts HyperHDR again | At boot, by its own Homebrew hook (`./pear ambilight install`) |

**Effects when the TV is off.** The board's page, `http://192.168.8.248`
(or `http://wled-tv.local`), is WLED's own: pick an effect, colors, speed
and brightness, save presets. Four to start with (2026-11-03): 1 Warm
glow, 2 Candle, 3 Christmas, 4 Off. Preset 1 is applied when the board
boots. Choose with the TV off: HyperHDR's "restore original state" puts
the board back to the state it found when the stream began, so a preset
picked while the TV is on is undone at the next power-off or screensaver
(the guard's release turns the board on but does not pick a preset). The
WLED phone app talks to the same page.

**Sleep and wake.** HyperHDR's WLED driver locks the board "live" with no
timeout while it streams (WLED's own return-to-effect timer never runs),
and releases it when it stops cleanly. So the strip returns to its effect
only if HyperHDR stops cleanly, and even then there is a race: HyperHDR's
last UDP frame can land after its "live off" request, leaving the board
locked on a black frame. `ambilightguard` handles both:

- On the screensaver, and on "Screen Off" (picture off, sound on), the
  loader stops HyperHDR by itself (it watches the power state and stops
  HyperHDR on anything but "Active"); the guard waits for the process to
  go and tells WLED to leave realtime mode and be on
  (`{"live":false,"on":true}` to `/json/state`). The loader restarts
  HyperHDR on wake. A HyperHDR that ignores the loader for 5 s gets a
  `pkill -TERM -x hyperhdr` (never -9: stale socket), because a release
  while it still streams is undone by its next frame.
- At power-off nothing stops HyperHDR: the power state stays "Active" all
  through the power-off sequence ("Suspend" only arrives once the TV is
  asleep; measured 2026-10-31, `docs/ambilight-shutdown-handoff.md`), so the
  stream would just die mid-frame. The guard, on "Request Power Off", stops
  HyperHDR through the loader, waits, and releases the board. HyperHDR's
  "restore original state" is on, so its clean stop also puts WLED back to
  the effect that was showing (the state it saw when the stream began).
- On "Screen On" the guard asks the loader to start HyperHDR: the loader
  only restarts HyperHDR by itself after stops it made on its own, not
  after one requested through its API.

The guard is its own Homebrew startup hook, nothing of Pear's:
`./pear ambilight install`, `status`, `uninstall`. Source:
`tv/ambilightguard`, tests in `tests/test_ambilightguard.py` (run under
`dash`). Its log is `/var/lib/ambilightguard/ambilightguard.log`. Measured
2026-11-03: power-off to Warm glow in about a second, wake to tracking in
the TV's normal wake time, screensaver to Warm glow as the loader stops
HyperHDR, back to tracking about 5 s after a key press.

Since 2026-11-02 the board runs from the LED supply instead of the TV's
USB (see Wiring), so it keeps running through standby and serves its page
with the TV off. The brownout restarts that used to clear the strip as the
USB rail collapsed are gone with it.

**Board hung after a power cut (2026-10-31, under Hyperk).** Once, after
the strip was remounted and the TV had been off, the board came back dead:
no Wi-Fi, no setup access point, and HyperHDR logging "Could not detect
HyperSerial". Its console showed the ROM and bootloader run and the app
start, then nothing. Resets through EN changed nothing. Unplugging and
replugging the USB cable fixed it at once, config intact. So a brownout can
leave the board in a state that only a full power cycle clears. If the
board's page is gone and its LED is on: power-cycle it before anything
else.

**"LED device: off" in HyperHDR** almost always means "no input", not a
device fault: HyperHDR switches its LED device off whenever no source is
active (its log says "New priority[255]" then "LED device: disabled") and
back on when one appears ("New source available -> switch LED-Device on").
So when the strip sits on WLED's effect with HyperHDR running, look at who
is feeding it. The usual culprit (2026-11-02, many times) is PicCap after
a HyperHDR restart: PicCap keeps reporting `connected: true` on a socket
connection that died with the old HyperHDR, HyperHDR's `FLATBUFSERVER`
input never appears, and `grep -c hyperhdr-domain /proc/net/unix` on the TV
shows 1 (the listener alone) instead of 2. Fix: relaunch PicCap,
`kill -TERM $(pidof hyperion-webos)` and then any call such as
`luna-send -n 1 -f luna://org.webosbrew.piccap.service/status '{}'`, which
makes webOS start the service again; it reconnects within seconds and the
LED device comes on by itself. The guard's wake-time start of HyperHDR has
not needed this so far (the loader's restart path is the same one).

**After a wake or a board reboot** HyperHDR's "Maximum number of retries"
matters: it is the number of extra connection attempts, 2.5 s apart, after
a failed one (0 means give up at once; the maximum is 120, about five
minutes), and with any value above 0 a send failure, such as the board
rebooting mid-stream, reconnects on its own. 120 since 2026-11-02.

## Signal chain

```
PicCap (screen capture on the TV)
  → HyperHDR (on the TV, "wled" driver: UDP to 192.168.8.248, port 21324)
  → Wi-Fi → ESP32-S3 running WLED
  → GPIO 4 → 74AHCT125 level shifter → SK6812 RGBW strip
```

The TV's USB cable to the board carries nothing now. It sits in the
board's native "USB" port, where Task 2 of the WLED move left it; it can
stay (the DevKitC's diode keeps the supply out of the TV) or go. The TV
only sees a serial console from the board's COM port (see the end).

## Settings in this repo

`./pear ambilight pull` (Windows: `python3 pear ambilight pull`) copies the
live settings into `ambilight/` as sorted JSON, so `git diff` shows what
changed on the TV since the last pull:

- `ambilight/hyperhdr/global/*.json` and `instance-0/*.json`: one file per
  HyperHDR settings section, read from its SQLite database on the TV
  (`/home/root/.config/HyperHDR/db/hyperhdr.db`). Filled-in password fields
  are written as `<redacted>`; the table of login hashes and API tokens is
  never read.
- `ambilight/wled/cfg.json` and `presets.json`: the board's settings and
  presets from WLED's `/cfg.json` and `/presets.json`, Wi-Fi network names
  redacted (WLED never exports passwords, only their lengths). The board's
  address is `wled` in `.pear.json`, or found through HyperHDR's device
  discovery when it lists a `wled-*.local` host.
- `ambilight/piccap.json`: PicCap's `config.json`.
- `ambilight/hyperk.json`: the last config of the Hyperk firmware the board
  ran until 2026-11-03, kept for going back (see Firmware).

Pull only, for now. To put a setting back, change it in HyperHDR's web page
(its admin API needs the web login) or WLED's.

## Hardware

| Part | Choice |
|---|---|
| LEDs | SK6812 RGBW, 5 V, neutral white, 60/m |
| Layout | 3 sides (top, left, right), 214 LEDs as mounted, ~3.6 m |
| Controller | Hosyond ESP32-S3-WROOM-1 N16R8 (DevKitC-1 pinout) |
| Firmware | WLED 16.0.1, the `ESP32-S3_16MB_opi` build (Hyperk until 2026-11-03) |
| Level shifter | 74AHCT125 on a small PCB (replaced the TXS0108E on 2026-11-01; see `docs/ambilight-wiring-change-handoff.md`) |
| Power | 5 V, 15–18 A (e.g. Mean Well LRS-100-5), mounted top center |

TV size without stand: about 172 × 99 cm. Strip runs, inset ~5 cm:
top ~162 cm (~97 LEDs), each side ~89 cm (~53 LEDs).

## Wiring

**Data** enters at the bottom of the left side, runs up, across the top
(left to right) and down the right side. One data line. HyperHDR's layout
matches: 56 LEDs up the left, 102 across the top, 56 down the right (214,
as mounted on 2026-11-01; the bench layout was 60/100/60). WLED's LED
count is the same 214; the counts must agree or colors land in the wrong
place.

**ESP32-S3 to TV: Wi-Fi, not USB (since 2026-11-03).** The serial path
was tried with WLED and failed: the stock build listens for Adalight on
the S3's native "USB" port, which ignores baud rates, and WLED empties its
256-byte receive buffer a byte at a time, so with 214 LEDs the first ~56
tracked and the rest flickered rainbows at 16 fps (frames overflowing the
buffer). Over UDP each frame is one packet handled whole: 50 fps, clean
all round. The board's Wi-Fi signal is -22 dBm (the router is close); if
tracking ever stutters, look at Wi-Fi first. The COM port (CH343 bridge,
`/dev/ttyACM0` on the TV when a cable is in it) is free for the serial
console; the cable is in the native port today.

**ESP32-S3**
- Powered from the LED supply's 5 V into its 5V pin (since 2026-11-02),
  on its own wire pair straight from the supply terminals: shared with
  the strip's feed, the board's LED dims on every surge of strip current.
  The DevKitC's diode between the USB connector and the 5V pin is what
  keeps the supply out of the TV's port if the cable stays plugged in.
  GPIO 4 → shifter input. GND → common ground.
- Avoid GPIO 0, 3, 45, 46 (boot straps), 19/20 (USB), 26–37 (flash and
  octal PSRAM on N16R8), 43/44 (UART), 48 (onboard RGB LED).
- No longer needed now that the board is on the LED supply: the voltage
  supervisor on EN (MAX809S / TLV803S / APX803L-44, 4.4 V) that was going
  to keep a browning-out board from clearing the strip.
- The flicker seen on 2026-10-31 with the board on the LED supply was a
  loose ground jumper, not the dual supply: single pixels wrong then
  correcting themselves.

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
and leave a loop of slack at each joint. One more lesson from that night:
with the TV on its screensaver the loader has stopped HyperHDR, so a meter
on GPIO 4 reads an effect's data, not a 50 fps stream.

**Power**, from the supply at top center:
- One 5 V + GND pair of 22 AWG silicone to each top corner (~1 m each),
  each 5 V feed fused at 5 A at the supply. Sides are fed from their top
  corner only. The ground must go to the corners too, or the return current
  runs along the strip's own ground trace and shifts the data reference
  (flicker near the input at high brightness).
- 470–1000 µF / 10 V across 5 V and GND where power enters the strip, on
  the PCB, for the supply's turn-on inrush.
- Cap the current at about 4 A per corner (8 A total). Two pairs per corner
  only for uncapped full white. Two limiters overlap: HyperHDR's power
  limiter (Image Processing, Color Calibration, a percentage of full white)
  and WLED's "Maximum PSU Current" (8000 mA at 80 mA per LED), which also
  caps the effects; the lower one wins.
- Trim the supply to ~5.1–5.2 V to offset drop; never above 5.3 V.
- The LRS-100-5 has an audible coil whine at light load (2026-11-02: the
  strip at 30, 30, 30 plus the board, about 10 W). It faded under full red
  (about 21 W), so the idle load has to stay up, and a dark strip (the
  "Off" preset, or the board locked on black) makes it sing. Warm glow is
  amber at half brightness, about 15 W, quiet; Candle and Christmas were
  quiet too. A 10 Ω 5 W resistor across the output would do the same for
  the same electricity (2.6 W, about $4 a year) and give heat instead of
  light. If the whine stays at any load, it is the transformer itself.
- Corners: solder 5 V, GND and data jumpers between sections; check the
  arrows on the strip.
- Common ground: supply, strip, shifter and ESP32.

## Firmware: WLED

Flashed 2026-11-03 from https://install.wled.me in Chrome, over the
board's native "USB" port, build `WLED_16.0.1_ESP32-S3_16MB_opi.bin`
(16 MB flash, octal PSRAM); the installer joins it to Wi-Fi. Settings, all
on its page under Config (read back from `/cfg.json`; `./pear ambilight
pull` records them):

- LED Preferences: output 1 **SK6812/WS2814 RGBW**, GRB, start 0, length
  **214**, GPIO **4**; auto-calculate white from RGB **Accurate**; automatic
  brightness limiter on, **8000 mA**, per-LED **80 mA** (Custom); apply
  preset **1** at boot.
- Sync Interfaces: Realtime timeout 2500 ms (does not apply to HyperHDR's
  stream, which asks for no timeout), **Force max brightness on** so the
  TV's frames ignore the master slider (tracking brightness is set in
  HyperHDR, effects on the page); Receive UDP realtime on (HyperHDR's
  stream uses it, port 21324); serial baud 1500000 (unused).
- WiFi Setup: mDNS `wled-tv`.
- Presets (JSON API, `psave`): 1 Warm glow (solid 255,147,41 at 128),
  2 Candle (Candle Multi, 255,120,20 / 120,40,0 at 180), 3 Christmas
  (Chase 2, red / green at 160), 4 Off.

With auto-white Accurate a gray such as 60,60,60 becomes white-channel
only at a fifth of the load, which is why Warm glow is amber: the supply
whines below about 15 W (see Power).

WLED's JSON API, for scripts: `GET /json/info` (`live`, `lm`, `leds.fps`),
`GET /json/state`, `POST /json/state` with `{"ps":2}` (apply preset 2),
`{"bri":128}`, `{"live":false}` (leave realtime mode; the guard's call),
`{"psave":5,"n":"Name","ib":true,"sb":true}` (save the current state as
preset 5), `POST /json/cfg` with `{"def":{"ps":1}}` (boot preset).

**Going back to Hyperk.** Flash from Chrome at https://hyperk.hyperhdr.org
using the board's COM port, ESP32-S3 build; join Wi-Fi; LED type SK6812
RGBW, count 214, GPIO 4, driver SPI bitbang, serial 2000000; Light Preset
60,60,60 (Hyperk 0.0.5 ignores the preset brightness, and dims only
through the color values). The values are in `ambilight/hyperk.json`.
HyperHDR then goes back to the adalight driver: output `ttyACM0`, 2000000,
AWA protocol, ESP handshake and force detection all on (the device section
of commit c17ca40 has them), the TV cable on the board's COM port (Hyperk
0.0.5 does not answer on the native port, its issue #75), and the guard
would need its old job back (commit 0e0c966 has it). Hyperk's only idle
effects are Solid Color and Rainbow.

## HyperHDR (on the TV, http://<tv-ip>:8090)

LED Hardware, controller type **wled** (set 2026-11-03; adalight to the
board over USB before that):

- Host 192.168.8.248. HyperHDR reads the board's LED count, port and
  power limiter from `/json/info` at every start, warns about the limiter
  ("half-measure"; ignore) and streams UDP to the board's `udpport`.
- Override brightness ("brightnessMax") **off**: HyperHDR would otherwise
  set WLED's master slider to 255 at every stream start, and the effects
  would come back full bright.
- Restore original state **on**: a clean stop puts WLED back to the state
  HyperHDR found at stream start (the effect, its brightness).
- Maximum number of retries 120 (the maximum; set 2026-11-02, it was 0).
- Image Processing, Color Calibration, power limiter 60 % (Eddie's
  setting, 2026-11-03; it was 50).

HyperHDR's admin API needs a login the config call does not have from a
script ("No Authorization"); the device section was changed by stopping
HyperHDR through the loader, editing `settings` row `device` in its SQLite
database (`/usr/bin/sqlite3` exists on the TV, or edit a copy on the
laptop), and starting it again, then relaunching PicCap. Backups from the
2026-11-03 changes: `hyperhdr.db.bak-adalight`, `hyperhdr.db.bak-wledudp`
next to the database.

## Is it working?

1. The board's page answers at `http://192.168.8.248`. Nothing there means
   the board has no power or no Wi-Fi (its own `WLED-AP` access point
   appears when it cannot join).
2. `curl -s http://192.168.8.248/json/info`: with the TV on, `"live":true`,
   `"lm":"UDP"`, `"fps"` about 50 under `leds`. `live` false with the TV
   on = HyperHDR is not streaming: HyperHDR has no input, almost always
   PicCap stuck on a dead connection after a HyperHDR restart (see Sleep
   and wake). `live` true with `fps` 0 and the TV off = the board is stuck
   in realtime mode; `POST /json/state {"live":false}` frees it, and the
   guard should have done that (check its log).
3. HyperHDR Remote Control: set a solid color. Strip lights = HyperHDR →
   Wi-Fi → board → LEDs works. Solid color works but video doesn't = PicCap
   side. Single pixels wrong then correcting themselves while a solid color
   is up = a loose ground or data jumper, not software. The strip frozen on
   garbage that no color changes = the LEDs are not getting valid data or
   enough voltage; put a meter on the shifter's 5 V with the strip
   connected.
4. `./pear ambilight status`: the guard is running and knows the board.
   Press Power: the strip goes to the current effect within a second or
   two and stays there. Press Power again: tracking is back without
   touching anything.

All four passed on 2026-11-03.

Do not `kill -9` HyperHDR on the TV: it leaves `/tmp/hyperhdr-domain`
behind and every HyperHDR after that fails to bind it, so PicCap shows
`"connected": false` and the strip stops tracking. Stop and start it through
the loader (`luna://org.webosbrew.hyperhdr.loader.service/stop` and
`/start`); if it has happened, remove the socket file and restart.

HyperHDR can also come up wedged after a wake (seen 2026-11-02, twice,
under Hyperk): the process exists with only 3 threads, port 8090 is not
listening, PicCap shows `"connected": false`, and the loader's `stop` does
nothing. Fix: `kill -TERM $(pidof hyperhdr)`, wait for it to exit, remove
the socket file if it is still there, then the loader's `start`. Both
wedges happened while the board was rebooting as HyperHDR started.

## Debugging from the TV

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

The board's console is its COM port, if the TV cable is moved to it
(it is in the native port today): `stty -F
/dev/ttyACM0 115200 raw -echo` and `cat /dev/ttyACM0` shows the ESP32's
boot messages; the TV has Python 2.7, and the DTR/RTS reset the flasher
uses is two `TIOCMSET` ioctls (DTR off and RTS on for 0.25 s, then both
off), which resets the board without touching it. Do not `pkill -f` by a
pattern that is in your own command line: busybox matches the ssh shell
and kills the session.
