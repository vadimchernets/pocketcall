---
name: ready
description: Check whether this machine can be left working while its owner walks away, and say in plain words what is not ready. Use when the person asks to work from their phone, to leave the computer running, to check the remote, or says they are about to go out.
---

# Is this machine ready to be left alone?

Run the check, read it out loud, fix what the person agrees to fix. Do not turn the remote on
inside this skill: that is the next step and the person does it knowingly.

## Do this

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check.py" --dir .` and show the person the
   lines that came back, unchanged. Do not summarise away a failure.
2. For each line marked NOT, offer to do the part you can do, one at a time, and wait:
   - the handover folder: make it, and say where it is;
   - the handover rule: show the two lines before you write them into CLAUDE.md;
   - the sleep setting: you cannot change it and must not try. Tell the person which
     setting and let them open it themselves. Then run the check again and read the result.
3. If the version or one of the quiet killers came back NOT, stop. There is no point
   continuing: the remote will not come up, and it will not say why.
4. When everything is ok, say the one sentence that matters and then stop:
   "The machine is ready. Turning the remote on is `/remote-control`, and it will show a
   code for your phone to scan."

## What you must not do

- Do not claim the remote is on. This skill checks; it does not connect.
- Do not read or change power settings for the person on any system. Name the setting, let
  them look at it. A person who has changed it once will change it again without you.
- Do not promise that work continues while the machine sleeps. It does not. Say instead what
  is true: nothing is lost, the connection comes back by itself when the machine wakes, and
  the time in between is gone.
- Do not offer any third-party remote, and if the person mentions one that asks them to sign
  in to their Claude account inside it, say plainly that handing a sign-in to another company
  is against the terms and that they should not.
