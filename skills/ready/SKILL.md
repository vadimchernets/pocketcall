---
name: ready
description: Check whether this machine can be left working while its owner walks away, and say in plain words what is not ready. Use when the person asks to work from their phone, to leave the computer running, to check the remote, or says they are about to go out.
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/check.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/check.py *)
---

# Is this machine ready to be left alone?

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
with one line saying pocketcall "is paused" because this computer has no working Python 3 yet, tell the
person that in one plain line and go on by hand — never show them a Python error and stop.

Run the check, read it out loud, fix what the person agrees to fix. Do not turn the remote on
inside this skill: that is the next step and the person does it knowingly.

## Do this

1. Run `sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/check.py --dir .` and show the person the
   lines that came back, unchanged. Do not summarise away a failure.
2. For each line marked NOT, offer to do the part you can do, one at a time, and wait:
   - the handover folder: make it, and say where it is;
   - the handover rule: show the two lines before you write them into CLAUDE.md;
   - the sleep setting: you cannot change it and must not try. Tell the person which
     setting and let them open it themselves. Then run the check again and read the result.
   - the shared folder: if the check found none, help them pick one inside Google Drive or
     Dropbox — not iCloud Drive if the phone in their pocket is an Android one — and run the
     check again with `--shared` and that folder. Make a folder inside their drive only where
     they tell you to, and never move, rename or open what is already in there.
3. If the version or one of the quiet killers came back NOT, stop. There is no point
   continuing: the remote will not come up, and it will not say why.
4. When everything is ok, say the one sentence that matters and then stop:
   "The machine is ready. Turning the remote on is `/remote-control`, and it will show a
   code for your phone to scan."

## What you must not do

- Do not claim the remote is on. This skill checks; it does not connect.
- Do not read or change power settings for the person on any system. Name the setting, let
  them look at it. A person who has changed it once will change it again without you.
- Do not promise that work continues while the machine sleeps. It does not. Say instead what
  is true: nothing is lost, the connection comes back by itself when the machine wakes, and
  the time in between is gone.
- Do not offer any third-party remote, and if the person mentions one that asks them to sign
  in to their Claude account inside it, say plainly that handing a sign-in to another company
  is against the terms and that they should not.
- Do not say the shared folder is syncing. Nothing on this machine can see that: a drive can
  be signed out, paused, full or quietly stuck and the folder looks the same. Read out what
  the check does see — the folder, the number of files, the date of the last change — and give
  them the test that proves it: one photo in from the phone, watched arriving here.
