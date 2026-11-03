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


def test_wled_config_drops_other_location_and_account_fields():
    cfg = {"nw": {"ins": [{"ssid": "Home", "bssid": "AA:BB:CC:DD:EE:FF"}]},
           "ap": {"ssid": "my-ap"},
           "if": {"ntp": {"ln": -97.7, "lt": 30.3, "host": "0.wled.pool.ntp.org"},
                  "mqtt": {"broker": "mqtt.lan", "user": "eddie", "port": 1883},
                  "hue": {"ip": [192, 168, 8, 50], "id": 1}}}

    out = ambilight.wled_for_repo(cfg)

    assert out["nw"]["ins"][0]["bssid"] == "<redacted>"
    assert out["ap"]["ssid"] == "<redacted>"
    assert out["if"]["ntp"] == {"ln": "<redacted>", "lt": "<redacted>", "host": "0.wled.pool.ntp.org"}
    assert out["if"]["mqtt"] == {"broker": "<redacted>", "user": "<redacted>", "port": 1883}
    assert out["if"]["hue"] == {"ip": "<redacted>", "id": 1}


def test_wled_config_leaves_empty_fields_empty():
    cfg = {"nw": {"ins": [{"ssid": "", "bssid": ""}]}, "ap": {"ssid": "WLED-AP"},
           "if": {"ntp": {"ln": 0, "lt": 0}, "mqtt": {"broker": "", "user": ""}, "hue": {"ip": [0, 0, 0, 0]}}}

    out = ambilight.wled_for_repo(cfg)

    assert out["nw"]["ins"][0] == {"ssid": "", "bssid": ""}
    assert out["ap"]["ssid"] == "WLED-AP"  # the factory name is not a secret
    assert out["if"] == cfg["if"]


def test_pull_helpers_tolerate_missing_sections():
    assert ambilight.wled_for_repo({"hw": {}}) == {"hw": {}}
    assert ambilight.wled_for_repo({"nw": {}}) == {"nw": {}}
    assert ambilight.wled_for_repo({"nw": {"ins": [{"pskl": 0}]}}) == {"nw": {"ins": [{"pskl": 0}]}}
    assert ambilight.wled_for_repo({"if": {"ntp": {}}}) == {"if": {"ntp": {}}}
    assert ambilight.wled_for_repo({"if": {"hue": {"ip": "not-a-list"}}}) == {"if": {"hue": {"ip": "<redacted>"}}}


def test_wled_address_comes_from_hyperhdr_discovery():
    sessions = [{"address": "ttyACM0", "host": "USB JTAG serial debug unit", "name": "ESP board", "port": -1},
                {"address": "192.168.8.248", "host": "wled-tv.local", "name": "WLED", "port": 80}]

    assert ambilight.wled_address(sessions) == "192.168.8.248"
    assert ambilight.wled_address(sessions[:1]) is None
    assert ambilight.wled_address(None) is None


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
