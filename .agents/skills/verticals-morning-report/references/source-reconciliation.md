# Source collection and reconciliation

The aim is to explain the *current* state of each material commitment, not to collect the maximum number of sources. Use the owner's configured connections from [setup.md](setup.md) and the least access needed for each claim.

## Source windows and summaries

Every source is read from where the last report stopped reading it. The `sources` tool, given `day` as today's date, returns each source with its `cutoff`: the end of the window in the last report's sources section ([report-contract.md](report-contract.md)). Read each source from there to the time you began (`Now:` in your context), and write that window in the new report's sources section: the next morning starts where this one ends. A source with no cutoff (the first morning, or a new source) starts where its document's "Since when" says. A source you could not read keeps its old end: write its old window again, with nothing read, so a day of silence never moves a cut-off.

Read each source with exactly the tools its document lists (`reads`). A source whose check the reader has not approved, one that is red, and one with no tool listed cannot be read: name it in the red block, and do not turn non-access into "nothing happened". An empty answer from a tool that worked is a finding, from one that did not is a gap.

Inventory first, rows second. Every item a source gave inside its window gets a place: a task, the Inbox, done by newer news, put off by the reader, context or a gap. Every request the reader made, in a voice note, a chat or a call, is its own item with what comes out of it and who does it; "probably create…" counts as asked. The counts per source go in the sources section, and they add up to what was read, so a miss shows as a number.

Summaries, search results, extracted action items and session titles route attention; they do not prove exact words, agreement, delivery, or that the input was saved. For each consequential claim, inspect the primary passage, message, artifact, board record or repository state at a sufficient read scope. If a summary says a new action exists, identify who actually committed and to what.

Record per-source coverage in the sources section's counts and, in the rows, what remains uncertain. A report-wide cutoff is the time through which the stated general collection really ran; a targeted later check is said in the row it concerns and does not move the source's window. If a source was unavailable, give its last known check and the claims left uncertain.

## Map a material input

For each new discussion, decision, result, or reply, make this internal check before publishing:

| Check | Question |
| --- | --- |
| Primary source | What was actually said, by whom, and at what read scope? Is it a promise, proposal, observation, or agent inference? |
| Existing destination | Which exact Verticals goal and owning session carry this work? What do the current body, document, comments, and result actually say? |
| Later state | Did subsequent messages, a delivered artifact, a merge, payment, or another decision supersede the older status? |
| Authorized incorporation | Was an update permitted, saved to the *authoritative* destination, and read back with its revision or equivalent state? A source mentioned only in the report, or saved only to a mirror, is **not** incorporated into the live task. |
| Remaining action | Who acts next, under what condition? Is a separate direct reader command or human acceptance still needed? A transferred comment or information-only notification is not execution authorization. |

One call may update several existing goals; several sources may explain one goal. Do not manufacture a new goal or review session when a suitable owner already exists. Preserve distinctions between discussing a document, saving a draft, sending it, receiving a reply, and the reader accepting the result.

## Adapted traces from actual use

**Meeting summary → exact passage → task document.** A meeting index surfaced a proposed client-marketplace engagement. The underlying discussion showed a possible contractor pairing and field research, not an accepted client scope. The existing project brief and attached Verticals document initially lacked that discussion. After an authorized update, both were read back. The report could then say “saved to the brief,” but not “strategy approved” or “client accepted.”

**Old status → later reply → corrected report.** An earlier report said a collaborator's skills PR awaited review. A later message said it was merged, another confirmed the skills were in use, and repository state confirmed the merge. The next report removed the obsolete review reminder. It did not mark the owner's overall sharing task accepted merely because the recipient could use the skills.

**Discussion → separate financial states.** A package conversation established what base and premium options meant, and mentioned annual payment. The existing economics document was updated and read back. The report retained the actual package terms, while keeping annual payment, final price selection, and money received as different states.

Before finalizing, compare every row of the last report with the new one: carried, closed or explained, none gone without a word. The comments the reader left in the last report are on their tasks already (the app saved them), and the ask lists them; they are input, not orders. Age and a compact child display never erase a real promise.

For each reported save, keep a compact source → destination → readback trail (exact task or document, observed state) while you work, and publish only the level of detail the reader needs. If a source is unavailable or a save cannot be verified, keep the claim pending; do not silently substitute another account or call the task updated.
