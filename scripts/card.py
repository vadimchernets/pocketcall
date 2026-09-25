#!/usr/bin/env python3
"""Write the card a person takes with them.

Everything a phone can and cannot do, on one page, in words that survive being read in a
corridor. It is written to a file and printed to the screen, because the whole point of this
plugin is that a screen you are not sitting in front of is no use.

The card is deliberately short and deliberately negative in places. A person who knows the
four things that do not work will not lose an afternoon to any of them.

Run:  python3 card.py [--dir <project directory>] [--out <file>] [--shared <shared folder>]
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

EN = """POCKETCALL — the card
Written {date}. Keep it where you can see it, not where you file it.

WHAT THE PHONE CAN DO while the work runs on your computer
  See the same conversation, as it happens.
  Send a new task, and it starts now.
  Answer the question it asks you.
  Say yes or no when it asks permission.
  Send a photo or a file from the phone, with or without a note.

WHAT THE PHONE CANNOT DO
  It cannot wake your computer. A sleeping machine does no work at all.
  It cannot hand you a finished document. That is why everything finished goes into
  {out}/ as a file, and you open the file with your normal phone app.
  It cannot turn on the modes that act without asking. Those stay at your desk on purpose.
  It cannot tell you that your allowance ran out. It will simply go quiet.
  It cannot tell you that the shared folder stopped syncing either. The photo you send
  simply sits on the phone, looking sent.

THIRTY SECONDS AT THE DOOR — say these five out loud, every time you go
  1. Plugged in. A battery that runs out is a computer switched off, and from town you
     cannot plug it back in.
  2. Lid open, sleep set to never. A closed lid is sleep, and sleep is a stop.
  3. The window with the work in it stays open. Close it and the phone goes dark in seconds.
  4. The shared folder is there: {shared}
     That is where a photo you take in town lands, and where finished work comes back.
     This computer worked that path out by itself. If it is not the folder you use, cross
     it out and write yours in with a pen — the card is yours, not the computer's.
  5. Phone in your hand before the door, not after it: signed in as you, notifications
     allowed, one message sent from where you are standing and one answer back.
  If all five are true, the evening works. Saying them out loud is the point: a person who
  says "plugged in" looks at the cable, and a person who reads it does not.

IF THE PHONE GOES QUIET
  It is one of four things, in this order of likelihood:
  the computer went to sleep · the window was closed · the allowance ran out ·
  the phone silenced the notification (focus mode, battery saver).
  None of them is a fault of yours, and none of them loses your work.

ONE RULE THAT IS NOT ABOUT CONVENIENCE
  Never sign in to your Claude account inside some other company's app or site that
  offers you a remote. Handing over your sign-in is against the terms, and the ones that
  ask for it are the ones you should walk away from. The remote you are using is the one
  that came with what you already pay for.

WHAT IS STORED WHERE, SO YOU ARE NOT SURPRISED
  While the remote is on, the conversation is kept on the company's servers so that all
  your screens can show the same thing. Your files stay on your computer, and the work is
  done there. Those are two different things, and only the first one leaves the house.
"""


def build(out_dir: str, today: str, shared: str = "") -> str:
    return EN.format(date=today, out=out_dir,
                     shared=shared or "the one your drive syncs and your phone can open")


def detect_shared(project: str) -> str:
    """Ask the readiness check where the shared folder is, so the card names a real path.

    A person reading "your shared folder" does not know which one is meant. If the check
    cannot find it either, the card says so in words instead of naming the wrong thing.
    """
    try:
        import check
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
    args = ap.parse_args()

    today = args.date or dt.date.today().strftime("%d.%m.%Y")
    text = build(args.out_dir, today, args.shared or detect_shared(args.dir))
    target = Path(args.out) if args.out else Path(args.dir) / "POCKETCALL-CARD.txt"
    target.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {target}. Print it. A card on the wall beats a file you will not open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
