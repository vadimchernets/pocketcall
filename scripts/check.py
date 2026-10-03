#!/usr/bin/env python3
"""Pocketcall readiness check.

Seven things decide whether an evening away from the desk works. Six of them fail silently:
the person walks out of the house believing the remote is on, and finds out in town that it
is not. This script looks at all seven on this machine and says, in plain words, which ones
are not ready and what to do about each.

Nothing here talks to the network, reads a conversation, or changes a setting. It reads
local files (the person's and the project's settings, and the organization's managed
settings file when IT has installed one), runs `claude --version` and, on a Mac,
`pmset -g custom`, and lists the names and dates of the shared folder without opening
anything inside it. It prints a report for a person, and with --json the same findings for a
program.

Every word a person reads comes from lang/<code>.json (en, es, pt, ru, uk), English
underneath anything a language is missing. The language is --lang, then POCKETCALL_LANG,
then the system's (LC_ALL, LC_MESSAGES, LANG), then English.

Run:  python3 check.py [--json] [--dir <project directory>] [--shared <shared folder>]
                       [--lang xx] [--trusted-devices]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANG_DIR = ROOT / "lang"
LANGUAGES = ("en", "es", "pt", "ru", "uk")


def lang_words(code: str = "en") -> dict:
    """lang/<code>.json, English underneath anything missing."""
    words: dict = {}
    for name in ("en", code):
        try:
            data = json.loads((LANG_DIR / f"{name}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            words.update(data)
    return words


def pick_lang(explicit: str | None = None) -> str:
    for value in (explicit, os.environ.get("POCKETCALL_LANG"), os.environ.get("LC_ALL"),
                  os.environ.get("LC_MESSAGES"), os.environ.get("LANG")):
        if isinstance(value, str) and len(value) >= 2:
            code = value[:2].lower()
            if (LANG_DIR / f"{code}.json").is_file():
                return code
    return "en"


# The functions below speak through WORDS. It is English until main() picks the person's
# language, so a program that imports this module gets English unless it asks otherwise.
WORDS = lang_words("en")


def use_lang(code: str) -> None:
    global WORDS
    WORDS = lang_words(code)


def t(key: str, **values) -> str:
    text = WORDS.get(key, key)
    return text.format(**values) if values else text


# Variables that switch off the feature-flag evaluation Remote Control needs. Set in a shell
# profile or in the "env" block of a settings file, they produce no error: the remote simply
# never comes up. The first two always do it. The last two do it only when the organization
# requires Trusted Devices, or on a Claude Code older than SOFT_FIXED_IN (code.claude.com/docs
# /en/remote-control, "Requirements" and "Troubleshooting").
HARD_KILLERS = ("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "DISABLE_GROWTHBOOK")
SOFT_KILLERS = ("DISABLE_TELEMETRY", "DO_NOT_TRACK")
KILLERS = SOFT_KILLERS + HARD_KILLERS
SOFT_FIXED_IN = (2, 1, 283)

REDIRECTS = ("ANTHROPIC_BASE_URL",)
NOT_A_SUBSCRIPTION = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
OTHER_CLOUDS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")

# Where IT puts the organization's managed settings (code.claude.com/docs/en/managed-settings).
# Settings that arrive from the claude.ai admin console are not on disk and are not read here.
MANAGED_DIRS = {
    "darwin": "/Library/Application Support/ClaudeCode",
    "linux": "/etc/claude-code",
    "win32": r"C:\Program Files\ClaudeCode",
}

# The handover rule: the phone cannot read a terminal, so every finished thing goes to a file.
OUT_DIR = "pocket-out"
RULE_MARK = "pocket-out"

MIN_VERSION = (2, 1, 196)  # below this, a custom base URL was still allowed; above it, refused

# Where a folder that both the phone and this computer can see usually lives. First match wins,
# so the desktop clients come before the Mac's newer CloudStorage layout only where they are
# genuinely the same folder. Nothing here proves a folder is syncing; see check_sync.
CLOUD_PLACES = (
    ("Google Drive", "Library/CloudStorage/GoogleDrive-*"),
    ("Google Drive", "Google Drive"),
    ("Dropbox", "Library/CloudStorage/Dropbox*"),
    ("Dropbox", "Dropbox"),
    ("OneDrive", "Library/CloudStorage/OneDrive*"),
    ("OneDrive", "OneDrive*"),
    ("iCloud Drive", "Library/Mobile Documents/com~apple~CloudDocs"),
)

# A whole cloud drive can hold a hundred thousand files. We only need enough to say a number
# and a date, so the walk stops here and says it stopped.
SCAN_CAP = 2000


def run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (out.stdout or "") + (out.stderr or "")


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def settings_env(path: Path) -> dict:
    """The env block of a settings file, or {} when there is no readable file."""
    env = read_json(path).get("env")
    return env if isinstance(env, dict) else {}


def settings_flag(path: Path, key: str):
    return read_json(path).get(key)


def managed_files(managed_dir: str | Path | None = None) -> list[Path]:
    """managed-settings.d/*.json and managed-settings.json, the files Claude Code merges."""
    # POCKETCALL_MANAGED_DIR points the check at a policy folder that is not installed yet:
    # IT reads what a draft policy would do to the remote, and the tests use it too.
    managed_dir = managed_dir or os.environ.get("POCKETCALL_MANAGED_DIR")
    folder = Path(managed_dir) if managed_dir else (
        Path(MANAGED_DIRS[sys.platform]) if sys.platform in MANAGED_DIRS else None)
    if folder is None:
        return []
    found = []
    drop_ins = folder / "managed-settings.d"
    try:
        found += sorted(p for p in drop_ins.glob("*.json") if p.is_file())
    except OSError:
        pass
    main_file = folder / "managed-settings.json"
    if main_file.is_file():
        found.append(main_file)
    return found


def managed_value(files: list[Path], key: str):
    """The value of key across the managed files; managed-settings.json is read last and wins."""
    value = None
    for f in files:
        data = read_json(f)
        if key in data:
            value = data[key]
    return value


def parse_version(text: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(g) for g in m.groups()) if m else None


def check_place(project: Path) -> dict:
    """A remote session has to start from a project directory, not from the home folder."""
    home = Path.home().resolve()
    here = project.resolve()
    if here == home:
        return {"id": "place", "ok": False, "says": t("place_home_says"), "do": t("place_home_do")}
    return {"id": "place", "ok": True, "says": t("place_ok_says", path=here), "do": ""}


def claude_version():
    return parse_version(run(["claude", "--version"]))


def check_version(ver=None) -> dict:
    ver = ver if ver is not None else claude_version()
    if not ver:
        return {"id": "version", "ok": False,
                "says": t("version_unknown_says"), "do": t("version_unknown_do")}
    shown = ".".join(map(str, ver))
    if ver < MIN_VERSION:
        return {"id": "version", "ok": False,
                "says": t("version_old_says", ver=shown), "do": t("version_old_do")}
    return {"id": "version", "ok": True, "says": t("version_ok_says", ver=shown), "do": ""}


def check_quiet_killers(project: Path, version=None, trusted_devices: bool = False,
                        managed_dir: str | Path | None = None) -> list[dict]:
    """The silent ones. Each of these turns the remote off without saying anything.

    `version` is Claude Code's, when it is known; it decides whether DISABLE_TELEMETRY and
    DO_NOT_TRACK still stop the remote. `trusted_devices` is the person saying their
    organization requires Trusted Devices, which nothing on this machine can see.
    """
    found: list[dict] = []
    files = [Path.home() / ".claude" / "settings.json",
             project / ".claude" / "settings.json",
             project / ".claude" / "settings.local.json"]
    managed = managed_files(managed_dir)
    from_files: dict[str, str] = {}
    for f in files + managed:
        for k in settings_env(f):
            from_files[k] = f"{f}"

    def where(name):
        return t("where_terminal") if os.environ.get(name) else from_files.get(name)

    for name in HARD_KILLERS:
        place = where(name)
        if place:
            found.append({"id": f"env:{name}", "ok": False,
                          "says": t("set_in_says", name=name, where=place),
                          "do": t("killer_hard_do")})
    for name in SOFT_KILLERS:
        place = where(name)
        if not place:
            continue
        if trusted_devices:
            found.append({"id": f"env:{name}", "ok": False,
                          "says": t("set_in_says", name=name, where=place),
                          "do": t("killer_soft_trusted_do")})
        elif version is None or version < SOFT_FIXED_IN:
            found.append({"id": f"env:{name}", "ok": False,
                          "says": t("set_in_says", name=name, where=place),
                          "do": t("killer_soft_old_do")})
        else:
            found.append({"id": f"env:{name}", "ok": True,
                          "says": t("killer_soft_fine_says", name=name, where=place,
                                    ver=".".join(map(str, version))),
                          "do": t("killer_soft_fine_do")})
    for name in REDIRECTS:
        place = where(name)
        if place:
            found.append({"id": f"env:{name}", "ok": False,
                          "says": t("set_in_says", name=name, where=place),
                          "do": t("redirect_do")})
    for name in NOT_A_SUBSCRIPTION:
        place = where(name)
        if place:
            found.append({"id": f"env:{name}", "ok": False,
                          "says": t("remote_off_says", name=name, where=place),
                          "do": t("api_key_do")})
    for f in files + managed:
        if settings_flag(f, "apiKeyHelper"):
            found.append({"id": "setting:apiKeyHelper", "ok": False,
                          "says": t("remote_off_says", name="apiKeyHelper", where=f),
                          "do": t("api_key_do")})
            break
    for name in OTHER_CLOUDS:
        place = where(name)
        if place:
            found.append({"id": f"env:{name}", "ok": False,
                          "says": t("remote_off_says", name=name, where=place),
                          "do": t("other_cloud_do")})
    for f in files:
        if settings_flag(f, "disableRemoteControl") is True:
            found.append({"id": "setting:disableRemoteControl", "ok": False,
                          "says": t("refusal_says", where=f), "do": t("refusal_do")})
    if managed_value(managed, "disableRemoteControl") is True:
        found.append({"id": "managed:disableRemoteControl", "ok": False,
                      "says": t("refusal_says", where=managed[-1].parent),
                      "do": t("refusal_managed_do")})
    if not any(not i["ok"] for i in found):
        found.insert(0, {"id": "quiet", "ok": True, "says": t("quiet_ok_says"), "do": ""})
    return found


def check_channels(managed_dir: str | Path | None = None):
    """What the organization's policy on this computer says about Channels, if there is one.

    Channels carry Telegram, Discord or iMessage into the session that is running here. On a
    Team or Enterprise plan they stay off until an Owner or IT turns them on; with no managed
    file on this computer there is nothing to read, and the check says nothing.
    """
    managed = managed_files(managed_dir)
    if not managed:
        return None
    if managed_value(managed, "channelsEnabled") is True:
        allowed = managed_value(managed, "allowedChannelPlugins")
        if isinstance(allowed, list):
            names = [str(p.get("plugin")) for p in allowed if isinstance(p, dict)]
            plugins = ", ".join(names) if names else "—"
        else:
            plugins = t("channels_any")
        return {"id": "channels", "ok": True, "says": t("channels_on_says", plugins=plugins), "do": ""}
    return {"id": "channels", "ok": True, "says": t("channels_off_says"), "do": t("channels_off_do")}


def check_sleep() -> dict:
    """A sleeping computer does no work. On a Mac we can read the setting; elsewhere we ask."""
    if sys.platform == "darwin":
        text = run(["pmset", "-g", "custom"])
        block = text.split("AC Power:", 1)[-1] if "AC Power:" in text else text
        m = re.search(r"^\s*sleep\s+(\d+)", block, re.M)
        if m:
            minutes = int(m.group(1))
            if minutes == 0:
                return {"id": "sleep", "ok": True, "says": t("sleep_never_says"), "do": ""}
            unit = t("minute_one") if minutes == 1 else t("minute_many")
            return {"id": "sleep", "ok": False,
                    "says": t("sleep_after_says", minutes=minutes, unit=unit),
                    "do": t("sleep_after_do")}
        return {"id": "sleep", "ok": False, "says": t("sleep_unread_says"), "do": t("sleep_unread_do")}
    if os.name == "nt":
        return {"id": "sleep", "ok": False, "says": t("sleep_windows_says"), "do": t("sleep_windows_do")}
    return {"id": "sleep", "ok": False, "says": t("sleep_other_says"), "do": t("sleep_other_do")}


def check_handover(project: Path) -> list[dict]:
    """The phone cannot read a terminal. Finished things have to land in a file it can open."""
    out = project / OUT_DIR
    rules = project / "CLAUDE.md"
    found = []
    found.append({
        "id": "out-folder",
        "ok": out.is_dir(),
        "says": t("out_ok_says", out=OUT_DIR) if out.is_dir() else t("out_missing_says", out=OUT_DIR),
        "do": "" if out.is_dir() else t("out_missing_do", out=OUT_DIR),
    })
    has_rule = rules.is_file() and RULE_MARK in rules.read_text(encoding="utf-8", errors="ignore")
    found.append({
        "id": "handover-rule",
        "ok": has_rule,
        "says": t("rule_ok_says") if has_rule else t("rule_missing_says"),
        "do": "" if has_rule else t("rule_missing_do", out=OUT_DIR),
    })
    return found


def service_of(folder: Path, home: Path) -> str:
    """The name the person uses for the drive a folder sits in, or "" when we do not know it."""
    for service, pattern in CLOUD_PLACES:
        for hit in sorted(home.glob(pattern)):
            try:
                if folder == hit or folder.is_relative_to(hit):
                    return service
            except (OSError, ValueError):
                continue
    return ""


def find_shared(project: Path, named: str = "", home: Path | None = None):
    """The folder the phone and this computer share, and the drive behind it.

    Named by hand if the person named it; otherwise the handover folder when it already lives
    inside a cloud drive, and otherwise the cloud drive itself. Returns (folder, service),
    with folder None when nothing on this machine looks like a shared folder at all.
    """
    home = (home or Path.home()).expanduser()
    if named:
        folder = Path(named).expanduser()
        return folder, service_of(folder, home)

    drives: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for service, pattern in CLOUD_PLACES:
        for hit in sorted(home.glob(pattern)):
            if hit.is_dir() and str(hit) not in seen:
                seen.add(str(hit))
                drives.append((hit, service))

    out = project / OUT_DIR
    for drive, service in drives:
        try:
            if out.is_dir() and out.resolve().is_relative_to(drive.resolve()):
                return out, service
        except (OSError, ValueError):
            continue
    return drives[0] if drives else (None, "")


def folder_facts(folder: Path, cap: int = SCAN_CAP) -> dict:
    """How many files are in there and when anything last changed. Names and dates only.

    Nothing is opened and nothing is written. A file that a cloud drive is keeping in the
    cloud still has a name and a date on disk, which is all this needs.
    """
    files = 0
    newest = 0.0
    newest_name = ""
    capped = False
    stack = [folder]
    while stack:
        here = stack.pop()
        try:
            entries = list(os.scandir(here))
        except OSError:
            continue
        for entry in entries:
            name = os.path.basename(entry.path)
            if name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                    continue
                stamp = entry.stat(follow_symlinks=False).st_mtime
            except OSError:
                continue
            files += 1
            if stamp > newest:
                newest, newest_name = stamp, name
            if files >= cap:
                capped = True
                stack = []
                break
    return {"files": files, "newest": newest or None, "newest_name": newest_name,
            "capped": capped}


def when_words(stamp: float, now: float) -> str:
    """When something last changed, in the words a person would use out loud."""
    moment = dt.datetime.fromtimestamp(stamp)
    days = (dt.datetime.fromtimestamp(now).date() - moment.date()).days
    clock = moment.strftime("%H:%M")
    date = moment.strftime("%d.%m.%Y")
    if days <= 0:
        return t("when_today", clock=clock)
    if days == 1:
        return t("when_yesterday", clock=clock)
    if days < 14:
        return t("when_days", days=days, date=date)
    return t("when_long", date=date)


def check_sync(project: Path, named: str = "", home: Path | None = None,
               now: float | None = None) -> dict:
    """The folder the phone drops a photo into and the work reads at home.

    Whether a drive is really syncing that folder at this minute is not knowable from this
    machine: the app can be signed out, paused, out of space or quietly stuck, and the folder
    looks the same either way. So this check states only what is on the disk — the folder is
    here, it holds this many files, the last one changed then — and hands the person the one
    test that does prove it. It never says the word synced about something it has not seen.
    """
    folder, service = find_shared(project, named, home)
    if folder is None:
        return {"id": "sync", "ok": False, "says": t("sync_none_says"), "do": t("sync_none_do")}
    if not folder.is_dir():
        return {"id": "sync", "ok": False,
                "says": t("sync_absent_says", folder=folder), "do": t("sync_absent_do")}

    facts = folder_facts(folder)
    count = f"{facts['files']}+" if facts["capped"] else str(facts["files"])
    where = t("sync_where_service", service=service) if service else t("sync_where_plain")
    if facts["newest"]:
        last = when_words(facts["newest"], now if now is not None else time.time())
        says = t("sync_found_says", where=where, folder=folder, count=count,
                 files=t("sync_files_one") if count == "1" else t("sync_files_many"),
                 last=last, name=facts["newest_name"])
    else:
        says = t("sync_empty_says", where=where, folder=folder)
    do = t("sync_test_do")
    if service == "iCloud Drive":
        do += t("sync_icloud_do")
    if not service:
        do = t("sync_unknown_do") + do
    return {"id": "sync", "ok": True, "says": says, "do": do}


def collect(project: Path, shared: str = "", home: Path | None = None,
            trusted_devices: bool = False, managed_dir: str | Path | None = None) -> list[dict]:
    ver = claude_version()
    items = [check_place(project), check_version(ver)]
    items += check_quiet_killers(project, ver, trusted_devices, managed_dir)
    channels = check_channels(managed_dir)
    if channels:
        items.append(channels)
    items.append(check_sleep())
    items += check_handover(project)
    items.append(check_sync(project, shared, home))
    return items


def report(items: list[dict]) -> str:
    bad = [i for i in items if not i["ok"]]
    lines = [t("report_title"), ""]
    for i in items:
        lines.append((t("report_ok") if i["ok"] else t("report_not")) + i["says"])
        if i["do"]:
            lines.append("       → " + i["do"])
    lines.append("")
    if bad:
        lines.append(t("report_bad", bad=len(bad), total=len(items)))
    else:
        lines.append(t("report_ready"))
    lines.append("")
    lines.append(t("report_look_yourself"))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether this machine can be left working alone.")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    ap.add_argument("--dir", default=".", help="the project directory to check")
    ap.add_argument("--shared", default="",
                    help="the folder the phone also sees, when it is not found by itself")
    ap.add_argument("--lang", default=None, help="en, es, pt, ru or uk (default: the system's)")
    ap.add_argument("--trusted-devices", action="store_true",
                    help="the organization requires Trusted Devices for Remote Control")
    args = ap.parse_args()
    use_lang(pick_lang(args.lang))
    items = collect(Path(args.dir), args.shared, trusted_devices=args.trusted_devices)
    if args.json:
        print(json.dumps({"ready": all(i["ok"] for i in items), "checks": items},
                         ensure_ascii=False, indent=1, default=str))
    else:
        print(report(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
