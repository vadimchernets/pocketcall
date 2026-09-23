---
name: leave
description: Walk the person through the four minutes before they go out of the door, ending with one real message answered from the phone. Use when they are about to leave and want the work to keep going, or the first time they try the remote.
---

# Before you walk out of the door

Four minutes, six steps, and the last one is the only proof that counts: a message sent from
the phone in the next room and answered here. Everything before it is preparation; without it
the person finds out in town.

Go one step at a time and wait for the person after each.

## The six steps

1. **Readiness.** Run the `ready` skill first if it has not run in this session. If anything
   comes back NOT, deal with it now, not later.

2. **The phone has the app and the same account.** Ask. If they do not have it, tell them to
   run `/mobile`, which shows a code that opens the right store for their phone. Say the
   thing that saves an argument: there is no separate "Claude Code" app. It is the **Code**
   tab inside the ordinary Claude app. Anything in a store by that name is somebody else's.

3. **Notifications.** On the phone, allow notifications for the app. Then here, run `/config`
   and turn on both of these: **Push when Claude decides** and **Push when actions required**.
   Tell them what each means in one line: the first is "I have finished", the second is
   "I need you to answer before I can go on". Without the second one they will stand in a
   queue while the work waits at home.

4. **Turn the remote on.** Have the person type `/remote-control` here. The first time, a
   dialog asks to enable it; they choose **Enable Remote Control**. Say that this carries the
   conversation you are having now — it is not a new chat.

5. **Join from the phone.** They scan the code shown, or open the **Code** tab and pick the
   session by name. Wait until they say they can see this conversation on the phone. Do not
   go on until they have seen it with their own eyes.

6. **The proof.** Ask them to walk to another room, and from there send one real message
   about their actual work. Answer it. Then ask them a question back, so that they answer
   from the phone once. Then finish something small and put it in the handover folder, and
   have them open that file on the phone. If all three happened, the evening works.

## Then give them the card

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/card.py" --dir .`, show the card, and tell them
to print it. The four reasons the phone goes quiet are on it, and a person who knows those
four does not panic in a corridor.

## What you must not say

- Not "close the lid and go" — a closed lid is sleep, and sleep is a stop.
- Not "it will tell you when the allowance runs out" — when it runs out, nothing can speak.
- Not "you will be able to download the finished document to your phone" — what is promised
  is sending files **from** the phone. Getting work back is the handover folder, which is why
  step 6 makes them open one.
- Not "you are in control of everything from there" — the modes that act without asking
  cannot be switched on from the phone at all. That is a protection, and it is worth saying
  out loud as one.
