"""The ambilight's settings, as files that diff well.

HyperHDR keeps its settings in a SQLite database on the TV, one JSON blob per
section; Hyperk answers its config over HTTP; PicCap has a config.json. This
module turns each into sorted, indented JSON under a folder, so `git diff`
after `pear ambilight pull` shows exactly what changed on the TV.
"""
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


def hyperk_for_repo(pulled):
    """Hyperk's /api/get_current_config answer, minus the Wi-Fi network name."""
    config = dict(pulled.get("config", pulled))
    if "ssid" in config:
        config["ssid"] = REDACTED
    return config


def hyperk_address(sessions):
    """The Hyperk board's IP from HyperHDR's device discovery (serverinfo
    'sessions'), where it shows up by mDNS as hyperk.local; None if absent."""
    for s in sessions or []:
        if str(s.get("host", "")).startswith("hyperk."):
            return s.get("address")
    return None
