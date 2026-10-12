# An agent's answer has its own Undo, and ⌘Z asks when it cannot tell whose change it means

PR #40 builds ⌘Z for the person's own changes (`board-undo.md`): an agent's writes never enter that history, so ⌘Z never takes back an agent's work by surprise. This piece gives an agent's answer a way back of its own, and teaches ⌘Z what to do when an agent has been at work since the person's last change.

The owner, 12 October: "This actually was about human actions, not agent's ones primarily. Just fyi. Since sometimes human might want to decline his action while in background there might be agent's one last in logs. And some time human might want to cancel agents action."

And: "While this one was last was the agent's one. So the thing is that maybe agent should ask what exactly to cancel if that's unclear. Treshold is time I belive. If action was human and it was less than 5 seconds ago, it's definietly human."

And: "Also if human is typing anything and doing cmd z while focused in any text field or any place with text that's definetely simple cmd z."

## Behaviour

### The answer's own Undo

- An answer of the agent that changed the board has an Undo where the answer shows: on its message in the open conversation, and in the field while the answer stands there (the circle's answer, and the note it becomes when it links a document, such as the morning report). It is the notice's Undo pill, in the same look: no new look.
- Undo takes back what that answer wrote, and only where the goal is still as the answer left it. What it deleted comes back with what was under it. What it ticked, retitled, moved or reparented on goals that were there goes back kind by kind: a tick still as the answer left it goes back even if the title was changed since. What it made goes to the trash, unless somebody has taken it up since (written to it, put something under it, commented on it).
- Then the same place offers Redo, which does the answer again with the same care.
- What changed since stays, and the field says so in one line, as in #40: `Put back “X” and 2 more; what changed since stays`, with Redo. When nothing could be taken back: `“X” changed since, so it stays`, with no button, and the answer is let go: it has no Undo any more.
- What you can see is undone in place, its own movement played backwards; what leaves your view (a goal it made, a goal it deleted again by Redo) is said in the field with its button, as in #40. When the answer is taken back from its message in the open conversation, the message's own pill is the Redo, so the field says only what happened.
- An answer that changed nothing on the board has no Undo. Neither has what an agent did from Claude Code or Codex outside the app: it carries no conversation of the app's, so it is nobody's answer.
- An answer is never a step of ⌘Z. The keys are the person's own.

### ⌘Z, and whose change it means

In this order:

1. Inside any text, ⌘Z is the text's own: it never asks and never takes back a change on the board. (The field, a title being renamed, a goal's notes, a document, the Inbox's write field, a step being added.)
2. The person's own last change is less than 5 seconds old: it is taken back at once, whatever an agent did.
3. No answer of an agent changed the board since the person's own last change: it is taken back at once, however old.
4. An agent's answer changed the board after the person's own last change, and that change is 5 seconds old or more, or there is none: the field asks, in the notice's shape, where the field stands: `Take back` and the candidates as pills. The person's own last change is worded as the notice words it (`Completed “Color check yellow”`); the agent's last answer says `3 changes by the agent`, or, when it changed one goal, says what it did to it (`Moved “Order two” to this month by the agent`). A click on a pill takes that back, and only that. Esc, a click elsewhere and the six seconds end the question with nothing taken back.

The question is the app's own: it costs no model call and writes nothing until a pick. A taken-back answer is nobody's to ask about any more, so the next ⌘Z is the person's own again.

## How

The server knows exactly which answer made each write, so nothing is guessed from a diff of the board, which is wrong whenever the person's own changes overlap the answer's.

- The desktop gateway marks each answer (one turn of the conversation is one answer, the morning report's too) and tells the MCP server which answer is open for which conversation. Claude's connection carries its conversation in a header; Codex's carries it through the stdio proxy. Every call the agent makes then says whose it is.
- The MCP server keeps in memory, per answer and since it started, what each write changed: each goal as it was and as it was left (`core/answers.py` reads the goals around the write, a goal made by a write is told by `tree.attach`, a delete lists everything under the goal). No table and no migration: the record goes with the process.
- The page reads the record when an answer ends and whenever ⌘Z needs it, so an answer given while the window was closed has its Undo when the window opens. What became of each answer (it stands, it was taken back, it was let go) is kept with it, so a window that opens again shows Redo where it showed Redo.
- The writes of an answer are put together goal by goal (`lib/answerNet.ts`): made, removed, or edited. Undo brings back what was removed, sets edited goals back with the restore #40 built (each kind of change held against what the answer left, the last write first), and sends what was made to the trash if it is intact. Redo is the same the other way round.
- ⌘Z learns of the person's own changes and of the agent's answers in the order the page heard of them, so "after the person's last change" is not a comparison of two clocks. The 5 seconds are the page's clock, which a test moves with the browser's own clock control.

## Done when

UI tests with the fake agent, whose marked calls are real calls to a real MCP server:

- an answer that ticks one goal, moves another and makes a third is taken back by its Undo on its message and in the field, and Redo plays it;
- ⌘Z after an answer takes the person's own last change, when that is less than 5 seconds old, or when no answer came after it;
- a goal the person changed after the answer stays as the person left it, and the field says so;
- an answer given while the window was closed shows its Undo when the window opens, and what became of it is kept;
- the three cases of ⌘Z, with the page's clock moved: at once inside 5 seconds, at once with no answer since, the question otherwise; each pill taking back only its own; Esc, a click elsewhere and the six seconds taking nothing back;
- ⌘Z inside text first: never asks, never takes back a change on the board.

Before and after pictures.
