---
name: ready
description: Check whether this machine can be left working while its owner walks away, say in plain words what is not ready, and at work pick the branch that fits the company - the built-in remote, a cloud session that runs while the laptop sleeps, or SSH and tmux for companies on Bedrock, Google Cloud, a gateway, ZDR or HIPAA, or the company's own relay that brings each permission question to the phone as an approval card. Use when the person asks to work from their phone, to leave the computer running, to check the remote, says they are about to go out, or asks how to do it on a work account.
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
with one line saying pocketcall "is paused" until this computer has Python 3, tell the
person that in one plain line and go on by hand — never show them a Python error and stop.

Run the check, read it out loud, fix what the person agrees to fix. Do not turn the remote on
inside this skill: that is the next step and the person does it knowingly.

## Do this

1. Run `sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" pocketcall say scripts/check.py --dir . --lang en` and show the
   person the lines that came back, unchanged. Do not summarise away a failure. Put the person's own language
   after `--lang` - `en`, `es`, `pt`, `ru` or `uk` - because the report speaks to them, not to you. If they say
   their organization requires Trusted Devices, add `--trusted-devices`.
2. For each line marked NOT, offer to do the part you can do, one at a time, and wait:
   - the handover folder: make it, and say where it is;
   - the handover rule: show the two lines before you write them into CLAUDE.md;
   - the sleep setting: the person sets it themselves. Name the setting and where it is,
     let them open it, then run the check again and read the result.
   - the shared folder: if the check found none, help them pick one inside Google Drive or
     Dropbox — not iCloud Drive if the phone in their pocket is an Android one — and run the
     check again with `--shared` and that folder. Make a folder inside their drive only where
     they tell you to, and never move, rename or open what is already in there.
3. If the version or one of the quiet killers came back NOT, do not go on to `/remote-control`:
   it will not come up, and it will not say why. Fix what can be fixed. If the line is one
   the person cannot change - a company API key, Bedrock, Google Cloud, Foundry, a required
   gateway, or the administrator's `disableRemoteControl` - go to "At work: four branches"
   below and pick the branch that works for them. For their company it is the way the
   evening runs.
4. When everything is ok, say the one sentence that matters and then stop:
   "The machine is ready. Turning the remote on is `/remote-control`, and it will show a
   code for your phone to scan."

## At work: four branches

On a personal Pro or Max plan the check above is the whole story. On a work account the same
evening goes one of four ways, and the check's lines tell you which. Say the branch letter and
its name, then walk the person through it one step at a time.

### A - the computer stays on: the built-in remote

The plan is Pro, Max, Team or Enterprise, signed in through claude.ai, and the check is clean.

- **Team and Enterprise: an Owner turns it on once.** Remote Control is off by default for an
  organization. An Owner opens claude.ai/admin-settings/claude-code and turns on the
  **Remote Control** toggle; it is a server-side setting and nothing on this computer can do
  it. If the person is not the Owner, give them one sentence to send: "Please turn on Remote
  Control in claude.ai/admin-settings/claude-code - I want to steer my Claude Code session
  from my phone."
- **Trusted Devices.** If the organization requires them (an Owner sets this at
  claude.ai/admin-settings/capabilities, Remote sessions, Require trusted devices), each
  computer and phone enrolls at sign-in: `/login` here, a fresh sign-in on the phone. A
  sign-in older than 18 hours asks again, with `/login` or Face ID, Touch ID, Windows Hello or
  a passkey. With Trusted Devices on, `DISABLE_TELEMETRY` and `DO_NOT_TRACK` stop the remote:
  run the check again with `--trusted-devices`, and unset what it names.
- **Several jobs at once.** `claude remote-control --spawn worktree` serves a session for each
  job started from the phone, each in its own git worktree, so two jobs never edit the same
  file (it needs a git repository; `w` switches back and forth while it runs).
- **A machine you reach over SSH** (the office desktop): start it inside tmux -
  `tmux new -s work`, then `claude remote-control` - so it keeps running when the SSH
  connection drops.

### B - the laptop sleeps or goes in the bag: a cloud session

The work runs on Anthropic's cloud, not on this computer, so a closed lid stops nothing.
Plans: Pro, Max, Team, and Enterprise premium or Chat + Claude Code seats. On Team and
Enterprise an Owner turns cloud sessions on at claude.ai/admin-settings/claude-code.

1. Push the branch first: the cloud copies the repository from GitHub at the current branch,
   not from this disk.
2. `claude --cloud "the task in one sentence"` - it prints the session; follow it from the
   **Code** tab of the Claude app.
3. No GitHub (GitLab, Bitbucket, or no remote at all):
   `CCR_FORCE_BUNDLE=1 claude --cloud "the task"` uploads this repository instead - at least
   one commit, under 100 MB, untracked files left behind (`git add` what the task needs), and
   on Mac and Linux uncommitted `.env` and key files are left on this machine. The session
   cannot push back to a non-GitHub remote. `--teleport` below still brings the conversation
   back (checked on 03.10.2026 with a repository that has no remote at all); file changes made
   in the cloud are taken from the session's diff at claude.ai/code.
4. Back at the desk: `claude --teleport <session-id>` (or plain `claude --teleport` for a
   list) from a clean checkout of the same repository, signed in to the same account. To keep
   steering from the phone after that, `/remote-control` in the teleported session.
5. One more message from anywhere, without opening anything: `claude -p "message" --cloud <session-id>`.

### C - the company is on Bedrock, Google Cloud, Foundry, a gateway, ZDR or HIPAA

The built-in remote and cloud sessions both need Anthropic's own service and a claude.ai
sign-in, and an organization with Zero Data Retention or a HIPAA configuration cannot turn the
remote on. Here the phone becomes a terminal into this machine, and every word still goes
through the company's own provider - nothing new leaves.

1. **Tailscale** on this computer and on the phone, signed in to the same network (the
   company's, if IT runs one). The computer gets a private name; no port is opened to the
   internet.
2. **SSH on this computer**: on a Mac, System Settings, General, Sharing, Remote Login; on
   Windows, the OpenSSH Server optional feature; on Linux, `sshd`.
3. **tmux**: `tmux new -s work`, then `claude` inside it. `Ctrl-b` then `d` leaves it running.
4. **On the phone**: Blink Shell (iPhone and iPad; its `mosh` survives switching from Wi-Fi to
   mobile data) or Termius (iPhone and Android): `ssh you@the-computer-name`, then
   `tmux attach -t work`. The same session, with everything in it.

The door ritual is the same as for everyone: a sleeping computer stops branch C too.

### D - the phone remote without a terminal: the company's relay and the approval card

Claude Code stays on this computer, on whatever the company runs - an API key, Bedrock, Google
Cloud, Foundry, a gateway, ZDR or HIPAA - and only the decisions travel. The company starts its own
relay with one command (`python3 scripts/relay.py --port 8787`), this computer pairs with it by a
link or QR code, and every permission question asked while the person is away arrives on the phone,
end-to-end encrypted and with a push, as an approval card: the full command, every file, and Yes /
No / Show the diff. The same card can go to the company's Telegram. Open the `remote` skill and
walk the person through its setup. Branch C stays for the person who wants the whole terminal.

### Channels: Telegram, Discord or iMessage into the running session

A channel brings a message from a chat app into the session that is already running here,
and the answer goes back to the same chat. It works with a claude.ai sign-in and also with a
Console API key - so a company that hands out only keys gets a phone path this way - but not
on Bedrock, Google Cloud or Foundry. It needs Bun on this computer, and it is a research
preview.

- **Team and Enterprise: off until an Owner turns it on**, at claude.ai, Admin settings,
  Claude Code, **Channels**; or IT sets `channelsEnabled` to `true` in managed settings.
  Which channel plugins may run is `allowedChannelPlugins`, also in managed settings; a
  person cannot override either. The check prints what the managed settings on this computer
  say, when there are any.
- **Setup, Telegram as the example**: `/plugin install telegram@claude-plugins-official`,
  `/telegram:configure <token from BotFather>`, restart with
  `claude --channels plugin:telegram@claude-plugins-official`, send the bot a message, then
  `/telegram:access pair <code>` and `/telegram:access policy allowlist`.
- **Allowlist only the person themselves.** Whoever is on that list can answer permission
  questions for this session.

## What you must not do

- Do not claim the remote is on. This skill checks; it does not connect.
- Do not read or change power settings for the person on any system. Name the setting, let
  them look at it. A person who has changed it once will change it again without you.
- Do not promise that work continues while the machine sleeps. It does not. Say instead what
  is true: nothing is lost, the connection comes back by itself when the machine wakes, and
  the time in between is gone.
- Do not offer any third-party remote that wants the person's Claude sign-in, and if the person
  mentions one that asks them to sign in to their Claude account inside it, say plainly that
  handing a sign-in to another company is against the terms and that they should not. Branch
  C is not that: Tailscale and an SSH app never see the Claude account, they carry a terminal
  to the person's own computer.
- Do not say the shared folder is syncing; prove it. A drive can be signed out, paused, full
  or quietly stuck while the folder looks the same, so read out what the check sees — the
  folder, the number of files, the date of the last change — and give them the test that
  proves it: one photo in from the phone, watched arriving here.
