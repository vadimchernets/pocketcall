#!/usr/bin/env python3
"""Branch D: the phone remote without a terminal. Pair this computer with the company's relay and
with a messenger, say when you are away, and every permission question Claude Code asks while you
are away arrives on the phone as an approval card with Yes, No and Show the diff.

    remote.py pair --relay https://relay.example.com     the phone link (and a QR when qrencode is here)
    remote.py join --link "<the phone link>"               another computer that stays on, same phone
    remote.py telegram --token <bot token> --allow <your Telegram user id>
    remote.py away                                         cards go to the phone from now on
    remote.py back                                         at the desk: the questions stay on this screen
    remote.py status
    remote.py test                                         one real card, answered from the phone
    remote.py off                                          forget the pairing

The settings live in ~/.pocketcall/remote.json (POCKETCALL_HOME moves the folder), readable by this
user only. The approvals themselves are made by scripts/approve_hook.py, the plugin's
PermissionRequest hook; it stays silent unless this computer is paired and marked away. A computer
joined with `join` (the machine that runs the relay, say) shares the phone: scripts/task.py runs the
desk there, which takes the phone's notes and sends pull request cards while the laptop sleeps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import approval_card  # noqa: E402
import check  # noqa: E402
import seal  # noqa: E402

TELEGRAM_TEXT = 3800  # a Telegram message holds 4096 characters; the card keeps room for its buttons
TELEGRAM_CAPTION = 1000  # a document's caption holds 1024
ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PRESSES = ("y", "n", "d")
SPOOL_DAYS = 1


def home() -> Path:
    return Path(os.environ.get("POCKETCALL_HOME") or Path.home() / ".pocketcall")


def spool_put(card_id: str, kind: str, update_id: int) -> None:
    """A press for a card another pocketcall process on this computer waits for (the hook and the
    desk read the same bot): one small file per press, which that process takes."""
    folder = home() / "telegram"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        old = time.time() - SPOOL_DAYS * 86400
        for path in folder.iterdir():
            if path.stat().st_mtime < old:
                path.unlink()
        (folder / f"{card_id}.{int(update_id)}").write_text(kind, encoding="utf-8")
    except OSError:
        pass


def spool_take(card_id: str) -> list:
    """The presses other processes put aside for this card, oldest first."""
    found = []
    folder = home() / "telegram"
    if not ID.match(card_id) or not folder.is_dir():
        return found
    presses = folder.glob(f"{card_id}.*")
    for path in sorted(presses, key=lambda p: int(p.suffix[1:]) if p.suffix[1:].isdigit() else 0):
        try:
            kind = path.read_text(encoding="utf-8").strip()
            path.unlink()
        except OSError:
            continue
        if kind in PRESSES:
            found.append(kind)
    return found


def load() -> dict:
    try:
        return json.loads((home() / "remote.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(cfg: dict) -> None:
    folder = home()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "remote.json"
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _http(url: str, data: dict | None = None, timeout: float = 40):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def _upload(url: str, fields: dict, name: str, filename: str, data: bytes, timeout: float = 60):
    """One multipart/form-data POST carrying a text file, as Telegram takes a document."""
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8")
             for key, value in fields.items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                 f"Content-Type: text/plain; charset=utf-8\r\n\r\n".encode("utf-8") + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(url, data=b"".join(parts), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


class Relay:
    """The computer's side of the company relay."""

    def __init__(self, url: str, secret: str):
        self.url = url.rstrip("/")
        self.pair = seal.Pair(secret)

    def send(self, card: dict) -> None:
        _http(f"{self.url}/r/{self.pair.room}/ask", {"id": card["id"], "box": self.pair.seal(card)}, 15)

    def poll(self, ask_id: str, wait: float = 2):
        status, data = _http(f"{self.url}/r/{self.pair.room}/answer?id={ask_id}&wait={wait}", None, wait + 15)
        if status != 200 or not data or not data.get("box"):
            return None
        try:
            answer = self.pair.open(data["box"])
        except seal.BadBox:
            return None
        if answer.get("id") != ask_id or answer.get("say") not in ("yes", "no"):
            return None
        return answer["say"]


class Telegram:
    """The approval card in Telegram, through a bot of the company's own. Only the people on the
    allowlist can press its buttons; anyone else's press is ignored. Several cards can wait at once,
    and a press for a card another pocketcall process on this computer sent is put aside for it.
    A card longer than one message arrives whole as a text file under the same buttons, Yes included,
    and a diff longer than one message arrives as one file."""

    def __init__(self, token: str, chat, allow, words: dict):
        self.api = (os.environ.get("POCKETCALL_TELEGRAM_API") or "https://api.telegram.org").rstrip("/")
        self.base = f"{self.api}/bot{token}"
        self.chat = chat
        self.allow = {int(a) for a in allow}
        self.words = words
        self.offset = None
        self.cards = {}   # card id -> (the card, whether it offered Yes)
        self.said = {}    # card id -> "yes" | "no", read while waiting for another card

    def call(self, method: str, **params):
        _, data = _http(f"{self.base}/{method}", params, 40)
        return (data or {}).get("result")

    def upload(self, method: str, filename: str, text: str, **params):
        """A Telegram method that takes a document: the text goes as a file named filename."""
        fields = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
        _, data = _upload(f"{self.base}/{method}", fields, "document", filename, text.encode("utf-8"))
        return (data or {}).get("result")

    def remember(self, card: dict, yes_offered: bool) -> None:
        self.cards[card["id"]] = (card, bool(yes_offered))

    def send(self, card: dict) -> None:
        text = approval_card.text_of(card, self.words)
        yes = bool(card["complete"])
        if not yes:                    # a card cut to fit: what cannot be read in full is answered at the desk
            text += "\n\n" + self.words["approve_cut"]
        row = [{"text": self.words["approve_yes"], "callback_data": f"y:{card['id']}"}] if yes else []
        row += [{"text": self.words["approve_no"], "callback_data": f"n:{card['id']}"},
                {"text": self.words["approve_diff"], "callback_data": f"d:{card['id']}"}]
        keys = {"inline_keyboard": [row]}
        if len(text) <= TELEGRAM_TEXT:
            self.call("sendMessage", chat_id=self.chat, text=text, reply_markup=keys)
        else:                          # longer than a message: the whole card as a file, nothing left out
            whole = text + ("\n\n" + self.words["approve_diff_head"] + "\n" + card["diff"] if card.get("diff") else "")
            caption = (card.get("heading") or self.words["approve_title"]) + "\n\n" + self.words["approve_in_file"]
            self.upload("sendDocument", f"card-{card['id'][:12]}.txt", whole, chat_id=self.chat,
                        caption=caption[:TELEGRAM_CAPTION], reply_markup=keys)
        self.remember(card, yes)

    def press(self, card_id: str, kind: str) -> None:
        """A press from the allowlist on one of this process's cards."""
        card, offered = self.cards[card_id]
        if kind == "d":
            diff = card.get("diff") or card.get("url") or self.words["approve_no_diff"]
            if len(diff) <= TELEGRAM_TEXT:
                self.call("sendMessage", chat_id=self.chat, text=diff)
            else:                      # one file, not a stream of messages
                self.upload("sendDocument", f"diff-{card_id[:12]}.txt", diff, chat_id=self.chat,
                            caption=self.words["approve_diff_head"])
        elif kind == "y" and offered:
            self.said[card_id] = "yes"
        elif kind == "n":
            self.said[card_id] = "no"

    def poll(self, ask_id: str, wait: float = 2):
        if ask_id in self.cards:
            for kind in spool_take(ask_id):
                self.press(ask_id, kind)
        if ask_id in self.said:
            return self.said.pop(ask_id)
        # messages too: a voice note or "stop" sent while a card waits is kept for steer.py, not lost
        params = {"timeout": int(wait), "allowed_updates": ["callback_query", "message"]}
        if self.offset is not None:
            params["offset"] = self.offset
        for update in self.call("getUpdates", **params) or []:
            self.offset = update["update_id"] + 1
            q = update.get("callback_query") or {}
            who = (q.get("from") or {}).get("id")
            kind, _, qid = str(q.get("data", "")).partition(":")
            if update.get("message") or kind in ("c", "s"):
                import steer  # noqa: PLC0415 - steer imports this module
                steer.spool_message(update)
                continue
            if kind not in PRESSES or not ID.match(qid):
                continue
            self.call("answerCallbackQuery", callback_query_id=q.get("id"))
            if who not in self.allow:
                continue
            if qid in self.cards:
                self.press(qid, kind)
            else:
                spool_put(qid, kind, update["update_id"])
        return self.said.pop(ask_id, None)


def channels(cfg: dict, words: dict) -> list:
    out = []
    if cfg.get("relay") and cfg.get("secret"):
        out.append(Relay(cfg["relay"], cfg["secret"]))
    tg = cfg.get("telegram") or {}
    if tg.get("token") and tg.get("allow"):
        out.append(Telegram(tg["token"], tg.get("chat") or tg["allow"][0], tg["allow"], words))
    return out


def ask(card: dict, cfg: dict, words: dict, wait: float) -> str | None:
    """Send the card everywhere this computer is paired and return the first answer: "yes", "no",
    or None when nobody answered in time (the question then stays on the screen at the desk)."""
    live = []
    for ch in channels(cfg, words):
        try:
            ch.send(card)
            live.append(ch)
        except (OSError, urllib.error.URLError, ValueError):
            continue
    end = time.monotonic() + wait
    while live and time.monotonic() < end:
        for ch in list(live):
            try:
                say = ch.poll(card["id"], wait=1 if len(live) > 1 else 2)
            except (OSError, urllib.error.URLError, ValueError):
                say = None
            if say == "yes" and not card["complete"]:
                say = "no"
            if say:
                return say
    return None


def phone_link(relay: str, secret: str) -> str:
    return f"{relay.rstrip('/')}/#k={secret}"


def link_parts(link: str) -> tuple:
    """The phone link -> (the relay's address, the pairing secret), or (address, "") when the link
    carries no usable key."""
    base, _, fragment = link.strip().partition("#")
    found = re.search(r"(?:^|&)k=([A-Za-z0-9_-]+)", fragment)
    if not found:
        return base.rstrip("/"), ""
    try:
        seal.Pair(found.group(1))
    except ValueError:
        return base.rstrip("/"), ""
    return base.rstrip("/"), found.group(1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pocketcall branch D: approvals on the phone, no terminal.")
    ap.add_argument("--lang", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair")
    p.add_argument("--relay", required=True)
    j = sub.add_parser("join")
    j.add_argument("--link", required=True, help="the phone link remote.py pair printed on the first computer")
    t = sub.add_parser("telegram")
    t.add_argument("--token", required=True)
    t.add_argument("--allow", required=True, action="append", type=int)
    t.add_argument("--chat", type=int, default=None)
    for name in ("away", "back", "status", "off"):
        sub.add_parser(name)
    sub.add_parser("test").add_argument("--wait", type=float, default=300)
    args = ap.parse_args(argv)
    words = check.lang_words(check.pick_lang(args.lang))
    cfg = load()

    if args.cmd == "pair":
        cfg.update(relay=args.relay.rstrip("/"), secret=seal.new_secret())
        save(cfg)
        link = phone_link(cfg["relay"], cfg["secret"])
        print(words["remote_paired"])
        print(link)
        if shutil.which("qrencode"):
            subprocess.run(["qrencode", "-t", "ANSIUTF8", link], check=False)
        return 0
    if args.cmd == "join":
        address, secret = link_parts(args.link)
        if not address or not secret:
            print(words["remote_bad_link"])
            return 1
        cfg.update(relay=address, secret=secret)
        save(cfg)
        print(words["remote_joined"])
        return 0
    if args.cmd == "telegram":
        cfg["telegram"] = {"token": args.token, "allow": args.allow, "chat": args.chat or args.allow[0]}
        save(cfg)
        print(words["remote_telegram"])
        return 0
    if args.cmd in ("away", "back"):
        if not channels(cfg, words):
            print(words["remote_not_paired"])
            return 1
        cfg["away"] = args.cmd == "away"
        save(cfg)
        print(words["remote_away" if cfg["away"] else "remote_back"])
        return 0
    if args.cmd == "off":
        (home() / "remote.json").unlink(missing_ok=True)
        print(words["remote_off"])
        return 0
    if args.cmd == "status":
        names = [type(c).__name__ for c in channels(cfg, words)]
        print(words["remote_status"].format(paths=", ".join(names) or "-",
                                            state=words["remote_away" if cfg.get("away") else "remote_back"]))
        return 0 if names else 1
    # test
    card = {"id": uuid.uuid4().hex, "tool": "Bash", "command": "echo pocketcall", "files": [],
            "diff": "", "folder": os.getcwd(), "complete": True}
    say = ask(card, cfg, words, args.wait)
    print(words["remote_test_answer"].format(answer=say or "-"))
    return 0 if say else 1


if __name__ == "__main__":
    raise SystemExit(main())
