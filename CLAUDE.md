# PearWebOS: notes for Claude Code

Pear replaces LG Home on a rooted webOS 6 TV by bind-mounting three patched
QML files over LG's while Home runs. Read README.md "How it works" first.

## Layout

- `pear` (Python, runs on the laptop): setup, sync, status, on/off, shot,
  doctor, uninstall. Talks to the TV over `ssh root@<tv>` with a key
  (`BatchMode=yes`, so the key must be in the agent). The TV address is in
  `.pear.json` (git-ignored).
- `tv/` (busybox `sh`, runs on the TV from `/var/lib/pearwebos`):
  - `pearwebos`: mounts, cold-starts Home, boot logic. The Homebrew Channel
    hook `/var/lib/webosbrew/init.d/05-pearwebos` runs `pearwebos boot` in
    the background at every boot.
  - `homeguard`: opens Home when only Live TV is in front.
  - `luna-send-n`: `luna-send -n` that works on webOS 6.4.
- `installer/patch_home.py`: exact-match edits to LG's QML. Each must match
  once, so a different firmware fails before installing.
- `qml/PearHome.qml`: Pear's Home.
- `docs/ambilight.md`: the DIY ambilight (HyperHDR + PicCap + ESP32-S3) that
  shares this TV.

## Working on the TV

Read-only, safe any time:

```bash
./pear doctor     # logs, startup hooks, memory, mounts, HyperHDR/PicCap, saved to .cache/doctor.txt
./pear status
ssh root@<tv> 'tail -n 80 /var/lib/pearwebos/pearwebos.log'
```

Changes the screen (fine, but say so before running):

```bash
./pear on         # also clears a previous off or failed-boot state
./pear off        # stock LG Home
./pear sync       # rebuild and push after editing tv/, qml/ or installer/
```

Ask Eddie before:

- `./pear uninstall`, rebooting the TV, or deleting anything under
  `/var/lib/webosbrew/init.d` or another app's directory.
- Changing HyperHDR or PicCap settings or their startup hooks.
- Anything touching firmware updates or the read-only system partition
  (`/usr`, `/etc` are read-only; Pear never writes there).

Notes:

- Scripts in `tv/` must stay POSIX `sh` for busybox: no bash arrays,
  `[[ ]]`, or `local` reliance. Check with `dash -n tv/<script>`.
- Edit files in `tv/` here and push with `./pear sync`; don't edit them in
  place on the TV, the next sync overwrites them.
- webOS takes a moment to restore Home; give `on`/`sync` ~15–40 s.

## Open issue: Pear stopped appearing after installing HyperHDR + PicCap

Symptom: after installing HyperHDR and PicCap (for the ambilight), the TV
shows LG's Home instead of Pear.

Leading hypothesis (fixed in `tv/pearwebos` on the `ambilight-debug` branch):
before the fix, `pearwebos boot` gave Pear 38 s after cold-starting Home for
the app manager to snapshot it. If the snapshot didn't appear (a busy boot,
low memory with HyperHDR and PicCap starting too), boot treated it as a Pear
failure, went back to stock and **touched `/var/lib/pearwebos/disabled`**,
which keeps Pear off at every later boot. One slow boot latched Pear off.

The fix:

- A missing snapshot with Home still running is not a failure: Pear stays,
  and the next boot rebuilds the snapshot. Boot now waits up to 90 s.
- A real failure (Home died with Pear mounted) goes in
  `/var/lib/pearwebos/failed`, one line per boot, and boot retries until
  three have piled up. `disabled` now only means `pear off`.
- Failure log lines include free memory and which of HyperHDR/PicCap are
  running.

To confirm on the TV:

1. `./pear doctor`. Look for, in `pearwebos.log`, "Home did not stay up with
   Pear; back to stock", and a `disabled` file. Both mean the latch fired.
2. `./pear sync` (installs the fixed scripts), then `./pear on` (clears the
   latch).
3. Reboot the TV (ask first), wait two minutes, `./pear doctor` again.
   Expect "boot: Pear Home up" or "...no snapshot after 90s; keeping Pear".

Other suspects if that isn't it:

- **PicCap autostart opens its app at boot.** If PicCap's own startup
  launches its UI into the foreground, Home is covered, and `pearwebos boot`
  won't call `open_home` because the front isn't bare. `doctor`'s
  foreground section and the init.d listing show it. The fix would be
  starting PicCap's service rather than its app, in PicCap's settings.
- **Memory.** If dmesg shows OOM kills of `com.webos.app.home`, the TV is
  too tight with HyperHDR, PicCap and Pear together. Check `doctor`'s
  biggest-processes section; webos-debloat (README, "Pairs well with")
  frees memory.
- **Mount conflict.** `doctor`'s "other mounts over LG Home" should list
  only Pear's three files.
- **Hook order.** Pear's hook is `05-` and backgrounds itself, so others
  can't block it, but a later hook that restarts the app manager or Home
  would drop Pear's mounted Home. The hook listing shows what each one runs.
