# Handoff: wiring change (TXS0108E → 74AHCT125, moving to a PCB)

From a planning conversation with Claude, for the Claude Code session on the
`ambilight` branch. Eddie has swapped the level shifter and is moving the
loose wiring onto a PCB. `docs/ambilight.md` still describes the TXS0108E;
update its Signal chain, Hardware table and Wiring sections to match this
once Eddie confirms the board is built as below.

## Outcome (2026-11-01)

Built as below, PCB and ESP32 together at the start of the strip (bottom
of the left side), so the data wire is short. `docs/ambilight.md` updated
(Signal chain, Hardware, Wiring, "Is it working?"). The LED count question
was already settled: 214 (56 / 102 / 56) in HyperHDR's layout and in
Hyperk. First power-up: the strip froze half white, half yellow and ignored
HyperHDR's colors while the board received the stream at 50 fps; the
AHCT's 5 V read 1 V with the strip connected. Bad solder joints on the PCB.
After the reflow the strip went black, red, green, blue on command and
tracks the screen. HyperHDR's "maximum number of retries" at 0 left the
LED device off after every power cycle of the board that day; raising it
is still Eddie's call.

## What changed

- **Level shifter:** 74AHCT125 replaces the TXS0108E. The TXS's weak
  auto-direction outputs were the risk on a long data wire; the AHCT is a
  proper 5 V driver and needs no 3.3 V supply.
- **Construction:** moving from point-to-point wiring to a PCB. Until now
  the system ran with **no resistors or capacitors at all**; the PCB is the
  chance to add the ones that are worth having (below).
- **Data pin:** stays **GPIO 4**. Decided after checking Hyperk issue #79
  (see "GPIO 4" below). If Eddie moves it for routing, use any of GPIO 1–18
  except 3 and change the data pin in Hyperk to match.

Unknown, ask Eddie: where the PCB is mounted (beside the ESP32 at the start
of the strip, or at top center with the power supply). It sets the data wire
length to the strip's input, bottom of the left side: short, or about 1.7 m.

## 74AHCT125 connections

| Pin | Connect to |
|---|---|
| 14 VCC | 5 V from the **LED supply**, 0.1 µF to GND right at the pin |
| 7 GND | Common ground |
| 1 1OE | GND (active low: gate 1 always on) |
| 2 1A | ESP32 GPIO 4, plus **10 kΩ to GND** |
| 3 1Y | **33–100 Ω**, then the strip's DIN |
| 4, 10, 13 (unused OE) | 5 V (disables the unused gates) |
| 5, 9, 12 (unused A) | GND |
| 6, 8, 11 (unused Y) | No connection |

Why each part:

- **0.1 µF at VCC:** supply decoupling against switching spikes. Without
  it: possible flicker or wrong colours starting at the first LEDs.
- **10 kΩ pulldown on 1A:** new. GPIO 4 floats while the ESP32 boots; the
  AHCT would turn that into junk on the data line, seen as random flashes
  on the first LEDs at power-on. Harmless to boot: GPIO 4 is not a strapping
  pin.
- **Series resistor at the chip's output (pin 3):** source termination,
  damps ringing on the wire to the strip. It belongs at the driver, on the
  PCB. (An earlier note said "near the strip input"; that was wrong.)
- **Unused gates tied off:** floating CMOS inputs can oscillate and add
  noise.
- No 3.3 V connection: AHCT inputs read 3.3 V as high at 5 V supply.
- Never connect the ESP32's 5V pin or the TV's USB 5 V to the LED supply's
  5 V. Grounds only are common.

## Power, as now decided

- Supply (Mean Well LRS-100-5) at top center. Each top corner gets a
  **5 V + GND pair** of 22 AWG silicone (~1 m each). GND must go to the
  corners too, not just one ground at the end: return current would
  otherwise run back along the strip's ground trace, dropping voltage at the
  far LEDs and shifting the data reference (flicker near the input at high
  brightness).
- **Fuses: 5 A per 5 V feed, at the supply** (blade-fuse block or holders
  on the PCB). The supply only current-limits around 20 A+, which would
  overheat 22 AWG or the strip on a short. These are the one protection
  that matters; HyperHDR's power limit does nothing for a short.
- **Bulk capacitor**, 470–1000 µF / 10 V across 5 V–GND where power enters
  the strip, on the PCB. Absorbs the inrush when the supply turns on.
- All grounds (supply, strip, AHCT, ESP32) meet at the supply's negative
  terminal; keep the GND jumpers at the corner solder joints.
- HyperHDR `powerLimit` is 0.5 (`ambilight/hyperhdr/instance-0/color.json`);
  aim for about 4 A per corner.

Optional on the PCB: a logic-level N-MOSFET (IRLB8721) in the strip's ground,
gate to the TV's USB 5 V through 100 Ω, 10 kΩ gate to GND, so the strip
loses power whenever the TV's USB does. `tv/ambilightguard` (commit 530f289)
already handles the power-off colour in software, so this is a backstop
only. Downside: with ground cut, the first LED can faintly glow through the
data line.

## GPIO 4: why it stays

Hyperk issue #79 ("ESP32-S3 will not boot after power loss if LEDs are
connected to GPIO4"): a XIAO ESP32-S3 with the strip wired straight to GPIO 4
(no shifter) would not boot after a full power loss. The maintainer traced
it to installing Hyperk by WLED OTA, which leaves WLED's bootloader and
partition table behind; a full flash with the official installer fixed it,
with the strip still on GPIO 4. This board was flashed with the official
installer. GPIO 4 is not an S3 strapping pin (those are 0, 3, 45, 46), and
behind the AHCT the pin only sees a high-impedance input and the pulldown.
https://github.com/awawa-dev/Hyperk/issues/79

## Layout and LED count: check against the strip

HyperHDR and Hyperk are set for 220 LEDs, 60 left / 100 top / 60 right
(commit 13a5dc9). At 60 LEDs/m that is 100 cm per side and 167 cm on top.
The TV is about 99 cm tall and 172 cm wide, so 60 per side can't physically
fit and 100 on top leaves under 3 cm inset per end. Recommended inset is
2–5 cm from the edge (hides the LEDs from off-axis seats, softer halo). Ask
Eddie for the real cut counts and make HyperHDR's layout, `ledConfig`, and
Hyperk's `numLeds` match them exactly; a mismatch puts colours in the wrong
place on screen.

## Debugging after the swap

| Symptom | Look at |
|---|---|
| Nothing lights | AHCT pin 1 really at GND (OE is active low), pin 14 has 5 V, common ground, Hyperk stats show "Serial port" ~50 FPS |
| Random flash on first LEDs at power-on | 10 kΩ pulldown on pin 2 missing |
| Flicker or wrong colours from the first LED onward | 0.1 µF at pin 14, series resistor at pin 3, data wire twisted with GND if long |
| Flicker only at high brightness | Ground not run to the corners; voltage drop on the strip ground |
| Far ends dim or warm-tinted on white | Voltage drop: corner pairs, trim supply to 5.1–5.2 V (never above 5.3) |
| Colours in the wrong place | LED count / layout mismatch (see above) |
| Board fails to boot with the strip connected | Not GPIO 4 per se; check it was flashed with the official installer (issue #79) |
| A corner section dark | Corner solder joint or fuse on that feed |

Ask Eddie before rebooting the TV, changing HyperHDR or PicCap settings, or
reflashing the board.
