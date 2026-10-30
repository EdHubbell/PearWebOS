import json
import os
import sqlite3

import ambilight


def make_db(path, rows, auth=()):
    """A HyperHDR-shaped settings database: (hyperhdr_instance, type, config_json)."""
    con = sqlite3.connect(path)
    con.execute("create table settings (type text, config text, hyperhdr_instance integer, updated_at text)")
    con.execute("create table instances (instance integer, friendly_name text, enabled integer, last_use text)")
    con.execute("create table auth (user text, password text, token text, salt text, comment text,"
                " portal_token text, id text, created_at text, last_use text)")
    con.executemany("insert into settings (hyperhdr_instance, type, config) values (?, ?, ?)", rows)
    con.execute("insert into instances values (0, 'First LED instance', 1, '2026-10-30T21:59:57Z')")
    for row in auth:
        con.execute("insert into auth (user, password, token) values (?, ?, ?)", row)
    con.commit()
    con.close()


def test_export_writes_one_json_file_per_setting_type(tmp_path):
    db = tmp_path / "hyperhdr.db"
    make_db(db, [
        (None, "network", '{"apiAuth": true, "ipWhitelist": []}'),
        (0, "device", '{"type": "adalight", "output": "ttyACM0", "rate": 2000000}'),
    ])
    out = tmp_path / "out"

    written = ambilight.export_hyperhdr(str(db), str(out))

    assert sorted(written) == ["hyperhdr/global/network.json", "hyperhdr/instance-0/device.json", "hyperhdr/instances.json"]
    with open(out / "hyperhdr" / "instance-0" / "device.json") as f:
        assert json.load(f) == {"type": "adalight", "output": "ttyACM0", "rate": 2000000}
    with open(out / "hyperhdr" / "instances.json") as f:
        assert json.load(f) == [{"instance": 0, "friendly_name": "First LED instance", "enabled": True}]


def test_export_never_writes_the_auth_table(tmp_path):
    db = tmp_path / "hyperhdr.db"
    make_db(db, [(None, "general", '{"name": "x"}')], auth=[("Hyperhdr", "hash", "secret-token")])
    out = tmp_path / "out"

    ambilight.export_hyperhdr(str(db), str(out))

    dumped = "".join(open(os.path.join(root, name)).read()
                     for root, _, names in os.walk(out) for name in names)
    assert "secret-token" not in dumped and "hash" not in dumped
    assert not (out / "hyperhdr" / "global" / "auth.json").exists()


def test_json_files_are_stable_for_diffing(tmp_path):
    """Sorted keys, two-space indent, LF line endings, trailing newline: so a
    pull that changed nothing is a clean git diff."""
    db = tmp_path / "hyperhdr.db"
    make_db(db, [(0, "device", '{"zeta": 1, "alpha": {"b": 2, "a": 1}}')])
    out = tmp_path / "out"

    ambilight.export_hyperhdr(str(db), str(out))

    with open(out / "hyperhdr" / "instance-0" / "device.json", "rb") as f:
        assert f.read() == b'{\n  "alpha": {\n    "a": 1,\n    "b": 2\n  },\n  "zeta": 1\n}\n'


def test_hyperk_config_drops_the_wifi_name():
    pulled = {"config": {"deviceName": "hyperk", "ssid": "My Home Wifi", "numLeds": 200}}

    assert ambilight.hyperk_for_repo(pulled) == {"deviceName": "hyperk", "ssid": "<redacted>", "numLeds": 200}


def test_hyperk_address_comes_from_hyperhdr_discovery():
    sessions = [{"address": "ttyACM0", "host": "USB JTAG serial debug unit", "name": "ESP board", "port": -1},
                {"address": "192.168.8.248", "host": "hyperk.local", "name": "WLED", "port": 80}]

    assert ambilight.hyperk_address(sessions) == "192.168.8.248"
    assert ambilight.hyperk_address(sessions[:1]) is None


def test_export_redacts_passwords_in_hyperhdr_sections(tmp_path):
    db = tmp_path / "hyperhdr.db"
    make_db(db, [
        (None, "mqtt", '{"host": "broker", "username": "ed", "password": "hunter2"}'),
        (None, "webConfig", '{"keyPath": "/k", "keyPassPhrase": "pem-secret", "port": 8090}'),
        (None, "general", '{"name": "x"}'),
    ])
    out = tmp_path / "out"

    ambilight.export_hyperhdr(str(db), str(out))

    with open(out / "hyperhdr" / "global" / "mqtt.json") as f:
        assert json.load(f) == {"host": "broker", "username": "ed", "password": "<redacted>"}
    with open(out / "hyperhdr" / "global" / "webConfig.json") as f:
        assert json.load(f)["keyPassPhrase"] == "<redacted>"


def test_empty_passwords_stay_empty(tmp_path):
    """An empty field is not a secret; keeping it empty keeps the diff honest."""
    db = tmp_path / "hyperhdr.db"
    make_db(db, [(None, "mqtt", '{"password": ""}')])
    out = tmp_path / "out"

    ambilight.export_hyperhdr(str(db), str(out))

    with open(out / "hyperhdr" / "global" / "mqtt.json") as f:
        assert json.load(f) == {"password": ""}
