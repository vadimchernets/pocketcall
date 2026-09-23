# Security

Pocketcall asks for no account, no password, no token and no API key, and it never will.
It makes no network requests. Its two scripts read local files and run `claude --version`
and, on macOS, `pmset -g custom`.

## What it deliberately does not do

- It does not turn the remote on. That is one command the person types knowingly.
- It does not change power settings, permission modes or any other system setting.
- It does not read, copy or send any conversation, file or credential.
- It does not offer, bundle or recommend any third-party remote. Signing in to your
  assistant account inside another company's product, or handing it a session token, is
  against the terms of the service you pay for. Pocketcall says so in its card.

## What it reports about your machine

`scripts/check.py` prints, to your screen, the names of environment variables and settings
files it found on this machine, and a work folder path. With `--json` the same goes to
standard output. Nothing is written anywhere else and nothing is transmitted. If you paste
that output into an issue, look at the paths first.

## Reporting a problem

Open an issue at https://github.com/vadimchernets/pocketcall/issues. If the problem involves
something you would rather not publish, say so in the issue without the detail and ask for a
private channel.
