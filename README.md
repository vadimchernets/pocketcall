# Pocketcall

**Leave the computer working, take the phone, and do not find out in town that it never
started.** Pocketcall does not connect your phone to anything. The remote already exists and
comes with the subscription you already pay for. What Pocketcall adds is the part nobody
ships: the six things that silently decide whether an unattended machine works at all, the
four minutes at the door, and the discipline of answering someone who is reading four lines
on a phone in a corridor.

Pocketcall is an independent open-source project. Not affiliated with Anthropic.

**Status: v0.1.** Written for people who are not programmers — a lawyer, a nurse, a pastor, a
teacher, a realtor, a bookkeeper — and who have a paid personal subscription, no API keys, no
server, and no intention of acquiring either.

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
- the person approves something in a corridor that they could not actually see.

None of those is hard. All of them are invisible. Pocketcall makes them visible before you
leave, not after.

## Install

```
/plugin marketplace add vadimchernets/pocketcall
/plugin install pocketcall@pocketcall
```

## What you get

| what | when you use it |
|---|---|
| `ready` | before leaving: checks the six silent things and says, in plain words, which are not ready |
| `leave` | the first time, and any time it matters: six steps ending with one real message answered from the phone |
| `handover` | standing guidance for the whole time you are away: short answers, finished work in a file |

You can also run the check by hand, without the plugin:

```
python3 scripts/check.py            # a report for a person
python3 scripts/check.py --json     # the same findings for a program
python3 scripts/card.py             # the card to print and keep where you can see it
```

Both scripts are standard library only, read-only, and talk to nothing over the network.

## The six things `ready` looks at

1. **Where you are.** A remote session has to start from a work folder. The trust question it
   needs is never remembered for your home folder.
2. **How old the program is.** Too old, and the rest of this is moot.
3. **The quiet killers.** Four environment variables each switch off the feature evaluation
   the remote depends on; a custom API address, an API key, or another company's cloud each
   make it unavailable. Set in a shell profile or in the `env` block of a settings file, they
   produce no error at all. `ready` names the exact file it found each one in.
4. **A written-down refusal.** Someone may have turned the remote off in a settings file.
   Including you, a year ago.
5. **Sleep.** On a Mac, `ready` reads the actual setting and tells you the number of minutes.
   Elsewhere it names the setting and asks you to look, because changing a person's power
   settings for them is not something a program should do.
6. **The handover.** Is there a folder your phone can see, and does your rules file say that
   finished work goes there?

## What it refuses to pretend

- **A sleeping computer does no work.** Not less work: none. What is true and worth knowing
  is the rest of it: nothing is lost, and the connection comes back by itself when the
  machine wakes. The hours do not come back.
- **There is no separate mobile app for the terminal tool.** It is a tab inside the ordinary
  assistant app. Anything in a store under the other name belongs to someone else.
- **You cannot be told that your allowance ran out.** At the moment it runs out, nothing can
  speak. So the card says it in advance instead.
- **Getting finished work back to the phone is not promised by anything.** Sending a photo or
  a file *from* the phone is. That asymmetry is exactly why the handover folder exists, and
  why `leave` makes you open one real file on the phone before you trust the arrangement.
- **Never sign in to your assistant account inside another company's app or site that offers
  you a remote.** Handing over a sign-in or a session token is against the terms of the
  service you pay for, and the products that ask for it are the ones to walk away from. A
  good number of them stopped existing during 2026; one of them deprecated itself in favour
  of the built-in remote. Pocketcall asks for no account, no token, and no sign-in, and never
  will.

## What leaves your house, and what does not

While a remote session is connected, the conversation is kept on the provider's servers so
that every screen you own shows the same thing. Your files stay on your machine and the work
happens there. Those are two different things, and a person is owed both halves of that
sentence before they turn anything on. Pocketcall states it on the printed card for that
reason.

## Tests

```
python3 -m unittest discover -s tests -v
```

The tests run the checks against temporary directories and recorded settings files. They do
not need a subscription, a network, or a phone.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
