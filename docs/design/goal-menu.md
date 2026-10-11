# The goal's menu: Agent, Reschedule, Move, Delete

The menu groups its actions by what they change: the agent's work, when, where, and the goal itself.

## Behaviour

- Order: **Agent**, a small grey heading, over Discuss · a line · **Reschedule** over Tomorrow, Next week, Date ›, Repeat › · a line · **Move** over Into a goal ›, To Inbox · a line · Delete, in red.
- Complete leaves the menu: a goal completes by its box, as a goal without steps already does.
- Comment leaves the menu: comments live in documents, in their text.
- Discuss opens the agent's discussion of the goal, as "Discuss with agent" does today. Without an available agent the Agent section isn't shown.
- Under becomes "Into a goal" and Inbox becomes "To Inbox", since it takes the date away.
- Delete shows in red (#c93a5b). Its class has carried that red all along, but the menu's item colour painted over it.
- Repeat works for a goal with steps: each new time brings the goal's steps back, unticked. Today the server refuses it ("goals with subgoals cannot repeat") and the menu greys it.

## Not in this piece

Start work and Open in ›, which join the Agent section with task sessions (`task-sessions.md`).

## Done when

UI tests for the order, the red Delete and the renamed items; core and HTTP tests for a repeating goal with steps (its steps come back unticked). Before and after pictures.
