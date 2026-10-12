# What the agent made stands under its words

The agent answers in one or two short paragraphs and writes anything longer as a document during the discussion. Whatever it made or changed is shown one way, everywhere.

## Behaviour

- What the agent made or changed stands under its words as chips, one form for every kind of thing: a document by its first page (`DocChip.tsx`, as today), a goal by its square, its title (two lines at most) and one grey line saying where it is and when ("Today · made just now"). The chips come from the links in the agent's own text, as document chips already do; nothing is a badge of its own.
- The same message with the same chips shows in the field's answer while the conversation is closed, and as the agent's balloon while it is open.
- A chip opens what it names: a document as a window, a goal as its window.
- A fresh discussion, about no goal yet, may make a task and its document at once; the conversation then belongs to that task, so Discuss on it goes on with this conversation.

## Not in this piece

The instructions that keep answers to two paragraphs (`agent-fixes.md`), comments in a document (`doc-comments-inline.md`).

## Done when

UI tests with the fake agent: a goal link in an answer becomes a goal chip in the field and in the open conversation; the chip opens the goal; a fresh discussion that makes a task becomes that task's conversation. Before and after pictures.
