# The period bars, | ||| |, on a line pinned at the column's top

Verticals pages a column with vertical bars, its own sign, in place of ← • →. The middle bar opens the column's spans mode, the same one a dragged task opens when it rests on the column's corner.

## Behaviour

- At rest every column but Life shows three bars, |||, the middle one dark.
- Under the pointer a bar comes at each side: | ||| |. The side bars step the column to the period before and after, as ← and → do today. The middle bar opens the column's spans mode (`lib/spans.ts`, `SpansBoard.vue`): a week in each column for Week, a month in each for Month, and so on. The mode is built; only the click on the middle is new.
- When a column scrolls, the line holding the bars stays pinned at its top on white, and the goals fade out under it over 14 px. While the column is at its top the line shows the kind ("Week"); once the big name has scrolled under it, the line shows the period ("5–11 Oct").
- The bars are buttons with names for the keyboard and assistive tech: "Previous week", "Week mode", "Next week", by the column's kind.
- The side bars appear at once under the pointer and fade back in 200 ms; under reduced motion they simply appear and go.

## Not in this piece

The names themselves (`column-names.md`).

## Done when

UI tests: the bars at rest, the side bars under the pointer, paging by the side bars, the middle opening the spans mode, the pinned line's two states while scrolling. Before and after pictures.
