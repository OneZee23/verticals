// A goal as a chip says it (docs/design/agent-chips.md): its square in its colour, its title, and one grey line saying where
// it is and when it was made or changed, "Today · made just now", "Week · changed 2 min ago". The goal is the board's own
// while the board holds it, so the chip follows every change the board shows; otherwise it is read once, and again each
// time the board changes. A goal that is gone says so.
import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { ApiError, getGoal, type GoalCard } from './api'
import { findGoal } from './boardIndex'
import { MONTH_NAMES, type VerticalScale } from './periods'
import { isoDate, localDate, periodKeyFor, plannedPeriodLabel, verticalHeadline } from './schedule'
import { store } from '../store'

export interface ChipGoal {
  title: string
  vertical: string | null
  anchor_date: string | null
  parent_id: string | null
  /** The value's colour, which is the one the board paints the goal's square in. */
  color: string | null
  created_at: string
  updated_at: string
  done: boolean
}

const chipOf = (goal: GoalCard): ChipGoal => ({
  title: goal.title, vertical: goal.vertical, anchor_date: goal.anchor_date, parent_id: goal.parent_id, color: goal.color,
  created_at: goal.created_at, updated_at: goal.updated_at, done: goal.done_at !== null,
})

/** The goal a chip names: the board's, else read from the server (marked best-effort: a goal that is gone answers 404 and
 *  that is no error here); 'gone' once the server says it is not there, null while it is read. */
export function useGoalChip(id: () => string): { goal: Ref<ChipGoal | 'gone' | null> } {
  const read = ref<ChipGoal | 'gone' | null>(null)
  const onBoard = computed(() => {
    const card = findGoal(store.state.board, id())
    return card ? chipOf(card) : null
  })
  async function load(): Promise<void> {
    const asked = id()
    try {
      const card = await getGoal(asked, true)
      if (asked === id()) read.value = chipOf(card)
    } catch (error) {
      // Any other failure leaves the chip with its link's words; the next change of the board asks again.
      if (asked === id() && error instanceof ApiError && error.status === 404) read.value = 'gone'
    }
  }
  watch(id, () => {
    read.value = null
    if (!onBoard.value) void load()
  }, { immediate: true })
  watch(() => store.state.board, () => {
    if (!onBoard.value) void load()
  })
  return { goal: computed(() => onBoard.value ?? read.value) }
}

/** The clock the grey line reads: it moves on every 30 s while a chip is on screen, so "just now" becomes "1 min ago". */
const now = ref(Date.now())
let watching = 0
let ticker: ReturnType<typeof setInterval> | null = null
export function useNow(): Ref<number> {
  onMounted(() => {
    now.value = Date.now()
    if (watching++ === 0) ticker = setInterval(() => { now.value = Date.now() }, 30_000)
  })
  onBeforeUnmount(() => {
    if (--watching === 0 && ticker) { clearInterval(ticker); ticker = null }
  })
  return now
}

/** How long ago, in a chip's words: "just now", "2 min ago", "3 h ago", "yesterday", then the day, "5 Oct" (with the year
 *  when it is not this one). A clock a little ahead of the server's never says "in 3 min". */
export function ago(at: number, nowMs: number): string {
  const minutes = Math.floor(Math.max(0, nowMs - at) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ago`
  const day = new Date(at)
  if (isoDate(day) === isoDate(new Date(nowMs - 86_400_000))) return 'yesterday'
  const year = day.getFullYear() === new Date(nowMs).getFullYear() ? '' : ` ${day.getFullYear()}`
  return `${day.getDate()} ${MONTH_NAMES[day.getMonth()]!.slice(0, 3)}${year}`
}

/** Where the goal is, as the board names its places: the period it stands in when that is the one it is now ("Today",
 *  "Week", "Month"), else the period itself as the board's cards write it ("Mon 10 Aug", "17–23 Aug", "Q4"); "Life", a
 *  step of another goal, or the Inbox when it has no date. */
export function whereIs(goal: ChipGoal, today: Date): string {
  if (!goal.vertical) return goal.parent_id ? 'Step' : 'Inbox'
  if (goal.vertical === 'life') return 'Life'
  if (!goal.anchor_date) return verticalHeadline(goal.vertical)
  const scale = goal.vertical as VerticalScale
  if (periodKeyFor(scale, localDate(goal.anchor_date)) !== periodKeyFor(scale, today)) {
    return plannedPeriodLabel({ vertical: goal.vertical, anchor_date: goal.anchor_date, period_key: null })
  }
  return scale === 'day' ? 'Today' : verticalHeadline(scale)
}

/** When: "made" until something changed it after the first minute, then "changed" and how long ago that was. */
export function whenIs(goal: ChipGoal, nowMs: number): string {
  const made = Date.parse(goal.created_at)
  const changed = Date.parse(goal.updated_at)
  return changed - made < 60_000 ? `made ${ago(made, nowMs)}` : `changed ${ago(changed, nowMs)}`
}

/** The chip's grey line. */
export function chipLine(goal: ChipGoal, nowMs: number): string {
  return `${whereIs(goal, new Date(nowMs))} · ${whenIs(goal, nowMs)}`
}
