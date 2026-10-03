---
name: leave
description: Walk the person through the four minutes before they go out of the door, ending with one real message answered from the phone, and after that the thirty seconds at the door they repeat every time. Use when they are about to leave and want the work to keep going, when they say they are going out with the phone, or the first time they try the remote. On a work account it follows the branch the ready check picked (the built-in remote, a cloud session, or SSH and tmux), and it covers the rule for approving from the phone and where a voice note from the street goes.
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/card.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/card.py *)
---

# Before you walk out of the door

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

Four minutes, six steps, and the last one is the only proof that counts: a message sent from
the phone in the next room and answered here. Everything before it is preparation; without it
the person finds out in town.

Go one step at a time and wait for the person after each.

## The six steps

1. **Readiness.** Run the `ready` skill first if it has not run in this session. If anything
   comes back NOT, deal with it now, not later.

2. **The phone has the app and the same account.** Ask. If they do not have it, tell them to
   run `/mobile`, which shows a code that opens the right store for their phone. Say the
   thing that saves an argument: there is no separate "Claude Code" app. It is the **Code**
   tab inside the ordinary Claude app. Anything in a store by that name is somebody else's.

3. **Notifications.** On the phone, allow notifications for the app. Then here, run `/config`
   and turn on both of these: **Push when Claude decides** and **Push when actions required**.
   Tell them what each means in one line: the first is "I have finished", the second is
   "I need you to answer before I can go on". Without the second one they will stand in a
   queue while the work waits at home.

4. **Turn the remote on.** Have the person type `/remote-control` here. The first time, a
   dialog asks to enable it; they choose **Enable Remote Control**. Say that this carries the
   conversation you are having now — it is not a new chat. On a Team or Enterprise plan, if it
   answers that Remote Control is not enabled for the organization, an Owner has to turn on
   the toggle at claude.ai/admin-settings/claude-code first (branch A in the `ready` skill).
   If `ready` sent them to branch B or C, this step is that branch instead: B is
   `claude --cloud "the task"`, joined from the **Code** tab; C is `claude` inside
   `tmux new -s work` here, joined with `ssh` and `tmux attach -t work` from the phone.
   Steps 5 and 6 happen just the same on that path.

5. **Join from the phone.** They scan the code shown, or open the **Code** tab and pick the
   session by name. Wait until they say they can see this conversation on the phone. Do not
   go on until they have seen it with their own eyes.

6. **The proof.** Ask them to walk to another room, and from there send one real message
   about their actual work. Answer it. Then ask them a question back, so that they answer
   from the phone once. Then finish something small and put it in the handover folder, and
   have them open that file on the phone. If all three happened, the evening works.

## The thirty seconds at the door — every time, not only the first time

The six steps above happen once. This part repeats: every evening the person walks out, read
these five out loud and wait for a yes on each one. Out loud is the whole trick — a person who
says "plugged in" looks at the cable, and a person who reads it does not.

1. **Plugged in.** A battery that runs out is a computer switched off, and from town they
   cannot plug it back in.
2. **Lid open, sleep set to never.** Never "close the lid and go".
3. **This window stays open.** The conversation lives inside it. Close it and the phone goes
   dark within seconds and nothing says why.
4. **The shared folder is there, and they know its name.** Say the path the `ready` check
   printed for it, not the word "folder" — that is where a photo taken in town lands and
   where finished work comes back. If `ready` found no such folder, that is tonight's job
   before the door, not after it.
5. **Phone in hand before the door, not after it.** Signed in as them, notifications allowed,
   and one message sent from where they are standing right now.

Then give them the two facts that keep the evening alive: when the allowance has run out, the
session simply goes quiet, so they look at it now; and a shared folder that has stopped syncing
goes quiet too, so they prove it now with a one-second test: put one photo in from the phone and
see it arrive here.

## Do not approve on the phone what you cannot see

Say this rule to the person in these words, once, before they leave: **do not approve on the
phone what you cannot see.** A permission question on a phone shows two lines of a command and
a big button. If it does not say which file, what happens to it, and whether it can be undone,
the answer is no, or "wait until I am at the desk" - waiting loses nothing, the question keeps.
It is on the card, under its own heading, so it is in their pocket when the question comes.

Your half of the rule, for the whole evening: before any permission question reaches the phone,
say in four lines or fewer which file, what changes, and whether it can be undone. Anything
irreversible - sending, paying, deleting, pushing - is not asked from the phone at all; write it
into the handover folder for the desk and say that is what you did.

## A thought on the way: a voice note into the queue

In town the person has thirty seconds and no patience for typing. Tell them where a spoken
thought goes, so it does not get lost and does not get acted on half-heard:

- **Into the remote, by voice.** The microphone on the phone keyboard turns speech into the
  message they send in the **Code** tab. You put it in a queue; you do not act on it on the
  spot unless they said "do it now".
- **Something that has to be chased** - a refund, a call back, a document someone owes them -
  goes to Chasecall: `/chasecall:take` with their words, from here. Or, without the remote, a
  voice memo shared into the Chasecall inbox folder, which they sort at home with "what came
  from my phone?".
- **A long job for tonight** goes to Nightcall: write their words unchanged into the handover
  folder as `for-tonight-<date>.md`, and at home `/nightcall:start` takes that text as the
  task, with its five minutes together before the night begins.
- **Neither plugin installed?** The note still goes into the handover folder as a file, word
  for word. Nothing spoken in the street is lost, and nothing is done on a guess.

## Then give them the card

Run `sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/card.py --dir . --lang en`, with the person's
own language after `--lang` (`en`, `es`, `pt`, `ru` or `uk`), show the card, and tell them
to print it. The five lines at the door and the four reasons the phone goes quiet are on it,
and a person who has those on a wall does not panic in a corridor. If the `ready` check named
a shared folder, pass it along with `--shared` so the card carries the real path.

## What you must not say

- Not "close the lid and go" — a closed lid is sleep, and sleep is a stop.
- Not "it will tell you when the allowance runs out" — when it runs out, nothing can speak.
- Not "you will be able to download the finished document to your phone" — what is promised
  is sending files **from** the phone. Getting work back is the handover folder, which is why
  step 6 makes them open one.
- Not "you are in control of everything from there" — the modes that act without asking
  cannot be switched on from the phone at all. That is a protection, and it is worth saying
  out loud as one.
