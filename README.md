# Pocketcall

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23107735.svg)](https://doi.org/10.5281/zenodo.23107735)

**Leave the computer working, take the phone, and do not find out in town that it never
started.** Pocketcall does not connect your phone to anything. The remote already exists and
comes with the subscription you already pay for. What Pocketcall adds is the part nobody
ships: the seven things that silently decide whether an unattended machine works at all, the
four minutes at the door and the thirty seconds you repeat every time after, and the
discipline of answering someone who is reading four lines on a phone in a corridor.

Pocketcall is an independent open-source project. Not affiliated with Anthropic.

**Status: v0.3.** Written for people who are not programmers — a lawyer, a nurse, a pastor, a
teacher, a realtor, a bookkeeper — with a paid personal subscription, no API keys, no server, and
no intention of acquiring either; and, since 0.3, for the same people on a work account, where
the company decides what is allowed (see [At work](#at-work-three-branches)). It speaks English,
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

Both scripts are standard library only, read-only, and talk to nothing over the network.

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

## At work: three branches

On a Team or Enterprise plan, or wherever a company decides how Claude Code is reached, `ready`
reads the check and walks the person down one of three branches. Every command is from Claude
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
  repository instead. An Owner turns cloud sessions on at the same admin page.
- **C — the company is on Bedrock, Google Cloud, Foundry, a gateway, ZDR or HIPAA.** Neither the
  remote nor cloud sessions are offered there, so the phone becomes a terminal into the person's
  own computer: Tailscale on both, SSH on the computer, `claude` inside `tmux`, and Blink Shell
  or Termius on the phone. Every word still goes through the company's own provider.

**Channels** (Telegram, Discord, iMessage into the running session) work with a claude.ai
sign-in or a Console API key; on Team and Enterprise an Owner turns them on (Admin settings,
Claude Code, Channels) or IT sets `channelsEnabled` and `allowedChannelPlugins` in managed
settings.

Two habits go with every branch. **Do not approve on the phone what you cannot see**: a
permission question that does not say which file, what changes and whether it can be undone
gets a no, or "wait until I am at the desk" — it is on the card in every language. And **a voice
note from the street goes into a queue, not into action**: something to chase goes to Chasecall,
a long job for tonight goes to Nightcall through the handover folder, and with neither installed
it still lands in that folder word for word.

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
  company's app or site that offers you a remote: handing over a sign-in or a session token is
  against the terms of the service you pay for. Pocketcall asks for no account, no token and no
  sign-in.

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

```
python3 -m pytest -q -p no:cacheprovider tests
python3 scripts/check_language.py
```

The tests run the checks against temporary directories, recorded settings files and a stand-in
folder for the organization's managed settings. They run with no subscription, no network and
no phone. `tests/mutate_code.py` (run by the tests too) breaks each promise in a copy — the API-key
sentence in English and Russian, the rule about approving from the phone, the Trusted Devices
logic, the administrator's switch — and expects red, with one control that stays green.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
