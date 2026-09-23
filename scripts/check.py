#!/usr/bin/env python3
"""Pocketcall readiness check.

Six things decide whether an evening away from the desk works. Five of them fail silently:
the person walks out of the house believing the remote is on, and finds out in town that it
is not. This script looks at all six on this machine and says, in plain words, which ones
are not ready and what to do about each.

Nothing here talks to the network, reads a conversation, or changes a setting. It reads
local files and runs `claude --version` and, on a Mac, `pmset -g custom`. It prints a report
for a person, and with --json the same findings for a program.

Run:  python3 check.py [--json] [--dir <project directory>]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
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


def collect(project: Path) -> list[dict]:
    items = [check_place(project), check_version()]
    items += check_quiet_killers(project)
    items.append(check_sleep())
    items += check_handover(project)
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
                 "notifications are allowed there, and how much of your allowance is left. "
                 "Those you look at yourself, and the evening says how.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether this machine can be left working alone.")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    ap.add_argument("--dir", default=".", help="the project directory to check")
    args = ap.parse_args()
    items = collect(Path(args.dir))
    if args.json:
        print(json.dumps({"ready": all(i["ok"] for i in items), "checks": items},
                         ensure_ascii=False, indent=1))
    else:
        print(report(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
