#!/usr/bin/env python3
"""Write the card a person takes with them.

Everything a phone can and cannot do, on one page, in words that survive being read in a
corridor. It is written to a file and printed to the screen, because the whole point of this
plugin is that a screen you are not sitting in front of is no use.

The card is deliberately short and deliberately negative in places. A person who knows the
four things that do not work will not lose an afternoon to any of them.

Run:  python3 card.py [--dir <project directory>] [--out <file>] [--shared <shared folder>]
                      [--lang xx]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check  # noqa: E402  (same folder; the words live in lang/<code>.json)


def build(out_dir: str, today: str, shared: str = "", words: dict | None = None) -> str:
    """The card in the person's language; English when no words are given."""
    words = words or check.lang_words("en")
    english = check.lang_words("en")
    lines = words.get("card") or english["card"]
    unknown = words.get("card_shared_unknown") or english["card_shared_unknown"]
    return "\n".join(lines).format(date=today, out=out_dir, shared=shared or unknown)


def detect_shared(project: str) -> str:
    """Ask the readiness check where the shared folder is, so the card names a real path.

    A person reading "your shared folder" does not know which one is meant. If the check
    cannot find it either, the card says so in words instead of naming the wrong thing.
    """
    try:
        folder, _ = check.find_shared(Path(project))
    except (ImportError, OSError, ValueError):
        return ""
    return str(folder) if folder and folder.is_dir() else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Write the card to carry.")
    ap.add_argument("--dir", default=".", help="the project directory")
    ap.add_argument("--out", default="", help="where to write the card")
    ap.add_argument("--out-dir", default="pocket-out", help="name of the handover folder")
    ap.add_argument("--shared", default="", help="the folder the phone also sees")
    ap.add_argument("--date", default="", help="date to stamp on the card")
    ap.add_argument("--lang", default=None, help="en, es, pt, ru or uk (default: the system's)")
    args = ap.parse_args()

    words = check.lang_words(check.pick_lang(args.lang))
    today = args.date or dt.date.today().strftime("%d.%m.%Y")
    text = build(args.out_dir, today, args.shared or detect_shared(args.dir), words)
    target = Path(args.out) if args.out else Path(args.dir) / words["card_file"]
    target.write_text(text, encoding="utf-8")
    print(text)
    print(words["card_saved"].format(path=target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
