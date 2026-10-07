# Changelog

## 0.5.0 — 2026-10-07

- **Steer long work from the phone.** New `scripts/steer.py`: a board ring for a job with a task folder carries
  Continue and Stop buttons in Telegram; Stop leaves a STOP file (the night loop ends after the current step), Continue
  removes it and starts an ended job again with its own command. "stop" / "continue" typed in five languages, with part
  of the name when several jobs run. Only the allowlist of `remote.py telegram` steers.
- **Voice task.** A voice note to the bot is transcribed on the computer (POCKETCALL_TRANSCRIBE, mlx-whisper, whisper,
  whisper.cpp, or the person's own OpenAI / Groq key) and becomes `TASK.md` in a new inbox folder; `task: ...` typed
  too; `steer.py inbox --start` begins it at once. With no transcriber the audio is kept and the phone is told how.
- The board: `put --folder --resume --meter --say`; the meter of subscriptions as bars on the phone page; a change of
  hands rings with `--say`. `remote.py`'s approval wait now also takes messages and keeps them for `steer.py`, so a voice
  note sent while a card waits is not lost. Tests: `tests/test_steer.py` (16).
- The board, the leftovers of 0.4.0's critic: the `StopFailure` hook (Claude Code's event for a turn ended by an API
  error, listed in the hooks reference) - a spent limit shows "resting until" with its hour, any other error shows
  "stopped" instead of "working" until the next prompt; and one lock per job around the read-compare-write, so two hooks
  of one session at the same moment ring once.

## 0.4.0 — 2026-10-07

- **The board: every job on one screen, the phone rings when one needs you.** New `scripts/board.py` and skill
  `board`. Five new hooks (UserPromptSubmit, Notification, PostToolUse, Stop, SessionEnd) write each Claude Code session's state
  to `~/.pocketcall/board/`: working (again as soon as an answered question lets a tool run), waits for you, done, or resting on a limit with the hour it goes on, read from
  Claude Code's own limit line at the end of the transcript (a model's long answer about limits stays "done"). A
  night run, a council review or a cron job adds its line with `board.py put`, or writes the job file itself.
  `board.py run --name <job> -- <command>` puts any long command on the board - working while it runs, done or
  stopped with its last line and exit code when it ends (a diffcall fix with `--wait`, a test suite, a deploy).
- **Rings on what changed**: once per change into waits / done / limit / stopped, one line to the Telegram chat of
  `remote.py telegram` and to the person's own ntfy topic (`board.py ring --ntfy <url>`); `--when away` (the
  default) rings while `remote.py away` says the person is out, `always` at the desk too, `never` keeps only the
  board. A permission question that already goes to the phone as an approval card does not ring twice.
  `put --ring` rings at the desk too (a night run). A hook's ring goes from a process of its own, so a session never
  waits for the network; a limit is read only from Claude Code's own error line, never from a model's words.
- **The board on the phone with no server**: `board.py page --to <shared folder>` writes `pocketcall-board.html`
  (plain HTML, no script, light and dark, refreshing every minute) into the folder the phone already sees, and
  rewrites it at every change. In all five languages. `tests/test_board.py`.

## 0.3.3 — 2026-10-03

- **Voice → task → pull request → Yes from the phone.** New `scripts/task.py` and skill `task`. A voice note
  becomes a task in the company's tracker, word for word: GitHub Issues through `gh issue create` (labelled
  `pocketcall`; the label is made once when the repository lacks it), or any other tracker through a webhook - a
  JSON POST with the title, the words, who and when, signed HMAC-SHA256 in `X-Pocketcall-Signature-256` when a
  secret is set, with the headers the tracker asks for. The note comes from a session (`task.py file`, the words on
  standard input), from a queued file (`--from`), or from the phone page of branch D, whose new **New task** box
  seals it with the pairing key: the relay forwards a note it cannot read, and the task's link comes back sealed.
- **A session picks the task up.** `task.py start <task> --cloud` hands it to a cloud session with the words
  unchanged and the rules of its pull request (a branch of its own from the default branch, `Closes #<n>` first);
  the laptop may sleep from there. The way in for a desk is a routine's API trigger
  (`task.py setup --routine <url> --routine-token <token>`): one POST per task, no terminal and no Claude Code on
  that machine, the default branch cloned, the person's own plan. Without a routine, `claude --cloud` runs in a
  pseudo-terminal of its own - Claude Code creates a cloud session only in a terminal - from the desk's own copy
  of the repository on the default branch. A task counts as started only with the session's link in hand;
  otherwise it stays filed and the desk tries again. `--home` makes a git worktree on `pocketcall/<n>-…` from the
  checkout given at setup or from the desk's own copy (`~/.pocketcall/repos`, `gh repo clone`), runs `claude -p` in
  it, then commits, pushes and opens the pull request itself - on any provider the company runs. Each step goes
  into the task's journal (a comment on the issue, or an event to the webhook) and back to the phone.
- **The pull request's approval card**, branch D's card reused: the steps Yes runs, word for word
  (`gh pr review <n> … --approve && gh pr merge <n> … --squash --match-head-commit <sha>`), every file, the diff
  behind Show the diff, the task's words, Yes / No, and a heading that names the author and a fork. Yes merges
  exactly the commit the card showed. Where the repository's checks are still running, the Yes is kept and that same
  commit merges when they pass (`task.py card` waits for them, the desk carries every kept Yes); auto-merge is never turned on, so a commit pushed after the card brings its
  own card and never rides on the Yes, and failed checks come back as a line. No leaves a comment and the pull
  request open. A card cut to fit comes without Yes. A pull request from a fork, or someone else's off the task's
  branch, is never linked by itself: `task.py card <pull request>` sends one by hand.
- **The desk: `task.py watch`.** Notes from the phone become tasks, new tasks get a session (`--start cloud` or
  `--start home`), every pull request for a task gets its card once per commit, the answers are carried out, a
  branch a cloud session pushed without a pull request gets one, a card lost with a restarted relay is sent again,
  and each step of a task comes back to the phone under its note, ringing it. On the machine that already runs the
  relay - joined to the phone with the new `remote.py join --link <the phone link>` - it keeps all of it going while
  the laptop sleeps: a task filed on the laptop reaches it through the relay, sealed, and a pull request for an
  issue Pocketcall filed anywhere is found through the issue it closes. Desks on one phone take turns through a
  lease on the relay, and each note goes to one desk at a time and is filed once.
- Telegram: several cards can wait at once, and a press for a card another pocketcall process on the same computer
  waits for is put aside for it, so the hook and the desk never take each other's answers. A card longer than one
  message arrives whole as one file under the same buttons, Yes included, and so does a long diff.
- The relay carries notes, receipts and tasks (`/r/<room>/note`, `/notes`, `/receipt`, `/task`, `/tasks`), sealed
  like the cards, and the desk lease (`/desk`). The list the phone polls carries card ids only; each card's box is
  fetched once (`/ask?id=`).
- README and `SECURITY.md` say what each script talks to now that tasks reach the tracker; the push line says
  that at the desk no permission question is sent, and that a pull request's card comes when it is ready.
- `tests/test_task.py`: a stand-in GitHub CLI and a stand-in Claude Code that, like the real one, creates a cloud
  session only in a terminal, a routine's API trigger, a webhook server, a bare repository as the far side of git,
  a stand-in Telegram that answers 429 to a flood, the relay, and two computers on one phone. Eleven new mutations -
  the merge pinned to the card's commit, no Yes on a card cut to fit, the words filed unchanged, a held Yes never
  merging a newer commit, no start without a session link, one desk at a time, no fork linked by itself, a task's
  news reaching the phone, ids only in the polled list, one note to one desk, Yes on a long Telegram card - each
  expected red.

## 0.3.2 — 2026-10-03

- **Branch D: the phone remote without a terminal.** `scripts/relay.py` is the company's own relay, started
  with one command (standard library only: no database, Redis or object store); it serves the phone page and
  forwards sealed boxes it cannot open. `scripts/remote.py pair --relay <url>` prints the phone link (a QR code
  with `qrencode`), its key after `#`, which a browser never sends. Cards and answers are sealed encrypt-then-MAC
  (HMAC-SHA256 counter mode and tag) by `scripts/seal.py` and by the same construction in WebCrypto on the phone
  (`scripts/phone/seal.js`). `--push` rings an ntfy app with "A decision is waiting" and nothing else; at the desk
  (`remote.py back`) nothing is sent. Claude Code stays on the computer, on the company's provider and sign-in,
  so D works on API keys, Bedrock, Google Cloud, Foundry, ZDR and HIPAA. New skill `remote`; `ready` names D.
- **The approval card.** The plugin's first hook, `PermissionRequest` (`scripts/approve_hook.py`, through the
  step 0 guard), sends the question Claude Code is about to ask, while the person is away, as a card
  (`scripts/approval_card.py`): the full command word for word, every file it names, and Yes / No / Show the
  diff. The same card goes to the company's Telegram (`remote.py telegram --token ... --allow <id>`), where a
  press from anyone off the allowlist is ignored. A card cut to fit the screen or the message comes without Yes,
  and a Yes to it counts as No. The first answer decides; none in ten minutes leaves the question at the desk.
  Card words in all five languages.
- README: the account-sharing line now names its source (Anthropic's Consumer Terms of Service).
- `tests/test_remote.py`: a relay on a local port, a stand-in Telegram, the phone's sealing code in Node.

## 0.3.1 — 2026-10-03

- **Wording: no disclaimers.** Pocketcall says what works as a capability. The card's "what the phone cannot
  do" is now "five things that keep the evening alive"; the report closes with what the person looks at
  themselves (one test photo for the shared folder) instead of what the check cannot see; the README's "what it
  refuses to pretend" is "what is true about an evening away"; the sleep and sync lines say what to do; the
  launcher's no-Python line says Pocketcall starts the moment Python 3 is there. All five languages.
  `SECURITY.md` is the reporting route and what the scripts touch. New `tests/test_no_disclaimers.py` keeps
  stop phrases (own risk, not legal advice, for now, unfortunately, honestly, sorry and their Russian and
  Ukrainian twins) out of every text a person or the model reads.

## 0.3.0 — 2026-10-03

- **At work: three branches** in `ready`, followed by `leave`. A — the computer stays on: the built-in
  remote, which an Owner turns on at claude.ai/admin-settings/claude-code; Trusted Devices (enrolled at sign-in,
  set by an Owner at claude.ai/admin-settings/capabilities); `claude remote-control --spawn worktree`; `tmux` on a
  machine reached over SSH. B — the laptop sleeps: `claude --cloud "..."`, `claude --teleport <session-id>` back
  at the desk, `CCR_FORCE_BUNDLE=1` without GitHub, `claude -p "..." --cloud <session-id>` for one more message.
  C — Bedrock, Google Cloud, Foundry, a gateway, ZDR or HIPAA, where neither is offered: SSH and `tmux` over
  Tailscale, with Blink Shell or Termius on the phone. Every command checked against code.claude.com/docs
  (remote-control, claude-code-on-the-web, channels, managed-settings, env-vars) on 03.10.2026.
- **Channels** in `ready`: what they are, that they work with a claude.ai sign-in or a Console API key, and that
  on Team and Enterprise an Owner (Admin settings, Claude Code, Channels) or IT (`channelsEnabled`,
  `allowedChannelPlugins` in managed settings) turns them on. `check.py` reads what the managed settings on this
  computer say about them.
- `check.py`: with `ANTHROPIC_API_KEY` (or `ANTHROPIC_AUTH_TOKEN`, or an `apiKeyHelper`) it says in so many words
  that the remote will not work while it is set, and points a company that hands out only keys at branch C or a
  channel. It now finds these in settings files too, not only in the terminal. `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`
  and `DISABLE_GROWTHBOOK` always count as switching the remote off; `DISABLE_TELEMETRY` and `DO_NOT_TRACK` only
  with `--trusted-devices` or on a Claude Code older than 2.1.283 (or of unknown version), as the documentation
  says. `CLAUDE_CODE_USE_FOUNDRY` joins Bedrock and Vertex. The organization's managed settings
  (`managed-settings.json` and `managed-settings.d/`) are read too: their `env`, and `disableRemoteControl` set by IT.
- **Do not approve on the phone what you cannot see**: a rule with its own heading in `leave`, Claude's side of it
  in `handover`, and a section of its own on the card.
- **A voice note into the queue**, in `leave`: dictated into the remote, it is queued, not acted on; something to
  chase goes to Chasecall (`/chasecall:take`, or the Chasecall inbox folder), a long job for tonight goes to
  Nightcall (`for-tonight-<date>.md` in the handover folder, then `/nightcall:start`), and with neither installed
  it still lands in the handover folder word for word.
- **Five languages**: every word `check.py` and `card.py` say lives in `lang/en.json`, `es.json`, `pt.json`,
  `ru.json`, `uk.json`, English underneath anything missing; `--lang`, then `POCKETCALL_LANG`, then the system's.
  The skills run both scripts in the person's language.
- New `scripts/check_language.py` (Cyrillic only in language places, as in the other plugins) and
  `tests/mutate_code.py`: eleven mutations, among them the API-key sentence removed in English and in Russian and
  the rule removed from `leave` and from the card, each expected red, plus a control expected green; the tests run it.
