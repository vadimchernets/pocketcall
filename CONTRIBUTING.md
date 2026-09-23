# Contributing

Pocketcall is written for people who are not programmers and who will read it once, in a
hurry, on a bad day. That shapes what a good change looks like here.

## What a good change looks like

- **It removes a silent failure.** The whole point of `ready` is that the things it checks
  fail without saying anything. A new check earns its place by naming a failure that a person
  would otherwise discover in town.
- **It says the true thing, including the unwelcome half.** "A sleeping computer does no
  work" belongs in this project. "It works even when your laptop is closed" does not, no
  matter how much nicer it reads.
- **It is plain.** Short sentences. No product names where a mechanism will do. No jargon
  that a nurse would have to look up.
- **It is tested.** Run `python3 -m unittest discover -s tests`. A change to `check.py` comes
  with a test that fails without it.

## What will not be merged

- A bridge, a tunnel, a bot, or anything that asks a person to sign in to their assistant
  account inside something else.
- A dependency. The scripts are standard library only, and that is a feature: they have to
  run on a machine whose owner cannot install anything.
- A claim about what a vendor's product does, unless the pull request quotes the official
  documentation and gives the date it was read. Vendors change these pages often; an
  undated claim rots silently, which is the exact failure mode this project exists to fight.

## Style

Comments explain why, not what. Test names are sentences. Anything shown to a person is
written to be read out loud.
