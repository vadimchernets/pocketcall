#!/usr/bin/env python3
"""Pocketcall readiness check.

Seven things decide whether an evening away from the desk works. Six of them fail silently:
the person walks out of the house believing the remote is on, and finds out in town that it
is not. This script looks at all seven on this machine and says, in plain words, which ones
are not ready and what to do about each.

Nothing here talks to the network, reads a conversation, or changes a setting. It reads
local files, runs `claude --version` and, on a Mac, `pmset -g custom`, and lists the names
and dates of the shared folder without opening anything inside it. It prints a report for a
person, and with --json the same findings for a program.

Run:  python3 check.py [--json] [--dir <project directory>] [--shared <shared folder>]
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

# Environment variables that each switch off the feature-flag evaluation Remote Control
# needs, or point the client somewhere it cannot be used from. Set in a shell profile or in
# the "env" block of a settings file, they produce no error: the remote simply never comes up.
KILLERS = (
    "DISABLE_TELEMETRY",
    "DO_NOT_TRACK",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "DISABLE_GROWTHBOOK",
)
REDIRECTS = ("ANTHROPIC_BASE_URL",)
NOT_A_SUBSCRIPTION = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
OTHER_CLOUDS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")

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


def settings_env(path: Path) -> dict:
    """The env block of a settings file, or {} when there is no readable file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    env = data.get("env")
    return env if isinstance(env, dict) else {}


def settings_flag(path: Path, key: str):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get(key)


def parse_version(text: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(g) for g in m.groups()) if m else None


def check_place(project: Path) -> dict:
    """A remote session has to start from a project directory, not from the home folder."""
    home = Path.home().resolve()
    here = project.resolve()
    if here == home:
        return {
            "id": "place",
            "ok": False,
            "says": "Claude Code is sitting in your home folder, not in a work folder.",
            "do": "Make or open a work folder and start there. The trust question that a "
                  "remote session needs is never remembered for the home folder.",
        }
    return {"id": "place", "ok": True, "says": f"Work folder: {here}", "do": ""}


def check_version() -> dict:
    text = run(["claude", "--version"])
    ver = parse_version(text)
    if not ver:
        return {
            "id": "version",
            "ok": False,
            "says": "Could not ask Claude Code for its version.",
            "do": "Open a new terminal window and try again. If the word claude is not "
                  "found there either, Claude Code is installed somewhere this terminal "
                  "does not look.",
        }
    if ver < MIN_VERSION:
        return {
            "id": "version",
            "ok": False,
            "says": f"Claude Code {'.'.join(map(str, ver))} is older than this evening needs.",
            "do": "Update Claude Code, then run this check again.",
        }
    return {"id": "version", "ok": True, "says": f"Claude Code {'.'.join(map(str, ver))}", "do": ""}


def check_quiet_killers(project: Path) -> list[dict]:
    """The silent ones. Each of these turns the remote off without saying anything."""
    found: list[dict] = []
    files = [Path.home() / ".claude" / "settings.json",
             project / ".claude" / "settings.json",
             project / ".claude" / "settings.local.json"]
    from_files: dict[str, str] = {}
    for f in files:
        for k, v in settings_env(f).items():
            from_files[k] = f"{f}"

    for name in KILLERS:
        where = "this terminal" if os.environ.get(name) else from_files.get(name)
        if where:
            found.append({
                "id": f"env:{name}",
                "ok": False,
                "says": f"{name} is set in {where}.",
                "do": "Remote Control needs the setting that this switches off. Unset it "
                      "where it is set, then start Claude Code again.",
            })
    for name in REDIRECTS:
        where = "this terminal" if os.environ.get(name) else from_files.get(name)
        if where:
            found.append({
                "id": f"env:{name}",
                "ok": False,
                "says": f"{name} is set in {where}.",
                "do": "The remote works only against Anthropic's own address. Unset this "
                      "and start Claude Code again.",
            })
    for name in NOT_A_SUBSCRIPTION:
        if os.environ.get(name):
            found.append({
                "id": f"env:{name}",
                "ok": False,
                "says": f"{name} is set in this terminal.",
                "do": "The remote works on a personal subscription, not on an API key. "
                      "Unset it and sign in with /login instead.",
            })
    for name in OTHER_CLOUDS:
        if os.environ.get(name):
            found.append({
                "id": f"env:{name}",
                "ok": False,
                "says": f"{name} is set in this terminal.",
                "do": "The remote is not available through another company's cloud. "
                      "Unset it and use your own subscription.",
            })
    for f in files:
        if settings_flag(f, "disableRemoteControl") is True:
            found.append({
                "id": "setting:disableRemoteControl",
                "ok": False,
                "says": f"disableRemoteControl is true in {f}.",
                "do": "Someone, possibly a past you, turned the remote off in writing. "
                      "Set it to false or remove the line.",
            })
    if not found:
        found.append({
            "id": "quiet",
            "ok": True,
            "says": "Nothing on this machine is quietly switching the remote off.",
            "do": "",
        })
    return found


def check_sleep() -> dict:
    """A sleeping computer does no work. On a Mac we can read the setting; elsewhere we ask."""
    if sys.platform == "darwin":
        text = run(["pmset", "-g", "custom"])
        block = text.split("AC Power:", 1)[-1] if "AC Power:" in text else text
        m = re.search(r"^\s*sleep\s+(\d+)", block, re.M)
        if m:
            minutes = int(m.group(1))
            if minutes == 0:
                return {"id": "sleep", "ok": True,
                        "says": "On mains power this Mac does not go to sleep by itself.", "do": ""}
            return {
                "id": "sleep", "ok": False,
                "says": f"On mains power this Mac sleeps after {minutes} "
                        f"minute{'' if minutes == 1 else 's'}.",
                "do": "While you are away the work stops when it sleeps. Nothing is lost and "
                      "it reconnects when the machine wakes, but the time is. Set sleep to "
                      "Never for mains power in System Settings, and leave the lid open.",
            }
        return {"id": "sleep", "ok": False,
                "says": "Could not read this Mac's sleep setting.",
                "do": "Check System Settings and set sleep to Never while on mains power."}
    if os.name == "nt":
        return {"id": "sleep", "ok": False,
                "says": "On Windows this check cannot read your power plan for you.",
                "do": "Open Power & sleep settings, set both screen and sleep to Never while "
                      "plugged in, and leave the lid open."}
    return {"id": "sleep", "ok": False,
            "says": "This check does not read power settings on this system.",
            "do": "Turn off automatic sleep while the machine is on mains power."}


def check_handover(project: Path) -> list[dict]:
    """The phone cannot read a terminal. Finished things have to land in a file it can open."""
    out = project / OUT_DIR
    rules = project / "CLAUDE.md"
    found = []
    found.append({
        "id": "out-folder",
        "ok": out.is_dir(),
        "says": f"{OUT_DIR}/ exists." if out.is_dir() else f"There is no {OUT_DIR}/ folder here.",
        "do": "" if out.is_dir() else
              f"Make a folder called {OUT_DIR} inside a folder your phone can already see "
              "(the one your cloud drive syncs). Everything finished goes there as a file.",
    })
    has_rule = rules.is_file() and RULE_MARK in rules.read_text(encoding="utf-8", errors="ignore")
    found.append({
        "id": "handover-rule",
        "ok": has_rule,
        "says": "The handover rule is in CLAUDE.md." if has_rule else
                "CLAUDE.md does not mention the handover rule.",
        "do": "" if has_rule else
              "Add two lines to CLAUDE.md: everything finished is written to a file in "
              f"{OUT_DIR}/ with a one-line summary on the first line, and the answer in the "
              "conversation stays short enough to read on a phone.",
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
    if days <= 0:
        return f"today at {clock}"
    if days == 1:
        return f"yesterday at {clock}"
    if days < 14:
        return f"{days} days ago, on {moment.strftime('%d.%m.%Y')}"
    return f"on {moment.strftime('%d.%m.%Y')}"


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
        return {
            "id": "sync",
            "ok": False,
            "says": "Found no folder on this machine that a phone also sees.",
            "do": "This is how a photo taken in town reaches the work at home. Make a folder "
                  "in Google Drive or Dropbox, put the same app on the phone, and run this "
                  "check again with --shared and the folder. Not iCloud Drive if the phone "
                  "you carry is an Android one: iCloud has no app there.",
        }
    if not folder.is_dir():
        return {
            "id": "sync",
            "ok": False,
            "says": f"The shared folder {folder} is not here.",
            "do": "Anything the phone puts in a folder by that name goes nowhere you will "
                  "find it. Open the drive's app, read the folder's real name, and run this "
                  "check again with --shared and that name.",
        }

    facts = folder_facts(folder)
    count = f"{facts['files']}+" if facts["capped"] else str(facts["files"])
    where = f"{service} folder" if service else "Shared folder"
    if facts["newest"]:
        last = when_words(facts["newest"], now if now is not None else time.time())
        says = (f"{where}: {folder} — {count} file{'' if count == '1' else 's'}, "
                f"last change {last} ({facts['newest_name']}).")
    else:
        says = f"{where}: {folder} — empty, so there is no date to show you."
    do = ("Whether the drive is really carrying this folder to your phone right now, nothing "
          "on this machine can prove. The test takes a second and you do it before you leave: "
          "put one photo in from the phone and watch the line above change. If it does not, "
          "the sync is stuck and you would have been dropping things into nowhere all evening.")
    if service == "iCloud Drive":
        do += (" And this is iCloud Drive, which has no Android app at all: if the phone in "
               "your pocket is an Android one, choose Google Drive or Dropbox instead.")
    if not service:
        do = ("Nothing on this machine says this folder is shared with anything — it may be "
              "an ordinary folder that only this computer can see. Check in the drive's own "
              "app that this is the folder it syncs. ") + do
    return {"id": "sync", "ok": True, "says": says, "do": do}


def collect(project: Path, shared: str = "", home: Path | None = None) -> list[dict]:
    items = [check_place(project), check_version()]
    items += check_quiet_killers(project)
    items.append(check_sleep())
    items += check_handover(project)
    items.append(check_sync(project, shared, home))
    return items


def report(items: list[dict]) -> str:
    bad = [i for i in items if not i["ok"]]
    lines = ["POCKETCALL — is this machine ready to be left alone?", ""]
    for i in items:
        lines.append(("  ok   " if i["ok"] else "  NOT  ") + i["says"])
        if i["do"]:
            lines.append("       → " + i["do"])
    lines.append("")
    if bad:
        lines.append(f"{len(bad)} of {len(items)} not ready. Fix those, then run this again.")
    else:
        lines.append("All ready. The remote itself is turned on with /remote-control, "
                     "and the phone joins by scanning the code it shows.")
    lines.append("")
    lines.append("What this check cannot see: whether you are signed in on the phone, whether "
                 "notifications are allowed there, whether the shared folder is really syncing "
                 "at this minute, and how much of your allowance is left. Those you look at "
                 "yourself, and the evening says how.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether this machine can be left working alone.")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    ap.add_argument("--dir", default=".", help="the project directory to check")
    ap.add_argument("--shared", default="",
                    help="the folder the phone also sees, when it is not found by itself")
    args = ap.parse_args()
    items = collect(Path(args.dir), args.shared)
    if args.json:
        print(json.dumps({"ready": all(i["ok"] for i in items), "checks": items},
                         ensure_ascii=False, indent=1))
    else:
        print(report(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
