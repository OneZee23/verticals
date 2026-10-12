# ⌘Z takes back your own last change on the board

Today a goal ticked by mistake, a wrong drop or a deleted goal can only be put back by hand: ⌘Z works inside a goal's notes and nowhere else.

The owner, 12 October: "This actually was about human actions, not agent's ones primarily. Just fyi. Since sometimes human might want to decline his action while in background there might be agent's one last in logs. And some time human might want to cancel agents action." And: "if human is typing anything and doing cmd z while focused in any text field or any place with text that's definetely simple cmd z."

## Behaviour

- ⌘Z undoes your last change on the board and ⇧⌘Z redoes it, back through everything you did since the app opened.
- Inside text ⌘Z is the text's own, in every place where one types: the field, a title being renamed, a goal's notes, a document, the Inbox's write field, a step being added. It undoes the typing and takes back no change on the board. In the field it takes back the last run of typing, not a letter.
- Every change you make on the board counts: ticking, moves (a drag, Tomorrow, Next week, a date, into a goal, to the Inbox), delete, repeat, a renamed title once saved.
- ⌘Z is for your own changes: an agent's writes never enter its history, so ⌘Z never takes back an agent's work by surprise; an agent's answer is taken back from the answer itself (PR #50).
- A step puts a goal back only where the goal still holds what the step left. What has been changed since, by an agent working in the background or by another window, stays as it is now; the step's other changes still go back. What is compared is what you see: the done mark, the title, the parent and the period, not the place in the list, which moves whenever a neighbour does.
- The field says it within its one line. When some of the step went back: `Put back “X”; what changed since stays`, with Redo. When none of it could: `“X” changed since, so it stays`, with no button, and the step is spent: the next ⌘Z goes to the step before it.
- A change you can see is undone in place, its own movement played backwards, with no message.
- A change that leaves your view (deleted, moved to another period, to the Inbox or into a folded goal) is said in the field, in the field's answer shape, compact: a black pill 64 px tall where the field stands, one line at 15/22 in white saying what happened to which goal (the title cut with "…"), and Undo as a white pill at its right end. It stays 6 seconds and the field comes back; Esc or a click elsewhere ends it sooner. It takes the place of today's delete notice.

## Done when

UI tests: undo and redo of a tick, a drag, a reschedule, a delete, and a later change of an agent's left as it is; ⌘Z inside text in each place one types; the notice's text, its 6 seconds and its Undo. Before and after pictures.
