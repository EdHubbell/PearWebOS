"""The ambilight's settings, as files that diff well.

HyperHDR keeps its settings in a SQLite database on the TV, one JSON blob per
section; WLED serves its config and presets over HTTP; PicCap has a
config.json. This module turns each into sorted, indented JSON under a
folder, so `git diff` after `pear ambilight pull` shows exactly what changed
on the TV.
"""
import copy
import json
import os
import sqlite3

REDACTED = "<redacted>"
# HyperHDR settings keys that hold a secret when filled in (MQTT login, the
# SSL key's passphrase); an empty one is left empty so the diff stays honest
SECRET_KEYS = {"password", "keyPassPhrase"}


def redact(obj):
    """A copy of a settings section with any filled-in secret replaced."""
    if isinstance(obj, dict):
        return {k: (REDACTED if k in SECRET_KEYS and v else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def write_json(path, obj):
    """Sorted keys, two-space indent, LF, trailing newline: stable for diffing."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def export_hyperhdr(db_path, out_dir):
    """One file per settings section: hyperhdr/global/<type>.json for the
    server-wide ones, hyperhdr/instance-<n>/<type>.json per LED instance, and
    hyperhdr/instances.json. The auth table (password hashes, API tokens) is
    never read. Returns the relative paths written."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        written = []
        for inst, kind, config in con.execute("select hyperhdr_instance, type, config from settings"):
            where = "global" if inst is None else f"instance-{inst}"
            rel = f"hyperhdr/{where}/{kind}.json"
            write_json(os.path.join(out_dir, rel), redact(json.loads(config)))
            written.append(rel)
        instances = [{"instance": i, "friendly_name": name, "enabled": bool(enabled)}
                     for i, name, enabled in con.execute(
                         "select instance, friendly_name, enabled from instances order by instance")]
        write_json(os.path.join(out_dir, "hyperhdr/instances.json"), instances)
        written.append("hyperhdr/instances.json")
        return written
    finally:
        con.close()


# WLED cfg.json fields that say where or whose the board is: (path, key)
WLED_PRIVATE = (("ap", "ssid"), ("if", "ntp", "ln"), ("if", "ntp", "lt"),
                ("if", "mqtt", "broker"), ("if", "mqtt", "user"), ("if", "hue", "ip"))
WLED_AP_DEFAULT = "WLED-AP"


def _private(value):
    """A filled-in value: not empty, zero, or an all-zero address."""
    if isinstance(value, list):
        return any(value)
    return bool(value)


def wled_for_repo(cfg):
    """WLED's /cfg.json, minus what would place or identify the owner: Wi-Fi
    network names and BSSIDs, the renamed setup AP, the NTP location, the
    MQTT broker and user, the Hue bridge address. Passwords are never in it
    (WLED exports only their lengths, `pskl`). Empty fields stay empty so the
    diff stays honest."""
    out = copy.deepcopy(cfg)
    for net in (out.get("nw") or {}).get("ins") or []:
        if isinstance(net, dict):
            for key in ("ssid", "bssid"):
                if _private(net.get(key)):
                    net[key] = REDACTED
    for *path, key in WLED_PRIVATE:
        node = out
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, dict) and _private(node.get(key)):
            if path == ["ap"] and node[key] == WLED_AP_DEFAULT:
                continue
            node[key] = REDACTED
    return out


def wled_address(sessions):
    """The WLED board's IP from HyperHDR's device discovery (serverinfo
    'sessions'), where it shows up by its mDNS name wled-*.local; None if
    absent."""
    for s in sessions or []:
        if str(s.get("host", "")).startswith("wled"):
            return s.get("address")
    return None
