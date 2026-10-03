# Security

## Reporting a vulnerability

Open an issue at https://github.com/vadimchernets/pocketcall/issues. For a detail that should not
be public, write "security" in the title without the detail, and a private channel follows.

## What Pocketcall touches

It asks for no account, password, token or API key and makes no network requests. Its two scripts
read local files and run `claude --version` and, on macOS, `pmset -g custom`. `scripts/check.py`
prints to your screen the names of environment variables and settings files it found and a work
folder path; with `--json` the same goes to standard output, and nothing goes anywhere else.
