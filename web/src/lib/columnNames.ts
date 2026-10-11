/* The names a board column carries (docs/design/column-names.md): its period is the big name and its kind the small grey
   line above it, so the seven read left to right as one path out through time, "Today, 5–11 Oct, October, Q4, ’26,
   ’26–’28, All time", over "Day, Week, Month, Quarter, Year, Three years, Life". Pure functions of the board's anchor
   and of now; `boardProjection.ts` hands them to the column.

   A name is never cut with "…": each period gives its forms from the longest to the shortest, and the header shows the
   longest that fits its room (`lib/fitName.ts`). What the short forms leave out is a thought, never letters in the middle
   of a word: a week's last day, then its first; a month moved up to the kind line; "Wednesday" and "September" as the
   three letters the board writes elsewhere. Years are written short everywhere: ’26, ’26–’28, "Month · ’27".

   The anchor names the period, not the clock (owner report 2026-08-10: the day and the week stayed on the real today
   while the other columns followed the anchor). Day and week are read off the anchor's date, which a period_key can't
   carry (a week's ISO key names no dates); month, quarter, year and three years are parsed from the server's own
   period_key by `periods.ts::periodLabel`, as before (AC-010: nothing here derives a key). */

import { MONTH_NAMES, periodLabel, type VerticalScale } from './periods'
import { addDays, isoDate, isoWeekStart, WEEKDAY_NAMES } from './schedule'
import type { NameForm } from '../types'

export interface ColumnNames {
  /** The name in every form, longest first: the column shows the first that fits its room. */
  forms: NameForm[]
  /** The accessible name: the full name, with full years, whichever form is on screen ("Year, 2026"). */
  label: string
}

/** Each scale's kind. Three years is spelled out: the name under it is the years themselves, "’26–’28". */
const KINDS: Record<string, string> = {
  day: 'Day', week: 'Week', month: 'Month', quarter: 'Quarter', year: 'Year', decade: 'Three years', life: 'Life',
}
/** A scale's kind, "Week": what a column's bars are named by, "Previous week", "Week mode", "Next week"
 *  (docs/design/column-bars.md). */
export function kindOf(vertical: string): string {
  return KINDS[vertical] ?? vertical
}
/** The scales whose name doesn't say its year; the kind line does, when it isn't this one. Year and three years are
 *  their years, and life has none. */
const YEAR_IN_KIND = new Set(['day', 'week', 'month', 'quarter'])

const short = (name: string): string => name.slice(0, 3)
const shortMonth = (date: Date): string => short(MONTH_NAMES[date.getMonth()])
/** A year as the board writes it: ’26. The apostrophe is U+2019. */
const shortYear = (year: number): string => `’${String(year % 100).padStart(2, '0')}`

/** The year of a period that lies outside the current year, else null. A week that reaches into the current year is this
 *  year's, so the week across New Year carries none (the one holding today never does); a week wholly outside takes the
 *  year it starts in. */
function outsideYear(from: Date, to: Date, today: Date): number | null {
  const year = today.getFullYear()
  return from.getFullYear() !== year && to.getFullYear() !== year ? from.getFullYear() : null
}

const TAIL = ' · '
/** The kind line: "Month", "Month · ’27", and for a week whose month moved up into it, "Week · Dec", "Week · Dec ’27". */
function kindLine(kind: string, month: string | null, year: number | null): string {
  const tail = [month, year === null ? null : shortYear(year)].filter(Boolean).join(' ')
  return tail ? `${kind}${TAIL}${tail}` : kind
}

/** What follows the kind on its line, " · Dec ’27", or nothing: the month a form moved up and the year of a period outside
 *  this one. The line pinned at a scrolled column's top names the period without its kind, so it says this after the
 *  name, "21–27 · Dec ’27": else a scrolled column would read as this year's, and a week as no month's
 *  (docs/design/column-bars.md). */
export function kindTail(kind: string): string {
  const at = kind.indexOf(TAIL)
  return at < 0 ? '' : kind.slice(at)
}

/** The kind in the accessible name, which speaks the whole year: "Month 2027". */
const spoken = (kind: string, year: number | null): string => (year === null ? kind : `${kind} ${year}`)

/** Today; within the current week (Monday to Sunday) its weekday, "Wednesday", then "Wed"; further away its date, "15 Oct". */
function dayNames(anchor: Date, today: Date): string[] {
  if (isoDate(anchor) === isoDate(today)) return ['Today']
  if (isoDate(isoWeekStart(anchor)) === isoDate(isoWeekStart(today))) {
    const weekday = WEEKDAY_NAMES[anchor.getDay()]
    return [weekday, short(weekday)]
  }
  return [`${anchor.getDate()} ${shortMonth(anchor)}`]
}

/** "5–11 Oct". Across two months, "30 Apr–6 May", then "30 Apr–May" (the widest of the twelve pairs, 179 px, still fits the
 *  184 px a window of 1470 px gives a column), then "Apr–May". Inside a month, "21–27 Dec", then "21–27" with the month
 *  moved up into the kind line, where it reads "Week · Dec". */
function weekForms(from: Date, to: Date): { name: string; month: string | null }[] {
  const first = from.getDate()
  const last = to.getDate()
  if (from.getMonth() === to.getMonth()) {
    return [{ name: `${first}–${last} ${shortMonth(to)}`, month: null }, { name: `${first}–${last}`, month: shortMonth(to) }]
  }
  const start = `${first} ${shortMonth(from)}`
  return [
    { name: `${start}–${last} ${shortMonth(to)}`, month: null },
    { name: `${start}–${shortMonth(to)}`, month: null },
    { name: `${shortMonth(from)}–${shortMonth(to)}`, month: null },
  ]
}

export function columnNames(
  column: { vertical: string | null; period_key: string | null },
  anchor: Date,
  today: Date,
): ColumnNames {
  const vertical = column.vertical
  // The Inbox bucket: no period, and the board doesn't draw it.
  if (vertical === null) return { forms: [{ name: 'Inbox', kind: '' }], label: 'Inbox' }
  const kind = KINDS[vertical] ?? vertical
  const key = column.period_key ?? ''
  const same = (names: string[], year: number | null): NameForm[] => names.map((name) => ({ name, kind: kindLine(kind, null, year) }))

  if (vertical === 'week') {
    const from = isoWeekStart(anchor)
    const to = addDays(from, 6)
    const year = outsideYear(from, to, today)
    const forms = weekForms(from, to).map(({ name, month }) => ({ name, kind: kindLine(kind, month, year) }))
    return { forms, label: `${spoken(kind, year)}, ${forms[0].name}` }
  }

  const year = YEAR_IN_KIND.has(vertical) ? outsideYear(anchor, anchor, today) : null
  if (vertical === 'day') {
    const names = dayNames(anchor, today)
    return { forms: same(names, year), label: `${spoken(kind, year)}, ${names[0]}` }
  }
  if (vertical === 'life') return { forms: same(['All time'], null), label: `${kind}, All time` }

  const full = periodLabel(vertical as VerticalScale, key)
  let names = [full]
  if (vertical === 'month' && MONTH_NAMES.includes(full) && short(full) !== full) names = [full, short(full)]
  if (vertical === 'year' && /^\d{4}$/.test(full)) names = [shortYear(Number(full))]
  if (vertical === 'decade') {
    const years = /^(\d{4})–(\d{4})$/.exec(full)
    if (years) names = [`${shortYear(Number(years[1]))}–${shortYear(Number(years[2]))}`]
  }
  return { forms: same(names, year), label: `${spoken(kind, year)}, ${full}` }
}
