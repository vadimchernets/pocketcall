---
name: board
description: The board - every job on this computer on one screen, on the computer and on the phone. Each Claude Code session reports itself (working, waits for you, done, resting on a limit until a given hour), a night run, a council review or any script adds its own line, and the phone rings only on what changed for the person - a job waits for an answer, a job is done, a job rests on a limit and when it goes on - through the Telegram chat already set for the remote and the person's own ntfy topic. The board is also one phone page written into the shared folder the phone already sees, with no server at all. Use when the person asks what is running, what waits for them, which session is stuck or done, wants a ping on the phone when a long job finishes, or keeps many sessions open at once. Also steers long work from the phone - Continue and Stop buttons under the ring, "stop" / "continue" typed, a voice note that becomes TASK.md - use when the person says "stop the night from the phone", "continue", "voice task", "dictate the task".
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/board.py *) Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/steer.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/steer.py *)
---

# The board - every job on one screen, the phone rings when one needs you

The plugin's hooks write each Claude Code session's state by themselves, from the moment the plugin
is on: **Working** when a message goes in, **Waits for you** when Claude Code asks a question or for
permission, **Done** when the turn ends, **Resting on a limit until 18:00** when a usage limit ended
it. A night run, a council review or a cron job adds its own line with `put`. Nothing to start.

## Running pocketcall's scripts (Mac, Linux, Windows)

Every script command on this page is written for the **Bash** tool and starts with
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/…`. If your shell tool is **PowerShell** (Windows
without Git Bash), only the start changes: write the launcher's path bare, with no quotes and no `&`
— `${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/…` — and keep the rest, on one line; that is the
form this skill's permission covers. Only if that path has a space in it, write
`& "${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1" …` instead (the person is then asked once).
Never call `python3`, `python` or `py` yourself: the launcher finds a real Python 3.8+ and never
starts the Microsoft Store or Apple stub. If it answers with one line saying pocketcall "is paused"
until this computer has Python 3, tell the person that in one plain line and go on by hand.

## What is running

`sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py show` prints the list, the job that waits
for the person first, then the ones resting on a limit, stopped, working, done. Read it back in plain
words, the waiting ones first, with the folder each one is in: "Two jobs wait for you: the shop (it
asks to run the tests) and the book (it asks a question). The report is done. The site rests on a
limit until 18:00 and goes on by itself."

## The phone rings - set once

Ask which of the two the person already has; one is enough, both work together.

1. **Telegram** - the chat set for the remote (`remote.py telegram`, skill `remote`) gets the ring
   too, nothing more to set.
2. **ntfy** - a free app on the phone (iPhone and Android). The person picks a long topic name no one
   would guess, subscribes to it in the app, and you run
   `sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py ring --ntfy https://ntfy.sh/<topic> --test`.
   A company with its own ntfy server gives its address instead.

When it rings: `ring --when away` (the default) - while `remote.py away` says the person is out;
`ring --when always` - every time, at the desk too; `ring --when never` - only the board and its
page. Each ring is one line: the state, the job, its folder, a few words of what it said. A
permission question that already goes to the phone as an approval card does not ring twice.

## The board on the phone, no server

`sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py page --to "<shared folder>"` writes
`pocketcall-board.html` into the Google Drive, iCloud Drive, Dropbox or OneDrive folder the phone
already sees (skill `ready` finds it) and rewrites it at every change. The person opens it once in
the phone's Files / Drive app and adds it to the home screen; it refreshes itself every minute. The
page carries the folder names and the first words of each job - pick a folder only the person's own
accounts see. `page --off` stops writing it.

## Other jobs on the board

Anything that runs long reports itself with one line, and rings when its state changes:

    sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py put --name "night run: book" --where nightcall --state working --note "chapter 4 of 12"
    sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py put --name "night run: book" --where nightcall --state limit --until "03:10"
    sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py put --name "diffcall review" --where shop --state done --note "4 findings, 1 disputed"

Any long command goes on the board by itself when it runs through `run`: working while it runs,
done or stopped - with its last line - when it ends, and the phone rings then. A fix run of diffcall
that waits for its end, a test suite, a build, a deploy:

    sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py run --name "diffcall fix" --where shop -- diffcall fix --task "fix the basket bugs" --wait
    sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/board.py run --name "shop tests" -- npm test

Start such a command with the Bash tool's background run, so the session stays free; the output
shows on the screen as usual and the command's exit code is `run`'s.

The same name is the same line. A tool that has no Python can write the job file itself:
`~/.pocketcall/board/<id>.json` with `id`, `name`, `where`, `state`
(`working`, `waiting`, `done`, `limit`, `failed`), `note`, `until` and `at` (seconds since 1970).

`clear` takes the finished jobs off the board, `clear --all` empties it; a finished job leaves by
itself after three days, a closed session at once.

## Steer long work from the phone: Continue, Stop, a voice task

A job with a task folder - a nightcall night or a long build (nightcall 0.5.0 puts its folder and its own
command on the board) - rings with two buttons in Telegram: **Continue** and **Stop**. Stop leaves a STOP file
in the folder, and the night loop ends after the step it is on; Continue takes the STOP away, and a night that
already ended goes on to the night's own end through nightcall's loop on this computer (the card holds only data -
folder, hours, end, box - and steer.py builds the command itself; the earlier MORNING.md is kept under a dated name). Typing "stop" or
"continue" (in any of the five languages, with part of the name when several run) does the same.

A voice note in the same chat becomes the next task: it is transcribed on this computer (mlx-whisper, whisper,
whisper.cpp, or the person's own OPENAI_API_KEY / GROQ_API_KEY), and lands as `TASK.md` in a new folder of the
inbox; `task: ...` typed does the same. With `--start` the task begins at once - for example a night through
nightcall's loop. The listener runs on the computer that stays on; `steer.py install` keeps it running after this
session ends (a LaunchAgent on a Mac, a systemd user service on Linux, restarted if it stops):

    sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/steer.py inbox --to "<folder for tasks from the phone>" --start "<command with {folder}>"
    sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/steer.py install

At the desk the same: `steer.py stop --id <job>` / `steer.py continue --id <job>` (the id is in `board.py show --json`).
Only the Telegram ids on the allowlist of `remote.py telegram` steer. A job with `--meter` shows how much each
subscription has left - as bars on the phone page, in brackets in the ring.
