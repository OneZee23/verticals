# ⌘Z takes back an agent's answer as one step

Agreed with the owner in `board-undo.md`: "The agent's changes undo the same way, and all the writes of one answer are one step." PR #40 builds ⌘Z for the person's own changes; this piece adds the agent's, on top of it.

## Behaviour

- Everything one answer of the agent changed on the board is one ⌘Z step, in order with the person's own steps: an answer in the field, Check again, Replan, the morning report.
- ⌘Z puts back only what that answer wrote. Anything changed since, by the person or by another answer, stays as it is now. ⇧⌘Z does the answer's writes again.
- What you can see is undone in place; what leaves your view is said in the field with Undo, as in #40.
- Answers given since the app opened count, including one given while its window was closed, such as the morning report. An agent using Verticals from Claude Code or Codex outside the app is not in this history.

## How

The server knows exactly which answer made each write. The gateway marks each answer, the mark reaches the MCP server with each of the agent's calls, and the server keeps in memory, per answer and since it started, what each write changed, before and after. When an answer ends, the page reads that record, adds it to its history as one step, and undoes and redoes it with #40's restore. Nothing is guessed from a diff of the board: a diff is wrong whenever the person's own changes overlap the answer's.

## Done when

UI tests with the fake agent:
- an answer that ticks one goal, moves another and makes a third is one step;
- ⌘Z puts all three back, and ⇧⌘Z does them again;
- a goal the person changed after the answer stays as the person left it;
- an answer given while the page was closed is in the history when it opens.

Before and after pictures.
