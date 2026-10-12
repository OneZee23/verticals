// The words of the notice (docs/design/board-undo.md): what happened to which goal, in one line, in the app's own words for
// its places (Tomorrow, Next week, the Inbox). A title is a `quote` segment: the notice cuts that one with “…”.
import type { Segment } from './fieldNotice'
import type { Shot } from './boardShots'
import { localDate, plannedPeriodLabel } from './schedule'

const DAY_MS = 86_400_000

function days(from: Date, to: Date): number {
  return Math.round((Date.UTC(to.getFullYear(), to.getMonth(), to.getDate()) - Date.UTC(from.getFullYear(), from.getMonth(), from.getDate())) / DAY_MS)
}

/** Monday of the week `d` is in, as a day number, to tell this week from next. */
function weekIndex(d: Date): number {
  const monday = (d.getDay() + 6) % 7
  return Math.floor((Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY_MS - monday + 3) / 7)
}

/** Where a goal now stands, for "Moved “…” to …": today, tomorrow, next week and the like when it is that, otherwise the
 *  period's own label, which is what its column's header says. */
export function periodWords(shot: Pick<Shot, 'vertical' | 'anchor_date' | 'period_key'>, today: Date = new Date()): string {
  if (shot.vertical === null) return 'the Inbox'
  const anchor = shot.anchor_date ? localDate(shot.anchor_date) : null
  const label = plannedPeriodLabel({ vertical: shot.vertical, anchor_date: shot.anchor_date, period_key: shot.period_key })
  if (!anchor) return label
  switch (shot.vertical) {
    case 'day': {
      const apart = days(today, anchor)
      return apart === 0 ? 'today' : apart === 1 ? 'tomorrow' : apart === -1 ? 'yesterday' : label
    }
    case 'week': {
      const apart = weekIndex(anchor) - weekIndex(today)
      return apart === 0 ? 'this week' : apart === 1 ? 'next week' : label
    }
    case 'month': {
      const apart = (anchor.getFullYear() - today.getFullYear()) * 12 + anchor.getMonth() - today.getMonth()
      if (apart === 0) return 'this month'
      if (apart === 1) return 'next month'
      return anchor.getFullYear() === today.getFullYear() ? label : `${label} ${anchor.getFullYear()}`
    }
    case 'quarter':
      return anchor.getFullYear() === today.getFullYear() ? label : `${label} ${anchor.getFullYear()}`
    case 'life':
      return 'Life'
    default:
      return label
  }
}

/** The line for a change of the goal `after` was in `before`; `parentTitle` names a goal by its id. `null` when the change
 *  is one nobody leaves the view with (a title, a tag), so there is nothing to say. */
export function changeWords(
  before: Shot, after: Shot, parentTitle: (id: string) => string, today: Date = new Date(),
): Segment[] | null {
  const moved: Segment[] = [{ text: 'Moved ' }, { quote: after.title }]
  if (after.parent_id !== before.parent_id) {
    return after.parent_id
      ? [...moved, { text: ' into ' }, { quote: parentTitle(after.parent_id) }]
      : [...moved, { text: ' out of ' }, { quote: before.parent_id ? parentTitle(before.parent_id) : 'its goal' }]
  }
  if (after.vertical !== before.vertical || after.anchor_date !== before.anchor_date || (after.period_key ?? null) !== (before.period_key ?? null)) {
    return [...moved, { text: ` to ${periodWords(after, today)}` }]
  }
  if (after.done !== before.done) return [{ text: after.done ? 'Completed ' : 'Reopened ' }, { quote: after.title }]
  return null
}

/** The line for a delete: the goal and, when it had steps, how many went with it. */
export function deleteWords(title: string, descendants: number): Segment[] {
  const steps = descendants === 1 ? '1 subgoal' : `${descendants} subgoals`
  return [{ text: 'Deleted ' }, { quote: title }, ...(descendants > 0 ? [{ text: ` and ${steps}` }] : [])]
}

/** A goal the person made, said when it is not in view, and the line for taking it back. */
export function addedWords(title: string): Segment[] {
  return [{ text: 'Added ' }, { quote: title }]
}
export function removedWords(title: string): Segment[] {
  return [{ text: 'Removed ' }, { quote: title }]
}

/** After an undo whose result is not on the screen: what was put back. */
export function putBackWords(title: string): Segment[] {
  return [{ text: 'Put back ' }, { quote: title }]
}


/** A step that could not be done whole because what it changed was changed since (an agent working in the background, another
 *  window): the change stays as it is now. `kept` are the goals it stays on; `set` says whether anything else went back. */
export function keptWords(direction: 'undo' | 'redo', title: string, kept: { title: string }[], set: boolean, extra = 0): Segment[] {
  if (set) {
    return [{ text: direction === 'undo' ? 'Put back ' : 'Redid ' }, { quote: title }, { text: `${extra > 0 ? ` and ${extra} more` : ''}; what changed since stays` }]
  }
  const more = kept.length - 1
  return [
    { quote: kept[0]?.title ?? title },
    { text: more > 0 ? ` and ${more} more changed since, so they stay` : ' changed since, so it stays' },
  ]
}
