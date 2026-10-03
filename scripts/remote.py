#!/usr/bin/env python3
"""Branch D: the phone remote without a terminal. Pair this computer with the company's relay and
with a messenger, say when you are away, and every permission question Claude Code asks while you
are away arrives on the phone as an approval card with Yes, No and Show the diff.

    remote.py pair --relay https://relay.example.com     the phone link (and a QR when qrencode is here)
    remote.py telegram --token <bot token> --allow <your Telegram user id>
    remote.py away                                         cards go to the phone from now on
    remote.py back                                         at the desk: the questions stay on this screen
    remote.py status
    remote.py test                                         one real card, answered from the phone
    remote.py off                                          forget the pairing

The settings live in ~/.pocketcall/remote.json (POCKETCALL_HOME moves the folder), readable by this
user only. The approvals themselves are made by scripts/approve_hook.py, the plugin's
PermissionRequest hook; it stays silent unless this computer is paired and marked away.
"""

from __future__ import annotations

import argparse
import json
import os
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


def home() -> Path:
    return Path(os.environ.get("POCKETCALL_HOME") or Path.home() / ".pocketcall")


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
    allowlist can press its buttons; anyone else's press is ignored."""

    def __init__(self, token: str, chat, allow, words: dict):
        self.api = (os.environ.get("POCKETCALL_TELEGRAM_API") or "https://api.telegram.org").rstrip("/")
        self.base = f"{self.api}/bot{token}"
        self.chat = chat
        self.allow = {int(a) for a in allow}
        self.words = words
        self.offset = None
        self.card = None
        self.yes_offered = False

    def call(self, method: str, **params):
        _, data = _http(f"{self.base}/{method}", params, 40)
        return (data or {}).get("result")

    def send(self, card: dict) -> None:
        self.card = card
        text = approval_card.text_of(card, self.words)
        fits = card["complete"] and len(text) <= TELEGRAM_TEXT
        if not fits:
            text = text[:TELEGRAM_TEXT] + "\n\n" + self.words["approve_cut"]
        row = [{"text": self.words["approve_yes"], "callback_data": f"y:{card['id']}"}] if fits else []
        row += [{"text": self.words["approve_no"], "callback_data": f"n:{card['id']}"},
                {"text": self.words["approve_diff"], "callback_data": f"d:{card['id']}"}]
        self.call("sendMessage", chat_id=self.chat, text=text, reply_markup={"inline_keyboard": [row]})
        self.yes_offered = fits

    def poll(self, ask_id: str, wait: float = 2):
        params = {"timeout": int(wait), "allowed_updates": ["callback_query"]}
        if self.offset is not None:
            params["offset"] = self.offset
        for update in self.call("getUpdates", **params) or []:
            self.offset = update["update_id"] + 1
            q = update.get("callback_query") or {}
            who = (q.get("from") or {}).get("id")
            kind, _, qid = str(q.get("data", "")).partition(":")
            if qid != ask_id:
                continue
            self.call("answerCallbackQuery", callback_query_id=q.get("id"))
            if who not in self.allow:
                continue
            if kind == "d":
                diff = (self.card or {}).get("diff") or self.words["approve_no_diff"]
                for part in approval_card.chunks(diff, TELEGRAM_TEXT):
                    self.call("sendMessage", chat_id=self.chat, text=part)
            elif kind == "y" and self.yes_offered:
                return "yes"
            elif kind == "n":
                return "no"
        return None


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pocketcall branch D: approvals on the phone, no terminal.")
    ap.add_argument("--lang", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair")
    p.add_argument("--relay", required=True)
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
