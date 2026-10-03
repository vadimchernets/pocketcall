# Changelog

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
