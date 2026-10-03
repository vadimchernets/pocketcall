#!/usr/bin/env python3
"""Break pocketcall's own promises on purpose, in a copy, and watch the tests redden.

Each mutation copies the plugin folder to a temporary place, changes one exact text in one file of
the copy (the text must be there exactly once, or the mutation itself is reported as broken), runs
the named tests in the copy, and expects them red. The control mutation changes a comment and
expects green. After every run the sha256 of every original file is compared with the one taken at
the start: the plugin itself is never touched. The last line counts the mutations that misbehaved;
anything but 0 is a failure. tests/test_mutations.py runs this.

  python3 tests/mutate_code.py            (about half a minute; needs pytest, like the tests)
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = (".git", "__pycache__", ".pytest_cache", "dist")
CHECKS = "tests/test_check.py"
WORDS = "tests/test_words.py"

# (what is broken, file, exact text, replacement, tests to run, expected outcome)
MUTATIONS = (
    ("control: a comment reworded", "scripts/check.py",
     "# The handover rule: the phone cannot read a terminal", "# The handover rule: a phone cannot read a terminal",
     CHECKS, "green"),
    ("with ANTHROPIC_API_KEY the report no longer says the remote will not work (English)", "lang/en.json",
     "{name} is set in {where}: the remote will not work while it is.", "{name} is set in {where}.",
     CHECKS + "::TestWorkAccounts", "red"),
    ("with ANTHROPIC_API_KEY the report no longer says the remote will not work (Russian)", "lang/ru.json",
     "\u043f\u043e\u043a\u0430 \u043e\u043d\u0430 \u0437\u0430\u0434\u0430\u043d\u0430, \u043f\u0443\u043b\u044c\u0442 "
     "\u043d\u0435 \u0431\u0443\u0434\u0435\u0442 \u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c",
     "\u043f\u043e\u043a\u0430 \u043e\u043d\u0430 \u0437\u0430\u0434\u0430\u043d\u0430",
     CHECKS + "::TestWorkAccounts", "red"),
    ("an API key is no longer looked for at all", "scripts/check.py",
     'NOT_A_SUBSCRIPTION = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")',
     'NOT_A_SUBSCRIPTION = ("ANTHROPIC_AUTH_TOKEN",)',
     CHECKS, "red"),
    ("the leave skill drops the rule about approving from the phone", "skills/leave/SKILL.md",
     "## Do not approve on the phone what you cannot see", "## Approving from the phone",
     WORDS + "::TestTheRuleForThePhone", "red"),
    ("the card drops the rule about approving from the phone", "lang/en.json",
     '"DO NOT APPROVE ON THE PHONE WHAT YOU CANNOT SEE",', '"APPROVING FROM THE PHONE",',
     WORDS + "::TestTheRuleForThePhone", "red"),
    ("telemetry switches are counted as stops on every version", "scripts/check.py",
     "elif version is None or version < SOFT_FIXED_IN:", "elif True:",
     CHECKS + "::TestWorkAccounts", "red"),
    ("telemetry switches are never counted as stops, even under Trusted Devices", "scripts/check.py",
     "        if trusted_devices:\n", "        if False:\n",
     CHECKS + "::TestWorkAccounts", "red"),
    ("GrowthBook is no longer a hard switch", "scripts/check.py",
     'HARD_KILLERS = ("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "DISABLE_GROWTHBOOK")',
     'HARD_KILLERS = ("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",)',
     CHECKS + "::TestWorkAccounts", "red"),
    ("the administrator's disableRemoteControl is ignored", "scripts/check.py",
     'if managed_value(managed, "disableRemoteControl") is True:', "if False:",
     CHECKS + "::TestWorkAccounts", "red"),
    ("branch B loses the way to the cloud without GitHub", "skills/ready/SKILL.md",
     "`CCR_FORCE_BUNDLE=1 claude --cloud \"the task\"`", "`claude --cloud \"the task\"`",
     WORDS + "::TestWorkBranches", "red"),
    ("a Yes to a card cut to fit is taken as Yes", "scripts/remote.py",
     'if say == "yes" and not card["complete"]:', "if False:",
     "tests/test_remote.py::TestHook", "red"),
    ("a stranger's press in Telegram decides", "scripts/remote.py",
     "            if who not in self.allow:\n                continue\n", "",
     "tests/test_remote.py::TestTelegram", "red"),
    ("the README slips an excuse back in", "README.md",
     "Keep it awake and the evening works.", "Keep it awake and the evening works, for now.",
     "tests/test_no_disclaimers.py", "red"),
    ("a Yes merges whatever the pull request holds by then, not the commit the card showed", "scripts/task.py",
     ', "--match-head-commit", card["sha"]]', "]",
     "tests/test_task.py::TestCard", "red"),
    ("a Yes to a pull request card cut to fit merges", "scripts/task.py",
     'if say == "yes" and card["complete"]:', 'if say == "yes":',
     "tests/test_task.py::TestCard", "red"),
    ("the voice note is filed as its title, not word for word", "scripts/task.py",
     'file_issue(cfg, words, title, text + "\\n\\n"', 'file_issue(cfg, words, title, title + "\\n\\n"',
     "tests/test_task.py::TestFile", "red"),
    ("a Yes kept while the checks run merges a commit pushed after the card", "scripts/task.py",
     'if str(info.get("headRefOid") or "") != sha:', "if False:",
     "tests/test_task.py::TestCard", "red"),
    ("a cloud start counts as started without a session link", "scripts/task.py",
     '    raise TaskError(words["task_session_failed"].format(why=why))\n', "    return last_line(said)\n",
     "tests/test_task.py::TestStart", "red"),
    ("two desks on one phone both act", "scripts/task.py",
     "return exc.code != 409", "return True",
     "tests/test_task.py::TestTwoComputers", "red"),
    ("a pull request from a fork is linked to a task by itself", "scripts/task.py",
     '    if pr.get("isCrossRepository"):\n        return False\n', "",
     "tests/test_task.py::TestCard", "red"),
    ("a task's news never reaches the phone", "scripts/task.py",
     'if task.get("note") and self.relay is not None:', "if False:",
     "tests/test_task.py::TestNotes", "red"),
    ("the phone polls whole cards again, diff and all, every few seconds", "scripts/relay.py",
     'return [{"id": k} for k in self.asks.get(room, {})]',
     'return [{"id": k, "box": v} for k, v in self.asks.get(room, {}).items()]',
     "tests/test_remote.py::TestRelay", "red"),
    ("the relay hands one note to two desks", "scripts/relay.py",
     "                if lease > 0:\n                    held[1] = now + min(lease, MAX_LEASE)\n", "",
     "tests/test_remote.py::TestRelay", "red"),
    ("Telegram drops Yes from a card longer than one message", "scripts/remote.py",
     'yes = bool(card["complete"])', 'yes = bool(card["complete"]) and len(text) <= TELEGRAM_TEXT',
     "tests/test_remote.py::TestTelegram", "red"),
)


def digest(root):
    """sha256 of every file under root (junk folders left out), keyed by relative path."""
    out = {}
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in names:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                out[os.path.relpath(path, root)] = hashlib.sha256(handle.read()).hexdigest()
    return out


def run_one(tmp, n, mutation):
    """-> ("red" | "green" | "error", detail)."""
    _name, rel, old, new, tests, _expect = mutation
    copy = os.path.join(tmp, "m%02d" % n)
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(*SKIP))
    target = os.path.join(copy, rel)
    with open(target, encoding="utf-8") as handle:
        text = handle.read()
    if text.count(old) != 1:
        return "error", "%r is in %s %d times, not once" % (old, rel, text.count(old))
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(text.replace(old, new, 1))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", tests],
                              cwd=copy, env=env, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "error", repr(exc)
    last = (done.stdout.strip().splitlines() or [""])[-1]
    if done.returncode == 0:
        return "green", last
    if done.returncode == 1:
        return "red", last
    return "error", "pytest exit %d: %s" % (done.returncode, (done.stdout + done.stderr).strip()[-300:])


def main():
    before = digest(ROOT)
    bad = 0
    tmp = tempfile.mkdtemp(prefix="pocketcall-mutate-")
    try:
        for n, mutation in enumerate(MUTATIONS):
            name, expect = mutation[0], mutation[5]
            outcome, detail = run_one(tmp, n, mutation)
            if outcome == expect:
                print("ok   %s: %s as expected (%s)" % (name, expect, detail))
            else:
                print("BAD  %s: expected %s, got %s (%s)" % (name, expect, outcome, detail))
                bad += 1
            after = digest(ROOT)
            if after != before:
                print("BAD  the plugin's own files changed during '%s'" % name)
                bad += 1
                before = after
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("misbehaving: %d" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
