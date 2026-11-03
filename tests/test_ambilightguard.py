"""tv/ambilightguard, run under dash with stand-in curl, luna-send and pidof.

The guard watches the TV's power state. When the TV is asked to power off
it stops HyperHDR through the loader, and once HyperHDR is gone it tells
WLED to leave realtime mode (HyperHDR locks the board "live" with no
timeout, so a stream that just vanishes leaves the strip frozen). On the
screensaver the loader stops HyperHDR by itself, so the guard only does
the release. These tests feed it one power event at a time
(`ambilightguard event '<json>'`) and read back what it ran.
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(os.path.dirname(HERE), "tv", "ambilightguard")
DASH = shutil.which("dash")

FAKE_CURL = """#!/bin/sh
echo "curl $*" >> "$FAKE_LOG"
echo '{"success":true}'
"""
FAKE_LUNA = """#!/bin/sh
echo "luna-send $*" >> "$FAKE_LOG"
echo '{"returnValue":true}'
"""
FAKE_PIDOF = """#!/bin/sh
# HyperHDR is "running" while $FAKE_ALIVE holds a positive count
[ -f "$FAKE_ALIVE" ] || exit 1
n=$(cat "$FAKE_ALIVE")
[ "$n" -gt 0 ] || exit 1
echo $((n - 1)) > "$FAKE_ALIVE"
echo 4242
"""
FAKE_PKILL = """#!/bin/sh
echo "pkill $*" >> "$FAKE_LOG"
echo 0 > "$FAKE_ALIVE"
"""
FAKE_USLEEP = """#!/bin/sh
exit 0
"""

pytestmark = pytest.mark.skipif(DASH is None, reason="needs dash")


class Guard:
    def __init__(self, tmp_path, board="192.0.2.9"):
        self.dir = tmp_path / "guard"
        self.dir.mkdir()
        if board:
            (self.dir / "wled").write_text(board + "\n")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name, body in (("curl", FAKE_CURL), ("luna-send", FAKE_LUNA), ("pidof", FAKE_PIDOF),
                           ("pkill", FAKE_PKILL), ("usleep", FAKE_USLEEP)):
            f = self.bin / name
            f.write_text(body, newline="\n")
            f.chmod(0o755)
        self.log = tmp_path / "calls.log"
        self.alive = tmp_path / "alive"

    def event(self, line):
        env = dict(os.environ,
                   PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                   AMBILIGHTGUARD_DIR=self.dir.as_posix(),
                   FAKE_LOG=self.log.as_posix(),
                   FAKE_ALIVE=self.alive.as_posix())
        r = subprocess.run([DASH, GUARD, "event", line], env=env, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        return r

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []


POWER_OFF = '{ "returnValue": true, "state": "Active", "processing": "Request Power Off", "onOff": "off" }'
ACTIVE_STANDBY = '{ "returnValue": true, "state": "Active", "processing": "Request Active Standby", "onOff": "off" }'
SCREEN_SAVER = '{ "returnValue": true, "state": "Screen Saver" }'
SCREEN_OFF = '{ "returnValue": true, "state": "Screen Off" }'


def test_power_off_stops_hyperhdr_then_releases_the_board(tmp_path):
    guard = Guard(tmp_path)
    guard.event(POWER_OFF)
    calls = guard.calls()
    assert len(calls) == 2
    assert calls[0].startswith("luna-send ")
    assert "luna://org.webosbrew.hyperhdr.loader.service/stop" in calls[0]
    assert calls[1].startswith("curl ")
    assert "http://192.0.2.9/json/state" in calls[1]
    assert '"live":false' in calls[1]


def test_active_standby_is_handled_like_power_off(tmp_path):
    guard = Guard(tmp_path)
    guard.event(ACTIVE_STANDBY)
    calls = guard.calls()
    assert [c.split()[0] for c in calls] == ["luna-send", "curl"]


def test_screen_saver_and_screen_off_release_the_board_without_touching_hyperhdr(tmp_path):
    for name, line in (("saver", SCREEN_SAVER), ("off", SCREEN_OFF)):
        (tmp_path / name).mkdir()
        guard = Guard(tmp_path / name)
        guard.event(line)
        calls = guard.calls()
        assert len(calls) == 1, line
        assert calls[0].startswith("curl ")
        assert '"live":false' in calls[0]


def test_release_turns_the_board_on_so_the_page_choice_shows(tmp_path):
    guard = Guard(tmp_path)
    guard.event(SCREEN_SAVER)
    assert '"on":true' in guard.calls()[0]


def test_waits_for_hyperhdr_to_exit_before_releasing(tmp_path):
    guard = Guard(tmp_path)
    guard.alive.write_text("3\n")  # three pidof polls see it, then it is gone
    guard.event(POWER_OFF)
    calls = guard.calls()
    assert [c.split()[0] for c in calls] == ["luna-send", "curl"]
    assert guard.alive.read_text().strip() == "0"


def test_terminates_hyperhdr_that_ignores_the_loader(tmp_path):
    guard = Guard(tmp_path)
    guard.alive.write_text("99\n")  # never exits on its own
    guard.event(POWER_OFF)
    calls = guard.calls()
    assert [c.split()[0] for c in calls] == ["luna-send", "pkill", "curl"]
    assert "-TERM" in calls[1] and "-x hyperhdr" in calls[1]


def test_board_address_file_with_crlf_still_works(tmp_path):
    guard = Guard(tmp_path, board=None)
    (guard.dir / "wled").write_text("192.0.2.9\r\n", newline="")
    guard.event(SCREEN_SAVER)
    assert "http://192.0.2.9/json/state" in guard.calls()[0]


def test_luna_calls_carry_a_timeout(tmp_path):
    guard = Guard(tmp_path)
    guard.event(POWER_OFF)
    assert "-w " in guard.calls()[0]


def test_power_off_without_a_board_address_still_stops_hyperhdr(tmp_path):
    guard = Guard(tmp_path, board=None)
    guard.event(POWER_OFF)
    calls = guard.calls()
    assert len(calls) == 1
    assert "loader.service/stop" in calls[0]


def test_screen_on_starts_hyperhdr_through_the_loader(tmp_path):
    guard = Guard(tmp_path)
    guard.event('{ "returnValue": true, "state": "Active", "processing": "Screen On", "onOff": "on" }')
    calls = guard.calls()
    assert len(calls) == 1
    assert calls[0].startswith("luna-send ")
    assert "luna://org.webosbrew.hyperhdr.loader.service/start" in calls[0]


def test_other_power_events_do_nothing(tmp_path):
    guard = Guard(tmp_path)
    for line in ('{ "returnValue": true, "state": "Active" }',
                 '{ "returnValue": true, "state": "Suspend", "processing": "Prepare Resume", "onOff": "on" }',
                 '{ "subscribed": true, "returnValue": true, "state": "Active" }'):
        guard.event(line)
    assert guard.calls() == []
