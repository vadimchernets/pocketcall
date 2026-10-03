---
name: task
description: Voice to task to pull request to a Yes from the phone. A spoken sentence becomes a ticket in the company's tracker (GitHub Issues, or any tracker that takes a webhook), word for word; a cloud session, or a session on a computer that stays on, does it on a branch of its own and opens a pull request; and the phone gets the approval card for that pull request - the steps Yes runs word for word, every file, the diff, Yes / No / Show the diff - and every step of the task. With the session in the cloud the laptop may sleep. Use when the person dictates a change to code or to a document kept in a repository, says "make this a task", "file it" or "put it in the tracker", wants a session to do it while they are away, or wants to approve a pull request from the phone.
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/task.py *) Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/remote.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/task.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/remote.py *)
---

# Voice → task → pull request → Yes from the phone

A thought spoken in the street becomes a ticket in the company's tracker, word for word. A session
picks it up, makes the change on a branch of its own and opens a pull request. The phone gets the
same approval card as branch D, for that pull request: **Yes** merges exactly the commit the card
showed, **No** leaves a comment and the pull request open, **Show the diff** shows every line.
Every step lands in the task's journal, so whoever reads the tracker sees who asked, which session
took it and who said Yes.

## Running pocketcall's scripts (Mac, Linux, Windows)

Every script command on this page is written for the **Bash** tool and starts with
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/…`. If your shell tool is **PowerShell** (Windows
without Git Bash), only the start changes: write the launcher's path bare, with no quotes and no `&`
— `${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/…` — and keep the rest, on one line; that is the
form this skill's permission covers. Only if that path has a space in it, write
`& "${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1" …` instead (the person is then asked once). Text for standard input:
`@'…'@ | ${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 …` (`| & "…"` if the path has a space) instead of `<<'EOF'` — also asked once.
Never call `python3`, `python` or `py` yourself: the launcher finds a real Python 3.8+ (`python`,
then `py -3`, then `python3`) and never starts the Microsoft Store or Apple stub. If it answers
with one line saying pocketcall "is paused" until this computer has Python 3, tell the
person that in one plain line and go on by hand — never show them a Python error and stop.

## Once per company, once per computer

1. **The tracker.** GitHub: the GitHub CLI signed in once (`gh auth login`), then
   `sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/task.py setup --github <owner/name>`.
   Run from inside a checkout of that repository, sessions here branch from it; run from anywhere
   else, Pocketcall keeps its own copy in `~/.pocketcall/repos/<owner>-<name>` (`--folder <checkout>`
   names one). Each task becomes an issue labelled `pocketcall`.
   Any other tracker: `… scripts/task.py setup --webhook <the address it takes tasks at> --repo <owner/name>`,
   with `--secret <a long random word>` to sign each call (HMAC-SHA256, header
   `X-Pocketcall-Signature-256`) and `--header "Name: value"` for whatever the tracker asks for.
   It receives a JSON POST with the title, the words, who and when.
2. **Who asked.** `--who "<the person's name>"` writes their name under each task they file.
3. **The phone.** Branch D, paired once (the `remote` skill). That is where the cards come, and
   the phone page gains a **New task** box.
4. **Cloud tasks without a terminal: a routine.** At claude.ai/code/routines, a new routine on the
   repository with this saved prompt: *Carry out the task in the routine-fire-payload block: Pocketcall
   filed it in this repository's tracker for me. Follow its numbered rules for the branch and the
   pull request.* Add an API trigger, generate its token, then
   `… scripts/task.py setup --routine <its URL> --routine-token <the token>`. The token starts that
   routine and reads nothing; the routine clones the default branch and runs on the person's own plan.

## A voice note becomes a task

- **In this session.** The person says it (the microphone on the phone keyboard, in the **Code**
  tab). File their words unchanged — do not rewrite, shorten or improve them: the words are the task.
  ```
  sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/task.py file <<'EOF'
  <their words, unchanged>
  EOF
  ```
  Then say the line it printed — the task and its link — in four lines or fewer.
- **From the phone page.** The **New task** box takes the keyboard's microphone. The note is sealed
  with the pairing key, so the relay forwards what it cannot read; the desk below files it and the
  task's link comes back to the same box, followed by each step after it - the session that took it,
  its pull request, the merge, or a session that did not start and is tried again.
- **From the queue.** A note waiting in the handover folder (`for-tonight-<date>.md`) or in the
  Chasecall inbox is filed with `… scripts/task.py file --from <file>`.

## A session picks it up

- **In the cloud, so the laptop may sleep:** `… scripts/task.py start <task> --cloud`. The cloud
  session gets the words unchanged and three rules: a branch of its own from the default branch, only
  what the words ask, and a pull request whose description starts with `Closes #<task>`. It goes to
  the routine when one is set; otherwise to `claude --cloud`, which Pocketcall runs in a terminal of
  its own from its own copy of the repository on the default branch. The line it prints carries the
  session's link; a line saying the session did not start leaves the task filed - say it, and the
  desk tries again.
- **On this computer:** `… scripts/task.py start <task> --home`. A git worktree on
  `pocketcall/<task>-…`, `claude -p` in it with file edits accepted there, then Pocketcall commits,
  pushes and opens the pull request itself. The person's own checkout is not touched. Tools beyond
  edits come from the company's list: `task.py setup --allow "Bash(npm test)"`.
- **From the phone alone:** in the **Code** tab, a new cloud session on the repository with
  "Take issue #<task> and open a pull request that says Closes #<task>". The desk finds that pull
  request like any other.

## The pull request comes to the phone

`… scripts/task.py card <pull request>` sends its card now; the desk does it by itself for every
pull request that belongs to a task, once per commit. The card shows the steps Yes runs, word for
word — `gh pr review <n> --repo <owner/name> --approve --body '…' && gh pr merge <n> --repo <owner/name> --squash --match-head-commit <sha>`
— every file, the diff behind **Show the diff**, and the task's words, with **Yes** and **No**; its
heading names the author, and a fork. Yes merges exactly the commit the card showed. Where the
repository's checks are still running, the Yes is kept and that same commit merges the moment they
pass (`task.py card` waits for them; the desk carries every kept Yes); auto-merge is never turned on, so anything pushed after the card brings its own card and
never rides on this Yes, and failed checks come back as a line. No leaves a comment and the pull
request open. A card cut to fit the phone comes without Yes. The desk links by itself only a pull
request from the task's own branch or from its own GitHub account; a fork's, or someone else's on
another branch, comes only through `task.py card <n>`.

## While the laptop sleeps: the desk

The desk is `task.py watch`, on whatever stays on — the machine that already runs the relay is the
natural place. There, from a copy of Pocketcall (the desk keeps its own copy of the repository):

1. `python3 scripts/remote.py join --link "<the phone link>"` — the same phone, the same key;
2. `gh auth login`, then `python3 scripts/task.py setup --github <owner/name>`, with
   `--routine <URL> --routine-token <token>` from step 4 above;
3. `python3 scripts/task.py watch --start cloud` (every new task goes to the routine, or to
   `claude --cloud` where Claude Code is signed in), or `watch --start home` (the sessions run on that
   machine, on the company's own provider: an API key, Bedrock, Google Cloud or Foundry).

From then on: a note from the phone becomes a task, the task gets a session, its pull request gets a
card, the answer is carried out, and each step comes back to the phone — with the laptop asleep in a
bag. A task filed on the laptop reaches the desk through the relay, sealed, and a pull request for an
issue Pocketcall filed anywhere is found through the issue it closes. On this computer,
`… scripts/task.py watch` does the same while it is awake: the desks on one phone take turns, one at
a time, and a note is filed once. `task.py list` shows every task and where it stands. A Telegram
bot has one reader at a time, so the desk machine gets a bot of its own (`remote.py telegram` there),
or carries the cards on the phone page alone.

## Read the card before Yes

The rule from `leave` holds here: **do not approve on the phone what you cannot see**. The card has
the steps Yes runs, every file and the whole diff; if any of the three is missing from what the
person reads, the answer is No, and the pull request waits for the desk.
