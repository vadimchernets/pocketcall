#!/usr/bin/env python3
"""Voice -> task -> pull request -> Yes from the phone.

A voice note becomes a task in the company's tracker; a cloud session (branch B) or a session on a
computer that stays on picks it up and opens a pull request; and the phone gets branch D's approval
card for that pull request: the steps Yes runs word for word, every file, the diff behind a button,
the task's words, Yes / No / Show the diff. Yes merges exactly the commit the card showed - at once,
or, where the repository's checks are still running, the moment they pass; No leaves a comment and
the pull request open. Each step of a task also comes back to the phone.

    task.py setup --github acme/site [--label pocketcall] [--merge squash] [--folder <checkout>]
                  [--who "Ann"] [--allow "Bash(npm test)"]
                  [--routine <the routine's API trigger URL> --routine-token <its token>]
    task.py setup --webhook https://tracker.example.com/in --repo acme/site [--secret <key>]
                  [--header "Name: value"]
    task.py file "the words, unchanged"     or --from <file>, or the words on standard input
    task.py start <task> --cloud            a cloud session takes it: the laptop may sleep from here
    task.py start <task> --home             a session on this computer, in a git worktree of its own
    task.py card <pull request>             its approval card on the phone; the answer is carried out
    task.py watch [--start cloud|home]      the desk: notes from the phone page become tasks, tasks
                                            get a session, every pull request for a task gets a card
    task.py list

The tracker is GitHub Issues through the GitHub CLI and its own sign-in (`gh auth login`), or any
other tracker through a webhook: a JSON POST, signed HMAC-SHA256 when a secret is set. A cloud
session starts through a routine's API trigger (code.claude.com/docs/en/routines) when one is set,
which needs no terminal and no Claude Code on the desk machine, or else through `claude --cloud`
given a terminal of its own. The desk runs wherever something stays on - this computer, or the
machine that runs the relay, joined to the phone with `remote.py join --link <the phone link>` - and
then the laptop may sleep through all of it. Several desks on one phone take turns through the
relay, one at a time, and the computers share their tasks through it, sealed. Settings live in
~/.pocketcall/task.json, the record of tasks and cards in ~/.pocketcall/tasks.json, the desk's own
copy of the repository in ~/.pocketcall/repos (POCKETCALL_HOME moves the folder), readable by this
user only. POCKETCALL_GH and POCKETCALL_CLAUDE name another command for gh and for claude.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import select
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import approval_card  # noqa: E402
import check  # noqa: E402
import remote  # noqa: E402

TRACKERS = ("github", "webhook")
MERGES = ("squash", "merge", "rebase")
STARTS = ("cloud", "home")
SOURCES = ("phone", "voice", "file", "tracker")
TASK_STATES = ("filed", "started", "pr", "merged", "no-change", "stopped")
CARD_STATES = ("sent", "approved", "merged", "declined", "refused", "replaced")
EVENTS = ("filed", "started", "pull_request", "approved", "merged", "declined", "refused", "replaced",
          "no-change", "stopped")
DONE = ("merged", "no-change", "stopped")      # a task in one of these has no more news to bring

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
URL = re.compile(r"https?://[^\s<>\"']+")
SESSION = re.compile(r"https://claude\.ai/code/(?:session_|cse_)[A-Za-z0-9_-]+")
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+"
                     r"(?:https?://\S+/issues/|[\w.-]+/[\w.-]+#|#)(\d+)\b", re.IGNORECASE)
MARK = "<!-- pocketcall -->"   # written under the words of each issue it files: where the words end
NOTE_MARK = "<!-- pocketcall-note: {nid} -->"   # the phone note an issue came from: filed once
SIGNATURE = "X-Pocketcall-Signature-256"
LABEL_COLOR = "1f7a3a"
TITLE = 72                     # characters of the first line that make a task's title
SAID = 4000                    # characters of a session's own summary carried into a pull request
CLOUD_WAIT = 180               # seconds `claude --cloud` has to show the new session's link
SESSION_GRACE = 3              # seconds it keeps after the link, to finish handing the task over
HOME_WAIT = 3600               # seconds a session on this computer has for one task
BRANCH_GRACE = 300             # seconds a pushed branch has to bring its own pull request
START_TRIES = 3                # times the desk tries to start a cloud session for one task
START_AGAIN = 600              # seconds before the next try, times the tries so far
ROUTINE_TEXT = 65536           # characters a routine's fire text may carry
ROUTINE_BETA = "experimental-cc-routine-2026-04-01"
NOTE_LEASE = 120               # seconds a note handed to this desk stays out of the other desks' sight
HELD_EVERY = 15                # seconds between two looks at the checks a kept Yes waits for
PR_FIELDS = ("number,title,url,headRefName,headRefOid,baseRefName,isDraft,state,files,changedFiles,"
             "author,isCrossRepository")
LIST_FIELDS = "number,title,body,url,headRefName,headRefOid,isDraft,author,isCrossRepository"
VIEW_FIELDS = "state,url,headRefOid,mergeStateStatus,statusCheckRollup"
PENDING = ("QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED", "EXPECTED")
FAILED = ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE")
RECORD_LOCK = threading.Lock()  # the desk's threads share the record
GIT_LOCK = threading.Lock()     # worktrees share one repository's config and refs


class TaskError(Exception):
    """A step that did not happen, said in the person's language."""


# --- settings and the record -------------------------------------------------------------------

def settings_path() -> Path:
    return remote.home() / "task.json"


def record_path() -> Path:
    return remote.home() / "tasks.json"


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def load_settings() -> dict:
    return _read(settings_path())


def save_settings(cfg: dict) -> None:
    _write(settings_path(), cfg)


def read_record() -> dict:
    rec = _read(record_path())
    for part in ("tasks", "cards", "notes"):
        if not isinstance(rec.get(part), dict):
            rec[part] = {}
    return rec


def change_record(change) -> dict:
    """Read, change and write the record under one lock."""
    with RECORD_LOCK:
        rec = read_record()
        change(rec)
        _write(record_path(), rec)
        return rec


def save_task(task: dict) -> None:
    """Into the record, stamped: the newer stamp wins when computers compare their tasks."""
    task["updated"] = stamp()
    change_record(lambda rec: rec["tasks"].__setitem__(task["key"], task))


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stamp() -> str:
    return f"{now()}.{time.time_ns() % 10**9:09d}"


# --- the programs it runs ----------------------------------------------------------------------

def command_of(variable: str, default: str) -> list:
    return shlex.split(os.environ.get(variable) or default, posix=os.name != "nt")


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run(cmd: list, cwd=None, stdin: str | None = None, timeout: float = 120) -> tuple:
    """(exit code, output, errors): 127 when the program is not there, 124 when its time ran out.
    Without text to feed, standard input is empty, so nothing ever waits for a keyboard."""
    feed = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    try:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, **feed)
    except subprocess.TimeoutExpired as exc:
        return 124, _text(exc.stdout), _text(exc.stderr)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)
    return done.returncode, done.stdout or "", done.stderr or ""


def run_in_terminal(cmd: list, cwd, timeout: float, until) -> tuple:
    """(exit code, what it printed) for a program that only does its work in a terminal: it gets a
    pseudo-terminal of its own (the standard library's pty), as `claude --cloud` creates a session
    only there - piped, it turns into --print and stops (github.com/anthropics/claude-code/issues/77751).
    Read until `until` shows up, then the program is let go; 124 when the time ran out first. Where
    no terminal can be made (Windows), it runs plainly."""
    try:
        import fcntl
        import pty
        import struct
        import termios
        master, slave = pty.openpty()
    except (ImportError, OSError):
        code, out, err = run(cmd, cwd=cwd, timeout=timeout)
        return code, out + "\n" + err
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 250, 0, 0))   # wide: no link is wrapped
    except OSError:
        pass
    try:
        env = dict(os.environ, TERM=os.environ.get("TERM") or "xterm-256color")
        proc = subprocess.Popen(cmd, cwd=cwd, stdin=slave, stdout=slave, stderr=slave, close_fds=True,
                                start_new_session=True, env=env)
    except OSError as exc:
        os.close(slave)
        os.close(master)
        return 127, str(exc)
    os.close(slave)
    seen, found, late = b"", None, False
    end = time.monotonic() + timeout
    try:
        while time.monotonic() < end:
            ready, _, _ = select.select([master], [], [], max(0.0, min(0.5, end - time.monotonic())))
            if not ready:
                if proc.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError:            # the program closed its terminal
                chunk = b""
            if not chunk:
                break
            seen += chunk
            if found is None and until.search(ANSI.sub("", seen.decode("utf-8", errors="replace"))):
                found = time.monotonic()
                end = min(end, found + SESSION_GRACE)
        else:
            late = found is None
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        os.close(master)
    text = ANSI.sub("", seen.decode("utf-8", errors="replace")).replace("\r", "")
    return (124 if late else proc.returncode), text


def gh(*args: str, stdin: str | None = None, timeout: float = 120) -> tuple:
    return run(command_of("POCKETCALL_GH", "gh") + list(args), stdin=stdin, timeout=timeout)


def git(folder, *args: str) -> tuple:
    return run(["git", "-C", str(folder)] + list(args))


def first_line(text) -> str:
    return next((line.strip() for line in str(text).splitlines() if line.strip()), "-")[:300]


def last_line(text) -> str:
    return next((line.strip() for line in reversed(str(text).splitlines()) if line.strip()), "-")[:300]


def last_url(text: str) -> str:
    found = URL.findall(text or "")
    return found[-1].rstrip(".,);") if found else ""


def gh_failed(words: dict, code: int, err: str, out: str = "") -> TaskError:
    if code == 127:
        return TaskError(words["task_need_gh"])
    return TaskError(words["task_gh_failed"].format(why=first_line(err or out)))


def login_of(pr: dict) -> str:
    author = pr.get("author")
    return str(author.get("login") or "") if isinstance(author, dict) else ""


# --- a voice note becomes a task ---------------------------------------------------------------

def title_of(text: str) -> str:
    line = next((part.strip() for part in text.splitlines() if part.strip()), "")
    if len(line) <= TITLE:
        return line
    cut = line[:TITLE - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:-") + "…"


def footer(cfg: dict, words: dict, source: str, name: str = "") -> str:
    origin = {"phone": words["task_from_phone"], "voice": words["task_from_voice"],
              "file": words["task_from_file"].format(name=name)}.get(source, source)
    when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    if cfg.get("who"):
        return words["task_footer_who"].format(who=cfg["who"], source=origin, when=when)
    return words["task_footer"].format(source=origin, when=when)


def pick(reply: dict, names) -> str:
    for name in names:
        value = reply.get(name)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip():
            return str(value).strip()
    return ""


def make_label(repo: str, label: str, words: dict) -> None:
    gh("label", "create", label, "--repo", repo, "--color", LABEL_COLOR,
       "--description", words["task_label"], "--force")


def filed_before(cfg: dict, nid: str) -> tuple:
    """(number, link) of the issue a phone note already became - on any computer - or ("", "")."""
    code, out, _ = gh("issue", "list", "--repo", cfg.get("repo", ""), "--state", "all", "--search",
                      f'"{nid}" in:body', "--json", "number,url,body", "--limit", "5")
    try:
        found = json.loads(out) if code == 0 else []
    except ValueError:
        found = []
    for issue in found if isinstance(found, list) else []:
        if isinstance(issue, dict) and NOTE_MARK.format(nid=nid) in str(issue.get("body") or ""):
            return str(issue.get("number") or ""), str(issue.get("url") or "")
    return "", ""


def file_issue(cfg: dict, words: dict, title: str, body: str) -> tuple:
    repo, label = cfg.get("repo", ""), cfg.get("label", "")
    args = ["issue", "create", "--repo", repo, "--title", title, "--body-file", "-"]
    if label:
        args += ["--label", label]
    code, out, err = gh(*args, stdin=body)
    if code not in (0, 127) and label and "label" in (err + out).lower():
        make_label(repo, label, words)            # a label the repository did not have: made once
        code, out, err = gh(*args, stdin=body)
    if code != 0:
        raise gh_failed(words, code, err, out)
    url = last_url(out)
    found = re.search(r"/issues/(\d+)", url)
    if not found:
        raise TaskError(words["task_gh_failed"].format(why=first_line(out + err)))
    return found.group(1), url


def post_webhook(cfg: dict, words: dict, payload: dict) -> dict:
    """One JSON POST to the tracker's address, signed when a secret is set; its reply, when JSON."""
    hook = cfg.get("webhook") or {}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "pocketcall"}
    headers.update({str(k): str(v) for k, v in (hook.get("headers") or {}).items()})
    if hook.get("secret"):
        digest = hmac.new(str(hook["secret"]).encode("utf-8"), data, hashlib.sha256).hexdigest()
        headers[SIGNATURE] = "sha256=" + digest
    try:
        req = urllib.request.Request(str(hook.get("url", "")), data=data, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except (OSError, ValueError) as exc:
        raise TaskError(words["task_webhook_failed"].format(why=first_line(str(exc)))) from None
    try:
        reply = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return reply if isinstance(reply, dict) else {}


def file_task(cfg: dict, words: dict, text: str, source: str, name: str = "", note: str = "") -> dict:
    """The words, unchanged, become a task in the tracker, and the task goes into the record. A note
    from the phone carries its id into the issue, so a note two desks both saw is filed once."""
    text = str(text).strip()
    if not text:
        raise TaskError(words["task_no_words"])
    if cfg.get("tracker") not in TRACKERS:
        raise TaskError(words["task_no_tracker"])
    title = title_of(text)
    signed = footer(cfg, words, source, name)
    if cfg["tracker"] == "github":
        key, url = filed_before(cfg, note) if note else ("", "")
        if not key:
            noted = "\n" + NOTE_MARK.format(nid=note) if note else ""
            key, url = file_issue(cfg, words, title, text + "\n\n" + MARK + "\n" + signed + noted)
        ref = "#" + key
    else:
        reply = post_webhook(cfg, words, {
            "event": "filed", "title": title, "words": text, "body": text + "\n\n" + signed,
            "source": source, "who": cfg.get("who", ""), "repo": cfg.get("repo", ""), "note": note,
            "labels": [cfg["label"]] if cfg.get("label") else [], "filed_at": now()})
        key = pick(reply, ("key", "identifier", "number", "iid", "id")) or "t" + uuid.uuid4().hex[:8]
        url = pick(reply, ("html_url", "web_url", "webUrl", "url", "link", "self"))
        ref = key
    task = {"key": key, "ref": ref, "url": url, "title": title, "words": text, "source": source,
            "state": "filed", "filed_at": now()}
    if note:
        task["note"] = note
    task["last"] = task["told"] = words["task_filed"].format(ref=ref, url=url or "-")
    save_task(task)
    return task


def journal(cfg: dict, words: dict, task: dict, event: str, text: str, close: bool = False) -> None:
    """The task's journal, for whoever reads the tracker: a comment on the issue (closing it after a
    merge), or the same event to the webhook. A journal line that does not arrive stops nothing."""
    if cfg.get("tracker") == "github":
        repo = cfg.get("repo", "")
        if close:
            gh("issue", "close", task["key"], "--repo", repo, "--comment", text)
        else:
            gh("issue", "comment", task["key"], "--repo", repo, "--body-file", "-", stdin=text)
        return
    try:
        post_webhook(cfg, words, {"event": event, "task": task["key"], "url": task.get("url", ""),
                                  "text": text, "at": now()})
    except TaskError:
        pass


def issue_task(cfg: dict, words: dict, key: str, ours_only: bool = False) -> dict | None:
    """An issue in the tracker as a task; with ours_only, only one Pocketcall filed (its body carries
    the mark). None when there is no such issue."""
    code, out, err = gh("issue", "view", key, "--repo", cfg.get("repo", ""), "--json", "number,title,body,url")
    if code == 127:
        raise TaskError(words["task_need_gh"])
    try:
        info = json.loads(out) if code == 0 else {}
    except ValueError:
        info = {}
    if not isinstance(info, dict) or not info.get("number"):
        return None
    title, body = str(info.get("title") or ""), str(info.get("body") or "").replace("\r\n", "\n")
    if MARK in body:
        text = body.split("\n\n" + MARK, 1)[0].strip()
        found = re.search(NOTE_MARK.format(nid="([0-9A-Za-z_-]+)"), body)
    elif ours_only:
        return None
    else:
        text, found = "\n\n".join(part for part in (title, body.strip()) if part), None
    task = {"key": key, "ref": "#" + key, "url": str(info.get("url") or ""), "title": title,
            "words": text, "source": "tracker", "state": "filed", "filed_at": now()}
    if found:
        task["note"] = found.group(1)
    return task


def find_task(cfg: dict, words: dict, key: str) -> dict:
    """A task from this computer's record, or an issue someone filed in the tracker directly."""
    key = str(key).strip()
    if "/issues/" in key:
        key = key.rstrip("/").rsplit("/", 1)[-1]
    key = key.lstrip("#")
    known = read_record()["tasks"].get(key)
    if known:
        return known
    if cfg.get("tracker") == "github" and key.isdigit():
        task = issue_task(cfg, words, key)
        if task is not None:
            task["last"] = task["told"] = words["task_filed"].format(ref=task["ref"], url=task["url"] or "-")
            save_task(task)
            return task
    raise TaskError(words["task_unknown"].format(key=key))


def share(rcfg: dict, task: dict) -> None:
    """The task, sealed with the phone's key, onto the relay: a desk on another computer that shares
    the phone finds it there and carries it on while this one sleeps."""
    if not (rcfg.get("relay") and rcfg.get("secret")):
        return
    relay = remote.Relay(rcfg["relay"], rcfg["secret"])
    box = relay.pair.seal({"kind": "task", "task": task})
    try:
        remote._http(f"{relay.url}/r/{relay.pair.room}/task", {"id": "t-" + key_slug(task["key"])[:60], "box": box},
                     15)
    except (OSError, ValueError):
        pass


# --- a session picks the task up --------------------------------------------------------------

def slug(text: str, size: int) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:size].strip("-")


def key_slug(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(key)).strip("-") or "task"


def branch_of(task: dict) -> str:
    tail = slug(task.get("title", ""), 32)
    return f"pocketcall/{key_slug(task['key'])}" + (f"-{tail}" if tail else "")


def branch_mark(task: dict) -> str:
    return r"pocketcall[/-]" + re.escape(key_slug(task["key"])) + r"(?![A-Za-z0-9])"


def closing_of(cfg: dict, task: dict) -> str:
    if cfg.get("tracker") == "github":
        return f"Closes #{task['key']}"
    return f"Task: {task.get('url') or task['key']}"


def belongs(cfg: dict, task: dict, title: str, body: str, branch: str) -> bool:
    """A pull request or a branch is this task's when its branch carries pocketcall-<key>, when it
    closes the issue, or when it names the task."""
    if re.search(branch_mark(task), branch or "", re.IGNORECASE):
        return True
    text = f"{title}\n{body}"
    if cfg.get("tracker") == "github":
        return str(task["key"]) in CLOSING.findall(text)
    names = [name for name in (task.get("url"), task["key"]) if name]
    return any(re.search(r"Task:\s*" + re.escape(name) + r"(?![A-Za-z0-9])", text) for name in names)


def trusted(task: dict, pr: dict, me: str) -> bool:
    """Whether a pull request may be linked to the task without anyone asking: never one from a fork
    (a task's session pushes to the repository itself), and one by somebody else only when its branch
    carries pocketcall-<key>. Any other pull request reaches the phone only through
    `task.py card <n>`, its heading naming the author and the fork."""
    if pr.get("isCrossRepository"):
        return False
    author = login_of(pr)
    if me and author and author.lower() == me.lower():
        return True
    return bool(re.search(branch_mark(task), str(pr.get("headRefName") or ""), re.IGNORECASE))


def prompt_of(cfg: dict, task: dict, home: bool) -> str:
    """What the session reads: the words unchanged, and the few rules that keep its result
    reviewable on a phone."""
    where = f" ({task['url']})" if task.get("url") else ""
    lines = [f"Task {task['ref']}{where} from the company's tracker. The words, unchanged:", "", task["words"], ""]
    if home:
        lines += [
            f"You are in a git worktree made for this task, on the branch {task['branch']}.",
            "1. Make the change these words ask for, and nothing else. Where they can be read two ways, "
            "take the smaller reading and put the question in your last lines.",
            "2. Run the project's own tests if it has them.",
            "3. Leave committing, pushing and the pull request to Pocketcall: it does them when you finish, "
            "and the person approves the pull request from the phone, on a card with every file and the whole diff.",
            "4. End with three plain lines on what changed; they go into the pull request description.",
        ]
    else:
        lines += [
            f"1. Work on a new branch named {task['branch']} (if this environment needs another prefix, keep "
            f"pocketcall-{key_slug(task['key'])} in the name), started from the default branch; leave the "
            "default branch as it is.",
            "2. Make the change these words ask for, and nothing else. Where they can be read two ways, "
            "take the smaller reading and write the question into the pull request description.",
            "3. Run the project's own tests if it has them.",
            f"4. Push the branch and open a pull request, not a draft, whose description starts with the line "
            f"\"{closing_of(cfg, task)}\", then three plain lines on what changed.",
            "The person approves the pull request from the phone, on a card with every file and the whole diff, "
            "so keep it to what the task asks.",
        ]
    return "\n".join(lines)


def fire_routine(cfg: dict, words: dict, text: str) -> str:
    """The task to the routine's API trigger -> the new session's link. The routine was made once at
    claude.ai/code/routines on the repository; it clones the default branch, runs on the person's own
    plan, and its saved prompt carries out the task in the fire text
    (platform.claude.com/docs/en/api/claude-code/routines-fire)."""
    routine = cfg.get("routine") or {}
    headers = {"Authorization": "Bearer " + str(routine.get("token", "")), "anthropic-version": "2023-06-01",
               "anthropic-beta": ROUTINE_BETA, "Content-Type": "application/json", "User-Agent": "pocketcall"}
    req = urllib.request.Request(str(routine.get("url", "")), data=json.dumps({"text": text}).encode("utf-8"),
                                 method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            said = json.loads(exc.read() or b"{}").get("error", {}).get("message", "")
        except (ValueError, AttributeError, OSError):
            said = ""
        raise TaskError(words["task_session_failed"].format(why=f"HTTP {exc.code} {said}".strip())) from None
    except (OSError, ValueError) as exc:
        raise TaskError(words["task_session_failed"].format(why=first_line(str(exc)))) from None
    try:
        reply = json.loads(raw or b"{}")
    except ValueError:
        reply = {}
    found = SESSION.search(str(reply.get("claude_code_session_url") or "") if isinstance(reply, dict) else "")
    if not found:
        raise TaskError(words["task_session_failed"].format(why=first_line(_text(raw))))
    return found.group(0)


def cloud_cli(cfg: dict, words: dict, prompt: str) -> str:
    """`claude --cloud` with the task, in a terminal of its own, from the desk's own copy of the
    repository on its default branch -> the new session's link."""
    folder = own_copy(cfg, words)
    cmd = command_of("POCKETCALL_CLAUDE", "claude") + ["--cloud", prompt]
    code, said = run_in_terminal(cmd, str(folder), CLOUD_WAIT, SESSION)
    found = SESSION.search(said)
    if found:
        return found.group(0)
    if code == 127:
        raise TaskError(words["task_need_claude"])
    why = words["task_no_session_link"].format(seconds=CLOUD_WAIT) if code == 124 else last_line(said)
    raise TaskError(words["task_session_failed"].format(why=why))


def start_cloud(cfg: dict, words: dict, task: dict) -> dict:
    """A cloud session takes the task, so the laptop may sleep: through the routine's API trigger when
    one is set, otherwise `claude --cloud`. It counts as started only once the session's link came
    back; until then the task stays filed."""
    task = dict(task, branch=task.get("branch") or branch_of(task))
    text = prompt_of(cfg, task, home=False)
    if (cfg.get("routine") or {}).get("url"):
        if len(text) > ROUTINE_TEXT:   # the words in full stay in the tracker, and the session reads them there
            text = prompt_of(cfg, dict(task, words=f"(Longer than one call carries: read them in full at "
                                                   f"{task.get('url') or task['ref']}.)"), home=False)
        session = fire_routine(cfg, words, text)
    else:
        session = cloud_cli(cfg, words, text)
    line = words["task_started_cloud"].format(session=session)
    task.update(state="started", how="cloud", session=session, started=now(), last=line)
    save_task(task)
    journal(cfg, words, task, "started", line)
    return task


def default_branch(folder) -> str:
    code, out, _ = git(folder, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if code == 0 and "/" in out.strip():
        return out.strip().split("/", 1)[1]
    code, out, _ = git(folder, "rev-parse", "--abbrev-ref", "HEAD")
    name = out.strip()
    return name if code == 0 and name and name != "HEAD" else "main"


def checkout_of(folder, repo: str) -> bool:
    """Whether the folder is a checkout of owner/name: its origin ends in that owner and name."""
    if not folder or not repo or not Path(folder).is_dir():
        return False
    code, out, _ = git(folder, "remote", "get-url", "origin")
    url = out.strip().rstrip("/")
    if code != 0 or not url:
        return False
    url = url[:-4] if url.endswith(".git") else url
    return "/".join(re.split(r"[/:]", url)[-2:]).lower() == repo.lower()


def copy_path(cfg: dict) -> Path:
    return remote.home() / "repos" / str(cfg.get("repo", "repo")).replace("/", "-")


def own_copy(cfg: dict, words: dict) -> Path:
    """The desk's own clone of the repository (~/.pocketcall/repos/<owner>-<name>), brought to the
    default branch as GitHub has it now: a cloud session starts from there, never from whatever
    branch a person's checkout is on, and a desk started from any folder works on the right repository."""
    copy = copy_path(cfg)
    with GIT_LOCK:
        if not checkout_of(copy, cfg.get("repo", "")):
            copy.parent.mkdir(parents=True, exist_ok=True)
            code, out, err = gh("repo", "clone", cfg.get("repo", ""), str(copy), timeout=1800)
            if code != 0 or not checkout_of(copy, cfg.get("repo", "")):
                raise gh_failed(words, code, err, out)
        git(copy, "fetch", "--quiet", "origin")
        base = default_branch(copy)
        code, out, err = git(copy, "checkout", "--quiet", "-B", base, f"origin/{base}")
        if code != 0:
            raise TaskError(words["task_git_failed"].format(why=first_line(err or out)))
    return copy


def home_folder(cfg: dict, words: dict) -> Path:
    """Where a session on this computer branches from: the configured checkout when it is one of this
    repository, otherwise the desk's own copy."""
    folder = cfg.get("folder") or ""
    if checkout_of(folder, cfg.get("repo", "")):
        return Path(folder)
    return own_copy(cfg, words)


def quoted(text: str) -> str:
    return "\n".join("> " + line if line else ">" for line in str(text).splitlines())


def stop(cfg: dict, words: dict, task: dict, host: str, tree, why: str) -> dict:
    line = words["task_stopped"].format(host=host, why=why, tree=tree)
    task.update(state="stopped", last=line)
    save_task(task)
    journal(cfg, words, task, "stopped", line)
    return task


def open_pr(cfg: dict, words: dict, task: dict, branch: str, body: str, base: str = "") -> dict:
    args = ["pr", "create", "--repo", cfg.get("repo", ""), "--head", branch,
            "--title", task.get("title") or branch, "--body-file", "-"]
    if base:
        args += ["--base", base]
    code, out, err = gh(*args, stdin=body)
    url = last_url(out + "\n" + err)
    found = re.search(r"/pull/(\d+)", url)
    if not found:                    # an existing pull request for the branch is named in the refusal
        raise gh_failed(words, code, err, out)
    line = words["task_pr_open"].format(url=url)
    task.update(state="pr", branch=branch, pr=int(found.group(1)), pr_url=url, last=line)
    save_task(task)
    journal(cfg, words, task, "pull_request", line)
    return task


def start_home(cfg: dict, words: dict, task: dict) -> dict:
    """A session on this computer, in a git worktree of its own: `claude -p` makes the change there,
    then Pocketcall commits, pushes and opens the pull request. The person's own checkout is not
    touched, and nothing reaches the default branch without a Yes on the card."""
    folder = home_folder(cfg, words)
    task = dict(task, branch=task.get("branch") or branch_of(task))
    tree = remote.home() / "worktrees" / f"{slug(folder.name, 40) or 'repo'}-{key_slug(task['key'])}"
    with GIT_LOCK:
        git(folder, "fetch", "--quiet", "origin")
        base = default_branch(folder)
        start = f"origin/{base}" if git(folder, "rev-parse", "--verify", "--quiet", f"origin/{base}")[0] == 0 else "HEAD"
        if not tree.is_dir():
            tree.parent.mkdir(parents=True, exist_ok=True)
            code, out, err = git(folder, "worktree", "add", "-b", task["branch"], str(tree), start)
            if code != 0:            # the branch is there from an earlier run: the worktree takes it as it is
                code, out, err = git(folder, "worktree", "add", str(tree), task["branch"])
            if code != 0:
                raise TaskError(words["task_git_failed"].format(why=first_line(err or out)))
    host = socket.gethostname()
    line = words["task_started_home"].format(host=host, branch=task["branch"])
    task.update(state="started", how="home", session=f"{host}:{tree}", started=now(), last=line)
    save_task(task)
    journal(cfg, words, task, "started", line)
    cmd = command_of("POCKETCALL_CLAUDE", "claude") + ["-p", prompt_of(cfg, task, home=True),
                                                       "--permission-mode", "acceptEdits"]
    if cfg.get("allow"):
        cmd += ["--allowedTools"] + [str(rule) for rule in cfg["allow"]]
    code, said, err = run(cmd, cwd=str(tree), timeout=HOME_WAIT)
    if code != 0:
        why = words["task_need_claude"] if code == 127 else first_line(err or said)
        return stop(cfg, words, task, host, tree, why)
    said = said.strip()[:SAID]
    with GIT_LOCK:
        git(tree, "add", "-A")
        if git(tree, "diff", "--cached", "--quiet")[0] == 0:
            line = words["task_no_change"].format(said=said or "-")
            task.update(state="no-change", last=line)
            save_task(task)
            journal(cfg, words, task, "no-change", line)
            return task
        message = f"{task['title'] or task['branch']} ({task['ref']})"
        code, out, err = git(tree, "commit", "--quiet", "-m", message)
        if code != 0:                # no git identity on this machine: the commit is written as Pocketcall
            code, out, err = git(tree, "-c", "user.name=Pocketcall", "-c", "user.email=pocketcall@localhost",
                                 "commit", "--quiet", "-m", message)
        if code == 0:
            code, out, err = git(tree, "push", "--quiet", "-u", "origin", task["branch"])
    if code != 0:
        return stop(cfg, words, task, host, tree, first_line(err or out))
    body = "\n".join([closing_of(cfg, task), "", words["task_pr_said"], said or "-", "",
                      words["task_pr_words"], quoted(task["words"])])
    try:
        return open_pr(cfg, words, task, task["branch"], body, base)
    except TaskError as exc:
        return stop(cfg, words, task, host, tree, str(exc))


# --- the pull request's card -------------------------------------------------------------------

def merge_steps(cfg: dict, words: dict, card: dict) -> list:
    """What Yes runs, in order - the card shows exactly these: the draft made ready, the Yes kept in
    GitHub as an approving review, the merge pinned to the commit the card showed."""
    repo, n = cfg.get("repo", ""), str(card["pr"])
    method = cfg.get("merge") if cfg.get("merge") in MERGES else "squash"
    steps = [["pr", "ready", n, "--repo", repo]] if card.get("draft") else []
    review = words["task_review"].format(sha=card["sha"])
    steps.append(["pr", "review", n, "--repo", repo, "--approve", "--body", review])
    steps.append(["pr", "merge", n, "--repo", repo, "--" + method, "--match-head-commit", card["sha"]])
    return steps


def shown(steps: list) -> str:
    return " && ".join(shlex.join(["gh"] + step) for step in steps)


def pr_card(cfg: dict, words: dict, number, task: dict | None = None) -> dict:
    """Branch D's approval card for a pull request: Yes runs its steps, word for word. The heading
    names the author, and says so when the pull request comes from a fork."""
    repo = cfg.get("repo", "")
    code, out, err = gh("pr", "view", str(number), "--repo", repo, "--json", PR_FIELDS)
    if code != 0:
        raise gh_failed(words, code, err, out)
    try:
        info = json.loads(out)
    except ValueError:
        raise TaskError(words["task_gh_failed"].format(why=first_line(out))) from None
    if not isinstance(info, dict) or not str(info.get("number", "")).isdigit():
        raise TaskError(words["task_gh_failed"].format(why=first_line(out)))
    n = int(info["number"])
    url = str(info.get("url") or "")
    if str(info.get("state") or "OPEN").upper() != "OPEN":
        raise TaskError(words["task_pr_closed"].format(url=url or n))
    code, diff, _ = gh("pr", "diff", str(n), "--repo", repo)
    files = [str(f.get("path", "")) for f in info.get("files") or [] if isinstance(f, dict)]
    sha = str(info.get("headRefOid") or "")
    draft = bool(info.get("isDraft"))
    author, title = login_of(info), info.get("title") or url
    if info.get("isCrossRepository"):
        heading = words["task_card_heading_fork"].format(title=title, author=author or "-")
    elif author:
        heading = words["task_card_heading_by"].format(title=title, author=author)
    else:
        heading = words["task_card_heading"].format(title=title)
    command = shown(merge_steps(cfg, words, {"pr": n, "sha": sha, "draft": draft}))
    whole = code == 0 and len(diff) <= approval_card.MAX_DIFF and len(files) >= int(info.get("changedFiles") or 0)
    return {"id": uuid.uuid4().hex, "tool": "Pull request", "heading": heading,
            "command": command, "files": files, "diff": diff[:approval_card.MAX_DIFF] if code == 0 else "",
            "folder": "", "complete": bool(whole and sha), "url": url, "task": (task or {}).get("words", ""),
            "receipt": True, "pr": n, "sha": sha, "draft": draft, "author": author,
            "fork": bool(info.get("isCrossRepository"))}


def remember_card(card: dict, task: dict | None, via: list) -> None:
    entry = {"id": card["id"], "pr": card["pr"], "sha": card["sha"], "url": card["url"], "yes": card["complete"],
             "draft": card["draft"], "task": (task or {}).get("key", ""), "via": via, "state": "sent", "sent": now()}
    change_record(lambda rec: rec["cards"].__setitem__(card["id"], entry))


def pr_now(cfg: dict, number) -> dict:
    """The pull request as GitHub has it now: its state, head commit, merge state and checks."""
    code, out, _ = gh("pr", "view", str(number), "--repo", cfg.get("repo", ""), "--json", VIEW_FIELDS)
    try:
        info = json.loads(out) if code == 0 else {}
    except ValueError:
        info = {}
    return info if isinstance(info, dict) else {}


def checks_of(info: dict) -> str:
    """"failed", "pending" or "passed", from the pull request's checks and commit statuses."""
    seen = []
    for one in info.get("statusCheckRollup") or []:
        if not isinstance(one, dict):
            continue
        status = str(one.get("status") or "").upper()
        if status and status != "COMPLETED":
            seen.append(status)
        else:
            seen.append(str(one.get("conclusion") or one.get("state") or "").upper())
    if any(s in FAILED for s in seen):
        return "failed"
    if any(s in PENDING for s in seen):
        return "pending"
    return "passed"


def standing(info: dict, sha: str) -> str:
    """Where a Yes for commit sha stands: merged, closed, moved (a newer commit is on the pull
    request), pending (checks still running), failed, ready to merge, or blocked."""
    state = str(info.get("state") or "").upper()
    if state == "MERGED":
        return "merged"
    if state == "CLOSED":
        return "closed"
    if str(info.get("headRefOid") or "") != sha:
        return "moved"
    merge_state = str(info.get("mergeStateStatus") or "").upper()
    checks = checks_of(info)
    if merge_state in ("CLEAN", "HAS_HOOKS", "UNSTABLE"):
        return "ready"
    if checks == "pending" or merge_state == "UNKNOWN":
        return "pending"
    if checks == "failed":
        return "failed"
    return "blocked"


def after_refusal(cfg: dict, words: dict, card: dict, why: str) -> tuple:
    """GitHub did not merge at once: what the Yes becomes. Checks still running - it is kept, and the
    desk merges that same commit when they pass; a newer commit on the pull request - its own card
    comes; failed checks or anything else - the reason goes to the phone."""
    info = pr_now(cfg, card["pr"])
    url = card.get("url") or str(card["pr"])
    where = standing(info, card["sha"]) if info else "blocked"
    if where == "merged":
        return "merged", words["task_merged_there"].format(url=url)
    if where == "moved":
        return "replaced", words["task_moved"].format(url=url)
    if where == "pending":
        return "approved", words["task_held"].format(sha=card["sha"][:7], url=url)
    if where == "failed":
        return "refused", words["task_checks_failed"].format(url=url)
    return "refused", words["task_merge_refused"].format(why=why)


def act(cfg: dict, words: dict, card: dict, say: str) -> tuple:
    """The phone's answer, carried out -> (the card's new state, the line for the phone and the journal).
    Yes runs the card's steps word for word and merges exactly the commit the card showed. Where the
    repository's checks are still running, the Yes is kept and the desk merges that commit the moment
    they pass (Desk.merge_approved); auto-merge is never turned on, so nothing pushed after the card can
    ride on this Yes. Anything else leaves the pull request open."""
    if say == "yes" and card["complete"]:
        steps = merge_steps(cfg, words, card)
        for step in steps[:-1]:
            gh(*step)                # GitHub keeps the Yes as a review; its own author's pull request takes none
        code, out, err = gh(*steps[-1])
        if code == 0:
            return "merged", words["task_merged"].format(url=card.get("url") or card["pr"])
        return after_refusal(cfg, words, card, first_line(err or out))
    gh("pr", "comment", str(card["pr"]), "--repo", cfg.get("repo", ""), "--body-file", "-",
       stdin=words["task_declined"])
    return "declined", words["task_declined"]


def tell(card: dict, line: str, relay=None, telegram=None, rid: str = "", more: bool = False) -> None:
    """What came of the answer, back to the phone: sealed through the relay - under the card's id, or
    under <id>-<n> for what follows a kept Yes, `more` telling the page to keep listening - and in
    Telegram."""
    if relay is not None:
        rid = rid or card["id"]
        box = relay.pair.seal({"id": rid, "text": line, "url": card.get("url", ""), "more": more})
        try:
            remote._http(f"{relay.url}/r/{relay.pair.room}/receipt",
                         {"id": rid, "box": box, "ring": rid != card["id"]}, 15)
        except (OSError, ValueError):
            pass
    if telegram is not None:
        try:
            telegram.call("sendMessage", chat_id=telegram.chat, text=line)
        except (OSError, ValueError):
            pass


def settle(cfg: dict, words: dict, card: dict, state: str, line: str, relay=None, telegram=None) -> None:
    """The answer's outcome: into the record, into the task's journal, and back to the phone."""
    found, told = {}, [0]

    def change(rec):
        entry = rec["cards"].get(card["id"])
        if entry is not None:
            told[0] = int(entry.get("told_n") or 0)
            entry.update(state=state, answered=now(), told_n=told[0] + 1)
        key = (entry or {}).get("task") or next(
            (k for k, t in rec["tasks"].items() if t.get("pr") == card["pr"]), "")
        task = rec["tasks"].get(key)
        if task is not None:
            task["last"] = task["told"] = line          # the phone hears it right here, under the card
            if state == "merged":
                task["state"] = "merged"
            found.update(task)

    change_record(change)
    if found and state == "merged":
        journal(cfg, words, found, "merged", line, close=True)
    elif found and (state in ("refused", "approved", "replaced") or cfg.get("tracker") == "webhook"):
        journal(cfg, words, found, state, line)
    tell(card, line, relay, telegram, f"{card['id']}-{told[0]}" if told[0] else "", more=state == "approved")


def carry_held(cfg: dict, words: dict, card: dict, relay=None, telegram=None):
    """A Yes kept while the checks ran: merged the moment GitHub says that commit can go in, with
    --match-head-commit, so GitHub itself refuses anything newer. A newer commit, failed checks or a
    closed pull request end the wait, and the phone hears which -> (state, line), or None while the
    checks still run."""
    url = card.get("url") or str(card["pr"])
    info = pr_now(cfg, card["pr"])
    where = standing(info, card["sha"]) if info else "pending"
    if where == "pending":
        return None
    if where in ("ready", "blocked"):
        code, out, err = gh(*merge_steps(cfg, words, card)[-1])
        state, line = ("merged", words["task_merged"].format(url=url)) if code == 0 else \
            ("refused", words["task_merge_refused"].format(why=first_line(err or out)))
    elif where == "merged":
        state, line = "merged", words["task_merged_there"].format(url=url)
    elif where == "moved":
        state, line = "replaced", words["task_moved"].format(url=url)
    elif where == "failed":
        state, line = "refused", words["task_checks_failed"].format(url=url)
    else:
        state, line = "refused", words["task_pr_closed"].format(url=url)
    settle(cfg, words, card, state, line, relay, telegram)
    return state, line


def card_now(cfg: dict, rcfg: dict, words: dict, number: str, wait: float) -> int:
    """`task.py card <pull request>`: one card, sent now; the first answer is carried out."""
    channels = remote.channels(rcfg, words)
    if not channels:
        print(words["remote_not_paired"])
        return 1
    number = str(number).strip().lstrip("#")
    task = next((t for t in read_record()["tasks"].values() if str(t.get("pr")) == number), None)
    card = pr_card(cfg, words, number, task)
    remember_card(card, task, [type(c).__name__ for c in channels])
    print(words["task_card_sent"].format(url=card["url"]), flush=True)
    say = remote.ask(card, rcfg, words, wait)
    if say is None:
        print(words["task_card_waiting"])
        return 1
    state, line = act(cfg, words, card, say)
    relay = next((c for c in channels if isinstance(c, remote.Relay)), None)
    telegram = next((c for c in channels if isinstance(c, remote.Telegram)), None)
    settle(cfg, words, card, state, line, relay, telegram)
    print(line, flush=True)
    end = time.monotonic() + wait
    while state == "approved":               # the checks still run: this command waits for them too
        if time.monotonic() >= end:
            print(words["task_held_desk"])
            return 0
        time.sleep(HELD_EVERY)
        done = carry_held(cfg, words, card, relay, telegram)
        if done is not None:
            state, line = done
            print(line)
    return 0 if state in ("merged", "declined") else 1


# --- the desk --------------------------------------------------------------------------------

class Desk:
    """What stays on while the laptop sleeps. One `cycle`: the tasks other computers shared are taken
    in, the phone's notes become tasks, open pull requests are linked to their tasks and each new
    commit's card goes to the phone once, new tasks get a session (with --start), a Yes kept for
    running checks is merged when they pass, the answers are carried out, and each task's news goes
    to the phone. Several desks on one phone take turns: the relay lets one act at a time."""

    def __init__(self, cfg: dict, rcfg: dict, words: dict, start: str | None = None, every: float = 30):
        self.cfg, self.rcfg, self.words, self.start = cfg, rcfg, words, start
        self.channels = remote.channels(rcfg, words)
        self.relay = next((c for c in self.channels if isinstance(c, remote.Relay)), None)
        self.telegram = next((c for c in self.channels if isinstance(c, remote.Telegram)), None)
        self.jobs = []
        self.id = hashlib.sha256(f"{socket.gethostname()}|{remote.home()}".encode("utf-8")).hexdigest()[:32]
        self.lease = max(3 * float(every), 90.0)
        self.me = None            # this machine's GitHub login, asked once
        self.foreign = set()      # (pull request, issue) pairs that are not Pocketcall's
        self.shared = {}          # task key -> the stamp last put on the relay
        self.away = False         # another desk holds the phone

    def cycle(self) -> None:
        if not self.hold():
            if not self.away:
                print(self.words["task_desk_elsewhere"], flush=True)
            self.away = True
            return
        self.away = False
        self.steps(self.take_tasks, self.take_notes, self.link, self.start_new, self.merge_approved,
                   self.collect, self.report, self.share)     # linked first: a task whose session already
                                                              # opened its pull request is not started again

    @staticmethod
    def steps(*steps) -> None:
        for step in steps:
            try:
                step()
            except Exception as exc:  # noqa: BLE001 - the desk says what stopped one step and stays on
                print(first_line(str(exc) or type(exc).__name__), flush=True)

    def room(self, what: str) -> str:
        return f"{self.relay.url}/r/{self.relay.pair.room}/{what}"

    def hold(self, seconds: float | None = None) -> bool:
        """The phone's desk lease on the relay, taken or renewed each pass: True while this desk may
        act, False while another desk holds it. A desk that stops coming back (a laptop gone to
        sleep) loses it when the lease runs out, and the next desk takes over."""
        if self.relay is None:
            return True
        lease = self.lease if seconds is None else seconds
        try:
            remote._http(self.room("desk"), {"id": self.id, "box": "", "for": lease}, 15)
        except urllib.error.HTTPError as exc:
            return exc.code != 409
        except (OSError, ValueError):
            return True
        return True

    def receipt(self, rid: str, text: str, url: str = "", more: bool = False, ring: bool = False) -> None:
        box = self.relay.pair.seal({"id": rid, "text": text, "url": url, "more": more})
        remote._http(self.room("receipt"), {"id": rid, "box": box, "ring": ring}, 15)

    def take_tasks(self) -> None:
        """The tasks other computers on this phone filed or started, sealed on the relay: into this
        desk's record, the newer version of each winning."""
        if self.relay is None:
            return
        _, data = remote._http(self.room("tasks"), None, 15)
        for item in (data or {}).get("tasks") or []:
            try:
                box = self.relay.pair.open(str(item.get("box", "")))
            except ValueError:
                continue
            theirs = box.get("task") if isinstance(box, dict) and box.get("kind") == "task" else None
            if not isinstance(theirs, dict) or not theirs.get("key") or theirs.get("state") not in TASK_STATES:
                continue

            def change(rec, theirs=theirs):
                mine = rec["tasks"].get(str(theirs["key"]))
                if mine is None or str(theirs.get("updated", "")) > str(mine.get("updated", "")):
                    rec["tasks"][str(theirs["key"])] = dict(theirs, told=theirs.get("told", theirs.get("last", "")))
            change_record(change)
            self.shared[str(theirs["key"])] = str(theirs.get("updated", ""))

    def take_notes(self) -> None:
        """Each sealed note from the phone page becomes a task, word for word; its link goes back
        sealed. The relay hands a note to one desk at a time, and the note's id goes into the issue,
        so a note two desks both saw is still filed once."""
        if self.relay is None:
            return
        _, data = remote._http(self.room(f"notes?lease={NOTE_LEASE}"), None, 15)
        for item in (data or {}).get("notes") or []:
            nid = str(item.get("id", ""))
            try:
                note = self.relay.pair.open(str(item.get("box", "")))
            except ValueError:
                note = None
            if not isinstance(note, dict) or note.get("id") != nid or not str(note.get("words") or "").strip():
                self.receipt(nid, self.words["task_note_unread"])
                continue
            key = read_record()["notes"].get(nid)
            if key is None:
                try:
                    key = file_task(self.cfg, self.words, str(note["words"]), "phone", note=nid)["key"]
                except TaskError as exc:
                    self.receipt(nid, self.words["task_note_failed"].format(why=str(exc), words=note["words"]))
                    continue
                change_record(lambda rec: rec["notes"].__setitem__(nid, key))
            filed = read_record()["tasks"].get(key) or {}
            url = filed.get("url") or ""
            self.receipt(nid, self.words["task_filed"].format(ref=filed.get("ref", key), url=url or "-"), url,
                         more=filed.get("state") not in DONE)

    def start_new(self) -> None:
        if not self.start:
            return
        for task in list(read_record()["tasks"].values()):
            if task.get("state") != "filed" or float(task.get("again_at") or 0) > time.time():
                continue
            if self.start == "cloud":
                try:
                    start_cloud(self.cfg, self.words, task)
                except TaskError as exc:
                    self.not_started(task, str(exc))
                continue
            claimed = dict(task, state="started", how="home")   # claimed first, so it starts once
            save_task(claimed)
            job = threading.Thread(target=self.home, args=(claimed,), daemon=True)
            job.start()
            self.jobs.append(job)

    def not_started(self, task: dict, why: str) -> None:
        """A cloud session that did not start: the task stays filed and is tried again later, a few
        times; the phone hears each line."""
        tries = int(task.get("tries") or 0) + 1
        if tries >= START_TRIES:
            line = self.words["task_not_started"].format(why=why, tries=tries)
            save_task(dict(task, state="stopped", tries=tries, last=line))
            journal(self.cfg, self.words, task, "stopped", line)
        else:
            minutes = START_AGAIN * tries // 60
            line = self.words["task_start_again"].format(why=why, minutes=minutes)
            save_task(dict(task, state="filed", tries=tries, again_at=time.time() + START_AGAIN * tries, last=line))
        print(line, flush=True)

    def home(self, task: dict) -> None:
        try:
            start_home(self.cfg, self.words, task)
        except TaskError as exc:
            save_task(dict(task, state="stopped", last=str(exc)))
            print(str(exc), flush=True)

    def login(self) -> str:
        if self.me is None:
            code, out, _ = gh("api", "user", "--jq", ".login")
            self.me = out.strip().splitlines()[0].strip() if code == 0 and out.strip() else ""
        return self.me

    def link(self) -> None:
        """Every open pull request that belongs to a task is linked to it and carded once per commit -
        including a task another computer filed, found through the issue the pull request closes; a
        task whose pull request left the open list is marked merged or closed, as GitHub says."""
        code, out, err = gh("pr", "list", "--repo", self.cfg.get("repo", ""), "--state", "open",
                            "--json", LIST_FIELDS, "--limit", "100")
        if code != 0:
            raise gh_failed(self.words, code, err, out)
        prs = json.loads(out or "[]")
        prs = prs if isinstance(prs, list) else []
        rec = read_record()
        live = [t for t in rec["tasks"].values() if t.get("state") in ("filed", "started", "pr", "stopped")]
        self.settled_elsewhere([t for t in live if t.get("state") == "pr"], {pr.get("number") for pr in prs})
        linked = set()
        for pr in prs:
            if not isinstance(pr, dict):
                continue
            title, body, head = (str(pr.get(k) or "") for k in ("title", "body", "headRefName"))
            task = next((t for t in live if belongs(self.cfg, t, title, body, head)
                         and trusted(t, pr, self.login())), None)
            if task is None:
                task = self.from_tracker(pr, rec)
            if task is None:
                continue
            linked.add(task["key"])
            if task.get("pr") != pr.get("number") or task.get("state") != "pr":
                task = dict(task, state="pr", pr=pr.get("number"), pr_url=pr.get("url", ""),
                            last=self.words["task_pr_open"].format(url=pr.get("url", "")))
                save_task(task)
            if pr.get("isDraft"):
                continue
            if any(c.get("pr") == pr.get("number") and c.get("sha") == pr.get("headRefOid")
                   and c.get("state") != "replaced" for c in read_record()["cards"].values()):
                continue
            self.send(pr.get("number"), task, pr.get("headRefOid"))
        self.adopt([t for t in live if t["key"] not in linked and t.get("state") == "started"
                    and t.get("how") == "cloud"])

    def from_tracker(self, pr: dict, rec: dict) -> dict | None:
        """A pull request for a task this computer has not heard of - filed on another one: the issue
        it closes, or the number in its pocketcall/<n> branch, becomes a task here when Pocketcall
        filed that issue (its body carries the mark)."""
        if self.cfg.get("tracker") != "github" or pr.get("isCrossRepository"):
            return None
        title, body, head = (str(pr.get(k) or "") for k in ("title", "body", "headRefName"))
        keys = CLOSING.findall(f"{title}\n{body}")
        keys += re.findall(r"pocketcall[/-](\d+)(?![A-Za-z0-9])", head, re.IGNORECASE)
        for key in dict.fromkeys(keys):
            if key in rec["tasks"] or (pr.get("number"), key) in self.foreign:
                continue
            task = issue_task(self.cfg, self.words, key, ours_only=True)
            if task is None or not trusted(task, pr, self.login()):
                self.foreign.add((pr.get("number"), key))
                continue
            task["last"] = task["told"] = self.words["task_filed"].format(ref=task["ref"], url=task["url"] or "-")
            return task
        return None

    def settled_elsewhere(self, waiting: list, still_open: set) -> None:
        """A task's pull request that left the open list: merged on GitHub, or closed there."""
        for task in waiting:
            if not task.get("pr") or task["pr"] in still_open:
                continue
            code, out, _ = gh("pr", "view", str(task["pr"]), "--repo", self.cfg.get("repo", ""), "--json", "state,url")
            try:
                info = json.loads(out) if code == 0 else {}
            except ValueError:
                info = {}
            info = info if isinstance(info, dict) else {}
            state = str(info.get("state") or "").upper()
            url = str(info.get("url") or task.get("pr_url") or task["pr"])
            if state == "MERGED":
                line = self.words["task_merged_there"].format(url=url)
                save_task(dict(task, state="merged", last=line))
                journal(self.cfg, self.words, task, "merged", line, close=True)
            elif state == "CLOSED":
                line = self.words["task_pr_closed"].format(url=url)
                save_task(dict(task, state="stopped", last=line))
                journal(self.cfg, self.words, task, "stopped", line)

    def adopt(self, waiting: list) -> None:
        """A cloud session that pushed its branch and opened no pull request: the desk opens it."""
        if not waiting:
            return
        code, out, _ = gh("api", "--paginate", f"repos/{self.cfg.get('repo', '')}/branches?per_page=100",
                          "--jq", ".[].name")
        if code != 0:
            return
        names = [name.strip() for name in out.splitlines() if name.strip()]
        for task in waiting:
            branch = next((name for name in names if belongs(self.cfg, task, "", "", name)), None)
            if branch is None:
                continue
            if not task.get("branch_seen"):
                task = dict(task, branch_seen=time.time())
                save_task(task)
            if time.time() - float(task["branch_seen"]) < BRANCH_GRACE:
                continue
            body = "\n".join([closing_of(self.cfg, task), "", self.words["task_pr_words"], quoted(task["words"])])
            try:
                open_pr(self.cfg, self.words, dict(task), branch, body)
            except TaskError as exc:
                print(str(exc), flush=True)

    def waiting_card(self, number, sha: str) -> dict | None:
        """A card for this commit that another desk on this phone already put on the relay."""
        if self.relay is None:
            return None
        try:
            _, data = remote._http(self.room("asks"), None, 15)
        except (OSError, ValueError):
            return None
        known = read_record()["cards"]
        for ask in (data or {}).get("asks") or []:
            aid = str(ask.get("id", ""))
            if aid in known or not remote.ID.match(aid):
                continue
            try:
                status, got = remote._http(self.room(f"ask?id={aid}"), None, 15)
                card = self.relay.pair.open(str((got or {}).get("box", ""))) if status == 200 else None
            except (OSError, ValueError):
                continue
            if isinstance(card, dict) and card.get("id") == aid and (card.get("pr"), card.get("sha")) == (number, sha):
                return card
        return None

    def send(self, number, task: dict, sha: str = "") -> None:
        mine = self.waiting_card(number, sha) if sha else None
        if mine is not None:              # the phone already has it: this desk waits for its answer
            remember_card(mine, task, ["Relay"])
            return
        card = pr_card(self.cfg, self.words, number, task)
        via = []
        for ch in self.channels:
            try:
                ch.send(card)
                via.append(type(ch).__name__)
            except (OSError, ValueError):
                continue
        if via:
            remember_card(card, task, via)

    def answer(self, card: dict):
        for ch in self.channels:
            if isinstance(ch, remote.Telegram) and card["id"] not in ch.cards:
                ch.remember(card, card["complete"])          # a card sent before this desk started
            try:
                say = ch.poll(card["id"], wait=0)
            except (OSError, ValueError):
                say = None
            if say in ("yes", "no"):
                return say
        return None

    def listed(self):
        """The ids of the cards the relay still holds for the phone, or None when it is out of reach."""
        try:
            _, data = remote._http(self.room("asks"), None, 15)
        except (OSError, ValueError):
            return None
        return {str(a.get("id")) for a in (data or {}).get("asks") or []}

    def collect(self) -> None:
        listed = None
        for entry in list(read_record()["cards"].values()):
            if entry.get("state") != "sent":
                continue
            card = {"id": entry["id"], "pr": entry["pr"], "sha": entry.get("sha", ""), "url": entry.get("url", ""),
                    "complete": bool(entry.get("yes")), "draft": bool(entry.get("draft")), "diff": ""}
            say = self.answer(card)
            if say is None and self.relay is not None and "Relay" in (entry.get("via") or []):
                if listed is None:
                    listed = self.listed()
                if listed is not None and card["id"] not in listed:
                    say = self.answer(card)       # answered a moment ago - or lost with a relay that restarted
                    if say is None:               # lost: the next pass sends this commit's card again
                        change_record(lambda rec: rec["cards"][card["id"]].update(state="replaced"))
                        continue
            if say is None:
                continue
            state, line = act(self.cfg, self.words, card, say)
            settle(self.cfg, self.words, card, state, line, self.relay, self.telegram)

    def merge_approved(self) -> None:
        """Every Yes kept while the checks ran (carry_held): merged when they pass."""
        for entry in list(read_record()["cards"].values()):
            if entry.get("state") == "approved":
                card = {"id": entry["id"], "pr": entry["pr"], "sha": entry.get("sha", ""),
                        "url": entry.get("url", ""), "complete": True, "draft": False}
                carry_held(self.cfg, self.words, card, self.relay, self.telegram)

    def report(self) -> None:
        """Each new line of a task goes to the phone: on the phone page under the note it came from,
        ringing the phone, and in Telegram. A task known from before this desk starts quiet."""
        for task in list(read_record()["tasks"].values()):
            line = str(task.get("last") or "")
            if "told" in task and (not line or line == task["told"]):
                continue
            n = int(task.get("told_n") or 0)
            if "told" in task:
                n += 1
                if task.get("note") and self.relay is not None:
                    try:
                        self.receipt(f"{task['note']}-{n}", line, task.get("pr_url") or task.get("url") or "",
                                     more=task.get("state") not in DONE, ring=True)
                    except (OSError, ValueError):
                        continue           # told on the next pass
                if self.telegram is not None:
                    try:
                        self.telegram.call("sendMessage", chat_id=self.telegram.chat,
                                           text=f"{task.get('ref', '')}: {line}")
                    except (OSError, ValueError):
                        pass

            def change(rec, key=task["key"], line=line, n=n):
                if key in rec["tasks"]:
                    rec["tasks"][key].update(told=line, told_n=n, updated=stamp())
            change_record(change)

    def share(self) -> None:
        """Every task this desk changed goes onto the relay, sealed, for the desk that takes over."""
        for task in list(read_record()["tasks"].values()):
            stamp = str(task.get("updated", ""))
            if stamp and self.shared.get(task["key"]) != stamp:
                share(self.rcfg, task)
                self.shared[task["key"]] = stamp


def watch(cfg: dict, rcfg: dict, words: dict, start, every: float, once: bool) -> int:
    desk = Desk(cfg, rcfg, words, start, every)
    if not desk.channels:
        print(words["remote_not_paired"])
        return 1
    print(words["task_watching"].format(start=words.get("task_watching_" + start, "") if start else ""),
          flush=True)
    try:
        while True:
            desk.cycle()
            if once:
                for job in desk.jobs:
                    job.join()
                desk.steps(desk.report, desk.share)        # what the sessions here came to, told before it stops
                return 0
            time.sleep(max(float(every), 1.0))
    except KeyboardInterrupt:
        desk.hold(0)                       # let the next desk take over at once
        return 0


# --- the command line ------------------------------------------------------------------------

def setup(args, cfg: dict, words: dict) -> int:
    for repo in (args.github, args.repo):
        if repo and not REPO.match(repo):
            raise TaskError(words["task_bad_repo"].format(repo=repo))
    if args.github:
        cfg.update(tracker="github", repo=args.github)
    if args.webhook:
        cfg.update(tracker="webhook", webhook=dict(cfg.get("webhook") or {}, url=args.webhook))
    if args.repo:
        cfg["repo"] = args.repo
    if args.secret is not None or args.header:
        hook = dict(cfg.get("webhook") or {})
        if args.secret is not None:
            hook["secret"] = args.secret
        for header in args.header:
            name, _, value = header.partition(":")
            if name.strip():
                hook.setdefault("headers", {})[name.strip()] = value.strip()
        cfg["webhook"] = hook
    if args.label is not None:
        cfg["label"] = args.label
    cfg.setdefault("label", "pocketcall")
    if args.merge:
        cfg["merge"] = args.merge
    cfg.setdefault("merge", "squash")
    if args.routine is not None or args.routine_token is not None:
        routine = dict(cfg.get("routine") or {})
        if args.routine is not None:
            routine["url"] = args.routine
        if args.routine_token is not None:
            routine["token"] = args.routine_token
        cfg["routine"] = routine
    if args.who is not None:
        cfg["who"] = args.who
    if args.allow:
        cfg["allow"] = list(args.allow)
    if cfg.get("tracker") not in TRACKERS or not cfg.get("repo") \
            or (cfg["tracker"] == "webhook" and not (cfg.get("webhook") or {}).get("url")):
        raise TaskError(words["task_no_tracker"])
    if args.folder:
        if not Path(args.folder).expanduser().is_dir():
            raise TaskError(words["task_no_folder"].format(folder=args.folder))
        cfg["folder"] = str(Path(args.folder).expanduser().resolve())
    elif checkout_of(os.getcwd(), cfg["repo"]):
        cfg["folder"] = str(Path(os.getcwd()).resolve())
    elif not checkout_of(cfg.get("folder"), cfg["repo"]):
        cfg["folder"] = str(copy_path(cfg))       # cloned there by the first session that needs it
    save_settings(cfg)
    if cfg["tracker"] == "github" and cfg["label"]:
        make_label(cfg["repo"], cfg["label"], words)
    where = cfg["repo"] if cfg["tracker"] == "github" else cfg["webhook"]["url"]
    print(words["task_setup_done"].format(where=where, repo=cfg["repo"]))
    if (cfg.get("routine") or {}).get("url"):
        print(words["task_setup_routine"])
    return 0


def list_tasks(words: dict) -> int:
    tasks = read_record()["tasks"]
    if not tasks:
        print(words["task_list_empty"])
        return 0
    for task in sorted(tasks.values(), key=lambda t: str(t.get("filed_at", ""))):
        link = task.get("pr_url") or task.get("url") or ""
        print(f"{task.get('ref', task.get('key'))}  {task.get('state', '-')}  {task.get('title', '')}  {link}".rstrip())
    return 0


def words_in(args, words: dict) -> tuple:
    """(the text, where it came from, a file name): the words after `file`, a file, or standard input."""
    if args.source:
        path = Path(args.source).expanduser()
        try:
            return path.read_text(encoding="utf-8"), "file", path.name
        except (OSError, UnicodeDecodeError) as exc:
            raise TaskError(words["task_unreadable"].format(path=path, why=first_line(str(exc)))) from None
    text = " ".join(args.words)
    if not text.strip():
        try:
            text = "" if sys.stdin.isatty() else sys.stdin.read()
        except (OSError, ValueError, AttributeError):
            text = ""
    return text, "voice", ""


def command(args, cfg: dict, words: dict) -> int:
    if args.cmd == "setup":
        return setup(args, cfg, words)
    if args.cmd == "list":
        return list_tasks(words)
    if cfg.get("tracker") not in TRACKERS:
        raise TaskError(words["task_no_tracker"])
    if args.cmd == "file":
        text, source, name = words_in(args, words)
        filed = file_task(cfg, words, text, source, name)
        share(remote.load(), filed)
        print(filed["last"])
        return 0
    if args.cmd == "start":
        task = find_task(cfg, words, args.task)
        done = start_cloud(cfg, words, task) if args.cloud else start_home(cfg, words, task)
        share(remote.load(), done)
        print(done.get("last", ""))
        return 0 if done["state"] in ("started", "pr") else 1
    if args.cmd == "card":
        return card_now(cfg, remote.load(), words, args.pr, args.wait)
    return watch(cfg, remote.load(), words, args.start, args.every, args.once)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pocketcall: voice -> task -> pull request -> Yes from the phone.")
    ap.add_argument("--lang", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--github", default=None, help="owner/name: tasks become issues there")
    s.add_argument("--webhook", default=None, help="the address another tracker takes tasks at")
    s.add_argument("--repo", default=None, help="owner/name of the repository the pull requests are in")
    s.add_argument("--secret", default=None, help="signs each webhook call with HMAC-SHA256")
    s.add_argument("--header", action="append", default=[], help="'Name: value', sent with each webhook call")
    s.add_argument("--label", default=None, help="the label on each issue; pocketcall unless set")
    s.add_argument("--merge", choices=MERGES, default=None)
    s.add_argument("--folder", default=None, help="a checkout of the repository on this computer")
    s.add_argument("--routine", default=None, help="the API trigger URL of the routine that takes cloud tasks")
    s.add_argument("--routine-token", dest="routine_token", default=None, help="that trigger's token")
    s.add_argument("--who", default=None, help="the person's name, written under each task they file")
    s.add_argument("--allow", action="append", default=[], help="a tool a session here may use, as Bash(npm test)")
    f = sub.add_parser("file")
    f.add_argument("words", nargs="*")
    f.add_argument("--from", dest="source", default=None, help="a file whose text is the task")
    st = sub.add_parser("start")
    st.add_argument("task")
    how = st.add_mutually_exclusive_group(required=True)
    how.add_argument("--cloud", action="store_true")
    how.add_argument("--home", action="store_true")
    c = sub.add_parser("card")
    c.add_argument("pr")
    c.add_argument("--wait", type=float, default=600)
    w = sub.add_parser("watch")
    w.add_argument("--start", choices=STARTS, default=None)
    w.add_argument("--every", type=float, default=30)
    w.add_argument("--once", action="store_true")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    words = check.lang_words(check.pick_lang(args.lang))
    try:
        return command(args, load_settings(), words)
    except TaskError as exc:
        print(str(exc))
        return 1
    except OSError as exc:
        print(words["task_failed"].format(why=first_line(str(exc))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
