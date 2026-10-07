#!/usr/bin/env python3
"""The board: every job on this computer on one screen, and the phone rings when one needs you.

Each Claude Code session, a night run, a council review or any script of your own writes one line
here: what it is, which folder, and its state - working, waiting for you, done, resting on a limit
until a given hour, or stopped. The phone sees the whole list and rings only on what changes for
you: a job waits for an answer, a job is done, a job rests on a limit (with the hour it goes on).

    board.py show [--json]                  the list, the job that waits for you first
    board.py put --name <job> --state working|waiting|done|limit|failed [--note <text>]
                 [--until <hour>] [--where <folder>] [--id <id>]
                                            a night run, a review, a cron job reports its state
    board.py page --to <folder>             the board as one phone page, rewritten at every change;
                                            a Google Drive / iCloud / Dropbox / OneDrive folder puts
                                            it on the phone with no server at all
    board.py page --off
    board.py ring --ntfy <url>              your own ntfy topic rings the phone (ntfy.sh or your server)
    board.py ring --when away|always|never  away (the default): ring while remote.py says you are away
    board.py run --name <job> [--where <folder>] -- <command...>
                                            any long command on the board: working while it runs, done or
                                            stopped (with its last line) when it ends - a diffcall fix with
                                            --wait, a test suite, a build, a deploy
    board.py put ... [--folder <task folder>] [--resume <command>] [--meter "<Claude 44% · Codex 100%>"] [--say]
                                            a job with a folder gets Stop and Continue buttons on the phone
                                            (steer.py); --meter shows how much each subscription has left;
                                            --say rings this line now (a change of hands, say)
    board.py clear [--all]                  drop finished jobs (all jobs with --all)
    board.py hook                           the plugin's hook (UserPromptSubmit, Notification, PostToolUse,
                                            Stop, SessionEnd): Claude Code sessions report themselves

The rings go where the phone already is: the Telegram chat set with `remote.py telegram` and the
ntfy topic set here. Each ring is one line: the state, the job and its folder name.

Anything may also write a job file itself: ~/.pocketcall/board/<id>.json with the keys
id, name, where, state, note, until and at (seconds since 1970). `put` does the same and rings.

The board lives in ~/.pocketcall/board/ (POCKETCALL_HOME moves it), readable by this user only.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check  # noqa: E402
import remote  # noqa: E402

STATES = ("waiting", "limit", "failed", "working", "done")      # the order the board shows them in
RINGS = ("waiting", "limit", "failed", "done")                 # a change into one of these rings
ID = re.compile(r"[^A-Za-z0-9_-]")
NOTE = 160
KEEP_DONE = 3 * 24 * 3600        # a finished job stays on the board for three days
KEEP_SILENT = 24 * 3600          # any other job not heard from for a day left with its session
WAITING_KINDS = ("permission_prompt", "idle_prompt", "elicitation_dialog", "")
PAGE = "pocketcall-board.html"
TAIL = 256 * 1024                # how much of a transcript's end is read to find a limit
LIMIT = re.compile(r"(usage limit|hit your (?:usage |session |weekly )?limit|limit reached|"
                   r"out of (?:extra )?usage|quota (?:exceeded|exhausted))", re.I)
RESETS = re.compile(r"resets?\s+(?:at\s+|on\s+)?((?:[A-Za-z]{3,9}\s+(?:\d{1,2},?\s+)?)?\d{1,2}(?::\d{2})?"
                    r"\s*(?:am|pm)?(?:\s*\([^)]{1,40}\))?)", re.I)


def folder() -> Path:
    return remote.home() / "board"


def settings_path() -> Path:
    return remote.home() / "board.json"


def load_settings() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(cfg: dict) -> None:
    _write(settings_path(), cfg)


def _write(path: Path, data) -> None:
    """Whole or not at all: a temporary file of this process's own, then one rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def safe_id(text: str) -> str:
    return ID.sub("-", str(text or ""))[:64] or "job"


def short(text, size: int = NOTE) -> str:
    line = " ".join(str(text or "").split())
    return line if len(line) <= size else line[: size - 1] + "…"


def jobs(now: float | None = None) -> list:
    """Every job on the board, the one that waits for you first; finished jobs older than three
    days leave it on the way."""
    now = time.time() if now is None else now
    out = []
    base = folder()
    if not base.is_dir():
        return out
    for path in base.glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(job, dict) or job.get("state") not in STATES:
            continue
        try:
            job["at"] = float(job.get("at") or 0)
        except (TypeError, ValueError):
            continue
        if now - job["at"] > (KEEP_DONE if job["state"] == "done" else KEEP_SILENT):
            path.unlink(missing_ok=True)
            continue
        out.append(job)
    out.sort(key=lambda j: (STATES.index(j["state"]), -float(j.get("at") or 0)))
    return out


def get(job_id: str) -> dict:
    try:
        return json.loads((folder() / f"{safe_id(job_id)}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ago(seconds: float, words: dict) -> str:
    minutes = int(max(0, seconds) // 60)
    if minutes < 1:
        return words["board_ago_now"]
    if minutes < 60:
        return words["board_ago_min"].format(n=minutes)
    if minutes < 48 * 60:
        return words["board_ago_h"].format(h=minutes // 60, n=minutes % 60)
    return words["board_ago_d"].format(n=minutes // (24 * 60))


def line_of(job: dict, words: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    state = words[f"board_{job['state']}"]
    if job["state"] == "limit" and job.get("until"):
        state += " " + words["board_until"].format(until=job["until"])
    where = f" ({job['where']})" if job.get("where") and job.get("where") != job.get("name") else ""
    text = f"{state} - {job.get('name') or job.get('id')}{where}, {ago(now - float(job.get('at') or now), words)}"
    if job.get("note"):
        text += f": {job['note']}"
    if job.get("meter"):
        text += f" [{job['meter']}]"
    return text


METER = re.compile(r"([^·%?]+?)\s+(\d{1,3})%")


def meter_html(meter: str) -> str:
    """The subscriptions' remaining % as bars; a part without a number stays as words."""
    esc = html.escape
    out = []
    for part in [p.strip() for p in str(meter or "").split("·") if p.strip()]:
        m = METER.fullmatch(part)
        if m:
            pct = max(0, min(100, int(m.group(2))))
            out.append(f'<span class="bar"><i style="width:{pct}%"></i><em>{esc(m.group(1).strip())} {pct}%</em></span>')
        else:
            out.append(f'<span class="bar off"><em>{esc(part)}</em></span>')
    return '<span class="meter">' + "".join(out) + "</span>" if out else ""


def show(words: dict, as_json: bool = False) -> str:
    items = jobs()
    if as_json:
        return json.dumps(items, indent=2, ensure_ascii=False)
    if not items:
        return words["board_empty"]
    return "\n".join([words["board_title"]] + ["- " + line_of(j, words) for j in items])


def page_html(words: dict, lang: str, now: float | None = None) -> str:
    """One page for the phone: no script, no outside file, light and dark, refreshed every minute."""
    now = time.time() if now is None else now
    items = jobs(now)
    esc = html.escape
    rows = []
    for job in items:
        state = words[f"board_{job['state']}"]
        if job["state"] == "limit" and job.get("until"):
            state += " " + words["board_until"].format(until=job["until"])
        where = job.get("where") if job.get("where") and job.get("where") != job.get("name") else ""
        rows.append(
            f'<li class="{esc(job["state"])}"><b>{esc(state)}</b>'
            f'<span class="name">{esc(str(job.get("name") or job.get("id")))}</span>'
            + (f'<span class="where">{esc(str(where))}</span>' if where else "")
            + f'<span class="ago">{esc(ago(now - float(job.get("at") or now), words))}</span>'
            + (f'<span class="note">{esc(str(job["note"]))}</span>' if job.get("note") else "")
            + meter_html(job.get("meter"))
            + "</li>")
    body = "<ul>" + "".join(rows) + "</ul>" if rows else f'<p class="empty">{esc(words["board_empty"])}</p>'
    stamp = time.strftime("%H:%M", time.localtime(now))
    return f"""<!doctype html>
<html lang="{esc(lang)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>{esc(words["board_title"])}</title>
<style>
:root{{--bg:#fafaf7;--fg:#1d1d1b;--mute:#6b6b66;--card:#fff;--line:#e4e2dc;
--waiting:#b45309;--limit:#7c3aed;--failed:#b91c1c;--working:#1d4ed8;--done:#15803d}}
@media (prefers-color-scheme: dark){{:root{{--bg:#151514;--fg:#ecebe6;--mute:#a3a29c;--card:#1f1f1d;
--line:#33322f;--waiting:#f59e0b;--limit:#a78bfa;--failed:#f87171;--working:#60a5fa;--done:#4ade80}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.4 -apple-system,system-ui,sans-serif}}
main{{max-width:640px;margin:0 auto;padding:16px}}
h1{{font-size:20px;margin:0 0 4px}} .stamp{{color:var(--mute);font-size:13px;margin:0 0 12px}}
ul{{list-style:none;margin:0;padding:0}}
li{{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--c);border-radius:10px;
padding:10px 12px;margin:0 0 10px;display:flex;flex-wrap:wrap;gap:2px 10px}}
li b{{color:var(--c);width:100%}} .name{{font-weight:600}} .where,.ago{{color:var(--mute)}}
.note{{width:100%;color:var(--mute);font-size:14px;overflow-wrap:anywhere}}
.waiting{{--c:var(--waiting)}} .limit{{--c:var(--limit)}} .failed{{--c:var(--failed)}}
.working{{--c:var(--working)}} .done{{--c:var(--done)}} .empty{{color:var(--mute)}}
.meter{{width:100%;display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}}
.bar{{position:relative;flex:1 1 120px;height:22px;border:1px solid var(--line);border-radius:6px;overflow:hidden}}
.bar i{{position:absolute;inset:0 auto 0 0;background:var(--working);opacity:.25}}
.bar em{{position:relative;font-style:normal;font-size:13px;padding:0 6px;line-height:22px}} .bar.off em{{color:var(--mute)}}
</style></head><body><main>
<h1>{esc(words["board_title"])}</h1>
<p class="stamp">{esc(words["board_page_stamp"].format(time=stamp))}</p>
{body}
</main></body></html>
"""


def write_page(cfg: dict, words: dict, lang: str) -> Path | None:
    target = cfg.get("page")
    if not target:
        return None
    try:
        path = Path(target).expanduser() / PAGE
        _write(path, page_html(words, lang))
        return path
    except OSError:
        return None


def should_ring(cfg: dict, force: bool = False) -> bool:
    when = cfg.get("when", "away")
    if force and when != "never":
        return True
    if when == "always":
        return True
    if when == "never":
        return False
    return bool(remote.load().get("away"))


def ring_later(text: str) -> None:
    """The ring from a hook goes from a process of its own, so the session never waits for the network."""
    if os.environ.get("POCKETCALL_BOARD_SYNC"):
        ring(text, load_settings())
        return
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "ring-line", text],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env=dict(os.environ))
    except OSError:
        pass


def ring(text: str, cfg: dict, timeout: float = 5, keys: str = "", words: dict | None = None) -> list:
    """One line to the phone, everywhere it is set: the Telegram chat of remote.py and the ntfy
    topic of this board. A job with a task folder (keys = its id) comes with Continue and Stop
    buttons in Telegram (steer.py takes the press). Returns the names of the places that took it."""
    took = []
    tg = (remote.load().get("telegram") or {})
    if tg.get("token") and (tg.get("chat") or tg.get("allow")):
        api = (os.environ.get("POCKETCALL_TELEGRAM_API") or "https://api.telegram.org").rstrip("/")
        msg = {"chat_id": tg.get("chat") or tg["allow"][0], "text": text}
        if keys and words:
            msg["reply_markup"] = {"inline_keyboard": [[
                {"text": words["steer_continue"], "callback_data": f"c:{keys}"[:64]},
                {"text": words["steer_stop"], "callback_data": f"s:{keys}"[:64]}]]}
        try:
            remote._http(f"{api}/bot{tg['token']}/sendMessage", msg, timeout)
            took.append("telegram")
        except Exception:  # noqa: BLE001 - a ring never breaks anything
            pass
    url = cfg.get("ntfy")
    if url:
        try:
            req = urllib.request.Request(url, data=text.encode("utf-8"), method="POST",
                                         headers={"Title": "Pocketcall"})
            urllib.request.urlopen(req, timeout=timeout).close()
            took.append("ntfy")
        except Exception:  # noqa: BLE001
            pass
    return took


def put(job: dict, words: dict, lang: str, now: float | None = None, quiet: bool = False,
        force: bool = False, later: bool = False, say: bool = False) -> dict:
    """Write one job; ring when its state changed into one that is news for the person, and
    rewrite the phone page. Returns the job as written, with "rang" naming where it rang."""
    now = time.time() if now is None else now
    job = dict(job)
    job["id"] = safe_id(job.get("id") or job.get("name"))
    job["note"] = short(job.get("note"))
    job["task"] = short(job.get("task"))
    job["at"] = now
    before = get(job["id"])
    job["meter"] = short(job.get("meter"))
    _write(folder() / f"{job['id']}.json", {k: job.get(k, "") for k in
                                              ("id", "name", "where", "state", "note", "until", "at", "task",
                                               "folder", "resume", "meter")})
    cfg = load_settings()
    rang = []
    changed = job["state"] in RINGS and before.get("state") != job["state"]
    if not quiet and (changed or say) and should_ring(cfg, force or say):
        keys = job["id"] if job.get("folder") else ""
        if later:
            ring_later(line_of(job, words, now))
            rang = ["later"]
        else:
            rang = ring(line_of(job, words, now), cfg, keys=keys, words=words)
    write_page(cfg, words, lang)
    job["rang"] = rang
    return job


def drop(job_id: str, words: dict, lang: str) -> None:
    (folder() / f"{safe_id(job_id)}.json").unlink(missing_ok=True)
    write_page(load_settings(), words, lang)


def transcript_tail(path: str) -> list:
    """The last entries of a Claude Code transcript (JSON lines), newest last."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL))
            raw = fh.read().decode("utf-8", "replace")
    except (OSError, TypeError):
        return []
    out = []
    for line in raw.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def last_words(entries: list) -> tuple:
    """(the text of the last assistant message in the transcript, whether Claude Code wrote it
    itself - an API error or a limit line - rather than the model)."""
    for item in reversed(entries):
        msg = item.get("message") if isinstance(item.get("message"), dict) else {}
        if item.get("type") != "assistant" and msg.get("role") != "assistant":
            continue
        own = bool(item.get("isApiErrorMessage") or item.get("error") or msg.get("model") == "<synthetic>")
        content = msg.get("content")
        if isinstance(content, str):
            return content, own
        texts = [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
        if any(texts):
            return "\n".join(texts), own
    return "", False


def limit_of(text: str, own: bool = False) -> tuple:
    """(True, the hour it goes on) when Claude Code's own line (own: an API error or synthetic
    message, or a command that failed) says a usage limit ended the turn. A model's answer that
    talks about limits is work, not a rest."""
    if not own or not text or not LIMIT.search(text):
        return False, ""
    found = RESETS.search(text)
    return True, (found.group(1).strip() if found else "")


def from_hook(hook: dict, words: dict, lang: str) -> dict | None:
    """A Claude Code hook event -> the session's job on the board (None: nothing to change)."""
    event = hook.get("hook_event_name") or ""
    sid = hook.get("session_id") or ""
    if not sid:
        return None
    cwd = hook.get("cwd") or os.getcwd()
    name = Path(cwd).name or cwd
    job_id = "claude-" + safe_id(sid)[:40]
    before = get(job_id)
    job = {"id": job_id, "name": name, "where": "Claude Code", "note": before.get("note", ""),
           "task": before.get("task", "")}
    if event == "SessionEnd":
        drop(job_id, words, lang)
        return None
    if event == "PostToolUse":                       # a tool ran: the session is at work, whatever the board said
        if not before or before.get("state") == "working":
            return None
        job.update(state="working", note=before.get("task") or before.get("note", ""))
        return put(job, words, lang, quiet=True)
    if event == "UserPromptSubmit":
        prompt = str(hook.get("prompt") or "")
        if prompt.lstrip().startswith("/"):          # a slash command: the job keeps its words
            prompt = before.get("task") or before.get("note") or prompt
        job.update(state="working", note=prompt, task=prompt)
    elif event == "Notification":
        kind = hook.get("notification_type") or ""
        if kind not in WAITING_KINDS:
            return None                                  # a sign-in done and the like: nothing waits
        if kind == "idle_prompt" and before.get("state") in ("done", "limit", "failed"):
            return None                                  # finished already: the board says so
        job.update(state="waiting", note=hook.get("message") or before.get("note", ""))
        rcfg = remote.load()
        if kind == "permission_prompt" and rcfg.get("away") and remote.channels(rcfg, words):
            return put(job, words, lang, quiet=True)     # the approval card itself is the ring
        return put(job, words, lang, later=True)
    elif event == "Stop":
        said, own = last_words(transcript_tail(hook.get("transcript_path") or ""))
        hit, until = limit_of(said, own)
        if hit:
            job.update(state="limit", until=until, note=said)
        else:
            job.update(state="done", note=said or before.get("note", ""))
        # a Stop that another plugin's Stop hook keeps going is not an end to ring about
        return put(job, words, lang, quiet=bool(hook.get("stop_hook_active")), later=True)
    else:
        return None
    return put(job, words, lang)


def run_job(name: str, where: str, command: list, words: dict, lang: str) -> int:
    """Run one command with its output on this screen as usual; the board says working while it runs
    and done or stopped, with the command's last line, when it ends. Returns the command's exit code."""
    job_id = "run-" + safe_id(name)[:56]
    put({"id": job_id, "name": name, "where": where, "state": "working", "note": " ".join(command)}, words, lang)
    last, tail = "", []
    try:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", bufsize=1)
    except OSError as exc:
        put({"id": job_id, "name": name, "where": where, "state": "failed", "note": str(exc)}, words, lang)
        print(str(exc), file=sys.stderr)
        return 127
    try:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if line.strip():
                last = line.strip()
                tail = (tail + [last])[-5:]
        code = proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        code = proc.wait()
    hit, until = limit_of("\n".join(tail), own=True) if code else (False, "")
    if hit:
        state, note = "limit", last
    elif code == 0:
        state, note = "done", last
    else:
        state, note = "failed", words["board_exit"].format(code=code, line=last)
    put({"id": job_id, "name": name, "where": where, "state": state, "note": note, "until": until}, words, lang)
    return code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pocketcall board: every job on one screen, the phone rings when one needs you.")
    ap.add_argument("--lang", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--json", action="store_true")
    p = sub.add_parser("put")
    p.add_argument("--name", required=True)
    p.add_argument("--state", required=True, choices=STATES)
    p.add_argument("--note", default="")
    p.add_argument("--until", default="")
    p.add_argument("--where", default="")
    p.add_argument("--id", default="")
    p.add_argument("--ring", action="store_true", help="ring on a change even at the desk (not with --when never)")
    p.add_argument("--folder", default="", help="the job's task folder: Stop and Continue from the phone")
    p.add_argument("--resume", default="", help="the command that goes on with the job (Continue)")
    p.add_argument("--meter", default="", help="how much each subscription has left, one line")
    p.add_argument("--say", action="store_true", help="ring this line now, even with no change of state")
    rl = sub.add_parser("ring-line")
    rl.add_argument("text")
    g = sub.add_parser("page")
    g.add_argument("--to", default="")
    g.add_argument("--off", action="store_true")
    r = sub.add_parser("ring")
    r.add_argument("--ntfy", default=None)
    r.add_argument("--when", choices=("away", "always", "never"), default=None)
    r.add_argument("--test", action="store_true")
    c = sub.add_parser("clear")
    c.add_argument("--all", action="store_true")
    sub.add_parser("hook")
    u = sub.add_parser("run")
    u.add_argument("--name", required=True)
    u.add_argument("--where", default="")
    u.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)

    lang = check.pick_lang(args.lang or remote.load().get("lang"))
    words = check.lang_words(lang)

    if args.cmd == "hook":
        try:
            hook = json.loads(sys.stdin.read() or "{}")
            if isinstance(hook, dict):
                from_hook(hook, words, lang)
        except Exception:  # noqa: BLE001 - a hook never stops the session
            pass
        return 0                                         # a hook never stops the session
    if args.cmd == "run":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            print(words["board_run_needs"])
            return 2
        return run_job(args.name, args.where or Path.cwd().name, command, words, lang)
    if args.cmd == "show":
        print(show(words, args.json))
        return 0
    if args.cmd == "ring-line":
        ring(args.text, load_settings())
        return 0
    if args.cmd == "put":
        job = put({"id": args.id or args.name, "name": args.name, "where": args.where,
                   "state": args.state, "note": args.note, "until": args.until, "folder": args.folder,
                   "resume": args.resume, "meter": args.meter}, words, lang, force=args.ring, say=args.say)
        print(line_of(job, words))
        if job["rang"]:
            print(words["board_rang"].format(where=", ".join(job["rang"])))
        return 0
    cfg = load_settings()
    if args.cmd == "page":
        if args.off or not args.to:
            cfg.pop("page", None)
            save_settings(cfg)
            print(words["board_page_off"])
            return 0
        target = Path(args.to).expanduser()
        if not target.is_dir():
            print(words["board_page_no_folder"].format(folder=target))
            return 1
        cfg["page"] = str(target.resolve())
        save_settings(cfg)
        path = write_page(cfg, words, lang)
        print(words["board_page_set"].format(path=path))
        return 0
    if args.cmd == "ring":
        if args.ntfy is not None:
            if args.ntfy and urllib.parse.urlparse(args.ntfy).scheme not in ("http", "https"):
                print(words["board_ring_bad"])
                return 1
            if args.ntfy:
                cfg["ntfy"] = args.ntfy
            else:
                cfg.pop("ntfy", None)
        if args.when:
            cfg["when"] = args.when
        save_settings(cfg)
        places = (["telegram"] if (remote.load().get("telegram") or {}).get("token") else []) + \
                 (["ntfy"] if cfg.get("ntfy") else [])
        print(words["board_ring_set"].format(where=", ".join(places) or "-",
                                             when=words["board_when_" + cfg.get("when", "away")]))
        if args.test:
            took = ring(words["board_ring_test"], cfg)
            print(words["board_rang"].format(where=", ".join(took) or "-"))
            return 0 if took else 1
        return 0
    # clear
    for job in jobs():
        if args.all or job["state"] == "done":
            (folder() / f"{safe_id(job['id'])}.json").unlink(missing_ok=True)
    write_page(cfg, words, lang)
    print(words["board_cleared"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
