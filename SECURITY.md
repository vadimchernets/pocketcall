# Security

## Reporting a vulnerability

Open an issue at https://github.com/vadimchernets/pocketcall/issues. For a detail that should not
be public, write "security" in the title without the detail, and a private channel follows.

## What Pocketcall touches

It never asks for a Claude sign-in or an Anthropic API key.

- `scripts/check.py` and `scripts/card.py` read local files and run `claude --version` and, on
  macOS, `pmset -g custom`; they make no network requests. `scripts/check.py` prints to your screen
  the names of environment variables and settings files it found and a work folder path; with
  `--json` the same goes to standard output, and nothing goes anywhere else.
- Branch D (`scripts/relay.py`, `scripts/remote.py`, `scripts/approve_hook.py`) talks only to the
  company's own relay, which forwards boxes sealed with the pairing key and cannot open them, to the
  ntfy server the company names for the push (one line, no command, file or name), and to the
  company's Telegram bot when one is set. Its settings are in `~/.pocketcall/remote.json`, readable
  by this user only.
- Tasks (`scripts/task.py`) reach the company's tracker through the GitHub CLI and its own sign-in,
  or through the company's webhook address (signed HMAC-SHA256 when a secret is set); they start
  sessions through Claude Code and its own sign-in, or through the API trigger of a routine the
  person made at claude.ai/code/routines (one POST to api.anthropic.com with that routine's token,
  which starts that routine and reads nothing), and push a task's branch with git. A task travels
  between the person's computers through the relay, sealed with the pairing key like the cards. Its
  settings, the routine's token included, are in `~/.pocketcall/task.json`, its record in
  `~/.pocketcall/tasks.json` and its own copy of the repository in `~/.pocketcall/repos`, readable
  by this user only. A computer joined with `remote.py join` holds the pairing key, as the first
  computer does; the relay process itself never does.
