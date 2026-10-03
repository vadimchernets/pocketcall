"""Branch D: the relay, the sealing on both sides, the approval card, the hook and the Telegram card.

Everything runs on this computer: a relay on a free local port, a stand-in Telegram API, and the
phone's own sealing code run by Node when Node is here.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import approval_card  # noqa: E402
import approve_hook  # noqa: E402
import check  # noqa: E402
import relay  # noqa: E402
import remote  # noqa: E402
import seal  # noqa: E402

WORDS = check.lang_words("en")


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, (json.loads(r.read() or b"null") if "json" in r.headers.get("Content-Type", "") else None)


def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


class RelayCase(unittest.TestCase):
    def setUp(self):
        self.pushes = []
        self.server = relay.serve("127.0.0.1", 0, "")
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.home = tempfile.mkdtemp()
        os.environ["POCKETCALL_HOME"] = self.home

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        os.environ.pop("POCKETCALL_HOME", None)
        shutil.rmtree(self.home, ignore_errors=True)


class TestSeal(unittest.TestCase):
    def test_a_box_opens_with_the_same_secret_and_hides_the_text(self):
        pair = seal.Pair(seal.new_secret())
        box = pair.seal({"command": "rm -rf build"})
        self.assertNotIn("rm -rf", box)
        self.assertEqual(pair.open(box), {"command": "rm -rf build"})

    def test_a_changed_box_or_another_secret_is_refused(self):
        pair = seal.Pair(seal.new_secret())
        raw = bytearray(seal.b64d(pair.seal({"say": "no"})))
        raw[20] ^= 1
        with self.assertRaises(seal.BadBox):
            pair.open(seal.b64e(bytes(raw)))
        with self.assertRaises(seal.BadBox):
            seal.Pair(seal.new_secret()).open(pair.seal({"say": "no"}))

    @unittest.skipUnless(shutil.which("node"), "node")
    def test_the_phone_and_the_computer_open_each_other_s_boxes(self):
        secret = seal.new_secret()
        pair = seal.Pair(secret)
        box = pair.seal({"id": "a1", "command": "git push"})
        js = ("const S=require(%s);(async()=>{const p=await S.pair(%s);const v=await p.open(%s);"
              "console.log(JSON.stringify({room:p.room,v,back:await p.seal({id:v.id,say:'yes'})}))})()"
              % (json.dumps(str(ROOT / "scripts/phone/seal.js")), json.dumps(secret), json.dumps(box)))
        out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30).stdout)
        self.assertEqual(out["room"], pair.room)
        self.assertEqual(out["v"]["command"], "git push")
        self.assertEqual(pair.open(out["back"]), {"id": "a1", "say": "yes"})


class TestRelay(RelayCase):
    def test_the_phone_page_and_its_sealing_code_are_served(self):
        with urllib.request.urlopen(self.url + "/", timeout=10) as r:
            self.assertIn(b"seal.js", r.read())
        with urllib.request.urlopen(self.url + "/seal.js", timeout=10) as r:
            self.assertIn(b"PocketSeal", r.read())

    def test_a_card_goes_through_sealed_and_the_answer_comes_back(self):
        pair = seal.Pair(seal.new_secret())
        card = approval_card.build({"tool_name": "Bash", "tool_input": {"command": "make deploy"}}, "c1")
        self.assertEqual(post(f"{self.url}/r/{pair.room}/ask", {"id": "c1", "box": pair.seal(card)}), 204)
        _, data = get(f"{self.url}/r/{pair.room}/asks")
        self.assertNotIn("make deploy", json.dumps(data))      # the relay holds only ciphertext
        self.assertEqual(pair.open(data["asks"][0]["box"])["command"], "make deploy")
        self.assertEqual(post(f"{self.url}/r/{pair.room}/answer", {"id": "c1", "box": pair.seal({"id": "c1", "say": "yes"})}), 204)
        _, left = get(f"{self.url}/r/{pair.room}/asks")
        self.assertEqual(left["asks"], [])

    def test_an_answer_for_nothing_waiting_is_refused(self):
        room = seal.Pair(seal.new_secret()).room
        self.assertEqual(post(f"{self.url}/r/{room}/answer", {"id": "nope", "box": "x"}), 404)

    def test_the_push_carries_no_secret_text(self):
        seen = []

        class Ntfy(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(self.rfile.read(int(self.headers["Content-Length"])).decode())
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a):
                pass

        ntfy = ThreadingHTTPServer(("127.0.0.1", 0), Ntfy)
        threading.Thread(target=ntfy.serve_forever, daemon=True).start()
        try:
            self.assertTrue(relay.push(f"http://127.0.0.1:{ntfy.server_address[1]}/topic"))
        finally:
            ntfy.shutdown()
            ntfy.server_close()
        self.assertEqual(seen, ["A decision is waiting"])


class TestCard(unittest.TestCase):
    def test_the_card_has_the_full_command_and_every_file(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "notes.txt").write_text("a", encoding="utf-8")
            long = "cp notes.txt backup/notes-old.txt && " + "x" * 5000
            card = approval_card.build({"tool_name": "Bash", "tool_input": {"command": long}, "cwd": d}, "i")
        self.assertEqual(card["command"], long)
        self.assertIn("notes.txt", card["files"])
        self.assertIn("backup/notes-old.txt", card["files"])
        self.assertTrue(card["complete"])

    def test_an_edit_shows_its_diff(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "a.md").write_text("price: 10\n", encoding="utf-8")
            card = approval_card.build({"tool_name": "Edit", "cwd": d, "tool_input": {
                "file_path": "a.md", "old_string": "10", "new_string": "12"}}, "i")
        self.assertEqual(card["files"], ["a.md"])
        self.assertIn("-price: 10", card["diff"])
        self.assertIn("+price: 12", card["diff"])

    def test_a_card_that_does_not_fit_is_incomplete(self):
        card = approval_card.build({"tool_name": "Write", "tool_input": {
            "file_path": "/nonexistent/big.txt", "content": "y\n" * 200_000}}, "i")
        self.assertFalse(card["complete"])


class FakeTelegram(BaseHTTPRequestHandler):
    calls = []
    updates = []

    def do_POST(self):
        method = self.path.rsplit("/", 1)[-1]
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        FakeTelegram.calls.append((method, body))
        result = FakeTelegram.updates[:] if method == "getUpdates" else True
        if method == "getUpdates":
            FakeTelegram.updates.clear()
        data = json.dumps({"ok": True, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class TestTelegram(unittest.TestCase):
    def setUp(self):
        FakeTelegram.calls, FakeTelegram.updates = [], []
        self.api = ThreadingHTTPServer(("127.0.0.1", 0), FakeTelegram)
        threading.Thread(target=self.api.serve_forever, daemon=True).start()
        os.environ["POCKETCALL_TELEGRAM_API"] = f"http://127.0.0.1:{self.api.server_address[1]}"

    def tearDown(self):
        self.api.shutdown()
        self.api.server_close()
        os.environ.pop("POCKETCALL_TELEGRAM_API", None)

    def press(self, who, data, n):
        FakeTelegram.updates.append({"update_id": n, "callback_query": {"id": str(n), "from": {"id": who}, "data": data}})

    def test_the_card_arrives_with_three_buttons_and_only_the_allowlist_decides(self):
        tg = remote.Telegram("T", 7, [7], WORDS)
        card = {"id": "k1", "tool": "Bash", "command": "terraform apply", "files": ["main.tf"],
                "diff": "+x", "folder": "/w", "complete": True}
        tg.send(card)
        method, body = FakeTelegram.calls[0]
        self.assertEqual(method, "sendMessage")
        self.assertIn("terraform apply", body["text"])
        self.assertIn("main.tf", body["text"])
        labels = [b["text"] for b in body["reply_markup"]["inline_keyboard"][0]]
        self.assertEqual(labels, ["Yes", "No", "Show the diff"])
        self.press(99, "y:k1", 1)                 # a stranger presses Yes: ignored
        self.assertIsNone(tg.poll("k1", 0))
        self.press(7, "d:k1", 2)                  # Show the diff: the diff arrives, no decision
        self.assertIsNone(tg.poll("k1", 0))
        self.assertIn(("sendMessage", {"chat_id": 7, "text": "+x"}), FakeTelegram.calls)
        self.press(7, "y:k1", 3)
        self.assertEqual(tg.poll("k1", 0), "yes")

    def test_a_card_cut_to_fit_offers_no_yes(self):
        tg = remote.Telegram("T", 7, [7], WORDS)
        tg.send({"id": "k2", "tool": "Bash", "command": "z" * 9000, "files": [], "diff": "", "folder": "",
                 "complete": True})
        labels = [b["text"] for b in FakeTelegram.calls[0][1]["reply_markup"]["inline_keyboard"][0]]
        self.assertEqual(labels, ["No", "Show the diff"])
        self.press(7, "y:k2", 1)
        self.assertIsNone(tg.poll("k2", 0))


class TestHook(RelayCase):
    def answer_from_phone(self, pair, say):
        def run():
            for _ in range(100):
                _, data = get(f"{self.url}/r/{pair.room}/asks")
                if data["asks"]:
                    a = data["asks"][0]
                    card = pair.open(a["box"])
                    post(f"{self.url}/r/{pair.room}/answer", {"id": a["id"], "box": pair.seal({"id": card["id"], "say": say})})
                    return
                threading.Event().wait(0.05)
        threading.Thread(target=run, daemon=True).start()

    def config(self, away=True):
        cfg = {"relay": self.url, "secret": seal.new_secret(), "away": away, "wait": 10}
        remote.save(cfg)
        return cfg

    def test_away_yes_on_the_phone_allows(self):
        cfg = self.config()
        self.answer_from_phone(seal.Pair(cfg["secret"]), "yes")
        out = approve_hook.decide({"tool_name": "Bash", "tool_input": {"command": "ls"}}, cfg, WORDS)
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PermissionRequest")

    def test_away_no_on_the_phone_denies(self):
        cfg = self.config()
        self.answer_from_phone(seal.Pair(cfg["secret"]), "no")
        out = approve_hook.decide({"tool_name": "Bash", "tool_input": {"command": "ls"}}, cfg, WORDS)
        self.assertEqual(out["hookSpecificOutput"]["decision"]["behavior"], "deny")

    def test_yes_on_an_incomplete_card_counts_as_no(self):
        cfg = self.config()
        self.answer_from_phone(seal.Pair(cfg["secret"]), "yes")
        out = approve_hook.decide({"tool_name": "Write", "tool_input": {
            "file_path": "/nonexistent/x", "content": "y\n" * 200_000}}, cfg, WORDS)
        self.assertEqual(out["hookSpecificOutput"]["decision"]["behavior"], "deny")

    def test_at_the_desk_the_hook_is_silent_and_sends_nothing(self):
        cfg = self.config(away=False)
        self.assertIsNone(approve_hook.decide({"tool_name": "Bash", "tool_input": {"command": "ls"}}, cfg, WORDS))
        _, data = get(f"{self.url}/r/{seal.Pair(cfg['secret']).room}/asks")
        self.assertEqual(data["asks"], [])

    def test_not_paired_the_hook_prints_nothing(self):
        with mock.patch("sys.stdin", io.StringIO('{"tool_name": "Bash"}')), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(approve_hook.main(), 0)
        self.assertEqual(out.getvalue(), "")

    def test_pair_prints_the_phone_link_with_the_key_after_the_hash(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out, mock.patch("shutil.which", return_value=None):
            self.assertEqual(remote.main(["--lang", "en", "pair", "--relay", self.url + "/"]), 0)
        cfg = remote.load()
        self.assertIn(f"{self.url}/#k={cfg['secret']}", out.getvalue())
        self.assertEqual(remote.main(["--lang", "en", "away"]), 0)
        self.assertTrue(remote.load()["away"])


class TestTheWords(unittest.TestCase):
    def test_the_plugin_hook_runs_the_approval_hook_through_the_step0_guard(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        command = hooks["PermissionRequest"][0]["hooks"][0]["command"]
        self.assertIn("python.sh\" pocketcall quiet", command)
        self.assertIn("approve_hook.py", command)

    def test_the_remote_skill_names_the_one_command_relay_and_the_three_buttons(self):
        body = (ROOT / "skills" / "remote" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("scripts/relay.py --port 8787", body)
        for button in ("**Yes**", "**No**", "**Show the diff**"):
            self.assertIn(button, body)
        self.assertIn("do not approve on the phone what you cannot see", body)


if __name__ == "__main__":
    unittest.main()
