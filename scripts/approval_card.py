#!/usr/bin/env python3
"""The approval card: what a person sees on the phone before saying yes.

A card holds the full command word for word, every file the action touches, and the diff behind a
third button. Three buttons: Yes, No, Show the diff. A card that had to be cut to fit a screen or a
message is marked incomplete, and an incomplete card offers no Yes: what cannot be read in full
is answered at the desk.
"""

from __future__ import annotations

import difflib
import shlex
import subprocess
from pathlib import Path

MAX_DIFF = 200_000          # characters of diff carried in one card
FILE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read")


def _path(cwd: str, name: str) -> Path:
    p = Path(name).expanduser()
    return p if p.is_absolute() else Path(cwd or ".") / p


def command_of(tool: str, data: dict) -> str:
    """The action, word for word, as one text."""
    if tool == "Bash":
        return str(data.get("command", ""))
    if tool in FILE_TOOLS:
        return f"{tool} {data.get('file_path') or data.get('notebook_path') or ''}".strip()
    if tool == "WebFetch":
        return f"WebFetch {data.get('url', '')}"
    return f"{tool} " + " ".join(f"{k}={v}" for k, v in sorted(data.items()) if isinstance(v, (str, int, float)))


def files_of(tool: str, data: dict, cwd: str) -> list[str]:
    """Every file the action names: the target of a file tool, or each word of a shell command that
    is an existing path or is written as one (has a slash or an extension)."""
    if tool in FILE_TOOLS:
        name = data.get("file_path") or data.get("notebook_path")
        return [str(name)] if name else []
    if tool != "Bash":
        return []
    try:
        words = shlex.split(str(data.get("command", "")), comments=True)
    except ValueError:
        words = str(data.get("command", "")).split()
    found = []
    for w in words:
        if w.startswith("-") or w in found or any(c in w for c in "|&;<>$`*"):
            continue
        looks = "/" in w or ("." in w.strip(".") and not w.replace(".", "").isdigit())
        if _path(cwd, w).exists() and (looks or _path(cwd, w).is_file()) or (looks and len(w) > 2):
            found.append(w)
    return found


def diff_of(tool: str, data: dict, cwd: str) -> str:
    """What changes: the edit itself for a file tool, the folder's uncommitted diff for a command."""
    if tool in ("Edit", "Write", "MultiEdit"):
        name = str(data.get("file_path", ""))
        target = _path(cwd, name)
        try:
            before = target.read_text(encoding="utf-8")
        except OSError:
            before = ""
        if tool == "Write":
            after = str(data.get("content", ""))
        else:
            edits = data.get("edits") if tool == "MultiEdit" else [data]
            after = before
            for e in edits or []:
                old, new = str(e.get("old_string", "")), str(e.get("new_string", ""))
                after = after.replace(old, new) if e.get("replace_all") else after.replace(old, new, 1)
            if not before:
                return "\n".join(f"- {e.get('old_string', '')}\n+ {e.get('new_string', '')}" for e in edits or [])
        return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                            f"a/{name}", f"b/{name}"))
    if tool == "Bash":
        try:
            done = subprocess.run(["git", "diff", "HEAD"], cwd=cwd or None, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=10)
            return done.stdout if done.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    return ""


def build(hook: dict, ask_id: str) -> dict:
    """A PermissionRequest hook's input -> the card."""
    tool = str(hook.get("tool_name", ""))
    data = hook.get("tool_input") or {}
    cwd = str(hook.get("cwd", ""))
    diff = diff_of(tool, data, cwd)
    complete = len(diff) <= MAX_DIFF
    return {
        "id": ask_id,
        "tool": tool,
        "command": command_of(tool, data),
        "files": files_of(tool, data, cwd),
        "diff": diff[:MAX_DIFF],
        "folder": cwd,
        "complete": complete,
    }


def text_of(card: dict, words: dict) -> str:
    """The card as plain text for a messenger, in the person's language."""
    lines = [words["approve_title"], "", words["approve_command"], card["command"], ""]
    lines.append(words["approve_files"])
    lines += [f"- {f}" for f in card["files"]] or [words["approve_no_files"]]
    if card.get("folder"):
        lines += ["", words["approve_folder"].format(path=card["folder"])]
    return "\n".join(lines)


def chunks(text: str, size: int) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]
