#!/usr/bin/env python3
"""The company's own relay between a computer running Claude Code and a phone. One command:

    python3 scripts/relay.py --port 8787 [--push https://ntfy.example.com/team-approvals]

Standard library only: no database, no Redis, no object store, nothing to install. Put it on any
machine both sides reach (an office server, a small VM, a Tailscale node) behind the company's
HTTPS. Both the computer and the phone connect outward to it; it opens no connection to either.

It forwards sealed boxes (scripts/seal.py) it cannot open: the pairing secret lives only in the
phone link's #fragment and on the computer. A room is named by a value derived from the secret, so
the relay knows which boxes belong together and nothing else.

  GET  /                          the phone page (scripts/phone/index.html)
  GET  /seal.js                   its sealing code
  POST /r/<room>/ask              {"id", "box"}  a decision waiting; sends the push
  GET  /r/<room>/asks             {"asks": [{"id", "box"}]}  what the phone has to answer
  POST /r/<room>/answer           {"id", "box"}  the phone's sealed answer
  GET  /r/<room>/answer?id=&wait= {"box"}  the computer waits for it (long poll), 204 if none

--push sends one line, "A decision is waiting", to an ntfy-style URL (a self-hosted ntfy server
or ntfy.sh topic): its app on the phone rings. The line carries no command, file or name.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PHONE = Path(__file__).resolve().parent / "phone"
ROOM = re.compile(r"^/r/([0-9a-f]{32})/(ask|asks|answer)$")
ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_BODY = 2 * 1024 * 1024
MAX_ASKS = 64
PUSH_TEXT = "A decision is waiting"


class Store:
    """Boxes in memory, by room. Nothing is written to disk."""

    def __init__(self):
        self.lock = threading.Condition()
        self.asks: dict[str, dict[str, str]] = {}
        self.answers: dict[str, dict[str, str]] = {}

    def ask(self, room, ask_id, box):
        with self.lock:
            asks = self.asks.setdefault(room, {})
            if len(asks) >= MAX_ASKS and ask_id not in asks:
                asks.pop(next(iter(asks)))
            asks[ask_id] = box

    def pending(self, room):
        with self.lock:
            return [{"id": k, "box": v} for k, v in self.asks.get(room, {}).items()]

    def answer(self, room, ask_id, box):
        with self.lock:
            if ask_id not in self.asks.get(room, {}):
                return False
            self.asks[room].pop(ask_id)
            self.answers.setdefault(room, {})[ask_id] = box
            self.lock.notify_all()
            return True

    def take(self, room, ask_id, wait):
        end = time.monotonic() + wait
        with self.lock:
            while True:
                box = self.answers.get(room, {}).pop(ask_id, None)
                if box is not None or time.monotonic() >= end:
                    return box
                self.lock.wait(max(0.05, end - time.monotonic()))


def push(url: str, timeout: float = 5) -> bool:
    if not url:
        return False
    try:
        req = urllib.request.Request(url, data=PUSH_TEXT.encode(), method="POST",
                                     headers={"Title": "Pocketcall", "Priority": "high"})
        urllib.request.urlopen(req, timeout=timeout).close()
        return True
    except OSError:
        return False


def make_handler(store: Store, push_url: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "pocketcall-relay"

        def log_message(self, *args):  # boxes and rooms stay out of the log
            pass

        def send(self, code, value=None, kind="application/json"):
            body = b"" if value is None else (value if isinstance(value, bytes) else json.dumps(value).encode())
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            size = int(self.headers.get("Content-Length") or 0)
            if size > MAX_BODY:
                return None
            try:
                data = json.loads(self.rfile.read(size) or b"{}")
            except ValueError:
                return None
            if not isinstance(data, dict) or not ID.match(str(data.get("id", ""))) \
                    or not isinstance(data.get("box"), str):
                return None
            return data

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self.send(200, (PHONE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path == "/seal.js":
                return self.send(200, (PHONE / "seal.js").read_bytes(), "text/javascript; charset=utf-8")
            m = ROOM.match(url.path)
            if not m:
                return self.send(404, {"error": "no such place"})
            room, what = m.groups()
            if what == "asks":
                return self.send(200, {"asks": store.pending(room)})
            if what == "answer":
                q = parse_qs(url.query)
                ask_id = (q.get("id") or [""])[0]
                if not ID.match(ask_id):
                    return self.send(400, {"error": "id"})
                wait = min(max(float((q.get("wait") or ["0"])[0] or 0), 0), 30)
                box = store.take(room, ask_id, wait)
                return self.send(200, {"box": box}) if box else self.send(204)
            return self.send(405, {"error": "method"})

        def do_POST(self):
            m = ROOM.match(urlparse(self.path).path)
            data = self.body()
            if not m or data is None:
                return self.send(400, {"error": "bad request"})
            room, what = m.groups()
            if what == "ask":
                store.ask(room, data["id"], data["box"])
                threading.Thread(target=push, args=(push_url,), daemon=True).start()
                return self.send(204)
            if what == "answer":
                return self.send(204) if store.answer(room, data["id"], data["box"]) \
                    else self.send(404, {"error": "nothing waits under that id"})
            return self.send(405, {"error": "method"})

    return Handler


def serve(host: str, port: int, push_url: str = "") -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(Store(), push_url))
    server.daemon_threads = True
    return server


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pocketcall relay: sealed approvals between a computer and a phone.")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--push", default="", help="ntfy-style URL that rings the phone when a decision is waiting")
    args = ap.parse_args(argv)
    server = serve(args.host, args.port, args.push)
    print(f"Pocketcall relay on port {server.server_address[1]}. Pair a computer with: "
          f"remote.py pair --relay https://<this machine's address>", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
