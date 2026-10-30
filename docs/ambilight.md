# DIY ambilight on the same TV

Notes for the ambient lighting that runs alongside Pear on the 2021 77" LG
OLED (C1). It doesn't use any Pear code, but HyperHDR and PicCap share the TV
with Pear, so it lives here. See CLAUDE.md for how they can interfere.

## Signal chain

```
PicCap (screen capture on the TV)
  → HyperHDR (on the TV, Adalight driver, AWA protocol, 2 Mb)
  → TV USB port → ESP32-S3 running Hyperk (HyperSerial on)
  → GPIO 4 → TXS0108E level shifter → SK6812 RGBW strip
```

## Hardware

| Part | Choice |
|---|---|
| LEDs | SK6812 RGBW, 5 V, neutral white, 60/m |
| Layout | 3 sides (top, left, right), about 200 LEDs, ~3.4 m |
| Controller | Hosyond ESP32-S3-WROOM-1 N16R8 (DevKitC-1 pinout) |
| Firmware | Hyperk (HyperSerialESP32 doesn't support the S3) |
| Level shifter | TXS0108E (a 74AHCT125 is the fallback if it glitches) |
| Power | 5 V, 15–18 A (e.g. Mean Well LRS-100-5), mounted top center |

TV size without stand: about 172 × 99 cm. Strip runs, inset ~5 cm:
top ~162 cm (~97 LEDs), each side ~89 cm (~53 LEDs).

## Wiring

**Data** enters at the bottom of the left side, runs up, across the top
(left to right) and down the right side. One data line.

**ESP32-S3**
- Powered from the TV's USB on the native USB port (shows as
  `/dev/ttyACM0`; the TV needs the `cdc_acm` driver).
- GPIO 4 → shifter. GND → common ground. Leave the 5V pin unconnected so
  the LED supply never feeds the TV's USB port.
- Avoid GPIO 0, 3, 45, 46 (boot straps), 19/20 (USB), 26–37 (flash and
  octal PSRAM on N16R8), 43/44 (UART), 48 (onboard RGB LED).

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
2. Join it to Wi-Fi and open its web page.
3. LED type SK6812 RGBW (neutral), count ~200, data pin GPIO 4, driver SPI
   bitbang (DMA) first (RMT can flood interrupts). Enable HyperSerial.

## HyperHDR (on the TV, http://<tv-ip>:8090)

Adalight driver:

- Serial port `/dev/ttyACM0`, baud 2000000
- High-speed serial AWA protocol with data integrity check: on
- ESP8266/ESP32/RP2040/RP2350 handshake: on
- Force HyperSerial detection: on
- LED layout: 3 sides, starting bottom of left side, clockwise
- Current limit per the power notes above

## Is it working?

1. On the TV: `dmesg | tail -20` and `ls /dev/ttyACM* /dev/ttyUSB*` after
   plugging the board in. No tty means a missing kernel driver.
   (`./pear doctor` lists the USB serial devices too.)
2. HyperHDR **System → Log**: a line saying it detected a HyperSerial
   device.
3. HyperHDR **Remote Control**: set a solid colour. Strip lights = HyperHDR
   → ESP32 → LEDs works.
4. PicCap running and connected to 127.0.0.1; HyperHDR's live preview
   mirrors the screen. Solid colour works but video doesn't = PicCap side.
