#!/usr/bin/env python3
"""Steer long work from the phone: Continue and Stop for a night run or a long build, and a voice
note that becomes the next task.

    steer.py stop     --id <job>              the job's folder gets a STOP file: the night loop ends after the step
    steer.py continue --id <job>              STOP goes away; a job that ended goes on with its own command
    steer.py listen [--once] [--wait 30]      take the phone's presses and messages from Telegram:
                                              Continue / Stop under a board ring, "stop" / "continue" typed,
                                              a voice note or "task: ..." -> a new task folder with TASK.md
    steer.py inbox --to <folder> [--start "<command with {folder}>"]
                                              where tasks from the phone land; --start runs one at once
                                              (e.g. bash ~/.claude/.../night-loop.sh {folder} 8)
    steer.py transcribe <audio file>          what the voice note says, with the first transcriber found

Telegram is the chat set with `remote.py telegram`; only the people on its allowlist steer. The board's
rings for a job with a task folder (nightcall puts its folder and its own command there) come with
Continue and Stop buttons; the approval cards' Yes / No / Show the diff are left for the process that
sent them, as before.

Transcribers, the first that is here: POCKETCALL_TRANSCRIBE (a command with {file}), mlx_whisper,
whisper (openai-whisper), whisper-cli (whisper.cpp, POCKETCALL_WHISPER_MODEL), then the person's own
OPENAI_API_KEY (gpt-4o-mini-transcribe) or GROQ_API_KEY (whisper-large-v3-turbo). With none the
audio is kept next to TASK.md and the phone is told to type the task.

State: ~/.pocketcall/steer.json (inbox, start) and ~/.pocketcall/steer-spool/ (messages the approval
process read while waiting for its card). POCKETCALL_HOME moves them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board  # noqa: E402
import check  # noqa: E402
import remote  # noqa: E402

STOP_WORDS = ("stop", "\u0441\u0442\u043e\u043f", "\u0441\u0442\u043e\u0439", "\u0437\u0443\u043f\u0438\u043d\u0438\u0441\u044c", "pare", "para", "detente", "alto")
GO_WORDS = ("continue", "go on", "\u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u0439", "\u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438", "\u0434\u0430\u043b\u0456", "\u043f\u0440\u043e\u0434\u043e\u0432\u0436\u0443\u0439", "continua", "contin\u00faa", "sigue",
            "continue!")
TASK_HEAD = re.compile(r"^\s*(/task|task|\u0442\u0437|\u0437\u0430\u0434\u0430\u0447\u0430|\u0437\u0430\u0432\u0434\u0430\u043d\u043d\u044f|tarea|tarefa)\s*[:\-]?\s*", re.I)


def home() -> Path:
    return remote.home()


def settings() -> dict:
    try:
        return json.loads((home() / "steer.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(cfg: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    path = home() / "steer.json"
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(path, 0o600)


# --- Continue and Stop --------------------------------------------------------------------------

def stop(job_id: str, words: dict) -> str:
    job = board.get(job_id)
    if not job.get("folder") or not Path(job["folder"]).is_dir():
        return words["steer_no_folder"].format(job=job.get("name") or job_id)
    (Path(job["folder"]) / "STOP").write_text(f"stopped from the phone at {time.strftime('%H:%M')}\n",
                                              encoding="utf-8")
    return words["steer_stopped"].format(job=job.get("name") or job_id)


def night_loop() -> str:
    """nightcall's own loop on THIS computer: POCKETCALL_NIGHTLOOP (the owner's environment), else the newest
    installed nightcall plugin. Never a path or a command taken from a job card."""
    named = os.environ.get("POCKETCALL_NIGHTLOOP", "")
    if named:
        return named if os.path.isfile(named) else ""
    roots = [Path(os.environ["CLAUDE_CONFIG_DIR"])] if os.environ.get("CLAUDE_CONFIG_DIR") else []
    roots.append(Path.home() / ".claude")
    found = [p for r in roots for p in r.glob("plugins/cache/*/nightcall/*/scripts/night-loop.sh")]
    return str(max(found, key=lambda p: p.stat().st_mtime)) if found else ""


def night_argv(job: dict, folder: Path) -> tuple:
    """Continue for a night run, built here from the card's DATA (kind, folder, hours, end, box), with no shell:
    a card is a file other programs can write, so it never carries a command. ([], None) for anything else."""
    if job.get("kind") != "night" or not (folder / "PLAN.md").is_file():
        return [], None
    loop = night_loop()
    if not loop:
        return [], None
    try:
        hours = max(1, int(float(job.get("hours") or 8)))
        end = float(job.get("end") or 0)
    except (TypeError, ValueError):
        hours, end = 8, 0
    if end > time.time():                      # Continue goes on to the night's own end, not a fresh full night
        hours = max(1, int((end - time.time() + 3599) // 3600))
    env = dict(os.environ)
    if job.get("box") is True:
        env["NIGHTCALL_BOX"] = "1"             # the night was in the box: it goes on in the box
    return ["bash", loop, str(folder), str(hours)], env


def go_on(job_id: str, words: dict, lang: str) -> str:
    job = board.get(job_id)
    folder = Path(job.get("folder") or "")
    if not job.get("folder") or not folder.is_dir():
        return words["steer_no_folder"].format(job=job.get("name") or job_id)
    (folder / "STOP").unlink(missing_ok=True)
    argv, env = night_argv(job, folder)
    if job.get("state") == "working" or not argv:
        return words["steer_goes_on"].format(job=job.get("name") or job_id)
    morning = folder / "MORNING.md"           # a report already written ends a night loop at once
    if morning.exists():
        morning.rename(folder / f"MORNING-{time.strftime('%Y%m%d-%H%M')}.md")
    with open(folder / "steer.log", "a", encoding="utf-8") as log:
        subprocess.Popen(argv, cwd=str(folder), env=env, stdin=subprocess.DEVNULL, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    board.put(dict(job, state="working", note=words["steer_resumed_note"]), words, lang, quiet=True)
    return words["steer_resumed"].format(job=job.get("name") or job_id)


def press(kind: str, job_id: str, words: dict, lang: str) -> str:
    return stop(job_id, words) if kind == "s" else go_on(job_id, words, lang)


def steerable() -> list:
    return [j for j in board.jobs() if j.get("folder")]


def command_of(text: str) -> tuple:
    """("s"|"c"|"", the rest): the command is the whole first word (or "go on"), never a prefix of one."""
    low = " ".join(text.strip().lower().split())
    for kind, table in (("s", STOP_WORDS), ("c", GO_WORDS)):
        for w in sorted(table, key=len, reverse=True):
            if low == w or low.startswith(w + " "):
                return kind, low[len(w):].strip()
    return "", ""


def by_words(text: str, words: dict, lang: str) -> str | None:
    """"stop" / "continue" typed in the chat, optionally with part of the job's name."""
    kind, rest = command_of(text)
    if not kind:
        return None
    jobs = steerable()
    if rest:
        jobs = [j for j in jobs if rest in str(j.get("name", "")).lower()]
    if kind == "s":
        jobs = [j for j in jobs if j["state"] in ("working", "limit")] or jobs
    if len(jobs) != 1:
        names = ", ".join(str(j.get("name")) for j in steerable()) or "-"
        return words["steer_which"].format(names=names)
    return press(kind, jobs[0]["id"], words, lang)


# --- a voice note becomes a task ----------------------------------------------------------------

def _post_audio(url: str, key: str, model: str, path: Path, timeout: float = 120) -> str:
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + path.read_bytes() + \
        f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return str(json.loads(resp.read() or b"{}").get("text") or "").strip()


def transcribe(path: Path) -> tuple:
    """(the text, which transcriber) - ("", "") when none is here or none could hear it."""
    tmp = Path(tempfile.mkdtemp())
    own = os.environ.get("POCKETCALL_TRANSCRIBE")
    tries = []
    if own:
        tries.append(("own", shlex.split(own.replace("{file}", shlex.quote(str(path))))))
    if shutil.which("mlx_whisper"):
        tries.append(("mlx_whisper", ["mlx_whisper", str(path), "--output-format", "txt", "--output-dir", str(tmp)]))
    if shutil.which("whisper"):
        tries.append(("whisper", ["whisper", str(path), "--model", os.environ.get("POCKETCALL_WHISPER", "turbo"),
                                  "--output_format", "txt", "--output_dir", str(tmp)]))
    if shutil.which("whisper-cli") and os.environ.get("POCKETCALL_WHISPER_MODEL"):
        tries.append(("whisper-cli", ["whisper-cli", "-m", os.environ["POCKETCALL_WHISPER_MODEL"], "-f", str(path),
                                      "-otxt", "-of", str(tmp / path.stem)]))
    for name, cmd in tries:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.SubprocessError):
            continue
        found = sorted(tmp.glob("*.txt"))
        text = found[0].read_text(encoding="utf-8").strip() if found else (p.stdout.strip() if name == "own" else "")
        if p.returncode == 0 and text:
            return text, name
    for env, url, model in (("OPENAI_API_KEY", "https://api.openai.com/v1/audio/transcriptions", "gpt-4o-mini-transcribe"),
                            ("GROQ_API_KEY", "https://api.groq.com/openai/v1/audio/transcriptions", "whisper-large-v3-turbo")):
        if os.environ.get(env):
            try:
                text = _post_audio(os.environ.get(env + "_URL") or url, os.environ[env], model, path)
                if text:
                    return text, model
            except Exception:  # noqa: BLE001 - the next one is tried
                continue
    return "", ""


def slug(text: str) -> str:
    s = re.sub(r"[^\w]+", "-", text.lower(), flags=re.U).strip("-")
    return s[:40].strip("-") or "task"


def new_task(text: str, words: dict, lang: str, source: str = "text", audio: Path | None = None) -> str:
    cfg = settings()
    inbox = Path(cfg.get("inbox") or (home() / "inbox")).expanduser()
    folder = inbox / f"{time.strftime('%Y-%m-%d-%H%M')}-{slug(text or 'voice')}"
    folder.mkdir(parents=True, exist_ok=True)
    if audio:
        shutil.copy(audio, folder / ("voice" + (audio.suffix or ".oga")))
    body = text or words["steer_task_no_text"]
    (folder / "TASK.md").write_text(
        f"# {board.short(body.splitlines()[0] if body else 'Task', 80)}\n\n"
        f"<!-- from the phone ({source}), {time.strftime('%Y-%m-%d %H:%M')} -->\n\n{body}\n\n"
        f"## Done when\n- {words['steer_task_done_when']}\n", encoding="utf-8")
    job = {"id": "task-" + folder.name[:50], "name": folder.name, "where": "phone", "folder": str(folder),
           "state": "waiting", "note": board.short(body)}
    start = cfg.get("start")
    if start and text:
        # the owner's own command from steer.json, split into words; the folder is one word of it, never shell text
        argv = [part.replace("{folder}", str(folder)) for part in shlex.split(start)]
        with open(folder / "steer.log", "a", encoding="utf-8") as log:
            subprocess.Popen(argv, cwd=str(folder), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
        job.update(state="working")
    board.put(job, words, lang, quiet=True)
    key = "steer_task_started" if job["state"] == "working" else "steer_task_saved"
    return words[key].format(folder=folder)


# --- the Telegram side --------------------------------------------------------------------------

class Phone:
    def __init__(self, cfg: dict, words: dict, lang: str):
        tg = cfg.get("telegram") or {}
        if not (tg.get("token") and tg.get("allow")):
            raise SystemExit(words["steer_no_telegram"])
        self.api = (os.environ.get("POCKETCALL_TELEGRAM_API") or "https://api.telegram.org").rstrip("/")
        self.token = tg["token"]
        self.chat = tg.get("chat") or tg["allow"][0]
        self.allow = {int(a) for a in tg["allow"]}
        self.words, self.lang = words, lang
        self.offset = None

    def call(self, method: str, **params):
        _, data = remote._http(f"{self.api}/bot{self.token}/{method}", params, 40)
        return (data or {}).get("result")

    def say(self, text: str) -> None:
        try:
            self.call("sendMessage", chat_id=self.chat, text=text[:3800])
        except Exception:  # noqa: BLE001
            pass

    def fetch(self, file_id: str) -> Path | None:
        info = self.call("getFile", file_id=file_id) or {}
        if not info.get("file_path"):
            return None
        out = Path(tempfile.mkdtemp()) / Path(info["file_path"]).name
        with urllib.request.urlopen(f"{self.api}/file/bot{self.token}/{info['file_path']}", timeout=60) as resp:
            out.write_bytes(resp.read())
        return out

    def message(self, msg: dict) -> None:
        if (msg.get("from") or {}).get("id") not in self.allow:
            return
        voice = msg.get("voice") or msg.get("audio")
        if voice:
            path = self.fetch(voice.get("file_id", ""))
            text, how = transcribe(path) if path else ("", "")
            reply = new_task(text, self.words, self.lang, "voice", path)
            self.say(reply + ("\n\n" + text if text else "\n\n" + self.words["steer_no_transcriber"]))
            return
        text = str(msg.get("text") or "")
        if not text.strip():
            return
        answer = by_words(text, self.words, self.lang)
        if answer is None and TASK_HEAD.match(text):
            answer = new_task(TASK_HEAD.sub("", text, count=1).strip(), self.words, self.lang)
        if answer:
            self.say(answer)

    def update(self, upd: dict) -> None:
        q = upd.get("callback_query")
        if q:
            kind, _, qid = str(q.get("data", "")).partition(":")
            if kind in ("c", "s"):
                try:
                    self.call("answerCallbackQuery", callback_query_id=q.get("id"))
                except Exception:  # noqa: BLE001
                    pass
                if (q.get("from") or {}).get("id") in self.allow:
                    self.say(press(kind, qid, self.words, self.lang))
            elif kind in remote.PRESSES and remote.ID.match(qid):
                remote.spool_put(qid, kind, upd.get("update_id", 0))   # an approval card's press: its process takes it
            return
        if upd.get("message"):
            self.message(upd["message"])

    def poll(self, wait: int) -> int:
        for path in sorted((home() / "steer-spool").glob("*.json")) if (home() / "steer-spool").is_dir() else []:
            try:
                self.update(json.loads(path.read_text(encoding="utf-8")))
            finally:
                path.unlink(missing_ok=True)
        # one poller per bot: while remote.py waits for an approval card it holds this lock and reads the
        # updates itself (and keeps ours in the spool); getUpdates from two places makes Telegram answer 409
        with remote.poll_lock(block=False) as mine:
            if not mine:
                time.sleep(min(wait, 2))
                return 0
            return self._fetch(min(wait, 10))

    def _fetch(self, wait: int) -> int:
        params = {"timeout": wait, "allowed_updates": ["callback_query", "message"]}
        if self.offset is not None:
            params["offset"] = self.offset
        got = self.call("getUpdates", **params) or []
        for upd in got:
            self.offset = upd["update_id"] + 1
            self.update(upd)
        return len(got)


def sender(update: dict):
    src = update.get("message") or update.get("callback_query") or {}
    return (src.get("from") or {}).get("id")


def spool_message(update: dict, allow=None) -> None:
    """A message or a Continue/Stop press the approval process read while it waited for its card - only the
    allowlist's, readable by this user only."""
    if allow is not None and sender(update) not in set(allow):
        return
    folder = home() / "steer-spool"
    try:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = folder / f"{int(update.get('update_id', 0)):012d}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(update, fh)
    except OSError:
        pass


def install(dry: bool = False) -> str:
    """Keep `steer.py listen` alive after the Claude Code session ends: a LaunchAgent on a Mac, a systemd user
    service on Linux, both restarted if they stop."""
    script = str(Path(__file__).resolve())
    env_home = os.environ.get("POCKETCALL_HOME", "")
    if sys.platform == "darwin":
        target = Path(os.environ.get("POCKETCALL_AGENT_DIR") or Path.home() / "Library" / "LaunchAgents") / \
            "ai.polya1.pocketcall.steer.plist"
        envs = f"<key>EnvironmentVariables</key><dict><key>POCKETCALL_HOME</key><string>{env_home}</string></dict>" \
            if env_home else ""
        body = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
                "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n<plist version=\"1.0\"><dict>"
                "<key>Label</key><string>ai.polya1.pocketcall.steer</string>"
                f"<key>ProgramArguments</key><array><string>{sys.executable}</string><string>{script}</string>"
                "<string>listen</string></array>"
                f"{envs}<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>"
                f"<key>StandardErrorPath</key><string>{home() / 'steer-listen.log'}</string>"
                "</dict></plist>\n")
        load = ["launchctl", "load", "-w", str(target)]
    else:
        target = Path(os.environ.get("POCKETCALL_AGENT_DIR") or Path.home() / ".config" / "systemd" / "user") / \
            "pocketcall-steer.service"
        body = ("[Unit]\nDescription=pocketcall: Continue / Stop and voice tasks from the phone\n\n[Service]\n"
                f"ExecStart={sys.executable} {script} listen\nRestart=always\nRestartSec=10\n"
                + (f"Environment=POCKETCALL_HOME={env_home}\n" if env_home else "")
                + "\n[Install]\nWantedBy=default.target\n")
        load = ["systemctl", "--user", "enable", "--now", "pocketcall-steer.service"]
    if dry:
        return body
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    if not os.environ.get("POCKETCALL_NO_LOAD"):
        subprocess.run(load, capture_output=True)
    return str(target)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pocketcall: Continue / Stop and voice tasks from the phone.")
    ap.add_argument("--lang", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("stop", "continue"):
        p = sub.add_parser(name)
        p.add_argument("--id", required=True)
    p = sub.add_parser("listen")
    p.add_argument("--once", action="store_true")
    p.add_argument("--wait", type=int, default=30)
    p = sub.add_parser("inbox")
    p.add_argument("--to", default="")
    p.add_argument("--start", default=None)
    p = sub.add_parser("install")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("transcribe")
    p.add_argument("file")
    args = ap.parse_args(argv)
    lang = check.pick_lang(args.lang or remote.load().get("lang"))
    words = check.lang_words(lang)
    if args.cmd == "stop":
        print(stop(args.id, words))
        return 0
    if args.cmd == "continue":
        print(go_on(args.id, words, lang))
        return 0
    if args.cmd == "install":
        print(install(args.dry_run))
        return 0
    if args.cmd == "transcribe":
        text, how = transcribe(Path(args.file))
        print(text or words["steer_no_transcriber"])
        return 0 if text else 1
    if args.cmd == "inbox":
        cfg = settings()
        if args.to:
            Path(args.to).expanduser().mkdir(parents=True, exist_ok=True)
            cfg["inbox"] = str(Path(args.to).expanduser().resolve())
        if args.start is not None:
            cfg["start"] = args.start
        save_settings(cfg)
        print(words["steer_inbox_set"].format(folder=cfg.get("inbox") or home() / "inbox",
                                              start=cfg.get("start") or "-"))
        return 0
    phone = Phone(remote.load(), words, lang)
    print(words["steer_listening"])
    while True:
        try:
            phone.poll(0 if args.once else args.wait)
        except KeyboardInterrupt:
            return 0
        except Exception:  # noqa: BLE001 - the network comes back
            if args.once:
                raise
            time.sleep(10)
        if args.once:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
