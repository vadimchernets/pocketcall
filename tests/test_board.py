"""The board: sessions report themselves through the hooks, other jobs through `put`, the phone rings
on what changed for the person, and the phone page is written into the shared folder.

Everything runs on this computer: a stand-in for Telegram and for ntfy on a free local port.
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

WORDS = check.lang_words("en")


class Phone(BaseHTTPRequestHandler):
    """Telegram's sendMessage and an ntfy topic in one: every POST is kept."""
    got = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
        Phone.got.append((self.path, body))
        out = json.dumps({"ok": True, "result": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class BoardCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Phone)
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
        Phone.got = []

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = board.main(list(args))
        return code, out.getvalue()

    def hook(self, event, **fields):
        data = {"hook_event_name": event, "session_id": "s-1", "cwd": "/work/shop"}
        data.update(fields)
        with mock.patch("sys.stdin", io.StringIO(json.dumps(data))):
            self.assertEqual(self.run_cli("hook")[0], 0)
        return board.get("claude-s-1")

    def transcript(self, text):
        path = os.path.join(self.tmp, "t.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "go"}}) + "\n")
            fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant",
                                 "content": [{"type": "text", "text": text}]}}) + "\n")
        return path

    def telegram(self):
        remote.save({"telegram": {"token": "T", "allow": [7], "chat": 7}})

    def rings(self):
        return [body for path, body in Phone.got]


class TestSessions(BoardCase):
    def test_a_session_walks_through_working_waiting_done(self):
        job = self.hook("UserPromptSubmit", prompt="add a basket to the shop")
        self.assertEqual((job["state"], job["name"], job["note"]), ("working", "shop", "add a basket to the shop"))
        self.assertEqual(self.hook("Notification", message="Claude is waiting for your input",
                                   notification_type="elicitation_dialog")["state"], "waiting")
        job = self.hook("Stop", transcript_path=self.transcript("The basket is in, 12 tests green."))
        self.assertEqual((job["state"], job["note"]), ("done", "The basket is in, 12 tests green."))

    def test_an_answered_question_is_working_again_and_rings_nothing(self):
        self.telegram()
        self.run_cli("ring", "--when", "always")
        self.hook("UserPromptSubmit", prompt="deploy the preview")
        self.hook("Notification", message="Claude needs your permission to use Bash", notification_type="permission_prompt")
        self.assertEqual(len(Phone.got), 1)
        job = self.hook("PostToolUse", tool_name="Bash")
        self.assertEqual((job["state"], job["note"]), ("working", "deploy the preview"))
        self.assertEqual(len(Phone.got), 1)
        at = job["at"]
        self.assertEqual(self.hook("PostToolUse", tool_name="Read")["at"], at)    # working stays as it is, unwritten

    def test_a_session_another_stop_hook_keeps_going_is_working_again_without_a_false_ring(self):
        self.telegram()
        self.run_cli("ring", "--when", "always")
        self.hook("UserPromptSubmit", prompt="the night")
        self.hook("Stop", transcript_path=self.transcript("Step 1 done."), stop_hook_active=True)
        self.assertEqual(Phone.got, [])
        self.assertEqual(self.hook("PostToolUse", tool_name="Edit")["state"], "working")

    def test_other_notifications_wait_for_nothing(self):
        self.hook("UserPromptSubmit", prompt="x")
        self.assertEqual(self.hook("Notification", message="Signed in", notification_type="auth_success")["state"],
                         "working")

    def test_a_hand_written_job_with_a_bad_time_is_skipped_and_silent_jobs_leave(self):
        base = Path(os.environ["POCKETCALL_HOME"]) / "board"
        base.mkdir(parents=True)
        (base / "bad.json").write_text(json.dumps({"id": "bad", "state": "working", "at": "abc"}))
        board.put({"name": "gone quiet", "state": "waiting"}, WORDS, "en", now=time.time() - 2 * 24 * 3600)
        board.put({"name": "fresh", "state": "working"}, WORDS, "en")
        self.assertEqual([j["name"] for j in board.jobs()], ["fresh"])

    def test_put_ring_rings_at_the_desk_too(self):
        self.telegram()
        self.run_cli("put", "--name", "night run", "--state", "done", "--ring")
        self.assertEqual(len(Phone.got), 1)

    def test_a_usage_limit_is_a_rest_with_the_hour_it_goes_on(self):
        path = os.path.join(self.tmp, "limit.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "assistant", "isApiErrorMessage": True,
                                 "message": {"role": "assistant", "model": "<synthetic>", "content": [
                                     {"type": "text", "text": "You've hit your limit · resets 6pm (Europe/Kyiv)"}]}}) + "\n")
        job = self.hook("Stop", transcript_path=path)
        self.assertEqual(job["state"], "limit")
        self.assertEqual(job["until"], "6pm (Europe/Kyiv)")
        self.assertIn("until 6pm", board.show(WORDS))

    def test_the_idle_reminder_after_done_changes_nothing(self):
        self.hook("Stop", transcript_path=self.transcript("Done."))
        self.assertEqual(self.hook("Notification", message="Claude is waiting for your input",
                                   notification_type="idle_prompt")["state"], "done")

    def test_a_slash_command_keeps_the_words_of_the_job(self):
        self.hook("UserPromptSubmit", prompt="write chapter 4")
        self.assertEqual(self.hook("UserPromptSubmit", prompt="/compact")["note"], "write chapter 4")

    def test_a_closed_session_leaves_the_board(self):
        self.hook("UserPromptSubmit", prompt="x")
        self.assertEqual(self.hook("SessionEnd"), {})
        self.assertEqual(board.jobs(), [])

    def test_a_broken_hook_input_never_stops_the_session(self):
        with mock.patch("sys.stdin", io.StringIO("not json")):
            self.assertEqual(self.run_cli("hook"), (0, ""))
        with mock.patch("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "Stop"}))):
            self.assertEqual(self.run_cli("hook"), (0, ""))


class TestRings(BoardCase):
    def test_the_phone_rings_once_per_change_on_telegram_and_ntfy(self):
        self.telegram()
        self.run_cli("ring", "--ntfy", self.url + "/my-topic", "--when", "always")
        self.hook("UserPromptSubmit", prompt="fix the login")                  # working: no ring
        self.assertEqual(Phone.got, [])
        self.hook("Stop", transcript_path=self.transcript("Fixed."))
        self.hook("Stop", transcript_path=self.transcript("Fixed again."))    # same state: no second ring
        paths = [p for p, _ in Phone.got]
        self.assertEqual(sorted(paths), ["/botT/sendMessage", "/my-topic"])
        tg = json.loads(dict(Phone.got)["/botT/sendMessage"])
        self.assertEqual(tg["chat_id"], 7)
        self.assertTrue(tg["text"].startswith("Done - shop (Claude Code)"), tg["text"])
        self.assertIn("Done - shop", dict(Phone.got)["/my-topic"])

    def test_by_default_it_rings_only_while_the_person_is_away(self):
        self.telegram()
        self.hook("Stop", transcript_path=self.transcript("Done."))
        self.assertEqual(Phone.got, [])
        remote.save({"telegram": {"token": "T", "allow": [7]}, "away": True})
        self.hook("UserPromptSubmit", prompt="next")
        self.hook("Stop", transcript_path=self.transcript("Done."))
        self.assertEqual(len(Phone.got), 1)

    def test_an_approval_card_on_the_phone_is_not_rung_twice(self):
        remote.save({"telegram": {"token": "T", "allow": [7]}, "away": True})
        job = self.hook("Notification", message="Claude needs your permission to use Bash",
                        notification_type="permission_prompt")
        self.assertEqual(job["state"], "waiting")
        self.assertEqual(Phone.got, [])

    def test_never_rings_but_keeps_the_board(self):
        self.telegram()
        self.run_cli("ring", "--when", "never")
        self.hook("Stop", transcript_path=self.transcript("Done."))
        self.assertEqual(Phone.got, [])
        self.assertEqual(board.get("claude-s-1")["state"], "done")

    def test_ring_test_and_a_bad_address(self):
        self.assertEqual(self.run_cli("ring", "--ntfy", "ftp://x")[0], 1)
        code, out = self.run_cli("ring", "--ntfy", self.url + "/t", "--test")
        self.assertEqual(code, 0)
        self.assertIn("Rang: ntfy", out)


class TestPutShowPage(BoardCase):
    def test_other_jobs_report_with_put_and_the_waiting_one_comes_first(self):
        self.run_cli("put", "--name", "night run: book", "--where", "nightcall", "--state", "working",
                     "--note", "chapter 4 of 12")
        self.run_cli("put", "--name", "diffcall review", "--where", "shop", "--state", "done")
        self.run_cli("put", "--name", "site", "--state", "limit", "--until", "03:10")
        self.hook("Notification", message="Claude is waiting for your input", notification_type="elicitation_dialog")
        names = [j["name"] for j in board.jobs()]
        self.assertEqual(names, ["shop", "site", "night run: book", "diffcall review"])
        text = board.show(WORDS)
        self.assertIn("Resting on a limit until 03:10 - site", text)
        self.assertIn("Working - night run: book (nightcall)", text)
        self.assertEqual(json.loads(self.run_cli("show", "--json")[1])[0]["state"], "waiting")

    def test_the_same_name_is_the_same_line(self):
        self.run_cli("put", "--name", "night run", "--state", "working")
        self.run_cli("put", "--name", "night run", "--state", "done")
        self.assertEqual([j["state"] for j in board.jobs()], ["done"])

    def test_finished_jobs_leave_after_three_days_and_on_clear(self):
        board.put({"name": "old", "state": "done"}, WORDS, "en", now=time.time() - 4 * 24 * 3600)
        board.put({"name": "new", "state": "done"}, WORDS, "en")
        board.put({"name": "busy", "state": "working"}, WORDS, "en")
        self.assertEqual(sorted(j["name"] for j in board.jobs()), ["busy", "new"])
        self.run_cli("clear")
        self.assertEqual([j["name"] for j in board.jobs()], ["busy"])
        self.run_cli("clear", "--all")
        self.assertEqual(board.jobs(), [])

    def test_the_phone_page_is_written_into_the_shared_folder_at_every_change(self):
        shared = os.path.join(self.tmp, "Google Drive")
        os.makedirs(shared)
        self.assertEqual(self.run_cli("page", "--to", os.path.join(self.tmp, "nowhere"))[0], 1)
        self.assertEqual(self.run_cli("page", "--to", shared)[0], 0)
        page = Path(shared) / board.PAGE
        self.assertIn("No jobs on the board", page.read_text(encoding="utf-8"))
        self.run_cli("put", "--name", "<script>x</script>", "--state", "waiting", "--note", "a & b")
        text = page.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", text)
        self.assertNotIn("<script>", text)
        self.assertIn("a &amp; b", text)
        self.assertIn("prefers-color-scheme: dark", text)
        self.assertIn('name="viewport"', text)
        self.run_cli("page", "--off")
        self.run_cli("put", "--name", "later", "--state", "done")
        self.assertNotIn("later", page.read_text(encoding="utf-8"))

    def test_the_page_speaks_the_persons_language(self):
        ru = check.lang_words("ru")
        self.assertIn(ru["board_title"], board.page_html(ru, "ru"))
        self.assertIn('lang="ru"', board.page_html(ru, "ru"))


class TestRun(BoardCase):
    def test_a_long_command_is_working_then_done_with_its_last_line(self):
        self.telegram()
        self.run_cli("ring", "--when", "always")
        code, out = self.run_cli("run", "--name", "shop tests", "--where", "shop", "--",
                                 sys.executable, "-c", "print('12 passing'); print(''); print('all green')")
        self.assertEqual(code, 0)
        self.assertIn("12 passing", out)
        job = board.get("run-shop-tests")
        self.assertEqual((job["state"], job["note"], job["where"]), ("done", "all green", "shop"))
        self.assertEqual(len(Phone.got), 1)
        self.assertIn("Done - shop tests (shop)", json.loads(Phone.got[0][1])["text"])

    def test_a_failing_command_is_stopped_with_its_code_and_keeps_the_code(self):
        code, _ = self.run_cli("run", "--name", "deploy", "--", sys.executable, "-c",
                               "import sys; print('step 3 broke'); sys.exit(4)")
        self.assertEqual(code, 4)
        job = board.get("run-deploy")
        self.assertEqual((job["state"], job["note"]), ("failed", "ended with code 4: step 3 broke"))

    def test_a_command_stopped_by_a_usage_limit_rests_with_the_hour(self):
        self.run_cli("run", "--name", "review", "--", sys.executable, "-c",
                     "import sys; print(\"You've hit your limit - resets 3am\"); sys.exit(1)")
        job = board.get("run-review")
        self.assertEqual((job["state"], job["until"]), ("limit", "3am"))

    def test_no_command_and_a_missing_program(self):
        self.assertEqual(self.run_cli("run", "--name", "x")[0], 2)
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(self.run_cli("run", "--name", "x", "--", "/no/such/program")[0], 127)
        self.assertEqual(board.get("run-x")["state"], "failed")


class TestWords(unittest.TestCase):
    def test_every_language_has_every_board_word_and_its_placeholders(self):
        en = {k: v for k, v in check.lang_words("en").items() if k.startswith("board_")}
        self.assertGreater(len(en), 20)
        import re
        for code in check.LANGUAGES:
            data = json.loads((ROOT / "lang" / f"{code}.json").read_text(encoding="utf-8"))
            for key, value in en.items():
                self.assertIn(key, data, f"{code}: {key}")
                self.assertEqual(set(re.findall(r"\{\w+\}", data[key])), set(re.findall(r"\{\w+\}", value)),
                                 f"{code}: {key}")

    def test_limit_words_from_the_two_programs(self):
        own = lambda text: board.limit_of(text, own=True)
        self.assertEqual(own("Claude usage limit reached. Your limit will reset at 5pm."), (True, "5pm"))
        self.assertEqual(own("5-hour limit reached ∙ resets 11:00"), (True, "11:00"))
        self.assertEqual(own("You've hit your weekly limit · resets Oct 9, 6pm"), (True, "Oct 9, 6pm"))
        self.assertEqual(own("Session limit reached, resets Sun 11:00"), (True, "Sun 11:00"))
        self.assertEqual(own("You've hit your usage limit. Try again later."), (True, ""))
        self.assertEqual(own("All 12 tests pass."), (False, ""))
        self.assertEqual(board.limit_of("Done. I raised the API usage limit in config.yaml to 500."), (False, ""))
        work = ("I added the rate-limit middleware: a client that hit your usage limit gets 429 and the header "
                "says when it resets at 5pm. " * 3)
        self.assertEqual(board.limit_of(work), (False, ""))
        self.assertEqual(board.limit_of(work, own=True)[0], True)

    def test_an_answer_about_limits_is_done_not_a_rest(self):
        entries = [{"type": "assistant", "message": {"role": "assistant", "model": "<synthetic>",
                                                     "content": [{"type": "text", "text": "API Error: quota exceeded"}]}}]
        self.assertEqual(board.last_words(entries), ("API Error: quota exceeded", True))


if __name__ == "__main__":
    unittest.main()
