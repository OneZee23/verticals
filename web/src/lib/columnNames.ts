/* The names a board column carries (docs/design/column-names.md): its period is the big name and its kind the small grey
   line above it, so the seven read left to right as one path out through time, "Today, 5–11 Oct, October, Q4, 2026,
   2026–2028, All time", over "Day, Week, Month, Quarter, Year, Three years, Life". Pure functions of the board's anchor
   and of now; `boardProjection.ts` hands them to the column.

   The anchor names the period, not the clock (owner report 2026-08-10: the day and the week stayed on the real today
   while the other columns followed the anchor). Day and week are read off the anchor's date, which a period_key can't
   carry (a week's ISO key names no dates); month, quarter, year and three years are parsed from the server's own
   period_key by `periods.ts::periodLabel`, as before (AC-010: nothing here derives a key). */

import { MONTH_NAMES, periodLabel, type VerticalScale } from './periods'
import { addDays, isoDate, isoWeekStart, WEEKDAY_NAMES } from './schedule'

export interface ColumnNames {
  /** The big name: the column's period. */
  name: string
  /** The name where the column is wide, when the period has a longer one: a week across two months, with its last day. */
  wideName?: string
  /** The small line above the name: the kind, and after it the year when the period is outside the current year. */
  kind: string
}

/** Each scale's kind. Three years is spelled out: the name under it is the years themselves, "2026–2028". */
const KINDS: Record<string, string> = {
  day: 'Day', week: 'Week', month: 'Month', quarter: 'Quarter', year: 'Year', decade: 'Three years', life: 'Life',
}
/** The scales whose name doesn't say its year; the kind line does, when it isn't this one. Year and three years are
 *  their years, and life has none. */
const YEAR_IN_KIND = new Set(['day', 'week', 'month', 'quarter'])

const short = (date: Date): string => MONTH_NAMES[date.getMonth()].slice(0, 3)

/** Today; within the current week (Monday to Sunday) its weekday, "Wednesday"; further away its date, "15 Oct". */
function dayName(anchor: Date, today: Date): string {
  if (isoDate(anchor) === isoDate(today)) return 'Today'
  if (isoDate(isoWeekStart(anchor)) === isoDate(isoWeekStart(today))) return WEEKDAY_NAMES[anchor.getDay()]
  return `${anchor.getDate()} ${short(anchor)}`
}

/** "5–11 Oct". Across two months the narrow name keeps the month the week ends in and leaves its last day out, "30 Apr–May":
 *  a thought cut, never letters, and the widest of the twelve pairs still fits the narrowest column. A wide column has
 *  room for the day, "30 Apr–6 May". */
function weekNames(anchor: Date): { name: string; wideName?: string; from: Date; to: Date } {
  const from = isoWeekStart(anchor)
  const to = addDays(from, 6)
  if (from.getMonth() === to.getMonth()) return { name: `${from.getDate()}–${to.getDate()} ${short(to)}`, from, to }
  const start = `${from.getDate()} ${short(from)}`
  return { name: `${start}–${short(to)}`, wideName: `${start}–${to.getDate()} ${short(to)}`, from, to }
}

/** The kind, and after it the year when the period lies outside the current year: "Month · 2027". A week that reaches into
 *  the current year is this year's, so the week across New Year carries none (the one holding today never does); a week
 *  wholly outside it takes the year it starts in. */
function kindLine(vertical: string, from: Date, to: Date, today: Date): string {
  const kind = KINDS[vertical] ?? vertical
  const year = today.getFullYear()
  const outside = from.getFullYear() !== year && to.getFullYear() !== year
  return YEAR_IN_KIND.has(vertical) && outside ? `${kind} · ${from.getFullYear()}` : kind
}

export function columnNames(
  column: { vertical: string | null; period_key: string | null },
  anchor: Date,
  today: Date,
): ColumnNames {
  const vertical = column.vertical
  // The Inbox bucket: no period, and the board doesn't draw it.
  if (vertical === null) return { name: 'Inbox', kind: '' }
  if (vertical === 'week') {
    const { name, wideName, from, to } = weekNames(anchor)
    return { name, wideName, kind: kindLine(vertical, from, to, today) }
  }
  let name: string
  if (vertical === 'day') name = dayName(anchor, today)
  else if (vertical === 'life') name = 'All time'
  else name = periodLabel(vertical as VerticalScale, column.period_key ?? '')
  return { name, kind: kindLine(vertical, anchor, anchor, today) }
}
