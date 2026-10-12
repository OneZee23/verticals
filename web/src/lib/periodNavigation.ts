import { isoDate, localDate } from './schedule'
import type { VerticalScale } from './periods'

export type AdjustableVertical = Exclude<VerticalScale, 'life'>
export type PeriodDirection = -1 | 1

function mondayOf(date: Date): Date {
  const monday = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const weekday = monday.getDay() || 7
  monday.setDate(monday.getDate() + 1 - weekday)
  return monday
}

/** First day of the period of `vertical` that holds `date`: what one navigator click steps from. */
function periodStart(date: Date, vertical: AdjustableVertical): Date {
  switch (vertical) {
    case 'day':
      return new Date(date.getFullYear(), date.getMonth(), date.getDate())
    case 'week':
      return mondayOf(date)
    case 'month':
      return new Date(date.getFullYear(), date.getMonth(), 1)
    case 'quarter':
      return new Date(date.getFullYear(), Math.floor(date.getMonth() / 3) * 3, 1)
    case 'year':
      return new Date(date.getFullYear(), 0, 1)
    case 'decade':
      return new Date(2026 + 3 * Math.floor((date.getFullYear() - 2026) / 3), 0, 1)
  }
}

/** Start date of the adjacent period selected by one navigator click. */
export function adjacentPeriodAnchor(
  anchor: string,
  vertical: AdjustableVertical,
  direction: PeriodDirection,
): string {
  const start = periodStart(localDate(anchor), vertical)
  const [year, month, day] = [start.getFullYear(), start.getMonth(), start.getDate()]
  let result: Date

  switch (vertical) {
    case 'day':
      result = new Date(year, month, day + direction)
      break
    case 'week':
      result = new Date(year, month, day + 7 * direction)
      break
    case 'month':
      result = new Date(year, month + direction, 1)
      break
    case 'quarter':
      result = new Date(year, month + 3 * direction, 1)
      break
    case 'year':
      result = new Date(year + direction, 0, 1)
      break
    case 'decade':
      result = new Date(year + 3 * direction, 0, 1)
      break
  }

  return isoDate(result)
}

/** Whether the period of `vertical` that holds `anchor` also holds `day`: a column of a board paged away from today no
 *  longer does, and its sign is the single bar that brings the board back (docs/design/column-bars.md). */
export function periodHoldsDay(vertical: AdjustableVertical, anchor: Date, day: Date): boolean {
  return periodStart(anchor, vertical).getTime() === periodStart(day, vertical).getTime()
}
