"""tv/ambilightguard, run under dash with a stand-in curl.

The guard watches the TV's power state and, when the TV is asked to power
off, tells HyperHDR to show Hyperk's idle color. These tests feed it one
power event at a time (`ambilightguard event '<json>'`) and read back what
it asked of curl.
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(os.path.dirname(HERE), "tv", "ambilightguard")
DASH = shutil.which("dash")

HYPERK_CONFIG = ('{"config":{"apMode":false,"relay-gpio":-1,"brightness":155,'
                 '"r":255,"g":97,"b":0,"numLeds":220,"version":"0.0.5"}}')

FAKE_CURL = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *get_current_config*) [ -f "$FAKE_HYPERK_DOWN" ] && exit 7; cat "$FAKE_HYPERK_JSON" ;;
  *json-rpc*) echo '{"success":true}' ;;
esac
"""

pytestmark = pytest.mark.skipif(DASH is None, reason="needs dash")


class Guard:
    def __init__(self, tmp_path):
        self.dir = tmp_path / "guard"
        self.dir.mkdir()
        (self.dir / "hyperk").write_text("192.0.2.9\n")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        curl = self.bin / "curl"
        curl.write_text(FAKE_CURL, newline="\n")
        curl.chmod(0o755)
        self.log = tmp_path / "curl.log"
        self.hyperk_json = tmp_path / "hyperk.json"
        self.hyperk_json.write_text(HYPERK_CONFIG)
        self.hyperk_down = tmp_path / "hyperk.down"

    def event(self, line):
        env = dict(os.environ,
                   PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                   AMBILIGHTGUARD_DIR=self.dir.as_posix(),
                   FAKE_LOG=self.log.as_posix(),
                   FAKE_HYPERK_JSON=self.hyperk_json.as_posix(),
                   FAKE_HYPERK_DOWN=self.hyperk_down.as_posix())
        r = subprocess.run([DASH, GUARD, "event", line], env=env, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        return r

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def hyperhdr_calls(self):
        return [c for c in self.calls() if "json-rpc" in c]


@pytest.fixture
def guard(tmp_path):
    return Guard(tmp_path)


def test_power_off_request_sends_hyperk_idle_color_to_hyperhdr(guard):
    guard.event('{ "returnValue": true, "state": "Active", "processing": "Request Power Off", "onOff": "off" }')
    calls = guard.hyperhdr_calls()
    assert len(calls) == 1
    assert "127.0.0.1:8090/json-rpc" in calls[0]
    assert '"command":"color"' in calls[0]
    assert '"priority":1' in calls[0]
    assert '"color":[255,97,0]' in calls[0]
    assert (guard.dir / "idle-color").read_text().split() == ["255", "97", "0"]


def test_uses_cached_color_when_the_board_does_not_answer(guard):
    (guard.dir / "idle-color").write_text("10 20 30\n", newline="\n")
    guard.hyperk_down.touch()
    guard.event('{ "returnValue": true, "state": "Active", "processing": "Request Power Off", "onOff": "off" }')
    calls = guard.hyperhdr_calls()
    assert len(calls) == 1
    assert '"color":[10,20,30]' in calls[0]
    assert (guard.dir / "idle-color").read_text().split() == ["10", "20", "30"]


def test_sends_nothing_without_a_color_to_send(guard):
    guard.hyperk_down.touch()
    guard.event('{ "returnValue": true, "state": "Active", "processing": "Request Power Off", "onOff": "off" }')
    assert guard.hyperhdr_calls() == []


def test_other_power_events_do_not_touch_hyperhdr(guard):
    for line in ('{ "returnValue": true, "state": "Active" }',
                 '{ "returnValue": true, "state": "Screen Saver" }',
                 '{ "returnValue": true, "state": "Suspend", "processing": "Prepare Resume", "onOff": "on" }',
                 '{ "subscribed": true, "returnValue": true, "state": "Active" }'):
        guard.event(line)
    assert guard.hyperhdr_calls() == []
