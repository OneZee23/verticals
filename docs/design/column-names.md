# Each column is named by its period

A column's big name becomes its period, and the small grey line above it the kind: "October" under "Month". Read left to right, the seven names are one path out through time.

## Behaviour

- At now the seven names are: Today, 5–11 Oct, October, Q4, 2026, 2026–2028, All time. Their kinds above them: Day, Week, Month, Quarter, Year, Three years, Life.
- The type stays the board's own: the name in the column title style (700, 31/40), the kind at 15/24 in grey.
- Day paged to another day says its weekday ("Wednesday") within the current week, and its date ("15 Oct") further away.
- A period outside the current year carries the year in the kind line: "Month · 2027".
- A week across two months: "30 Apr–May" in a narrow column, "30 Apr–6 May" in a wide one. Every month pair fits the narrow column's 184 px in the title type; the widest, "30 Apr–May", takes 179 px. A week inside one month stays "5–11 Oct".
- The column's accessible name says the same words.

## Not in this piece

The line pinned at a scrolled column's top and the period bars (`column-bars.md`).

## Done when

Unit tests cover the names: every month pair, the year edges, Day's weekday rule. A UI test reads the seven names at now. Before and after pictures from a sample board.
