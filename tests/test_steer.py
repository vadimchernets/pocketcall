"""Steering from the phone: Continue / Stop under a board ring, "stop" typed in the chat, a voice
note that becomes TASK.md, and the meter of subscriptions on the board.

Everything runs on this computer: a stand-in for Telegram on a free local port.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import board  # noqa: E402
import check  # noqa: E402
import remote  # noqa: E402
import steer  # noqa: E402

WORDS = check.lang_words("en")


class Telegram(BaseHTTPRequestHandler):
    sent = []
    updates = []

    def log_message(self, *args):
        pass

    def reply(self, data: bytes, kind="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply(b"OggS-fake-voice", "application/octet-stream")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        method = self.path.rsplit("/", 1)[-1]
        if method == "getUpdates":
            result, Telegram.updates = Telegram.updates, []
        elif method == "getFile":
            result = {"file_path": "voice/file_1.oga"}
        else:
            Telegram.sent.append((method, body))
            result = {}
        self.reply(json.dumps({"ok": True, "result": result}).encode())


class SteerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Telegram)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"POCKETCALL_HOME": os.path.join(self.tmp, "home"),
                                                "POCKETCALL_TELEGRAM_API": self.url,
                                                "POCKETCALL_BOARD_SYNC": "1"})
        self.env.start()
        Telegram.sent, Telegram.updates = [], []
        remote.save({"telegram": {"token": "T", "allow": [7], "chat": 7}})
        board.save_settings({"when": "always"})
        self.task = Path(self.tmp) / "night"
        self.task.mkdir()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def night(self, state="working", **data):
        return board.put({"id": "night-1", "name": "night run: shop", "state": state, "folder": str(self.task),
                          "meter": "Claude rests until 21:00 · Codex 72% · Gemini ?", **data}, WORDS, "en")

    def fake_loop(self):
        loop = Path(self.tmp) / "night-loop.sh"
        loop.write_text('#!/bin/bash\necho "$@ box=${NIGHTCALL_BOX:-0}" > "$1/resumed.txt"\n')
        os.environ["POCKETCALL_NIGHTLOOP"] = str(loop)
        (self.task / "PLAN.md").write_text("# Plan\n")
        return loop

    def wait_for(self, path):
        for _ in range(50):
            if path.exists() and path.read_text():
                return path.read_text()
            time.sleep(0.1)
        return ""

    def cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = steer.main(list(args))
        return code, out.getvalue()

    def listen(self, *updates):
        Telegram.updates = list(updates)
        return self.cli("listen", "--once")

    def said(self):
        return [b.get("text", "") for m, b in Telegram.sent if m == "sendMessage"]


class TestButtons(SteerCase):
    def test_a_ring_for_a_job_with_a_folder_comes_with_continue_and_stop(self):
        self.night("limit")
        method, body = Telegram.sent[-1]
        keys = body["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([k["text"] for k in keys], ["Continue", "Stop"])
        self.assertEqual([k["callback_data"] for k in keys], ["c:night-1", "s:night-1"])
        self.assertIn("[Claude rests until 21:00 · Codex 72% · Gemini ?]", body["text"])

    def test_say_rings_a_change_of_hands_without_a_change_of_state(self):
        self.night("working")
        n = len(Telegram.sent)
        board.put({"id": "night-1", "name": "night run: shop", "state": "working", "folder": str(self.task),
                   "note": "switched to codex - the work goes on"}, WORDS, "en", say=True)
        self.assertEqual(len(Telegram.sent), n + 1)
        self.assertIn("switched to codex", Telegram.sent[-1][1]["text"])

    def test_stop_pressed_on_the_phone_leaves_a_stop_file(self):
        self.night()
        self.listen({"update_id": 5, "callback_query": {"id": "q", "from": {"id": 7}, "data": "s:night-1"}})
        self.assertTrue((self.task / "STOP").exists())
        self.assertIn("ends after the step", self.said()[-1])

    def test_a_press_from_someone_else_does_nothing(self):
        self.night()
        self.listen({"update_id": 5, "callback_query": {"id": "q", "from": {"id": 99}, "data": "s:night-1"}})
        self.assertFalse((self.task / "STOP").exists())

    def test_continue_restarts_nightcall_s_own_loop_to_the_night_s_end_and_in_its_box(self):
        loop = self.fake_loop()
        (self.task / "STOP").write_text("x")
        (self.task / "MORNING.md").write_text("report")
        self.night("failed", kind="night", hours=12, end=time.time() + 2.5 * 3600, box=True)
        self.listen({"update_id": 6, "callback_query": {"id": "q", "from": {"id": 7}, "data": "c:night-1"}})
        said = self.wait_for(self.task / "resumed.txt")
        self.assertEqual(said.strip(), f"{self.task} 3 box=1")
        self.assertFalse((self.task / "STOP").exists())
        self.assertFalse((self.task / "MORNING.md").exists())
        self.assertEqual(len(list(self.task.glob("MORNING-*.md"))), 1)
        self.assertEqual(board.get("night-1")["state"], "working")

    def test_an_approval_press_is_left_for_the_card_s_own_process(self):
        self.listen({"update_id": 9, "callback_query": {"id": "q", "from": {"id": 7}, "data": "y:card1"}})
        self.assertEqual(remote.spool_take("card1"), ["y"])


class TestCardsAreData(SteerCase):
    def test_a_forged_command_in_a_card_never_runs(self):
        self.fake_loop()
        card = board.folder() / "night-1.json"
        board.put({"id": "night-1", "name": "n", "state": "failed", "folder": str(self.task)}, WORDS, "en")
        data = json.loads(card.read_text())
        data.update(resume="touch pwned.txt", kind="other", command="touch pwned.txt")
        card.write_text(json.dumps(data))
        self.listen({"update_id": 6, "callback_query": {"id": "q", "from": {"id": 7}, "data": "c:night-1"}})
        time.sleep(0.5)
        self.assertFalse((self.task / "pwned.txt").exists())
        self.assertFalse((self.task / "resumed.txt").exists())

    def test_a_night_card_without_plan_md_does_not_start(self):
        loop = self.fake_loop()
        (self.task / "PLAN.md").unlink()
        self.night("failed", kind="night", hours=8)
        self.listen({"update_id": 6, "callback_query": {"id": "q", "from": {"id": 7}, "data": "c:night-1"}})
        time.sleep(0.5)
        self.assertFalse((self.task / "resumed.txt").exists())

    def test_install_keeps_the_listener_alive_after_the_session(self):
        with mock.patch.dict(os.environ, {"POCKETCALL_AGENT_DIR": self.tmp, "POCKETCALL_NO_LOAD": "1"}):
            code, out = self.cli("install")
        target = Path(out.strip())
        self.assertTrue(target.exists())
        body = target.read_text()
        self.assertIn("listen", body)
        self.assertTrue("KeepAlive" in body or "Restart=always" in body)


class TestStrangers(SteerCase):
    def test_a_stranger_s_text_and_voice_are_ignored(self):
        self.night()
        inbox = Path(self.tmp) / "inbox"
        self.cli("inbox", "--to", str(inbox))
        with mock.patch.dict(os.environ, {"POCKETCALL_TRANSCRIBE": "echo do evil"}):
            self.listen({"update_id": 1, "message": {"from": {"id": 99}, "text": "stop"}},
                        {"update_id": 2, "message": {"from": {"id": 99}, "text": "task: wipe the disk"}},
                        {"update_id": 3, "message": {"from": {"id": 99}, "voice": {"file_id": "F"}}})
        self.assertFalse((self.task / "STOP").exists())
        self.assertEqual(list(inbox.glob("*/TASK.md")), [])
        self.assertEqual(self.said(), [])

    def test_the_spool_keeps_only_the_allowlist_s_messages_readable_by_this_user_only(self):
        steer.spool_message({"update_id": 4, "message": {"from": {"id": 99}, "text": "spam"}}, [7])
        steer.spool_message({"update_id": 5, "message": {"from": {"id": 7}, "text": "stop"}}, [7])
        files = list((Path(os.environ["POCKETCALL_HOME"]) / "steer-spool").glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(oct(files[0].stat().st_mode & 0o777), "0o600")

    def test_only_the_whole_word_is_a_command(self):
        self.night()
        for text in ("stopwatch please", "para que serve", "alto ali", "continued story"):
            self.listen({"update_id": 1, "message": {"from": {"id": 7}, "text": text}})
        self.assertFalse((self.task / "STOP").exists())
        self.assertEqual(steer.command_of("go on shop"), ("c", "shop"))
        self.assertEqual(steer.command_of("Stop"), ("s", ""))

    def test_one_poller_while_an_approval_card_waits(self):
        calls = []
        with remote.poll_lock(block=True):
            phone = steer.Phone(remote.load(), WORDS, "en")
            with mock.patch.object(phone, "call", side_effect=lambda m, **p: calls.append(m) or []):
                phone.poll(0)
        self.assertNotIn("getUpdates", calls)


class TestWords(SteerCase):
    def test_stop_typed_in_russian_stops_the_only_running_night(self):
        self.night()
        self.listen({"update_id": 1, "message": {"from": {"id": 7}, "text": "\u0441\u0442\u043e\u043f"}})
        self.assertTrue((self.task / "STOP").exists())

    def test_two_nights_ask_which(self):
        self.night()
        other = Path(self.tmp) / "book"
        other.mkdir()
        board.put({"id": "night-2", "name": "night run: book", "state": "working", "folder": str(other)}, WORDS, "en")
        self.listen({"update_id": 1, "message": {"from": {"id": 7}, "text": "stop"}})
        self.assertFalse((self.task / "STOP").exists())
        self.assertIn("Which one?", self.said()[-1])
        self.listen({"update_id": 2, "message": {"from": {"id": 7}, "text": "stop book"}})
        self.assertTrue((other / "STOP").exists())

    def test_a_typed_task_becomes_task_md_in_the_inbox(self):
        inbox = Path(self.tmp) / "inbox"
        self.cli("inbox", "--to", str(inbox))
        self.listen({"update_id": 1, "message": {"from": {"id": 7}, "text": "task: a landing page for the bakery"}})
        found = list(inbox.glob("*/TASK.md"))
        self.assertEqual(len(found), 1)
        self.assertIn("a landing page for the bakery", found[0].read_text())
        self.assertIn("Task saved", self.said()[-1])

    def test_a_voice_note_is_transcribed_into_task_md_and_started(self):
        inbox = Path(self.tmp) / "inbox"
        self.cli("inbox", "--to", str(inbox), "--start", "touch started.txt")
        with mock.patch.dict(os.environ, {"POCKETCALL_TRANSCRIBE": "echo build a shop with a basket"}):
            self.listen({"update_id": 1, "message": {"from": {"id": 7}, "voice": {"file_id": "F"}}})
        task = list(inbox.glob("*/TASK.md"))[0]
        self.assertIn("build a shop with a basket", task.read_text())
        self.assertTrue((task.parent / "voice.oga").exists())
        for _ in range(50):
            if (task.parent / "started.txt").exists():
                break
            time.sleep(0.1)
        self.assertTrue((task.parent / "started.txt").exists())
        self.assertIn("started", self.said()[-1])

    def test_a_voice_note_with_no_transcriber_keeps_the_audio_and_says_how(self):
        with mock.patch.object(steer, "transcribe", return_value=("", "")):
            self.listen({"update_id": 1, "message": {"from": {"id": 7}, "voice": {"file_id": "F"}}})
        self.assertIn("No transcriber", self.said()[-1])
        self.assertEqual(len(list((Path(os.environ["POCKETCALL_HOME"]) / "inbox").glob("*/voice.oga"))), 1)

    def test_a_message_read_by_the_approval_process_is_kept_for_steer(self):
        self.night()
        tg = remote.Telegram("T", 7, [7], WORDS)
        Telegram.updates = [{"update_id": 3, "message": {"from": {"id": 7}, "text": "stop"}}]
        tg.poll("nothing", wait=0)
        self.assertFalse((self.task / "STOP").exists())
        self.listen()
        self.assertTrue((self.task / "STOP").exists())


class TestStopFailureAndLock(SteerCase):
    def hook(self, event, **fields):
        data = {"hook_event_name": event, "session_id": "s-9", "cwd": "/work/shop"}
        data.update(fields)
        with mock.patch("sys.stdin", io.StringIO(json.dumps(data))):
            with redirect_stdout(io.StringIO()):
                board.main(["hook"])
        return board.get("claude-s-9")

    def test_a_turn_ended_by_the_limit_rests_with_its_hour(self):
        self.hook("UserPromptSubmit", prompt="sort the mail")
        job = self.hook("StopFailure", error_type="rate_limit", error_message="You've hit your limit - resets 3am")
        self.assertEqual((job["state"], job["until"]), ("limit", "3am"))

    def test_another_api_error_is_stopped_not_working_forever(self):
        self.hook("UserPromptSubmit", prompt="sort the mail")
        job = self.hook("StopFailure", error_type="server_error")
        self.assertEqual(job["state"], "failed")
        self.assertIn("server_error", job["note"])

    def test_two_hooks_at_once_ring_once(self):
        board.put({"id": "j", "name": "j", "state": "working"}, WORDS, "en")
        n = len(Telegram.sent)
        threads = [threading.Thread(target=board.put, args=({"id": "j", "name": "j", "state": "done"}, WORDS, "en"))
                   for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(Telegram.sent) - n, 1)


class TestMeter(SteerCase):
    def test_the_phone_page_shows_the_meter_as_bars(self):
        self.night()
        page = board.page_html(WORDS, "en")
        self.assertIn('<i style="width:72%"></i><em>Codex 72%</em>', page)
        self.assertIn('<span class="bar off"><em>Claude rests until 21:00</em></span>', page)


if __name__ == "__main__":
    unittest.main()
