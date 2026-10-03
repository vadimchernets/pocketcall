---
name: remote
description: Branch D, the phone remote without a terminal - the company starts its own relay with one command, the computer pairs with it by a link or QR code, and every permission question asked while the person is away arrives on the phone, end-to-end encrypted, as an approval card with the full command, the files, and Yes / No / Show the diff, with a push; the same card can go to the company's Telegram. Works on an API key, Bedrock, Google Cloud, Foundry, ZDR and HIPAA setups because Claude Code itself stays on this computer. Use when the person wants to approve from the phone without a terminal app, says the built-in remote is off at their company, or asks for approvals in a messenger.
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/remote.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 pocketcall say scripts/remote.py *)
---

# D - the phone remote without a terminal

Claude Code keeps running here, on the company's own provider and sign-in. Only the decisions travel:
when Claude Code is about to ask for permission and the person is away, the plugin's hook sends an
**approval card** to the phone and waits for the answer. The card holds the command word for word,
every file it names, and three buttons: **Yes**, **No**, **Show the diff**. A card too long to read
in full on the phone comes without Yes - it is answered with No, or at the desk.

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

## Setup, once per company and once per computer

1. **The relay - once for the whole company, one command.** On any always-on machine both the
   computers and the phones reach (an office server, a small VM, a Tailscale node):
   `python3 scripts/relay.py --port 8787 --push https://<ntfy server>/<topic>`.
   Standard library only, nothing else to install. Put it behind the company's HTTPS (the
   reverse proxy it already has, or `tailscale serve 8787`). The relay forwards sealed boxes it
   cannot open; the push carries one line, "A decision is waiting", and nothing else. The ntfy app
   on the phone, subscribed to that topic, rings.
2. **Pair this computer**: `… scripts/remote.py pair --relay https://relay.example.com`. It prints
   the phone link (and a QR code when `qrencode` is installed). The key is in the part after `#`,
   which a browser never sends to the relay. Open the link on the phone and add it to the home
   screen: that is the remote.
3. **The company's messenger (optional)**: a Telegram bot of the company's own, made with
   BotFather, separate from any bot a channel uses:
   `… scripts/remote.py telegram --token <bot token> --allow <the person's Telegram user id>`.
   Cards arrive in that chat with the same three buttons; a press from anyone not on `--allow` is
   ignored. Repeat `--allow` for a second person who may decide.
4. **Prove it before relying on it**: `… scripts/remote.py away`, then `… scripts/remote.py test`
   and answer the card on the phone. The script prints the answer it received.

## Every day

- Leaving: `… scripts/remote.py away`. From now on permission questions go to the phone, with a push.
- Back at the desk: `… scripts/remote.py back`. Questions stay on the screen again; no cards, no push.
- `… scripts/remote.py status` names the paths that are set and whether the person is away.
- No answer in time (ten minutes by default, `"wait"` in `~/.pocketcall/remote.json`): the question
  waits on the screen at the desk, exactly as it would have without the phone.

## When to offer it

- The company is on Bedrock, Google Cloud, Foundry, a gateway, ZDR or HIPAA, or hands out only API
  keys: the built-in remote is not offered there, and branch D gives the phone the decisions without
  SSH. Branch C stays for the person who wants the whole terminal.
- The person wants approvals in a messenger the team already uses: step 3.
- With Channels on (`channelsEnabled`, `allowedChannelPlugins`, which `ready` reads), a channel
  carries whole conversations; branch D carries the decisions with the card. Both can run together.

## Pull requests from voice notes

The same card carries a pull request. The `task` skill turns a voice note - from this session, or
from the **New task** box on the phone page - into a task in the company's tracker; a cloud or home
session opens a pull request for it; and the card shows the steps Yes runs word for word (an approving
review and the merge pinned to the commit shown), every file, the diff and the task's words. A machine that stays on - the one that runs the relay - joins the
same phone with `… scripts/remote.py join --link "<the phone link>"` and runs the desk there, so
notes and cards keep moving while the laptop sleeps. A Telegram bot has one reader at a time: that
machine gets a bot of its own, or carries the cards on the phone page alone.

## Read the card before Yes

The rule from `leave` holds here: **do not approve on the phone what you cannot see**. The card shows
the full command and every file; Show the diff shows what changes. If any of the three is missing
from what the person reads, the answer is No.
