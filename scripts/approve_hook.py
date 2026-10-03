#!/usr/bin/env python3
"""PermissionRequest hook: while the person is away, the question goes to the phone.

Claude Code runs this when it is about to ask for permission. Paired (scripts/remote.py) and marked
away, it sends the approval card to the relay and the messenger and waits for the first answer:
Yes allows, No denies, and no answer in time leaves the question on the screen at the desk, as it
would have been. At the desk (`remote.py back`) or not paired, it prints nothing and the ordinary
dialog appears - no card, no push.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import approval_card  # noqa: E402
import check  # noqa: E402
import remote  # noqa: E402


def decide(hook: dict, cfg: dict, words: dict) -> dict | None:
    if not cfg.get("away") or not remote.channels(cfg, words):
        return None
    card = approval_card.build(hook, uuid.uuid4().hex)
    say = remote.ask(card, cfg, words, float(cfg.get("wait", 600)))
    if say is None:
        return None
    decision = {"behavior": "allow"} if say == "yes" else {"behavior": "deny", "message": words["approve_denied"]}
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}


def main() -> int:
    try:
        hook = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    cfg = remote.load()
    words = check.lang_words(check.pick_lang(cfg.get("lang")))
    out = decide(hook, cfg, words)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
