# Pocketcall

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23107735.svg)](https://doi.org/10.5281/zenodo.23107735)

**Leave the computer working, take the phone, and do not find out in town that it never
started.** Pocketcall does not connect your phone to anything. The remote already exists and
comes with the subscription you already pay for. What Pocketcall adds is the part nobody
ships: the seven things that silently decide whether an unattended machine works at all, the
four minutes at the door and the thirty seconds you repeat every time after, and the
discipline of answering someone who is reading four lines on a phone in a corridor.

Pocketcall is an independent open-source project. Not affiliated with Anthropic.

**Status: v0.5.0.** Written for people who are not programmers — a lawyer, a nurse, a pastor, a
teacher, a realtor, a bookkeeper — with a paid personal subscription, no API keys, no server, and
no intention of acquiring either; and, since 0.3, for the same people on a work account, where
the company decides what is allowed (see [At work](#at-work-four-branches)). It speaks English,
Spanish, Portuguese, Russian and Ukrainian.

## Why this exists

The connection between a phone and a session running on your own machine is built in. Turning
it on is one command. And yet the evening fails, again and again, for reasons that never
announce themselves:

- the machine went to sleep four minutes after the front door closed;
- a variable set in a shell profile two years ago switches off the thing the remote depends
  on, and nothing says so;
- notifications for "I need an answer to continue" were never turned on, so the work waits
  politely for six hours;
- the finished document is sitting in a terminal, which a phone cannot read;
- the shared folder stopped syncing three days ago, so the photo taken in town is still on the
  phone, looking sent;
- the person approves something in a corridor that they could not actually see.

None of those is hard. All of them are invisible. Pocketcall makes them visible before you
leave, not after.

## Install

```
/plugin marketplace add https://raw.githubusercontent.com/vadimchernets/poly-a1-plugins/main/.claude-plugin/marketplace.json
/plugin install pocketcall@poly-a1
```

The first line adds Poly A1's catalogue by its link - one file, no git and no GitHub account - and
later corrections reach you from the same place (Claude Code 2.1.224 or later; `claude update`). If
`poly-a1` is already there, from the Poly A1 folder or from before, skip it: the second line is enough.

Without internet, from the Poly A1 folder:

```
/plugin marketplace add <path to the Poly A1 folder>
/plugin install pocketcall@poly-a1
```

Once there is internet, the folder is switched to the link in place, keeping everything installed
([how](https://github.com/vadimchernets/poly-a1-plugins/blob/main/OFFER-THESE.md#later-from-the-folder-to-github-without-losing-anything)). Never `/plugin marketplace remove poly-a1`: it uninstalls every plugin that came from
it and deletes their saved data.

## What you get

| what | when you use it |
|---|---|
| `ready` | before leaving: checks the seven silent things and says, in plain words, which are not ready |
| `leave` | the first time, and any time it matters: six steps ending with one real message answered from the phone, then the thirty seconds at the door you repeat every evening |
| `remote` | branch D: pair with the company's relay and messenger; while you are away every permission question arrives on the phone as an approval card with Yes, No and Show the diff |
| `task` | a voice note becomes a task in the company's tracker, a cloud or home session opens its pull request, and the phone gets that pull request's card: every file, the diff, Yes / No / Show the diff |
| `board` | every job on one screen - each Claude Code session, a night run, a review: working, waits for you, done, resting on a limit until a given hour - and the phone rings on what changed for you, through Telegram or your own ntfy topic; the board is also one phone page in your shared folder |
| `handover` | standing guidance for the whole time you are away: short answers, finished work in a file |

You can also run the check by hand, without the plugin:

```
python3 scripts/check.py                      # a report for a person
python3 scripts/check.py --json               # the same findings for a program
python3 scripts/check.py --shared ~/Dropbox/phone   # when the shared folder is not found by itself
python3 scripts/check.py --lang ru            # en, es, pt, ru or uk; default: the system's language
python3 scripts/check.py --trusted-devices    # your organization requires Trusted Devices
python3 scripts/card.py --lang es             # the card to print and keep where you can see it
```

`check.py` and `card.py` are standard library only, read-only, and talk to nothing over the network. The branch D scripts and `task.py` are standard library only too: the first talk only to the company's relay and messenger, and `task.py` to the company's tracker (through the GitHub CLI's own sign-in, or the company's webhook), to git, to Claude Code, to the relay (tasks sealed like the cards) and, for a cloud task, to the routine's own API trigger.

## The seven things `ready` looks at

1. **Where you are.** A remote session has to start from a work folder. The trust question it
   needs is never remembered for your home folder.
2. **How old the program is.** Too old, and the rest of this is moot.
3. **The quiet killers.** `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` and `DISABLE_GROWTHBOOK`
   always switch off the feature evaluation the remote depends on; `DISABLE_TELEMETRY` and
   `DO_NOT_TRACK` do it only when the organization requires Trusted Devices, or on a Claude
   Code older than 2.1.283, and `ready` says which case you are in. A custom API address, an
   API key (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `apiKeyHelper`), or another company's
   cloud (Bedrock, Google Cloud, Foundry) make it unavailable — and for an API key it says so in
   those words: the remote will not work while it is set. Set in a shell profile, in the `env`
   block of a settings file or in the organization's managed settings, they produce no error at
   all. `ready` names the exact file it found each one in, and on a work account the branch that
   does work instead.
4. **A written-down refusal.** Someone may have turned the remote off in a settings file.
   Including you, a year ago — or your IT administrator, in the managed settings, which nothing
   of yours overrides. When those managed settings exist, `ready` also reads what they say about
   Channels (`channelsEnabled`, `allowedChannelPlugins`).
5. **Sleep.** On a Mac, `ready` reads the actual setting and tells you the number of minutes.
   Elsewhere it names the setting, and you set it once.
6. **The handover.** Is there a folder your phone can see, and does your rules file say that
   finished work goes there?
7. **The shared folder.** The folder you drop a photo into from the street and the work reads
   at home — Google Drive or Dropbox, and not iCloud Drive if the phone in your pocket runs
   Android. `ready` finds it, says how many files are in it and when anything last changed,
   and gives you the one-photo test that proves the drive carries it. Point it at the right
   folder with `--shared` if it guessed wrong.

## At work: four branches

On a Team or Enterprise plan, or wherever a company decides how Claude Code is reached, `ready`
reads the check and walks the person down one of four branches. Every command is from Claude
Code's own documentation (code.claude.com/docs: remote-control, claude-code-on-the-web, channels,
managed-settings).

- **A — the computer stays on: the built-in remote.** An Owner turns on the **Remote Control**
  toggle once at claude.ai/admin-settings/claude-code (it is off by default for an
  organization). With Trusted Devices required, each computer and phone enrolls at sign-in.
  `claude remote-control --spawn worktree` gives each job started from the phone its own git
  worktree; on a machine reached over SSH it runs inside `tmux`.
- **B — the laptop sleeps or goes in the bag: a cloud session.** `claude --cloud "the task"`
  runs it on Anthropic's cloud, followed from the Code tab of the Claude app; back at the desk,
  `claude --teleport <session-id>`. Without GitHub, `CCR_FORCE_BUNDLE=1` uploads the local
  repository instead. An Owner turns cloud sessions on at the same admin page. A voice note can go
  straight to this branch as a task, and come back to the phone as a pull request to approve (see
  [Voice → task → pull request](#voice--task--pull-request--yes-from-the-phone)).
- **C — the company is on Bedrock, Google Cloud, Foundry, a gateway, ZDR or HIPAA.** Neither the
  remote nor cloud sessions are offered there, so the phone becomes a terminal into the person's
  own computer: Tailscale on both, SSH on the computer, `claude` inside `tmux`, and Blink Shell
  or Termius on the phone. Every word still goes through the company's own provider.
- **D — the phone remote without a terminal (new in 0.3.2).** The company starts its own relay
  with one command; each computer pairs with it by a link or QR code; while the person is away,
  every permission question arrives on the phone, end-to-end encrypted and with a push, as an
  **approval card**: the full command word for word, every file it names, and three buttons —
  **Yes**, **No**, **Show the diff**. The same card can go to the company's Telegram, where only
  the people on its allowlist can press the buttons. Claude Code keeps running on the computer, on
  the company's own provider and sign-in, so D works on API keys, Bedrock, Google Cloud, Foundry,
  ZDR and HIPAA. See [Branch D](#branch-d-the-phone-remote-without-a-terminal).

**Channels** (Telegram, Discord, iMessage into the running session) work with a claude.ai
sign-in or a Console API key; on Team and Enterprise an Owner turns them on (Admin settings,
Claude Code, Channels) or IT sets `channelsEnabled` and `allowedChannelPlugins` in managed
settings.

Two habits go with every branch. **Do not approve on the phone what you cannot see**: a
permission question that does not say which file, what changes and whether it can be undone
gets a no, or "wait until I am at the desk" — it is on the card in every language. And **a voice
note from the street goes into a queue, not into action**: something to chase goes to Chasecall,
a long job for tonight goes to Nightcall through the handover folder, a change to code goes to the
company's tracker as a task and reaches the code only with a Yes on its pull request's card, and
with none of those set up it still lands in that folder word for word.

## Branch D: the phone remote without a terminal

```
python3 scripts/relay.py --port 8787 --push https://ntfy.example.com/approvals   # once, on a company server
python3 scripts/remote.py pair --relay https://relay.example.com                  # once per computer: the phone link
python3 scripts/remote.py telegram --token <bot token> --allow <Telegram user id> # the card in Telegram too
python3 scripts/remote.py away        # leaving: questions go to the phone
python3 scripts/remote.py test        # one real card, answered from the phone
python3 scripts/remote.py back        # at the desk: no cards, no push
```

- **The relay** (`scripts/relay.py`) is standard library only: no database, no Redis, no object
  store. It serves the phone page and forwards sealed boxes. Both the computer and the phone connect
  outward to it. Put it behind the company's HTTPS (its reverse proxy, or `tailscale serve 8787`).
- **End-to-end encryption.** The pairing key is 32 random bytes in the phone link after `#`, the
  part a browser never sends to a server. Each card and each answer is sealed encrypt-then-MAC
  (HMAC-SHA256 in counter mode, HMAC-SHA256 tag) by `scripts/seal.py` on the computer and by the
  same construction in WebCrypto on the phone (`scripts/phone/seal.js`). The relay sees a room name
  derived from the key and ciphertext, nothing else.
- **Push.** `--push` points at an ntfy server (the company's own, or ntfy.sh): the ntfy app on the
  phone rings with one line, "A decision is waiting". No command, file or name is in it. At the desk
  (`remote.py back`) no permission question is sent at all; a pull request's card for a task comes
  whenever the pull request is ready, wherever the person is.
- **The approval card** is built by `scripts/approval_card.py` from the question Claude Code is about
  to ask (the plugin's `PermissionRequest` hook, `scripts/approve_hook.py`). A card that had to be
  cut to fit the phone or the message comes without Yes. The first answer from any path decides; no
  answer in ten minutes leaves the question on the screen at the desk.
- **The company's messenger.** With Channels already on (`channelsEnabled`, `allowedChannelPlugins`,
  which `ready` reads), a channel carries the conversation and branch D carries the decisions; with
  a bot of the company's own, `remote.py telegram` puts the card in the chat the team already reads.

## Voice → task → pull request → Yes from the phone

New in 0.3.3. A sentence spoken in the street becomes a ticket in the company's tracker, word for
word; a session makes the change on a branch of its own and opens a pull request; and the phone gets
branch D's approval card for that pull request. Every step lands in the task's journal — who asked,
which session took it, what changed, who said Yes — so a manager reads it in the tracker the team
already uses, on the seats the company already pays for.

```
python3 scripts/task.py setup --github acme/site                    # once: tasks become GitHub issues (gh auth login once)
python3 scripts/task.py setup --webhook https://tracker.example.com/in --repo acme/site --secret <key>   # or another tracker
python3 scripts/task.py setup --routine <the routine's API trigger URL> --routine-token <its token>   # cloud tasks, no terminal
python3 scripts/task.py file "the words, unchanged"                 # a voice note becomes a task
python3 scripts/task.py start 12 --cloud                            # a cloud session takes it: the laptop may sleep
python3 scripts/task.py start 12 --home                             # or a session here, in a git worktree of its own
python3 scripts/task.py card 7                                      # that pull request's card on the phone
python3 scripts/remote.py join --link "<the phone link>"            # on a machine that stays on: the same phone
python3 scripts/task.py watch --start cloud                         # the desk: all of the above by itself
```

- **The voice note.** In a session, the person says it and the `task` skill files their words
  unchanged. On the phone page of branch D, the **New task** box takes the keyboard's microphone; the
  note is sealed with the pairing key like the cards, so the relay forwards a note it cannot read,
  and the task's link comes back to the same box, followed by every step after it — the session that
  took the task, its pull request, the merge, or a session that did not start and is tried again —
  each one ringing the phone. A note already queued in the handover folder or the Chasecall inbox is
  filed with `--from <file>`.
- **The tracker.** GitHub Issues through `gh issue create` under the GitHub CLI's own sign-in, labelled
  `pocketcall`. Any other tracker through a webhook: a JSON POST with the title, the words, who and
  when, signed HMAC-SHA256 in `X-Pocketcall-Signature-256` when a secret is set, with whatever header
  the tracker asks for (`--header "Name: value"`); later steps arrive at the same address as events.
- **The session.** `--cloud` hands the task to a cloud session (branch B) with the words unchanged
  and three rules: a branch of its own from the default branch, only what the words ask, a pull
  request whose description starts with `Closes #12`. It goes one of two ways:
  - **A routine** — the way for a desk, on any system, with no terminal and no Claude Code on that
    machine. Made once at claude.ai/code/routines on the repository, with this saved prompt:
    *Carry out the task in the routine-fire-payload block: Pocketcall filed it in this repository's
    tracker for me. Follow its numbered rules for the branch and the pull request.* Its API trigger's
    URL and token go to `task.py setup --routine <url> --routine-token <token>` (kept in `task.json`,
    readable by this user only; the token starts that routine and reads nothing). Each task is one
    POST to the trigger; the routine clones the default branch and runs on the person's own plan.
  - **`claude --cloud`**, where Claude Code is signed in. Claude Code creates a cloud session only in
    a terminal, so Pocketcall gives it one of its own (a pseudo-terminal), runs it from the desk's own
    copy of the repository on the default branch — never from whatever branch a checkout is on — and
    lets it go once the session's link is printed.

  The task counts as started only with a session link in hand. Without one it stays filed, the desk
  tries again ten and twenty minutes later, and the phone hears each line. `--home` makes a git
  worktree on `pocketcall/12-…` from the checkout given at setup, or from the desk's own copy
  (`~/.pocketcall/repos/<owner>-<name>`, cloned with `gh repo clone`), runs `claude -p` there with
  file edits accepted, then commits, pushes and opens the pull request itself, so it works on any
  provider the company runs. Either way nothing reaches the default branch without a Yes.
- **The card.** Branch D's card, for a pull request: the steps Yes runs, word for word
  (`gh pr review 7 --repo acme/site --approve --body '…' && gh pr merge 7 --repo acme/site --squash --match-head-commit <sha>`),
  every file, the diff behind **Show the diff**, the task's words, **Yes** and **No**; the heading
  names the pull request's author, and says so when it comes from a fork. Yes merges exactly the
  commit the card showed. Where the repository's checks are still running, the Yes is kept and that
  same commit merges, `--match-head-commit` and all, the moment they pass — `task.py card` waits for
  them, and the desk carries every kept Yes. Auto-merge is never turned on, so a commit pushed after
  the card never rides on this Yes: it brings its own card, and failed checks come back to the phone
  as a line. The Yes is also kept in GitHub as an approving review. No leaves a comment and the pull
  request open. A card cut to fit comes without Yes; in Telegram a card longer than one message
  arrives whole, as one file under the same buttons, and so does a long diff.
- **Whose pull request.** The desk links a pull request to a task by itself when it closes the task's
  issue and comes from the task's own branch (`pocketcall/12-…`, or any branch with `pocketcall-12`
  in its name) or from the desk's own GitHub account. A pull request from a fork, or someone else's
  on another branch, reaches the phone only through `task.py card <n>`, its heading naming the author
  and the fork.
- **While the laptop sleeps.** The desk (`task.py watch`) runs on whatever stays on — the machine
  that already runs the relay, joined to the same phone with `remote.py join`. A task filed on the
  laptop reaches it through the relay, sealed like the cards, and a pull request for an issue
  Pocketcall filed anywhere is found through the issue it closes. Several desks on one phone take
  turns: the relay lets one act at a time and hands each note to one desk; when the laptop's desk
  stops, the other takes over within a minute and a half, with the laptop's tasks and the cards
  already on the phone. With `--start cloud` the work runs in Anthropic's cloud; with `--start home`
  on that machine, on the company's own provider (an API key, Bedrock, Google Cloud, Foundry).
  Neither needs the laptop. A cloud session that pushed its branch without opening a pull request
  gets one from the desk.

## The board: every job on one screen, the phone rings when one needs you

Fifteen terminals open and no idea which one waits for you: the board answers that on the computer
and on the phone. The plugin's hooks write each Claude Code session's state by themselves -
**Working** when a message goes in, **Waits for you** on a question or a permission, **Done** when
the turn ends, **Resting on a limit until 18:00** when Claude Code's own limit line ended it. A night
run, a council review or a cron job adds its own line:

```
python3 scripts/board.py show                                   # the waiting job first
python3 scripts/board.py put --name "night run" --where nightcall --state limit --until 03:10
python3 scripts/board.py ring --ntfy https://ntfy.sh/<your topic> --test   # the phone rings
python3 scripts/board.py ring --when always                     # away (default) | always | never
python3 scripts/board.py page --to ~/Google\ Drive/phone        # the board as one phone page
python3 scripts/board.py run --name "shop tests" -- npm test    # any long command: working, then done or stopped
```

The rings go where the phone already is - the Telegram chat set with `remote.py telegram` and the
person's own ntfy topic - once per change of state, one line each: the state, the job, its folder, a
few words of what it said. A permission question that goes to the phone as an approval card does not
ring twice. The page is plain HTML with no script, light and dark, refreshing itself every minute,
rewritten at every change into the Google Drive / iCloud / Dropbox / OneDrive folder the phone
already sees: the board on the phone with no server at all. Any tool can also write its job file
into `~/.pocketcall/board/` itself (the keys are in `scripts/board.py`). Standard library only.

## Continue, Stop and a voice task from the phone

The board's ring for a night run or a long build comes with **Continue** and **Stop** buttons in Telegram; "stop" or
"continue" typed works too. A voice note to the same bot is transcribed on the computer and becomes `TASK.md` in a
new folder of the inbox (with `--start`, it begins at once). The meter of subscriptions ("Claude rests until 21:00
· Codex 72% · Gemini ?", from nightcall's "my subscriptions") shows as bars on the phone page.

```
python3 scripts/steer.py inbox --to ~/Tasks --start 'bash ~/nightcall/scripts/night-loop.sh {folder} 8'
python3 scripts/steer.py listen        # on the computer that stays on
```

## What is true about an evening away

- **The work runs while the computer is awake.** Keep it awake and the evening works. If it
  does sleep, nothing is lost, and the connection comes back by itself the moment it wakes.
- **The phone side is the Code tab in the ordinary assistant app.** Anything in a store under
  the terminal tool's name belongs to someone else.
- **The allowance is on the card in advance.** When it runs out the session simply goes quiet,
  so the card tells you before you leave.
- **One photo proves a folder is syncing.** A drive app can be signed out, paused, out of space
  or stuck on one file while the folder on disk looks the same, so `ready` reports what is
  visible — the folder, the number of files, the date of the last change — and hands you the
  proof: put one photo in from the phone before you leave and watch that date change.
- **Finished work comes back through the handover folder.** The phone sends photos and files
  on its own; the way back is a file in the handover folder, and `leave` has you open one real
  file on the phone before you rely on it.
- **Your sign-in stays yours.** Never sign in to your assistant account inside another
  company's app or site that offers you a remote: a sign-in is for its owner alone (Anthropic's
  Consumer Terms of Service, anthropic.com/legal/consumer-terms, on account credentials). Pocketcall
  never asks for your Claude sign-in: branch D runs on the company's own relay, and tasks reach the
  tracker through the GitHub CLI's own sign-in or the company's webhook.

## What leaves your house, and what does not

While a remote session is connected, the conversation is kept on the provider's servers so
that every screen you own shows the same thing. Your files stay on your machine and the work
happens there. Those are two different things, and the printed card says both.

## Languages

Everything the scripts say to a person lives in `lang/<code>.json`: English, Spanish,
Portuguese, Russian and Ukrainian, with English underneath any word a language is missing. The
language is `--lang`, then `POCKETCALL_LANG`, then the system's. The code and its comments are
English; `python3 scripts/check_language.py` keeps Cyrillic inside `lang/`.

## Tests

`tests/test_remote.py` runs a relay on a local port, a stand-in Telegram, and the phone's sealing
code in Node, and proves a card goes through sealed and comes back as Yes or No. `tests/test_board.py` walks a session through
the board's states with a stand-in Telegram and ntfy; `tests/test_steer.py` presses Continue and Stop, types "stop" and sends a voice note to a stand-in Telegram. `tests/test_task.py`
runs the whole way from a voice note to a merge with a stand-in GitHub CLI and a stand-in Claude Code
that, like the real one, creates a cloud session only in a terminal, a routine's API trigger, a webhook
server, a bare repository as the far side of git, the relay, and two computers on one phone.

```
python3 -m pytest -q -p no:cacheprovider tests
python3 scripts/check_language.py
```

The tests run the checks against temporary directories, recorded settings files and a stand-in
folder for the organization's managed settings. They run with no subscription, no network and
no phone. `tests/mutate_code.py` (run by the tests too) breaks each promise in a copy — the API-key
sentence in English and Russian, the rule about approving from the phone, the Trusted Devices
logic, the administrator's switch, the merge pinned to the commit the card showed, the words filed
unchanged — and expects red, with one control that stays green.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
