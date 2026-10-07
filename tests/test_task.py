"""Voice -> task -> pull request -> Yes from the phone (scripts/task.py).

Everything runs on this computer: a stand-in GitHub CLI that records every call and answers from a
table, a stand-in Claude Code, a webhook server on a local port, a bare repository as the far side
of git, a stand-in Telegram, and the relay itself on a free local port.
"""

import hashlib
import hmac
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import approval_card  # noqa: E402
import check  # noqa: E402
import relay  # noqa: E402
import remote  # noqa: E402
import seal  # noqa: E402
import task  # noqa: E402

WORDS = check.lang_words("en")
SPOKEN = "On the pricing page the price should be 12, not 10.\nAnd say it in the footer too."

# The stand-in gh: every call goes into gh-calls.jsonl; the answer is looked up in gh-answers.json by
# the first two words and the --json fields of the call, then by the first two words, then by the
# first one. A list of answers is given out in turn. `repo clone` clones FAKE_ORIGIN when it is set.
FAKE_GH = r'''
import json, os, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[1:]
fed = sys.stdin.read()
with open(os.path.join(here, "gh-calls.jsonl"), "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"argv": argv, "stdin": fed}) + "\n")
if argv[:2] == ["repo", "clone"] and os.environ.get("FAKE_ORIGIN"):
    sys.exit(subprocess.run(["git", "clone", "--quiet", os.environ["FAKE_ORIGIN"], argv[3]]).returncode)
with open(os.path.join(here, "gh-answers.json"), encoding="utf-8") as fh:
    answers = json.load(fh)
fields = argv[argv.index("--json") + 1] if "--json" in argv[:-1] else ""
for key in ([" ".join(argv[:2]) + " --json " + fields] if fields else []) + [" ".join(argv[:2]), argv[0] if argv else ""]:
    if key in answers:
        value = answers[key]
        if value and isinstance(value[0], list):
            code, out = value.pop(0) if len(value) > 1 else value[0]
            with open(os.path.join(here, "gh-answers.json"), "w", encoding="utf-8") as fh:
                json.dump(answers, fh)
        else:
            code, out = value
        sys.stdout.write(out)
        sys.exit(code)
'''

# The stand-in claude, as Claude Code behaves: `--cloud` creates a session only in a terminal - piped,
# it turns into --print and stops with that error - prints the session's link and keeps its live
# checklist on until it is let go; FAKE_CLAUDE_MODE silent ends with nothing, hang never shows a link.
# A session here changes price.txt.
FAKE_CLAUDE = r'''
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "claude-calls.jsonl"), "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "tty": sys.stdout.isatty()}) + "\n")
mode = os.environ.get("FAKE_CLAUDE_MODE", "")
if "--cloud" in sys.argv:
    if mode == "silent":
        sys.exit(0)
    if mode == "hang":
        time.sleep(30)
        sys.exit(0)
    if not sys.stdout.isatty():
        sys.stderr.write("Error: Input must be provided either through stdin or as a prompt argument when using --print\n")
        sys.exit(1)
    print("Created cloud session: session_0123", flush=True)
    print("View: https://claude.ai/code/session_0123?from=cli&m=0", flush=True)
    time.sleep(30)
else:
    with open("price.txt", "w", encoding="utf-8") as fh:
        fh.write("price: 12\n")
    print("The price is 12 on the pricing page and in the footer.")
'''

SHA = "a" * 40
PR_URL = "https://github.com/acme/site/pull/7"
PR_LIST = [{"number": 7, "title": "Price 12", "body": "Closes #12\n\nThe price is 12.",
            "url": PR_URL, "headRefName": "pocketcall/12-price", "headRefOid": SHA, "isDraft": False,
            "author": {"login": "ann"}, "isCrossRepository": False}]
PR_VIEW = {"number": 7, "title": "Price 12", "url": PR_URL,
           "headRefName": "pocketcall/12-price", "headRefOid": SHA, "baseRefName": "main", "isDraft": False,
           "state": "OPEN", "files": [{"path": "price.txt", "additions": 1, "deletions": 1}], "changedFiles": 1,
           "author": {"login": "ann"}, "isCrossRepository": False, "headRepositoryOwner": {"login": "acme"}}
PR_DIFF = "diff --git a/price.txt b/price.txt\n--- a/price.txt\n+++ b/price.txt\n@@ -1 +1 @@\n-price: 10\n+price: 12\n"
NOW = "pr view --json " + task.VIEW_FIELDS          # the pull request as GitHub has it when a Yes is carried out
RUNNING = [{"__typename": "CheckRun", "name": "test", "status": "IN_PROGRESS", "conclusion": ""}]
PASSED = [{"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]
FAILING = [{"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "FAILURE"}]
ISSUE_12 = {"number": 12, "title": "Price 12 on the pricing page", "url": "https://github.com/acme/site/issues/12",
            "body": SPOKEN + "\n\n" + task.MARK + "\nFiled by Pocketcall from the phone, 2026-10-03 15:00 UTC."}


def pr_now(**more):
    found = {"state": "OPEN", "url": PR_URL, "headRefOid": SHA, "mergeStateStatus": "BLOCKED", "statusCheckRollup": RUNNING}
    found.update(more)
    return json.dumps(found)


def can_pty():
    try:
        import pty
        master, slave = pty.openpty()
    except (ImportError, OSError):
        return False
    os.close(master)
    os.close(slave)
    return True


class Routine(BaseHTTPRequestHandler):
    """A routine's API trigger: records each fire and answers with the new session, or with an error."""
    seen = []
    status = 200

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Routine.seen.append((self.headers, json.loads(body)))
        if Routine.status == 200:
            data = {"type": "routine_fire", "claude_code_session_id": "session_01R",
                    "claude_code_session_url": "https://claude.ai/code/session_01R"}
        else:
            data = {"type": "error", "error": {"type": "authentication_error",
                                               "message": "the token does not match this routine"}}
        raw = json.dumps(data).encode()
        self.send_response(Routine.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def run_git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class Stand(unittest.TestCase):
    """POCKETCALL_HOME in a temporary folder, the stand-in gh and claude, settings for acme/site."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tools = self.tmp / "tools"
        self.tools.mkdir()
        (self.tools / "gh.py").write_text(FAKE_GH, encoding="utf-8")
        (self.tools / "claude.py").write_text(FAKE_CLAUDE, encoding="utf-8")
        self.answers({})
        self.env = mock.patch.dict(os.environ, {
            "POCKETCALL_HOME": str(self.tmp / "home"),
            "POCKETCALL_GH": '"%s" "%s"' % (sys.executable, self.tools / "gh.py"),
            "POCKETCALL_CLAUDE": '"%s" "%s"' % (sys.executable, self.tools / "claude.py"),
            "HOME": str(self.tmp), "XDG_CONFIG_HOME": str(self.tmp / "xdg"), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Ann", "GIT_AUTHOR_EMAIL": "ann@example.com",
            "GIT_COMMITTER_NAME": "Ann", "GIT_COMMITTER_EMAIL": "ann@example.com",
        })
        self.env.start()
        self.cfg = {"tracker": "github", "repo": "acme/site", "label": "pocketcall", "merge": "squash"}

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def answers(self, table):
        (self.tools / "gh-answers.json").write_text(json.dumps(table), encoding="utf-8")

    def calls(self, *prefix):
        path = self.tools / "gh-calls.jsonl"
        if not path.exists():
            return []
        seen = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [c for c in seen if c["argv"][:len(prefix)] == list(prefix)]

    def claude_calls(self):
        path = self.tools / "claude-calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def task_12(self, **more):
        found = {"key": "12", "ref": "#12", "url": "https://github.com/acme/site/issues/12",
                 "title": "Price 12 on the pricing page", "words": SPOKEN, "source": "voice", "state": "filed"}
        found.update(more)
        task.save_task(found)
        return found

    def origin(self):
        """acme/site on the far side of git: a bare repository whose main holds price: 10. The stand-in
        gh clones it for `gh repo clone acme/site`."""
        origin, seed = self.tmp / "github" / "acme" / "site.git", self.tmp / "seed"
        origin.parent.mkdir(parents=True)
        run_git(self.tmp, "init", "--quiet", "--bare", str(origin))
        seed.mkdir()
        run_git(seed, "init", "--quiet")
        run_git(seed, "symbolic-ref", "HEAD", "refs/heads/main")
        (seed / "price.txt").write_text("price: 10\n", encoding="utf-8")
        run_git(seed, "add", "-A")
        run_git(seed, "commit", "--quiet", "-m", "first")
        run_git(seed, "remote", "add", "origin", str(origin))
        run_git(seed, "push", "--quiet", "-u", "origin", "main")
        os.environ["FAKE_ORIGIN"] = str(origin)
        return origin

    def routine(self, status=200):
        """A routine with an API trigger on a local port; its settings, as `task.py setup --routine` keeps them."""
        Routine.seen, Routine.status = [], status
        server = ThreadingHTTPServer(("127.0.0.1", 0), Routine)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = "http://127.0.0.1:%d/v1/claude_code/routines/trig_01ABC/fire" % server.server_address[1]
        return dict(self.cfg, routine={"url": url, "token": "sk-ant-oat01-test"})


class Hook(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Hook.seen.append((self.headers, body))
        data = json.dumps({"key": "OPS-7", "self": "https://tracker.example.com/OPS-7"}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class TestFile(Stand):
    def test_the_words_go_to_github_unchanged_and_the_task_is_recorded(self):
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/12\n"]})
        filed = task.file_task(self.cfg, WORDS, SPOKEN, "voice")
        call = self.calls("issue", "create")[0]
        argv = call["argv"]
        self.assertEqual(argv[argv.index("--repo") + 1], "acme/site")
        self.assertEqual(argv[argv.index("--label") + 1], "pocketcall")
        self.assertEqual(argv[argv.index("--title") + 1], "On the pricing page the price should be 12, not 10.")
        self.assertTrue(call["stdin"].startswith(SPOKEN + "\n\n"), call["stdin"])     # the words, unchanged
        self.assertIn(task.MARK, call["stdin"])
        self.assertIn("Filed by Pocketcall from a voice note in the session", call["stdin"])
        self.assertEqual((filed["key"], filed["ref"], filed["url"]),
                         ("12", "#12", "https://github.com/acme/site/issues/12"))
        self.assertEqual(task.read_record()["tasks"]["12"]["words"], SPOKEN)

    def test_a_label_the_repository_lacks_is_made_once_and_the_task_filed_again(self):
        self.answers({"issue create": [[1, "could not add label: 'pocketcall' not found"],
                                       [0, "https://github.com/acme/site/issues/13\n"]]})
        filed = task.file_task(self.cfg, WORDS, "Fix the footer", "voice")
        self.assertEqual(filed["key"], "13")
        self.assertEqual(len(self.calls("label", "create")), 1)
        self.assertEqual(len(self.calls("issue", "create")), 2)

    def test_another_tracker_gets_a_signed_json_post_with_the_words_unchanged(self):
        Hook.seen = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), Hook)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        cfg = {"tracker": "webhook", "repo": "acme/site", "label": "pocketcall", "who": "Ann",
               "webhook": {"url": "http://127.0.0.1:%d/in" % server.server_address[1], "secret": "s3cret",
                           "headers": {"X-Token": "t1"}}}
        try:
            filed = task.file_task(cfg, WORDS, SPOKEN, "phone")
        finally:
            server.shutdown()
            server.server_close()
        headers, body = Hook.seen[0]
        payload = json.loads(body)
        self.assertEqual((payload["event"], payload["words"], payload["who"]), ("filed", SPOKEN, "Ann"))
        self.assertIn("Filed by Pocketcall for Ann from the phone", payload["body"])
        self.assertEqual(headers["X-Token"], "t1")
        self.assertEqual(headers[task.SIGNATURE], "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest())
        self.assertEqual((filed["key"], filed["url"]), ("OPS-7", "https://tracker.example.com/OPS-7"))

    def test_a_queued_note_is_filed_from_its_file(self):
        note = self.tmp / "for-tonight-2026-10-03.md"
        note.write_text(SPOKEN + "\n", encoding="utf-8")
        task.save_settings(self.cfg)
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/14\n"]})
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(task.main(["--lang", "en", "file", "--from", str(note)]), 0)
        self.assertIn("Filed as #14", out.getvalue())
        stdin = self.calls("issue", "create")[0]["stdin"]
        self.assertTrue(stdin.startswith(SPOKEN))
        self.assertIn("the note for-tonight-2026-10-03.md", stdin)


class TestPlainLines(Stand):
    """Nothing throws: a missing tracker or a missing GitHub CLI is one plain line and exit code 1."""

    def test_without_a_tracker_file_says_how_to_set_one(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(task.main(["--lang", "en", "file", "Fix the footer"]), 1)
        self.assertIn("task.py setup --github", out.getvalue())

    def test_without_the_github_cli_it_says_where_to_get_it(self):
        task.save_settings(self.cfg)
        os.environ["POCKETCALL_GH"] = str(self.tmp / "no-such-gh")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(task.main(["--lang", "en", "file", "Fix the footer"]), 1)
        self.assertIn("cli.github.com", out.getvalue())

    def test_setup_keeps_the_tracker_and_makes_the_label(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(task.main(["--lang", "en", "setup", "--github", "acme/site", "--who", "Ann"]), 0)
        cfg = task.load_settings()
        self.assertEqual((cfg["tracker"], cfg["repo"], cfg["label"], cfg["merge"], cfg["who"]),
                         ("github", "acme/site", "pocketcall", "squash", "Ann"))
        self.assertEqual(len(self.calls("label", "create")), 1)
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(task.main(["--lang", "en", "setup", "--github", "not a repo"]), 1)
        self.assertIn("owner/name", out.getvalue())


class TestStart(Stand):
    def test_a_cloud_session_gets_the_words_unchanged_and_the_rules_of_the_pull_request(self):
        started = task.start_cloud(self.routine(), WORDS, self.task_12())
        headers, body = Routine.seen[0]
        self.assertEqual(headers["Authorization"], "Bearer sk-ant-oat01-test")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(headers["anthropic-beta"], task.ROUTINE_BETA)
        self.assertIn(SPOKEN, body["text"])
        self.assertIn('"Closes #12"', body["text"])
        self.assertIn("pocketcall/12-price-12-on-the-pricing-page", body["text"])
        self.assertEqual((started["state"], started["how"]), ("started", "cloud"))
        self.assertEqual(started["session"], "https://claude.ai/code/session_01R")
        comment = self.calls("issue", "comment")[0]
        self.assertEqual(comment["argv"][2], "12")
        self.assertIn("https://claude.ai/code/session_01R", comment["stdin"])
        self.assertEqual(self.claude_calls(), [])            # no Claude Code needed on the desk for a routine

    def test_a_routine_that_refuses_starts_nothing_and_says_why(self):
        with self.assertRaises(task.TaskError) as said:
            task.start_cloud(self.routine(status=401), WORDS, self.task_12())
        self.assertIn("The session did not start: HTTP 401 the token does not match this routine", str(said.exception))
        self.assertEqual(task.read_record()["tasks"]["12"]["state"], "filed")

    @unittest.skipUnless(shutil.which("git"), "git")
    def test_without_a_terminal_claude_cloud_starts_nothing_and_the_task_stays_filed(self):
        self.origin()
        with mock.patch("pty.openpty", side_effect=OSError("out of pty devices")):
            with self.assertRaises(task.TaskError) as said:
                task.start_cloud(self.cfg, WORDS, self.task_12())
        self.assertIn("The session did not start: Error: Input must be provided", str(said.exception))
        self.assertFalse(self.claude_calls()[0]["tty"])
        self.assertEqual(task.read_record()["tasks"]["12"]["state"], "filed")
        self.assertEqual(self.calls("issue", "comment"), [])

    @unittest.skipUnless(shutil.which("git"), "git")
    def test_claude_cloud_that_ends_or_hangs_without_a_session_link_starts_nothing(self):
        self.origin()
        for mode in ("silent", "hang"):
            with mock.patch.dict(os.environ, {"FAKE_CLAUDE_MODE": mode}), mock.patch.object(task, "CLOUD_WAIT", 2):
                with self.assertRaises(task.TaskError) as said:
                    task.start_cloud(self.cfg, WORDS, self.task_12())
            self.assertIn("The session did not start", str(said.exception))
            self.assertEqual(task.read_record()["tasks"]["12"]["state"], "filed", mode)
        self.assertIn("no link to a session came within 2 seconds", str(said.exception))

    @unittest.skipUnless(shutil.which("git") and can_pty(), "git and a pseudo-terminal")
    def test_in_a_terminal_of_its_own_claude_cloud_gives_the_link_from_the_default_branch(self):
        self.origin()
        work = self.tmp / "checkout"
        run_git(self.tmp, "clone", "--quiet", os.environ["FAKE_ORIGIN"], str(work))
        run_git(work, "checkout", "--quiet", "-b", "half-done-feature")     # the person's own checkout, elsewhere
        with mock.patch.object(task, "SESSION_GRACE", 0.2):
            started = task.start_cloud(dict(self.cfg, folder=str(work)), WORDS, self.task_12())
        call = self.claude_calls()[0]
        self.assertTrue(call["tty"])
        self.assertEqual(Path(call["cwd"]).resolve(), task.copy_path(self.cfg).resolve())
        self.assertEqual(subprocess.run(["git", "-C", call["cwd"], "rev-parse", "--abbrev-ref", "HEAD"],
                                        capture_output=True, text=True).stdout.strip(), "main")
        self.assertEqual((started["state"], started["session"]), ("started", "https://claude.ai/code/session_0123"))

    @unittest.skipUnless(shutil.which("git"), "git")
    def test_a_desk_set_up_outside_a_checkout_keeps_its_own_copy_and_reaches_the_pull_request(self):
        origin = self.origin()
        elsewhere = self.tmp / "pocketcall"           # a copy of Pocketcall, not of acme/site
        elsewhere.mkdir()
        with mock.patch("os.getcwd", return_value=str(elsewhere)), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(task.main(["--lang", "en", "setup", "--github", "acme/site"]), 0)
        cfg = task.load_settings()
        self.assertEqual(Path(cfg["folder"]), task.copy_path(cfg))
        self.answers({"pr create": [0, "https://github.com/acme/site/pull/7\n"]})
        done = task.start_home(cfg, WORDS, self.task_12())
        self.assertEqual((done["state"], done.get("pr")), ("pr", 7), done.get("last"))
        self.assertEqual(self.calls("repo", "clone")[0]["argv"], ["repo", "clone", "acme/site", cfg["folder"]])
        pushed = subprocess.run(["git", "--git-dir", str(origin), "show",
                                 "pocketcall/12-price-12-on-the-pricing-page:price.txt"], capture_output=True, text=True)
        self.assertEqual(pushed.stdout, "price: 12\n")

    @unittest.skipUnless(shutil.which("git"), "git")
    def test_a_home_session_works_in_its_own_worktree_and_pocketcall_opens_the_pull_request(self):
        branch = "pocketcall/12-price-12-on-the-pricing-page"
        origin, work = self.tmp / "acme" / "site.git", self.tmp / "work"
        origin.parent.mkdir()
        run_git(self.tmp, "init", "--quiet", "--bare", str(origin))
        work.mkdir()
        run_git(work, "init", "--quiet")
        run_git(work, "symbolic-ref", "HEAD", "refs/heads/main")
        (work / "price.txt").write_text("price: 10\n", encoding="utf-8")
        run_git(work, "add", "-A")
        run_git(work, "commit", "--quiet", "-m", "first")
        run_git(work, "remote", "add", "origin", str(origin))
        run_git(work, "push", "--quiet", "-u", "origin", "main")
        self.answers({"pr create": [0, "https://github.com/acme/site/pull/7\n"]})
        done = task.start_home(dict(self.cfg, folder=str(work)), WORDS, self.task_12())
        pushed = subprocess.run(["git", "--git-dir", str(origin), "show", branch + ":price.txt"],
                                capture_output=True, text=True)
        self.assertEqual((done["state"], done.get("pr")), ("pr", 7), done.get("last"))
        self.assertEqual(pushed.stdout, "price: 12\n")
        self.assertEqual((work / "price.txt").read_text(encoding="utf-8"), "price: 10\n")   # the checkout untouched
        create = self.calls("pr", "create")[0]
        argv = create["argv"]
        self.assertEqual(argv[argv.index("--head") + 1], branch)
        self.assertEqual(argv[argv.index("--base") + 1], "main")
        self.assertTrue(create["stdin"].startswith("Closes #12\n"), create["stdin"])
        self.assertIn("The price is 12", create["stdin"])
        self.assertIn("> On the pricing page the price should be 12, not 10.", create["stdin"])
        session = self.claude_calls()[0]
        self.assertEqual(session["argv"][0], "-p")
        self.assertIn("acceptEdits", session["argv"])
        self.assertNotEqual(Path(session["cwd"]).resolve(), work.resolve())


class Phone(Stand):
    """The relay on a free local port, this computer paired with it, and task 12 handed to the cloud."""

    def setUp(self):
        super().setUp()
        self.server = relay.serve("127.0.0.1", 0, "")
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.rcfg = {"relay": self.url, "secret": seal.new_secret()}
        self.pair = seal.Pair(self.rcfg["secret"])
        self.room = "%s/r/%s" % (self.url, self.pair.room)
        self.task_12(state="started", how="cloud")
        self.answers({"pr list": [0, json.dumps(PR_LIST)], "pr view": [0, json.dumps(PR_VIEW)],
                      "pr diff": [0, PR_DIFF]})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def desk(self, cfg=None, start=None):
        return task.Desk(cfg or self.cfg, self.rcfg, WORDS, start)

    def asks(self):
        return get(self.room + "/asks")[1]["asks"]

    def card(self, n=0):
        """The n-th waiting card, as the phone page reads it: the id from the list, the box by itself."""
        status, data = get("%s/ask?id=%s" % (self.room, self.asks()[n]["id"]))
        self.assertEqual(status, 200)
        return self.pair.open(data["box"])

    def say(self, answer):
        card = self.card()
        sealed = self.pair.seal({"id": card["id"], "say": answer})
        self.assertEqual(post(self.room + "/answer", {"id": card["id"], "box": sealed}), 204)
        return card

    def receipt(self, rid):
        status, data = get("%s/receipt?id=%s" % (self.room, rid))
        return self.pair.open(data["box"]) if status == 200 else None

    def at(self, name):
        """Another computer on the same phone: its own POCKETCALL_HOME, the same pairing."""
        return mock.patch.dict(os.environ, {"POCKETCALL_HOME": str(self.tmp / name)})


class TestCard(Phone):
    def test_the_card_for_a_task_s_pull_request_has_every_file_the_diff_and_the_exact_merge(self):
        self.desk().cycle()
        self.assertEqual(list(self.asks()[0]), ["id"])          # the list the phone polls carries ids only
        self.assertNotIn("price: 12", json.dumps(get("%s/ask?id=%s" % (self.room, self.asks()[0]["id"]))[1]))
        card = self.card()
        self.assertEqual(card["files"], ["price.txt"])
        self.assertIn("+price: 12", card["diff"])
        self.assertEqual(card["task"], SPOKEN)
        self.assertEqual(card["url"], PR_URL)
        self.assertTrue(card["command"].endswith(" && gh pr merge 7 --repo acme/site --squash --match-head-commit " + SHA))
        self.assertNotIn("--auto", card["command"])
        self.assertTrue(card["complete"])
        self.assertEqual(task.read_record()["tasks"]["12"]["pr"], 7)
        text = approval_card.text_of(card, WORDS)
        self.assertIn("A pull request by ann waits for your Yes: Price 12", text)
        self.assertIn(SPOKEN, text)

    def test_yes_runs_word_for_word_what_the_card_showed_and_closes_the_task(self):
        self.desk().cycle()
        card = self.say("yes")
        self.desk().cycle()                       # a fresh desk, as after a restart, finds the answer
        merges = self.calls("pr", "merge")
        self.assertEqual([m["argv"] for m in merges],
                         [["pr", "merge", "7", "--repo", "acme/site", "--squash", "--match-head-commit", SHA]])
        review = self.calls("pr", "review")[0]["argv"]     # the Yes, kept in GitHub's own record
        self.assertIn("--approve", review)
        self.assertIn(SHA, review[-1])
        ran = [c["argv"] for c in self.calls("pr") if c["argv"][1] in ("ready", "review", "merge")]
        self.assertEqual([shlex.split(step) for step in card["command"].split(" && ")], [["gh"] + argv for argv in ran])
        rec = task.read_record()
        self.assertEqual(rec["tasks"]["12"]["state"], "merged")
        self.assertEqual(len(self.calls("issue", "close")), 1)
        self.assertIn("Merged from the phone", self.receipt(card["id"])["text"])
        self.assertTrue(all(t["state"] in task.TASK_STATES and t["source"] in task.SOURCES
                            for t in rec["tasks"].values()))
        self.assertTrue(all(c["state"] in task.CARD_STATES for c in rec["cards"].values()))

    def held_yes(self):
        """A card on the phone, a Yes while the required checks still run: GitHub refuses the merge."""
        self.desk().cycle()
        self.answers({"pr list": [0, json.dumps(PR_LIST)], "pr view": [0, json.dumps(PR_VIEW)], "pr diff": [0, PR_DIFF],
                      "pr merge": [1, "the base branch policy prohibits the merge"], NOW: [0, pr_now()]})
        card = self.say("yes")
        self.desk().cycle()
        return card

    def test_yes_while_the_checks_run_is_kept_and_merges_that_commit_once_they_pass(self):
        card = self.held_yes()
        self.assertEqual(task.read_record()["cards"][card["id"]]["state"], "approved")
        kept = self.receipt(card["id"])
        self.assertIn("kept for commit aaaaaaa", kept["text"])
        self.assertTrue(kept["more"])
        self.desk().cycle()                                   # still running: nothing happens
        self.assertEqual(len(self.calls("pr", "merge")), 1)
        self.answers({"pr list": [0, json.dumps(PR_LIST)], "pr merge": [0, ""],
                      NOW: [0, pr_now(mergeStateStatus="CLEAN", statusCheckRollup=PASSED)]})
        self.desk().cycle()
        merges = [m["argv"] for m in self.calls("pr", "merge")]
        self.assertEqual(merges, [["pr", "merge", "7", "--repo", "acme/site", "--squash", "--match-head-commit", SHA]] * 2)
        self.assertFalse(any("--auto" in c["argv"] for c in self.calls("pr")))     # GitHub never merges by itself
        self.assertEqual(task.read_record()["tasks"]["12"]["state"], "merged")
        self.assertEqual(len(self.calls("issue", "close")), 1)
        self.assertIn("Merged from the phone", self.receipt(card["id"] + "-1")["text"])   # the page kept listening

    def test_a_commit_pushed_after_the_yes_is_never_merged_by_it_and_brings_its_own_card(self):
        card = self.held_yes()
        moved = "b" * 40
        self.answers({"pr list": [0, json.dumps([dict(PR_LIST[0], headRefOid=moved)])],
                      "pr view": [0, json.dumps(dict(PR_VIEW, headRefOid=moved))], "pr diff": [0, PR_DIFF],
                      "pr merge": [0, ""], NOW: [0, pr_now(headRefOid=moved, mergeStateStatus="CLEAN", statusCheckRollup=PASSED)]})
        self.desk().cycle()
        self.assertEqual(len(self.calls("pr", "merge")), 1)            # only the refused one, for the shown commit
        self.assertEqual(task.read_record()["cards"][card["id"]]["state"], "replaced")
        self.assertIn("A newer commit is on", self.receipt(card["id"] + "-1")["text"])
        self.assertEqual(len(self.asks()), 1)
        self.assertIn(moved, self.card()["command"])

    def test_failed_checks_end_the_wait_and_the_phone_hears_it(self):
        card = self.held_yes()
        self.answers({"pr list": [0, json.dumps(PR_LIST)], "pr merge": [0, ""],
                      NOW: [0, pr_now(statusCheckRollup=FAILING)]})
        self.desk().cycle()
        self.assertEqual(len(self.calls("pr", "merge")), 1)
        self.assertEqual(task.read_record()["cards"][card["id"]]["state"], "refused")
        self.assertIn("did not pass", self.receipt(card["id"] + "-1")["text"])

    def test_a_pull_request_from_a_fork_comes_only_by_hand_and_says_so(self):
        fork = dict(PR_LIST[0], number=9, headRefName="pocketcall/12-price", isCrossRepository=True,
                    author={"login": "mallory"})      # a fork may name its branch like the task's own
        self.answers({"pr list": [0, json.dumps([fork])], "pr diff": [0, PR_DIFF],
                      "pr view": [0, json.dumps(dict(PR_VIEW, number=9, isCrossRepository=True, author={"login": "mallory"}))]})
        self.desk().cycle()
        self.assertEqual(self.asks(), [])
        self.assertNotEqual(task.read_record()["tasks"]["12"].get("pr"), 9)
        heading = task.pr_card(self.cfg, WORDS, 9)["heading"]
        self.assertEqual(heading, "A pull request from a fork, by mallory, waits for your Yes: Price 12")

    def test_somebody_else_s_pull_request_is_linked_only_on_the_task_s_own_branch(self):
        other = dict(PR_LIST[0], headRefName="bob-price", author={"login": "bob"})
        self.answers({"api user": [0, "ann\n"], "pr list": [0, json.dumps([other])], "pr diff": [0, PR_DIFF],
                      "pr view": [0, json.dumps(dict(PR_VIEW, author={"login": "bob"}))]})
        self.desk().cycle()
        self.assertEqual(self.asks(), [])
        self.answers({"api user": [0, "ann\n"], "pr list": [0, json.dumps([dict(other, headRefName="pocketcall/12-price")])],
                      "pr diff": [0, PR_DIFF], "pr view": [0, json.dumps(dict(PR_VIEW, author={"login": "bob"}))]})
        self.desk().cycle()
        self.assertEqual(self.card()["heading"], "A pull request by bob waits for your Yes: Price 12")

    def test_a_pull_request_merged_on_github_later_closes_its_task(self):
        self.task_12(state="pr", pr=7, pr_url="https://github.com/acme/site/pull/7")
        self.answers({"pr list": [0, "[]"],
                      "pr view": [0, json.dumps({"state": "MERGED", "url": "https://github.com/acme/site/pull/7"})]})
        self.desk().cycle()
        self.assertEqual(task.read_record()["tasks"]["12"]["state"], "merged")
        close = self.calls("issue", "close")[0]["argv"]
        self.assertIn("Merged on GitHub", close[-1])

    def test_no_leaves_a_comment_and_a_new_commit_brings_a_new_card(self):
        desk = self.desk()
        desk.cycle()
        desk.cycle()
        self.assertEqual(len(self.asks()), 1)    # one card per commit, not one per pass
        self.say("no")
        desk.cycle()
        self.assertEqual(self.calls("pr", "merge"), [])
        comment = self.calls("pr", "comment")[0]
        self.assertEqual(comment["argv"][2], "7")
        self.assertIn("Declined from the phone", comment["stdin"])
        self.assertEqual(self.asks(), [])
        moved = "b" * 40
        self.answers({"pr list": [0, json.dumps([dict(PR_LIST[0], headRefOid=moved)])],
                      "pr view": [0, json.dumps(dict(PR_VIEW, headRefOid=moved))], "pr diff": [0, PR_DIFF]})
        desk.cycle()
        self.assertEqual(len(self.asks()), 1)
        self.assertIn(moved, self.card()["command"])

    def test_a_yes_to_a_card_cut_to_fit_merges_nothing(self):
        cut = {"id": "c1", "pr": 7, "sha": SHA, "url": "https://github.com/acme/site/pull/7",
               "complete": False, "draft": False}
        state, _ = task.act(self.cfg, WORDS, cut, "yes")
        self.assertEqual(state, "declined")
        self.assertEqual(self.calls("pr", "merge"), [])

    def test_a_diff_too_long_or_files_left_out_make_the_card_incomplete(self):
        self.answers({"pr view": [0, json.dumps(PR_VIEW)], "pr diff": [0, "+" + "x" * (approval_card.MAX_DIFF + 1)]})
        self.assertFalse(task.pr_card(self.cfg, WORDS, 7)["complete"])
        self.answers({"pr view": [0, json.dumps(dict(PR_VIEW, changedFiles=120))], "pr diff": [0, PR_DIFF]})
        self.assertFalse(task.pr_card(self.cfg, WORDS, 7)["complete"])

    def test_a_branch_the_cloud_session_pushed_without_a_pull_request_gets_one(self):
        self.answers({"pr list": [0, "[]"], "api": [0, "main\nclaude/pocketcall-12-price\n"],
                      "pr create": [0, "https://github.com/acme/site/pull/8\n"]})
        with mock.patch.object(task, "BRANCH_GRACE", 0):
            self.desk().cycle()
        create = self.calls("pr", "create")[0]
        self.assertEqual(create["argv"][create["argv"].index("--head") + 1], "claude/pocketcall-12-price")
        self.assertTrue(create["stdin"].startswith("Closes #12"))
        self.assertEqual(task.read_record()["tasks"]["12"]["pr"], 8)

    def test_a_card_the_relay_lost_is_sent_again(self):
        self.desk().cycle()
        self.server.shutdown()
        self.server.server_close()
        self.server = relay.serve("127.0.0.1", 0, "")        # the relay restarted: all it held is gone
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.rcfg["relay"] = self.url
        self.room = "%s/r/%s" % (self.url, self.pair.room)
        self.desk().cycle()                       # finds its card gone
        self.desk().cycle()                       # and sends this commit's card again
        self.assertEqual(len(self.asks()), 1)

    def test_task_py_card_sends_the_card_and_carries_out_the_phone_s_answer(self):
        remote.save(self.rcfg)
        task.save_settings(self.cfg)

        def phone():
            for _ in range(200):
                waiting = get(self.room + "/asks")[1]["asks"]
                if waiting:
                    card = self.card()
                    post(self.room + "/answer", {"id": waiting[0]["id"],
                                                 "box": self.pair.seal({"id": card["id"], "say": "yes"})})
                    return
                threading.Event().wait(0.05)

        threading.Thread(target=phone, daemon=True).start()
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            code = task.main(["--lang", "en", "card", "7", "--wait", "20"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(len(self.calls("pr", "merge")), 1)
        self.assertIn("Merged from the phone", out.getvalue())

    def test_task_py_card_keeps_a_yes_while_the_checks_run_and_then_merges_that_commit(self):
        remote.save(self.rcfg)
        task.save_settings(self.cfg)
        self.answers({"pr view": [0, json.dumps(PR_VIEW)], "pr diff": [0, PR_DIFF],
                      "pr merge": [[1, "the base branch policy prohibits the merge"], [0, ""]],
                      NOW: [[0, pr_now()], [0, pr_now()], [0, pr_now(mergeStateStatus="CLEAN", statusCheckRollup=PASSED)]]})

        def phone():
            for _ in range(200):
                if get(self.room + "/asks")[1]["asks"]:
                    self.say("yes")
                    return
                threading.Event().wait(0.05)

        threading.Thread(target=phone, daemon=True).start()
        with mock.patch.object(task, "HELD_EVERY", 0), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            code = task.main(["--lang", "en", "card", "7", "--wait", "20"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("kept for commit aaaaaaa", out.getvalue())
        self.assertIn("Merged from the phone", out.getvalue())
        self.assertEqual([m["argv"][-1] for m in self.calls("pr", "merge")], [SHA, SHA])


class TestNotes(Phone):
    def test_a_note_from_the_phone_page_becomes_a_task_and_its_link_comes_back_sealed(self):
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/13\n"]})
        box = self.pair.seal({"id": "n1", "kind": "note", "words": SPOKEN, "at": "2026-10-03T15:00:00Z"})
        self.assertEqual(post(self.room + "/note", {"id": "n1", "box": box}), 204)
        self.assertNotIn("pricing", json.dumps(get(self.room + "/notes")[1]))   # the relay holds ciphertext
        self.desk().cycle()
        stdin = self.calls("issue", "create")[0]["stdin"]
        self.assertTrue(stdin.startswith(SPOKEN))
        self.assertIn("from the phone", stdin)
        self.assertEqual(get(self.room + "/notes")[1]["notes"], [])
        status, data = get(self.room + "/receipt?id=n1")
        self.assertEqual(status, 200)
        got = self.pair.open(data["box"])
        self.assertIn("#13", got["text"])
        self.assertEqual(got["url"], "https://github.com/acme/site/issues/13")
        self.assertEqual(task.read_record()["notes"]["n1"], "13")

    def test_a_note_the_phone_sends_again_is_filed_once(self):
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/13\n"]})
        box = self.pair.seal({"id": "n4", "kind": "note", "words": SPOKEN})
        for _ in range(2):                        # the page sends it again until the receipt comes
            post(self.room + "/note", {"id": "n4", "box": box})
            self.desk().cycle()
        self.assertEqual(len(self.calls("issue", "create")), 1)
        self.assertIn("#13", self.pair.open(get(self.room + "/receipt?id=n4")[1]["box"])["text"])

    def test_a_note_sealed_with_another_key_is_not_filed(self):
        other = seal.Pair(seal.new_secret())
        post(self.room + "/note", {"id": "n2", "box": other.seal({"id": "n2", "kind": "note", "words": "rm -rf"})})
        self.desk().cycle()
        self.assertEqual(self.calls("issue", "create"), [])
        self.assertEqual(get(self.room + "/notes")[1]["notes"], [])

    def test_the_desk_hands_each_new_task_to_a_cloud_session(self):
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/13\n"]})
        post(self.room + "/note", {"id": "n3", "box": self.pair.seal({"id": "n3", "kind": "note", "words": "Fix the footer"})})
        self.desk(self.routine(), start="cloud").cycle()
        self.assertEqual(task.read_record()["tasks"]["13"]["state"], "started")
        self.assertIn("Fix the footer", Routine.seen[0][1]["text"])

    def test_each_step_of_a_task_comes_back_to_the_phone_under_its_note(self):
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/13\n"]})
        post(self.room + "/note", {"id": "n5", "box": self.pair.seal({"id": "n5", "kind": "note", "words": "Fix the footer"})})
        cfg = self.routine()
        self.desk(cfg, start="cloud").cycle()
        filed = self.receipt("n5")
        self.assertIn("Filed as #13", filed["text"])
        self.assertTrue(filed["more"])                          # the page keeps listening under n5-1, n5-2...
        self.assertIn("A cloud session took this task", self.receipt("n5-1")["text"])
        self.answers({"pr list": [0, json.dumps([dict(PR_LIST[0], body="Closes #13", headRefName="claude/pocketcall-13-footer")])],
                      "pr view": [0, json.dumps(PR_VIEW)], "pr diff": [0, PR_DIFF]})
        self.desk(cfg, start="cloud").cycle()
        self.assertIn("Pull request for this task: " + PR_URL, self.receipt("n5-2")["text"])
        self.assertEqual(len(self.asks()), 1)

    def test_a_session_that_did_not_start_is_told_to_the_phone_and_tried_again(self):
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/13\n"]})
        post(self.room + "/note", {"id": "n6", "box": self.pair.seal({"id": "n6", "kind": "note", "words": "Fix the footer"})})
        cfg = self.routine(status=401)
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.desk(cfg, start="cloud").cycle()
        said = self.receipt("n6-1")
        self.assertIn("The session did not start: HTTP 401", said["text"])
        self.assertIn("tries again in 10 min", said["text"])
        self.assertTrue(said["more"])
        filed = task.read_record()["tasks"]["13"]
        self.assertEqual((filed["state"], filed["tries"]), ("filed", 1))
        Routine.status = 200
        self.desk(cfg, start="cloud").cycle()
        self.assertEqual(task.read_record()["tasks"]["13"]["state"], "filed")      # waits its ten minutes
        later = task.time.time() + task.START_AGAIN + 1
        with mock.patch.object(task.time, "time", return_value=later):
            self.desk(cfg, start="cloud").cycle()
        self.assertEqual(task.read_record()["tasks"]["13"]["state"], "started")
        self.assertIn("A cloud session took this task", self.receipt("n6-2")["text"])


    @unittest.skipUnless(shutil.which("git"), "git")
    def test_claude_cloud_that_stops_without_a_terminal_is_told_to_the_phone_under_the_note(self):
        self.origin()
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/13\n"]})
        post(self.room + "/note", {"id": "n8", "box": self.pair.seal({"id": "n8", "kind": "note", "words": "Fix the footer"})})
        with mock.patch("pty.openpty", side_effect=OSError("out of pty devices")), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.desk(start="cloud").cycle()
        self.assertIn("Filed as #13", self.receipt("n8")["text"])
        said = self.receipt("n8-1")["text"]
        self.assertIn("The session did not start: Error: Input must be provided", said)
        self.assertEqual(task.read_record()["tasks"]["13"]["state"], "filed")

class TestTwoComputers(Phone):
    """The laptop and a machine that stays on, joined to one phone: one relay room, two records."""

    def test_a_task_filed_on_the_laptop_gets_its_card_from_the_desk_on_the_server(self):
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/12\n"], "pr list": [0, json.dumps(PR_LIST)],
                      "pr view": [0, json.dumps(PR_VIEW)], "pr diff": [0, PR_DIFF]})
        with self.at("laptop"):
            remote.save(self.rcfg)
            task.save_settings(self.cfg)
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(task.main(["--lang", "en", "file", SPOKEN]), 0)
        with self.at("server"):
            self.assertEqual(task.read_record()["tasks"], {})
            self.desk().cycle()
            self.assertEqual(task.read_record()["tasks"]["12"]["pr"], 7)
        self.assertEqual(self.card()["task"], SPOKEN)

    def test_a_pull_request_for_an_issue_pocketcall_filed_elsewhere_gets_its_card_with_no_record_here(self):
        self.answers({"pr list": [0, json.dumps(PR_LIST)], "pr view": [0, json.dumps(PR_VIEW)], "pr diff": [0, PR_DIFF],
                      "issue view": [0, json.dumps(ISSUE_12)]})
        with self.at("server"):
            self.desk().cycle()
            found = task.read_record()["tasks"]["12"]
        self.assertEqual((found["state"], found["pr"], found["words"]), ("pr", 7, SPOKEN))
        self.assertEqual(self.card()["task"], SPOKEN)

    def test_an_issue_pocketcall_did_not_file_brings_no_card_by_itself(self):
        self.answers({"pr list": [0, json.dumps(PR_LIST)], "pr view": [0, json.dumps(PR_VIEW)], "pr diff": [0, PR_DIFF],
                      "issue view": [0, json.dumps(dict(ISSUE_12, body="Somebody's own words."))]})
        with self.at("server"):
            self.desk().cycle()
            self.desk().cycle()
            self.assertEqual(task.read_record()["tasks"], {})
        self.assertEqual(self.asks(), [])

    def test_two_desks_on_one_phone_file_a_note_once_and_send_one_card(self):
        self.answers({"issue create": [0, "https://github.com/acme/site/issues/13\n"],
                      "pr list": [0, json.dumps([dict(PR_LIST[0], body="Closes #13", headRefName="pocketcall/13-footer")])],
                      "pr view": [0, json.dumps(PR_VIEW)], "pr diff": [0, PR_DIFF]})
        post(self.room + "/note", {"id": "n7", "box": self.pair.seal({"id": "n7", "kind": "note", "words": "Fix the footer"})})
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            for name in ("laptop", "server", "laptop", "server"):
                with self.at(name):
                    self.desk().cycle()
        self.assertEqual(len(self.calls("issue", "create")), 1)
        self.assertEqual(len(self.asks()), 1)
        self.assertIn("Another desk on this phone is on", out.getvalue())
        with self.at("laptop"):
            self.desk().hold(0)                       # the laptop goes to sleep and lets go
        with self.at("server"):
            self.desk().cycle()                       # takes over: the task from the relay, the card already waiting
            rec = task.read_record()
        self.assertEqual(rec["tasks"]["13"]["pr"], 7)
        self.assertEqual(len(rec["cards"]), 1)
        self.assertEqual(len(self.asks()), 1)
        self.say("yes")
        with self.at("server"):
            self.desk().cycle()
            self.assertEqual(task.read_record()["tasks"]["13"]["state"], "merged")
        self.assertEqual(len(self.calls("pr", "merge")), 1)


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


class TestTwoWaitingProcesses(Stand):
    def setUp(self):
        super().setUp()
        FakeTelegram.calls, FakeTelegram.updates = [], []
        self.api = ThreadingHTTPServer(("127.0.0.1", 0), FakeTelegram)
        threading.Thread(target=self.api.serve_forever, daemon=True).start()
        os.environ["POCKETCALL_TELEGRAM_API"] = "http://127.0.0.1:%d" % self.api.server_address[1]

    def tearDown(self):
        self.api.shutdown()
        self.api.server_close()
        super().tearDown()

    def test_the_hook_and_the_desk_on_one_bot_each_get_their_own_answer(self):
        hook, desk = remote.Telegram("T", 7, [7], WORDS), remote.Telegram("T", 7, [7], WORDS)
        card = {"tool": "Bash", "command": "ls", "files": [], "diff": "", "folder": "", "complete": True}
        hook.send(dict(card, id="h1"))
        desk.send(dict(card, id="d1"))
        FakeTelegram.updates += [{"update_id": 1, "callback_query": {"id": "1", "from": {"id": 7}, "data": "y:d1"}},
                                 {"update_id": 2, "callback_query": {"id": "2", "from": {"id": 7}, "data": "n:h1"}}]
        self.assertEqual(hook.poll("h1", 0), "no")     # reads both presses and puts the desk's aside
        self.assertEqual(desk.poll("d1", 0), "yes")
        self.assertEqual(list((self.tmp / "home" / "telegram").iterdir()), [])


class TestJoin(Stand):
    def test_a_computer_that_stays_on_joins_the_phone_s_pairing_from_its_link(self):
        secret = seal.new_secret()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remote.main(["--lang", "en", "join", "--link", "https://relay.example.com/#k=" + secret]), 0)
            self.assertEqual(remote.main(["--lang", "en", "join", "--link", "https://relay.example.com/"]), 1)
        self.assertEqual(remote.load(), {"relay": "https://relay.example.com", "secret": secret})


class TestTheWords(unittest.TestCase):
    def test_the_task_skill_runs_task_py_and_keeps_the_words_unchanged(self):
        body = (ROOT / "skills" / "task" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn('sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/task.py file', body)
        for fact in ("--cloud", "--home", "remote.py join --link", "watch --start cloud", "gh auth login",
                     "**Yes**", "**No**", "**Show the diff**", "--match-head-commit",
                     "do not approve on the phone what you cannot see", "unchanged"):
            self.assertIn(fact, body)

    def test_the_readme_the_changelog_and_the_manifests_name_this_version(self):
        version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual(version, "0.4.0")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("**Status: v%s.**" % version, readme)
        self.assertIn("## %s " % version, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertIn("## Voice → task → pull request → Yes from the phone", readme)
        for fact in ("scripts/task.py setup --github", "scripts/task.py watch", "remote.py join --link"):
            self.assertIn(fact, readme)

    def test_leave_sends_a_change_to_code_to_the_tracker_and_ready_names_the_way(self):
        self.assertIn("`task` skill", (ROOT / "skills" / "leave" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("`task` skill", (ROOT / "skills" / "ready" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("`task` skill", (ROOT / "skills" / "remote" / "SKILL.md").read_text(encoding="utf-8"))

    def test_the_phone_page_has_the_task_box_and_reads_what_comes_back(self):
        page = (ROOT / "scripts" / "phone" / "index.html").read_text(encoding="utf-8")
        for fact in ('post("note"', "/receipt?id=", "Send as a task", "card.task", "card.heading"):
            self.assertIn(fact, page)

    def test_every_journal_event_is_from_its_closed_list(self):
        source = (ROOT / "scripts" / "task.py").read_text(encoding="utf-8")
        events = set(re.findall(r'journal\([^\n]*?, "([a-z_-]+)", ', source))
        self.assertGreaterEqual(len(events), 4, events)
        self.assertLessEqual(events, set(task.EVENTS))

    def test_every_word_the_new_lines_use_is_in_each_language_with_the_same_placeholders(self):
        source = "".join((ROOT / "scripts" / name).read_text(encoding="utf-8")
                         for name in ("task.py", "remote.py", "approval_card.py"))
        used = set(re.findall(r'words\["([a-z_]+)"\]', source)) | {"task_watching_cloud", "task_watching_home"}
        english = json.loads((ROOT / "lang" / "en.json").read_text(encoding="utf-8"))
        for code in ("en", "es", "pt", "ru", "uk"):
            other = json.loads((ROOT / "lang" / ("%s.json" % code)).read_text(encoding="utf-8"))
            for key in sorted(used):
                self.assertIn(key, other, (code, key))
                self.assertEqual(sorted(re.findall(r"{\w+}", other[key])), sorted(re.findall(r"{\w+}", english[key])),
                                 (code, key))


if __name__ == "__main__":
    unittest.main()
