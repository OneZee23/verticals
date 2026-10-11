# Each column is named by its period

A column's big name becomes its period, and the small grey line above it the kind: "October" under "Month". Read left to right, the seven names are one path out through time. A name is never cut with "…": each period has shorter forms of the same name, and the column shows the longest one that fits.

## Behaviour

- At now the seven names are: Today, 5–11 Oct, October, Q4, ’26, ’26–’28, All time. Their kinds above them: Day, Week, Month, Quarter, Year, Three years, Life.
- The type stays the board's own: the name in the column title style (700, 31/40), the kind at 15/24 in grey.
- Years are written short everywhere: Year is "’26", Three years is "’26–’28". A period outside the current year carries its year in the kind line: "Month · ’27", "Week · ’27", "Week · Dec ’27". The apostrophe is the typographic ’ (U+2019), and a range takes the en dash, as in "5–11 Oct".
- Day paged to another day says its weekday ("Wednesday") within the current week, and its date ("15 Oct") further away.
- A week across two months names both ends, "30 Apr–6 May". A week inside one month is "5–11 Oct".
- Each name has its forms from the longest to the shortest, and the column shows the first that fits its room:

  | Name | Forms, longest first |
  | --- | --- |
  | Day | Wednesday, Wed (Today and a date like "15 Oct" are short already) |
  | Week across two months | 30 Apr–6 May, 30 Apr–May, Apr–May |
  | Week inside one month | 21–27 Dec, then 21–27 with the month moved up to the kind line: "Week · Dec" ("Week · Dec ’27" outside the current year) |
  | Month | September, Sep (a month name that doesn't fit) |
  | Quarter, Year, Three years, All time | one form: they always fit |

- What a short form leaves out is a thought, never letters in the middle of a word: a week's last day, then its first; a month moved up a line; "Wed" and "Sep" as the three letters the board writes elsewhere.
- The room is the title's width: the column's width less its 26 px of padding. At a window of 1470 px it is 184 px with nothing open and 152 px beside an open column; in the desktop app's first window, 1320 px, it is 163 px and 134 px. At 184 px every name is whole, except a week across two months that is wider than that: it takes its second form (the widest, "30 Apr–May", takes 179 px).
- A form is measured with the real title font against the room of the column's final layout, and chosen before a column moves (one opening or closing, the spans), so the words never change in the middle of a movement. They are chosen again when the window is resized.
- The shortest form of a name, and a kind line, may take up to 8 px of the padding beside them before they are cut. At 134 px, the narrowest everyday room (a window from 1240 to 1360 px with a column open, the desktop app's first window among them), "Apr–May" is 134.8 px and the kind line "Week · May ’27" is 100.7 px of the 98 it has (the kind row keeps 36 px free at its right); both stand whole that way.
- Where even that is not enough the text ends in "…" as the last resort: a window narrower than about 1210 px with a column open.
- The column's accessible name always says the full name and the full year, whichever form is on screen: "Day, Wednesday", "Week, 30 Apr–6 May", "Year, 2026", "Three years, 2026–2028" (a screen reader would read "’26" as "apostrophe 26").

## Not in this piece

The line pinned at a scrolled column's top and the period bars (`column-bars.md`).

## Done when

Unit tests cover the names: every month pair, the year edges, Day's weekday rule. A UI test reads the seven names at now. Every form is measured in the title font against its room (184 px and 152 px at 1470 px), and in the everyday state (one column open at 1470 px) and in the 1320 px window, with nothing open and with a column open, no name or kind ends in "…" and each name shows its expected form. Before and after pictures from a sample board, with the open-column state and the 1320 px window.
