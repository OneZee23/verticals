# Worked example: a whole report, with sample sources

This is a complete report of the shape in [report-contract.md](report-contract.md), made up of sample data: three sources ("Team chat", "Mail", "Calendar"), a small launch, and generic names. The decisions and the state distinctions are adapted from real reports; every name, ID and link here is a placeholder. Links to a task are `goal:<id>` and to a source `doc:<path>`; the IDs below are not real.

## What the run had (not part of the report)

The reader's clock is Europe/Berlin, and the context said `Now: 2026-10-12 06:57`. `sources` with `day` 2026-10-12 returned three sources with their cutoffs and the tools that read them. The Calendar's check was waiting for the reader's Approve, so its tools could not be called. The last report was Sunday's; its sources section ended Team chat at 06:58 and Mail at 06:41. Sunday's report left one comment in a row's last cell; the app saved it on its task before this run, word for word, and the ask listed it.

## The report

The document's title is `Morning report — 12 October 2026`. Its body, as it is saved:

`````
```unread
Calendar: waiting for your Approve, so it was not read. Its window still ends 2026-10-11 07:00.
```

Not checked yet: a second agent is reading it against the sources.

## Inbox — decisions needed

| Task | Purpose | Latest | Next action | Your comment |
| --- | --- | --- | --- | --- |
| Partner call is booked | Agree the launch date with the partner. | Sam wrote in Team chat on Sun 11 Oct: “probably set up a call with the partner this week”. No task for it yet. | Make it a task? Sam would join. | |

## Today

| Task | Purpose | Latest | Next action | Your comment |
| --- | --- | --- | --- | --- |
| **[Launch plan is shared with the team](goal:AAAA1111)** | The team works from one plan. | The plan went to the team on Sat 10 Oct. Two of four reviews are in; the other two were promised for Mon 12 Oct and have not arrived. | Waiting for the two reviews. Nothing to decide yet. | |
| – [Notes are written](goal:BBBB2222) | The launch notes are ready to send. | A first draft is saved in the plan's document. The partner has not answered about the date. | Finish the draft once the date is known. | |
| [Offer package is priced](goal:CCCC3333) | The base and premium options have prices. | The base option was agreed in Team chat on Sun 11 Oct. The premium price is open. Annual payment was discussed, not decided. | Your decision on the premium price. | |

## This week — keep in mind

| Task | Purpose | Latest | Next action | Your comment |
| --- | --- | --- | --- | --- |
| [Skills are shared with Sam](goal:DDDD4444) | Sam can use the skills without help. | Merged on Sat 10 Oct, and Sam says he uses them. That is not your acceptance of the task. | Your call whether it is done. | |

## Closed since the last report

- [Invoice is sent](goal:EEEE5555): Mail shows the client's reply “paid” on Sun 11 Oct.

## Sources

Times in Europe/Berlin.

| Source | Window | Read | Tasks | Inbox | Done | Put off | Context | Gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [Team chat](doc:sources/team-chat.md) | 2026-10-11 06:58 – 2026-10-12 06:57 | 42 | 11 | 4 | 6 | 3 | 15 | 3 |
| [Mail](doc:sources/mail.md) | 2026-10-11 06:41 – 2026-10-12 06:57 | 8 | 4 | 1 | 1 | 0 | 2 | 0 |
| [Calendar](doc:sources/calendar.md) | 2026-10-11 07:00 – 2026-10-11 07:00 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
`````

## How to read it

- **Top to bottom.** What could not be read comes first and in red. The check line is under it, and the app replaces it with the second agent's verdict. The rows follow, then what was closed, and the sources last.
- **Windows.** Team chat and Mail start where Sunday's report stopped and end at the time the run began. The Calendar could not be read, so its row repeats its old end and counts nothing. Tomorrow it starts again at 2026-10-11 07:00.
- **Counts.** Team chat gave 42 items: 11 + 4 + 6 + 3 + 15 + 3. The three in the last column are messages that could not be placed or understood, and they show as a number. Mail gave 8: 4 + 1 + 1 + 0 + 2 + 0.
- **Names.** A task is named by its result. The first row has no task yet, so it is named the same way and links nothing; it sits in the Inbox group as a decision.
- **Parent and child.** The launch plan is in bold, and its child stands under it after a dash.
- **Dates** are written as the schedule writes them (`Sat 10 Oct`), and the state of a thing is said as it is: reviews promised, not received; merged, not accepted; discussed, not decided.
- **Closed.** The invoice was closed on the board first, with its evidence recorded, and is listed once. It is not a row.

## After the reader writes in a comment

Suppose the reader writes in the last cell of the Offer row: `Take the lower premium price, 49, and tell Sam today.` The next morning the app saves those words, exactly, as a comment on the task “Offer package is priced”, reads the thread back, and clears the cell. The comment is the reader's input. It does not move the price or message Sam; it waits for a direct command. When the reader asks for a report to be checked again, the same is done for the comments in it, and the row's Next action says “Your comment is on the task.”
