# WLED on the ambilight board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Hyperk with WLED on the ESP32-S3 so the strip runs chosen effects from the board's own page whenever the TV is off, while HyperHDR tracking stays as it is.

**Architecture:** The board side is a stock WLED binary configured through its web page (Eddie does the flash and the cable move; the executor verifies over HTTP and ssh). The TV side changes one HyperHDR output setting. The repo retires `tv/ambilightguard` and its `pear` commands, and `pear ambilight pull` exports WLED's `cfg.json` and `presets.json` the way it exported Hyperk's config.

**Tech Stack:** WLED 16.0.1 (`WLED_16.0.1_ESP32-S3_16MB_opi.bin`), HyperHDR 22 Adalight (classic), Python 3 (`pear`, `installer/ambilight.py`), pytest, busybox `sh` on the TV, `curl`.

**Spec:** `docs/ambilight-wled-handoff.md`

## Global Constraints

- Ask Eddie before: reflashing the board, moving the TV's cable, changing HyperHDR or PicCap settings, running `pear ambilight uninstall`, rebooting the TV. Tasks 1, 2, 3 and the TV half of Task 4 are gated on his word.
- Commit only when Eddie says "commit" (and push only on "push"). The commit steps below are written as commands; the executor stages them and asks.
- American English spelling everywhere.
- Files handed to Eddie get their full absolute Windows path on its own line.
- Nothing on the TV is edited by hand: TV-side changes go through HyperHDR's page, luna calls, or `pear`.
- Never `kill -9` HyperHDR on the TV (stale socket); use the loader's luna `stop`/`start`.
- Tracking parity outranks "stock binary": if Task 2 shows stutter or board resets, stop and report; the fallback build is a separate plan.
- Board address: `192.168.8.248`. TV: `root@192.168.8.154` (ssh `BatchMode` works). HyperHDR page: `http://192.168.8.154:8090`.

## Review Focus

1. `pear ambilight pull` with the board unreachable: must still write the HyperHDR and PicCap files and say the board was skipped, as it does today. (Task 5, `test_pull_helpers_tolerate_missing_sections`.)
2. A `cfg.json` with no `nw` section or with an entry lacking `ssid` (fresh board, AP mode): the redaction must not raise. (Task 5, same test.)
3. HyperHDR's discovery lists the board under a different host than `wled-*.local` (user renamed it): the address must then come from `.pear.json` key `wled`, and the message must say which key to set. (Task 5 Step 6 checks the message by hand; `test_wled_address_comes_from_hyperhdr_discovery` pins the `None` case.)
4. The TV names the native USB port something other than `/dev/ttyACM0`: Task 2 reads `dmesg` before touching HyperHDR, and the output path is set to what the TV reports.
5. The guard's hook left on the TV after the code is gone would run a missing script at boot: Task 4 verifies the hook file is absent before the repo deletion is committed.

---

### Task 1: Flash and configure WLED (Eddie flashes; executor verifies)

**Files:** none in the repo.

**Interfaces:**
- Produces: a WLED board at `http://192.168.8.248` answering `/json/info` with `"ver":"16.0.1"`, four presets, settings per the spec.

- [ ] **Step 1: Confirm with Eddie that the TV's USB cable is unplugged from the board and he is ready to flash.** Do not continue until he says so.

- [ ] **Step 2: Give Eddie the flash instructions**

Say exactly this, with the path line as is:

Open https://install.wled.me in Chrome on the laptop. Plug the laptop into the board's port marked **USB** (the native one, not COM). Choose the ESP32-S3 build for 16 MB flash with OPI PSRAM (the binary is `WLED_16.0.1_ESP32-S3_16MB_opi.bin`; the installer's wording may differ, the binary name is what matters), Install, then enter the Wi-Fi name and password when the installer asks. When it shows the board's IP, tell me the IP. If the installer offers to open the board's page, decline; the settings below are done next.

- [ ] **Step 3: Verify the board is up**

Run: `curl -s -m 5 http://192.168.8.248/json/info | python -c "import sys,json; i=json.load(sys.stdin); print(i['ver'], i['name'], i['ip'])"`
Expected: `16.0.1 WLED 192.168.8.248`. If the IP differs, use the one Eddie gave and tell him the router may need a reservation.

- [ ] **Step 4: Give Eddie the settings, page by page**

Config, **LED Preferences**:
- LED output 1: type **SK6812 RGBW**, color order **GRB**, start 0, count **214**, GPIO **4**.
- Auto-calculate white channel from RGB: **Accurate**.
- Enable automatic brightness limiter: on; Maximum PSU Current **8000** mA; per-LED current **80** mA (select Custom if the preset list has no 80).
- Apply preset at boot: fill in later, after presets exist (Step 6).
- Save.

Config, **Sync Interfaces**:
- Serial: Baud rate **1500000**.
- Realtime: leave "Receive UDP realtime" at its default (whether it gates serial too is undocumented; don't find out the hard way); Timeout **2500** ms; **Force max brightness: on**.
- Save.

Config, **WiFi Setup**: mDNS address **wled-tv** (so the page is `http://wled-tv.local`), Save. The board reboots.

- [ ] **Step 5: Verify the settings landed**

Run: `curl -s -m 5 http://192.168.8.248/cfg.json | python -c "import sys,json; c=json.load(sys.stdin); print(c['hw']['led']['ins'][0]['len'], c['hw']['led']['ins'][0]['pin'], c['hw']['led']['ins'][0]['type'], c['hw']['led']['maxpwr'], c['if']['live']['timeout'], c['if']['live']['maxbri'], c['id']['mdns'])"`
Expected: `214 [4] 30 8000 25 True wled-tv` (30 is SK6812 RGBW in WLED's type list; if the page's SK6812 RGBW choice stores another number, accept it; timeout is stored in 100 ms units). If a value differs, tell Eddie which page to revisit.

- [ ] **Step 6: Give Eddie the four presets**

On the main page, each as: pick effect/colors/brightness, then Presets, +, name, **Save current state**, Save.

| Preset | Effect | Colors | Brightness |
|---|---|---|---|
| 1 Warm glow | Solid | color 1 = 60,60,60 (white channel off) | 255 |
| 2 Candle | Candle (multi) | color 1 = 255,120,20, color 2 = 120,40,0 | 180 |
| 3 Christmas | Chase 2 (or Running Dual) | color 1 = 255,0,0, color 2 = 0,180,0 | 160 |
| 4 Off | Solid | black, or Power toggle off | any |

Then Config, LED Preferences, **Apply preset at boot**: 1, Save.

- [ ] **Step 7: Verify the presets and the supply**

Run: `curl -s -m 5 http://192.168.8.248/presets.json | python -c "import sys,json; p=json.load(sys.stdin); print({k:v.get('n') for k,v in p.items() if v})"`
Expected: `{'1': 'Warm glow', '2': 'Candle', '3': 'Christmas', '4': 'Off'}`.

Then apply each in turn and ask Eddie whether the supply whines on it:
Run: `for p in 1 2 3; do curl -s -m 5 -X POST http://192.168.8.248/json/state -H "Content-Type: application/json" -d "{\"ps\":$p}"; echo; done` with a pause for his answer between each. Candle that whines: raise its brightness and re-save the preset; still whining at a brightness that no longer looks like a candle: note it for the resistor (spec, "Idle load for the supply") and move on.

Leave the board on preset 1.

---

### Task 2: Move the TV's cable and switch HyperHDR to classic Adalight

**Files:**
- Modify (via `pear ambilight pull` after the change, not by hand): `ambilight/hyperhdr/instance-0/device.json`

**Interfaces:**
- Consumes: the configured board from Task 1.
- Produces: `device.json` with `awa_mode` false, `espHandshake` false, `forceSerialDetection` false, `rate` 1500000, `output` = the TV's name for the port.

- [ ] **Step 1: Ask Eddie to move the TV's USB cable from the board's COM port to its USB port.** Wait for his word.

- [ ] **Step 2: Find the port name on the TV**

Run: `ssh -o BatchMode=yes root@192.168.8.154 'dmesg | grep -i -e "303a" -e "cdc_acm" -e "ttyACM" | tail -5; ls -l /dev/ttyACM*'`
Expected: a `303a:1001` device bound to `cdc_acm` and a `/dev/ttyACM0` (or other) node. Note the node name for Step 3. No node at all: the board's USB port is not enumerating; stop and report.

- [ ] **Step 3: Ask Eddie to confirm the HyperHDR change, then make it on HyperHDR's page**

In `http://192.168.8.154:8090`, LED Hardware, controller adalight: output path = the node from Step 2; baud **1500000**; **AWA protocol off**; **ESP handshake off**; **force serial detection off**; Save. (Settings on the page are the same fields as `device.json`.)

- [ ] **Step 4: Verify tracking**

Run: `curl -s -m 5 http://192.168.8.248/json/info | python -c "import sys,json; i=json.load(sys.stdin); print(i['live'], i['lm'])"`
Expected: `True Adalight` while the TV shows a picture. If `live` is False: check HyperHDR's log for "LED device: disabled" (PicCap stale socket; relaunch PicCap per `docs/ambilight.md`), then re-run.

Run: `ssh -o BatchMode=yes root@192.168.8.154 'dmesg | tail -3'`
Expected: no new USB disconnect/reconnect lines since Step 2. Lines showing the board re-enumerating when HyperHDR opened the port = the DTR/RTS reset case: stop and report (fallback build, separate plan).

Ask Eddie to watch a few minutes of video and say whether the strip stutters or tears compared with before. Stutter: stop and report.

- [ ] **Step 5: Pull the HyperHDR change into the repo**

Run: `python3 pear ambilight pull` (Windows) and `git diff --stat ambilight/`
Expected: `ambilight/hyperhdr/instance-0/device.json` changed; `git diff ambilight/hyperhdr/instance-0/device.json` shows exactly `awa_mode`, `espHandshake`, `forceSerialDetection`, `rate`, and possibly `output`. (The Hyperk pull in `pear` will print a skip line for the board; that is expected until Task 5.)

- [ ] **Step 6: Stage for commit (ask Eddie)**

```bash
git add ambilight/hyperhdr/instance-0/device.json
git commit -m "Ambilight: HyperHDR drives WLED over classic Adalight on the board's native USB"
```

---

### Task 3: Power-off and screensaver behavior (Eddie presses the buttons)

**Files:** none.

- [ ] **Step 1: Power-off.** With the TV showing a picture, ask Eddie to press Power. Expected: the strip holds the last frame for about 2.5 s, then shows preset 1 (or whichever preset was current). Ask him what he saw.

Verify from the board while the TV is off:
Run: `curl -s -m 5 http://192.168.8.248/json/state | python -c "import sys,json; s=json.load(sys.stdin); print(s['on'], s['bri'], s['ps'])"`
Expected: `True <preset brightness> 1`.

- [ ] **Step 2: Wake.** Ask Eddie to press Power again. Expected: tracking resumes within the TV's usual wake time without touching anything. Verify with the `/json/info` `live` check from Task 2 Step 4.

- [ ] **Step 3: Screensaver.** Ask Eddie to leave the TV idle until the screensaver starts (or trigger it). Expected: the loader stops HyperHDR, and 2.5 s later the strip shows the preset. Back out of the screensaver: tracking resumes.

- [ ] **Step 4: Record outcomes** in a new "Outcome (date)" section at the top of `docs/ambilight-wled-handoff.md`, mirroring `docs/ambilight-shutdown-handoff.md`: what was measured, what differed from the spec, and any whine notes from Task 1 Step 7. Commit with Task 6.

---

### Task 4: Retire ambilightguard

**Files:**
- Delete: `tv/ambilightguard`, `tests/test_ambilightguard.py`
- Modify: `pear` (docstring lines 10-12; constants `GUARD_DIR`, `GUARD_HOOK` at lines 40-41; `cmd_ambilight` lines 327-334; `ambilight_install`, `ambilight_uninstall`, `ambilight_status` lines 363-390)
- Modify: `README.md:120-122`, `README.md:146`

**Interfaces:**
- Produces: `cmd_ambilight` with `pull` as its only subcommand; usage text `usage: {PEAR} ambilight pull`.

- [ ] **Step 1: Ask Eddie for the go-ahead, then remove the guard from the TV**

Run: `python3 pear ambilight uninstall`
Expected: `ambilightguard removed.`

- [ ] **Step 2: Verify nothing of it is left on the TV**

Run: `ssh -o BatchMode=yes root@192.168.8.154 'ls /var/lib/webosbrew/init.d/; ls -d /var/lib/ambilightguard 2>&1; pgrep -f ambilightguard || echo no-process'`
Expected: no `60-ambilightguard` in the listing, `No such file or directory` for the dir, `no-process`.

- [ ] **Step 3: Delete the guard and its tests from the repo**

```bash
git rm tv/ambilightguard tests/test_ambilightguard.py
```

- [ ] **Step 4: Remove the guard commands from `pear`**

In `pear`: delete `ambilight_install`, `ambilight_uninstall`, `ambilight_status`, the `GUARD_DIR` and `GUARD_HOOK` constants, and the three subcommand entries in `cmd_ambilight` so `cmds = {"pull": ambilight_pull}` and the usage line reads `usage: {PEAR} ambilight pull`. Docstring lines 10-12 become one line: `./pear ambilight pull   copy HyperHDR, WLED and PicCap settings into ambilight/`.

- [ ] **Step 5: Update the README**

`README.md:120-122`: the same one docstring line as above. `README.md:146`: replace the guard sentence with: "The board runs WLED and shows its own effects, chosen on its page, whenever the TV is off." Keep the rest of the paragraph.

- [ ] **Step 6: Run the suite**

Run: `python -m pytest -q`
Expected: all tests pass; count is the previous total minus 4 (the guard's tests).

Run: `python3 pear ambilight` (no subcommand)
Expected: exits with `usage: python3 pear ambilight pull`.

- [ ] **Step 7: Stage for commit (ask Eddie)**

```bash
git add -A pear README.md tv tests
git commit -m "Ambilight: retire ambilightguard; WLED returns to its effect by itself"
```

---

### Task 5: `pear ambilight pull` exports WLED's config and presets

**Files:**
- Modify: `installer/ambilight.py` (replace `hyperk_for_repo` and `hyperk_address`, lines 58-73)
- Modify: `pear` (replace `hyperk_address(conf)` lines 313-324 and the Hyperk block in `ambilight_pull`, lines 349-359)
- Modify: `tests/test_ambilight.py` (replace the two Hyperk tests, lines 66-78)
- Create on first run: `ambilight/wled/cfg.json`, `ambilight/wled/presets.json`
- Keep untouched: `ambilight/hyperk.json` (the record for going back)

**Interfaces:**
- Consumes: Task 4's `cmd_ambilight` with only `pull`.
- Produces in `installer/ambilight.py`:
  - `wled_for_repo(cfg: dict) -> dict`: a copy of WLED's `cfg.json` with every `nw.ins[*].ssid` replaced by `REDACTED`; tolerates a missing `nw`, missing `ins`, or entries without `ssid`.
  - `wled_address(sessions) -> str | None`: the `address` of the first HyperHDR discovery session whose `host` starts with `wled`; `None` otherwise.
- Produces in `pear`: `wled_address(conf) -> str | None` reading `.pear.json` key `wled` first, then HyperHDR discovery via `ambilight.wled_address`, saving a found address under `wled`.

- [ ] **Step 1: Write the failing tests** (replace the two Hyperk tests in `tests/test_ambilight.py`)

```python
def test_wled_config_drops_the_wifi_names():
    cfg = {"nw": {"ins": [{"ssid": "My Home Wifi", "pskl": 12, "ip": [0, 0, 0, 0]},
                          {"ssid": "Cabin", "pskl": 8}]},
           "ap": {"ssid": "WLED-AP", "pskl": 8}, "hw": {"led": {"total": 214}}}

    out = ambilight.wled_for_repo(cfg)

    assert [n["ssid"] for n in out["nw"]["ins"]] == ["<redacted>", "<redacted>"]
    assert out["nw"]["ins"][0]["pskl"] == 12
    assert out["ap"]["ssid"] == "WLED-AP"
    assert out["hw"] == {"led": {"total": 214}}
    assert cfg["nw"]["ins"][0]["ssid"] == "My Home Wifi"  # input untouched


def test_pull_helpers_tolerate_missing_sections():
    assert ambilight.wled_for_repo({"hw": {}}) == {"hw": {}}
    assert ambilight.wled_for_repo({"nw": {}}) == {"nw": {}}
    assert ambilight.wled_for_repo({"nw": {"ins": [{"pskl": 0}]}}) == {"nw": {"ins": [{"pskl": 0}]}}


def test_wled_address_comes_from_hyperhdr_discovery():
    sessions = [{"address": "ttyACM0", "host": "USB JTAG serial debug unit", "name": "ESP board", "port": -1},
                {"address": "192.168.8.248", "host": "wled-tv.local", "name": "WLED", "port": 80}]

    assert ambilight.wled_address(sessions) == "192.168.8.248"
    assert ambilight.wled_address(sessions[:1]) is None
    assert ambilight.wled_address(None) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_ambilight.py -q`
Expected: 3 failures with `AttributeError: module 'ambilight' has no attribute 'wled_for_repo'` / `wled_address`; the old Hyperk tests are gone, so no other failures.

- [ ] **Step 3: Implement `wled_for_repo(cfg)` and `wled_address(sessions)` in `installer/ambilight.py`**, deleting `hyperk_for_repo` and `hyperk_address`. Update the module docstring's "Hyperk answers its config over HTTP" to "WLED serves its config and presets over HTTP". Deep-copy before redacting (`copy.deepcopy`), so the caller's dict is untouched.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Rewire `pear`**

Replace `hyperk_address(conf)` with `wled_address(conf)` (key `wled`, discovery via `ambilight.wled_address`). In `ambilight_pull`, replace the Hyperk block with:

- `wled = wled_address(conf)`; if found, print `WLED: reading the board's config and presets at {wled}...`, fetch `http://{wled}/cfg.json` and `http://{wled}/presets.json` with `http_json`, write `ambilight/wled/cfg.json` (through `wled_for_repo`) and `ambilight/wled/presets.json` (as is), append both relative paths to `written`; on `OSError` print `  (skipped: the board did not answer at {wled}: {e})`.
- If not found, print `WLED: not found by HyperHDR's discovery; set "wled" to the board's IP in .pear.json`.

- [ ] **Step 6: Run the real pull**

Run: `python3 pear ambilight pull` then `git status --short ambilight/`
Expected: `ambilight/wled/cfg.json` and `ambilight/wled/presets.json` appear; `grep -c '"ssid": "<redacted>"' ambilight/wled/cfg.json` prints at least 1; `grep -c '"ssid": "' ambilight/wled/cfg.json` equals the `<redacted>` count plus 1 (the AP name). `presets.json` lists the four names from Task 1. `ambilight/hyperk.json` unchanged.

Then check Review Focus 3 by hand: temporarily remove `wled` from `.pear.json` and run the pull with the board's mDNS name changed in your head to something not starting with `wled` (that is, read the code path): the not-found message must name the key `wled`. Put the key back as `"wled": "192.168.8.248"` if discovery did not find the board.

- [ ] **Step 7: Stage for commit (ask Eddie)**

```bash
git add installer/ambilight.py pear tests/test_ambilight.py ambilight/wled/
git commit -m "Ambilight: pear ambilight pull exports WLED's config and presets"
```

---

### Task 6: Docs and memory

**Files:**
- Modify: `docs/ambilight.md` (sections at lines 9-16 "Who does what", 18-22 "Lights on or off", 24-88 "Sleep and wake" through the retry paragraph, 99-116 "Settings in this repo", 141-148 the COM-port paragraph, 230-246 "Firmware: Hyperk", 248-262 HyperHDR, 303-end "Debugging the board from the TV")
- Modify: `docs/ambilight-wled-handoff.md` (Outcome section from Task 3)
- Modify: Claude's project memory `ambilight-shutdown.md` and `ambilight-serial-link.md` (outside the repo; the executor updates them, no commit)

- [ ] **Step 1: Rewrite the affected sections of `docs/ambilight.md`**

- "Who does what": Hyperk row becomes WLED ("Paints the strip with what HyperHDR sends; runs its own effects, chosen on its page, 2.5 s after the stream stops"); the ambilightguard row goes.
- "Lights on or off": delete.
- "Sleep and wake": the board on the supply plus WLED's timeout is the whole story; drop the guard paragraphs; keep "Board hung after a power cut" and the retry paragraph.
- "Settings in this repo": `ambilight/wled/cfg.json` and `presets.json` replace `hyperk.json` in the list; note `hyperk.json` is kept as the record for going back.
- The COM-port paragraph becomes "use the board's USB port" with the reason (stock WLED's serial is the native USB), and the note that the COM port is now free for the serial console.
- "Firmware: Hyperk" becomes "Firmware: WLED" with the Task 1 settings as a checklist, the preset table, the Force max brightness decision, and a short "Going back to Hyperk" subsection pointing at `ambilight/hyperk.json`, the Hyperk release page, and the old settings (count, GPIO, SPI bitbang, 2000000 baud, COM port).
- HyperHDR section: Adalight classic, 1500000, AWA/handshake/detection off, output node.
- "Debugging the board from the TV": the foreground-HyperHDR recipe is unchanged; the console recipe now needs the laptop on the COM port, and WLED's `/json/info` replaces Hyperk's `/api/stats`.

- [ ] **Step 2: Check spelling and links**

Run: `grep -n -i -E "colour|behaviour|centre|grey|optimis|initialis|analys(e|ing)" docs/ambilight.md docs/ambilight-wled-handoff.md README.md`
Expected: no output.

Run: `grep -n "ambilightguard\|hyperk" docs/ambilight.md`
Expected: only lines in the "Going back to Hyperk" subsection and the history paragraphs ("Board hung after a power cut", 2026-10-31/11-01 notes).

- [ ] **Step 3: Update memory** (`C:\Users\ed\.claude\projects\C--Development-Github-PearWebOS\memory\`): `ambilight-serial-link.md` (WLED, native USB port, classic Adalight 1500000, `/json/info`, `/cfg.json`, `/presets.json`) and `ambilight-shutdown.md` (guard retired; WLED timeout 2.5 s; Force max brightness on). Keep the never-`kill -9` and PicCap relaunch notes.

- [ ] **Step 4: Run the suite once more**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Stage for commit (ask Eddie)**

```bash
git add docs/ambilight.md docs/ambilight-wled-handoff.md
git commit -m "Ambilight: docs for WLED on the board"
```
