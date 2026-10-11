# ⌘Z takes back the last change on the board

Today a goal ticked by mistake, a wrong drop or a deleted goal can only be put back by hand: ⌘Z works inside a goal's notes and nowhere else.

## Behaviour

- ⌘Z undoes the last change on the board and ⇧⌘Z redoes it, back through everything done since the app opened. Inside a text field ⌘Z stays the field's own.
- Every change made on the board counts: ticking, moves (a drag, Tomorrow, Next week, a date, into a goal, to the Inbox), delete, repeat, a renamed title once saved.
- The agent's changes undo the same way, and all the writes of one answer are one step.
- A change you can see is undone in place, its own movement played backwards, with no message.
- A change that leaves your view (deleted, moved to another period, to the Inbox or into a folded goal) is said in the field, in the field's answer shape, compact: a black pill 64 px tall where the field stands, one line at 15/22 in white saying what happened to which goal (the title cut with "…"), and Undo as a white pill at its right end. It stays 6 seconds and the field comes back; Esc or a click elsewhere ends it sooner. It takes the place of today's delete notice.

## Done when

UI tests: undo and redo of a tick, a drag, a reschedule, a delete, and one agent answer's writes as one step; the notice's text, its 6 seconds and its Undo. Before and after pictures.
