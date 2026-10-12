/* A step of the goal's menu (web/src/components/MoveStep.tsx, docs/design-handoff S5.P5): it takes the menu's place, with
   ‹ and its name at the top, and is never a window of its own. Date lists its levels; each level is a plain list forward
   of its periods' starts; a specific date opens the most basic calendar; Into a goal finds the goal to sit under and makes
   this one its last step. */
import { Fragment, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent } from 'react'
import { computed, nextTick, onMounted, ref, watch } from '../reactivity'
import { AppIcon } from './AppIcon'
import { store, todayIso } from '../store'
import { findGoals, type GoalCard } from '../lib/api'
import { findGoal } from '../lib/boardIndex'
import { VERTICAL_SCALES, MONTH_NAMES, verticalRank, type VerticalScale } from '../lib/periods'
import { isoDate, localDate, periodKeyFor } from '../lib/schedule'
import { bindRef, cx, fallthrough, model } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './moveStep.css'

export type MoveStepName = 'date' | 'week' | 'month' | 'quarter' | 'year' | 'calendar' | 'under'

interface Props {
  id: string
  step: MoveStepName
  onGo?: (step: MoveStepName | null) => void
  onDone?: () => void
}

const TITLES: Record<MoveStepName, string> = {
  date: 'Move to a date', week: 'Week', month: 'Month', quarter: 'Quarter', year: 'Year', calendar: 'Date', under: 'Into a goal',
}
const LEVELS = ['week', 'month', 'quarter', 'year'] as const
const WEEKDAY_LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

/* The levels: only the starts of their periods, forward from this one (S5.P5.013, .014). */
interface Row { key: string; how: string; day: string; month: string; date: Date; own: boolean; newMonth: boolean }

export const MoveStep = tracked(function MoveStep(raw: Props & Record<string, unknown>) {
  const { id, step, onGo, onDone, ...attrs } = raw
  const s = useSetup({ id, step, onGo, onDone }, (props) => {
    const root = ref<HTMLElement | null>(null)
    const goal = computed(() => findGoal(store.state.board, props.id) ?? null)
    const today = computed(() => localDate(todayIso()))

    function back(): void {
      props.onGo?.(props.step === 'date' || props.step === 'under' ? null : 'date')
    }
    function schedule(scale: VerticalScale, day: Date): void {
      void store.scheduleGoalQuick(props.id, scale, periodKeyFor(scale, day), isoDate(day))
      props.onDone?.()
    }

    function starts(scale: VerticalScale, count: number): Date[] {
      const t = today.value
      const first = scale === 'week' ? new Date(t.getFullYear(), t.getMonth(), t.getDate() - ((t.getDay() + 6) % 7))
        : scale === 'month' ? new Date(t.getFullYear(), t.getMonth(), 1)
          : scale === 'quarter' ? new Date(t.getFullYear(), Math.floor(t.getMonth() / 3) * 3, 1)
            : new Date(t.getFullYear(), 0, 1)
      return Array.from({ length: count }, (_, i) => {
        if (scale === 'week') return new Date(first.getFullYear(), first.getMonth(), first.getDate() + 7 * i)
        if (scale === 'month') return new Date(first.getFullYear(), first.getMonth() + i, 1)
        if (scale === 'quarter') return new Date(first.getFullYear(), first.getMonth() + 3 * i, 1)
        return new Date(first.getFullYear() + i, 0, 1)
      })
    }
    const rows = computed<Row[]>(() => {
      const scale = props.step
      if (scale !== 'week' && scale !== 'month' && scale !== 'quarter' && scale !== 'year') return []
      const own = goal.value?.vertical === scale ? goal.value.period_key : null
      let lastMonth = -1
      return starts(scale, scale === 'week' ? 13 : scale === 'year' ? 5 : 8).map((d, i) => {
        const how = i === 0 ? 'This' : i === 1 ? 'Next' : String(i)
        const key = periodKeyFor(scale, d)
        if (scale === 'week') {
          // The month in full, once: on the first week that starts in it (S5.P5.015).
          const month = d.getMonth() !== lastMonth ? MONTH_NAMES[d.getMonth()]! : ''
          // A small gap before each month after the first (S5.P5.F04).
          const newMonth = i > 0 && !!month
          lastMonth = d.getMonth()
          return { key, how, day: String(d.getDate()), month, date: d, own: key === own, newMonth }
        }
        const label = scale === 'month' ? `${MONTH_NAMES[d.getMonth()]}${d.getFullYear() !== today.value.getFullYear() ? ` ${d.getFullYear()}` : ''}`
          : scale === 'quarter' ? `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}` : String(d.getFullYear())
        return { key, how, day: '', month: label, date: d, own: key === own, newMonth: false }
      })
    })

    /* The calendar: its month on the left of the arrows, Monday first; today black, the goal's own day on its green, past
       days grey and still yours (S5.P5.017, .038, .040). */
    const shown = ref(new Date(today.value.getFullYear(), today.value.getMonth(), 1))
    const monthLabel = computed(() => `${MONTH_NAMES[shown.value.getMonth()]!.slice(0, 3)} ’${String(shown.value.getFullYear()).slice(2)}`)
    const days = computed(() => {
      const first = shown.value
      const lead = (first.getDay() + 6) % 7
      const count = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
      const own = goal.value?.vertical === 'day' ? goal.value.anchor_date : null
      const todayKey = isoDate(today.value)
      return [
        ...Array.from({ length: lead }, () => null),
        ...Array.from({ length: count }, (_, i) => {
          const date = new Date(first.getFullYear(), first.getMonth(), i + 1)
          const key = isoDate(date)
          return { date, key, today: key === todayKey, own: key === own, past: key < todayKey }
        }),
      ]
    })
    function stepMonth(n: number): void {
      shown.value = new Date(shown.value.getFullYear(), shown.value.getMonth() + n, 1)
    }

    /* Under: the goal it sits under now first, then the goals of each vertical from the nearest; typing narrows it to the
       names that match, each with its vertical (S5.P5.010-.012, .027). */
    const query = ref('')
    const found = ref<GoalCard[] | null>(null)
    let findVersion = 0
    watch(query, async (q) => {
      const version = ++findVersion
      // The search starts at three letters; before that the board's own goals are narrowed here.
      if (q.trim().length < 3) { found.value = null; return }
      const result = await findGoals(q.trim()).catch(() => null)
      if (version === findVersion) found.value = result ? result.goals : []
    })
    function subtree(): Set<string> {
      const out = new Set<string>([props.id])
      const board = store.state.board
      const walk = (id: string) => {
        for (const kid of board?.children[id] ?? []) { out.add(kid.id); walk(kid.id) }
      }
      walk(props.id)
      return out
    }
    const candidates = computed(() => {
      const own = goal.value
      const skip = subtree()
      const pool = found.value ?? (store.state.board?.columns.flatMap((c) => c.goals) ?? [])
      const seen = new Set<string>()
      const q = query.value.trim().toLowerCase()
      const list = pool.filter((g) => {
        if (skip.has(g.id) || g.id === own?.parent_id || seen.has(g.id) || g.done_at) return false
        if (q && !found.value && !g.title.toLowerCase().includes(q)) return false
        seen.add(g.id)
        return true
      })
      const rank = (g: GoalCard) => (g.vertical ? VERTICAL_SCALES.indexOf(g.vertical as VerticalScale) : 99)
      const from = own?.vertical ? verticalRank(own.vertical as VerticalScale) : 0
      return found.value ? list : [...list].sort((a, b) => Math.abs(rank(a) - from) - Math.abs(rank(b) - from))
    })
    const nowUnder = computed(() => {
      const parentId = goal.value?.parent_id
      return parentId ? findGoal(store.state.board, parentId) ?? null : null
    })
    function parts(title: string): Array<{ text: string; match: boolean }> {
      const q = query.value.trim()
      if (!q) return [{ text: title, match: false }]
      const at = title.toLowerCase().indexOf(q.toLowerCase())
      if (at < 0) return [{ text: title, match: false }]
      return [
        { text: title.slice(0, at), match: false },
        { text: title.slice(at, at + q.length), match: true },
        { text: title.slice(at + q.length), match: false },
      ].filter((p) => p.text)
    }
    function under(target: GoalCard): void {
      // Under a smaller vertical's goal it takes that goal's period first (S5.P6.002); otherwise it keeps its own dates.
      const own = goal.value?.vertical
      const smaller = !!own && !!target.vertical && verticalRank(own as VerticalScale) > verticalRank(target.vertical as VerticalScale)
      void (smaller ? store.combineInto(props.id, target.id) : store.reparentQuick(props.id, target.id))
      props.onDone?.()
    }
    function out(): void {
      void store.reparentQuick(props.id, null)
      props.onDone?.()
    }
    function verticalName(h: string | null): string {
      return h ? h === 'decade' ? '3 years' : h[0]!.toUpperCase() + h.slice(1) : 'Inbox'
    }
    function onSearchKey(event: ReactKeyboardEvent): void {
      if (event.key === 'Enter' && candidates.value[0]) {
        event.preventDefault()
        under(candidates.value[0])
      }
    }
    function onKey(event: ReactKeyboardEvent): void {
      const inField = (event.target as HTMLElement).matches('input')
      if (event.key === 'ArrowLeft' && !inField) {
        event.preventDefault()
        back()
      }
    }

    /* Each step takes the focus, so ↑ ↓ ↵ and ← work at once (S5.P5.021). */
    async function focusFirst(): Promise<void> {
      await nextTick()
      root.value?.querySelector<HTMLElement>('input, [role="menuitem"]:not([data-back])')?.focus()
    }
    onMounted(focusFirst)
    watch(() => props.step, focusFirst)

    return {
      root, back, schedule, rows, monthLabel, days, stepMonth, query, candidates, nowUnder, parts, under, out, verticalName,
      onSearchKey, onKey,
    }
  })

  const stop = (fn: () => void) => (event: ReactMouseEvent) => {
    event.stopPropagation()
    fn()
  }
  const rows = s.rows.value
  const nowUnder = s.nowUnder.value
  const query = s.query.value

  return (
    <div {...fallthrough({
      ref: bindRef(s.root), className: 'move-step', 'data-step': step, 'data-role': 'move-step', onKeyDown: s.onKey,
    }, attrs)}>
      <div className="move-step__head">
        <button type="button" className="move-step__back" data-back="" role="menuitem" aria-label={`Back from ${TITLES[step]}`} onClick={stop(s.back)}>
          <AppIcon name="chevron-left" size={14} /><span className="move-step__title">{TITLES[step]}</span>
        </button>
        {step === 'calendar' ? (
          <span className="move-step__month">
            {`${s.monthLabel.value} `}
            <button type="button" className="move-step__arrow" aria-label="Previous month" onClick={stop(() => s.stepMonth(-1))}><AppIcon name="chevron-left" size={14} /></button>
            <button type="button" className="move-step__arrow" aria-label="Next month" onClick={stop(() => s.stepMonth(1))}><AppIcon name="chevron-right" size={14} /></button>
          </span>
        ) : null}
      </div>

      {step === 'date' ? (
        <>
          {LEVELS.map((level) => (
            <button key={level} type="button" role="menuitem" className="dropdown__item goal-actions__item" data-level={level}
              onClick={stop(() => onGo?.(level))}>
              <span>{TITLES[level]}</span><span data-role="submenu-arrow" aria-hidden="true"><AppIcon name="chevron-right" size={14} /></span>
            </button>
          ))}
          <hr />
          <button type="button" role="menuitem" className="dropdown__item goal-actions__item" data-level="calendar" onClick={stop(() => onGo?.('calendar'))}>
            <span>Specific date</span><span data-role="submenu-arrow" aria-hidden="true"><AppIcon name="chevron-right" size={14} /></span>
          </button>
        </>
      ) : rows.length ? (
        <>
          {rows.map((row) => (
            <button key={row.key} type="button" role="menuitem"
              className={cx('move-step__row', { 'move-step__row--own': row.own, 'move-step__row--table': step === 'week', 'move-step__row--month': row.newMonth })}
              data-period-key={row.key}
              onClick={stop(() => s.schedule(step as VerticalScale, row.date))}>
              <span className={cx('move-step__how', { 'move-step__how--word': !/^\d+$/.test(row.how) })}>{row.how}</span>
              {step === 'week' ? <span className="move-step__day">{row.day}</span> : null}
              <span className="move-step__name">{row.month}</span>
            </button>
          ))}
        </>
      ) : step === 'calendar' ? (
        <div className="move-step__calendar">
          {/* The letters repeat (T, S), so each takes a key made anew on each drawing. */}
          {WEEKDAY_LETTERS.map((d) => (
            <span key={d + Math.random()} className="move-step__weekday" aria-hidden="true">{d}</span>
          ))}
          {s.days.value.map((cell, i) => (!cell ? (
            <span key={i} aria-hidden="true"></span>
          ) : (
            <button key={i} type="button" role="menuitem" className={cx('move-step__date', { 'is-today': cell.today, 'is-own': cell.own, 'is-past': cell.past })}
              data-date={cell.key} onClick={stop(() => s.schedule('day', cell.date))}>{cell.date.getDate()}</button>
          )))}
        </div>
      ) : step === 'under' ? (
        <>
          <label className="move-step__search">
            <AppIcon name="search" size={16} />
            <input {...model(s.query)} type="text" placeholder="Find a goal" aria-label="Find the goal to move under" data-role="move-under-search"
              onKeyDown={s.onSearchKey} />
            {query ? (
              <button type="button" className="move-step__clear" aria-label="Clear" onClick={stop(() => { s.query.value = '' })}><AppIcon name="x-circle" size={16} /></button>
            ) : null}
          </label>
          {nowUnder && !query ? (
            <>
              <p className="move-step__label">Now under</p>
              <div className="move-step__goal move-step__goal--now" data-color={nowUnder.color ?? undefined}>
                <span className="move-step__square" style={{ background: nowUnder.color ?? '#d9d9dc' }}></span>
                <span className="move-step__goal-title">{nowUnder.title}</span>
                <span className="move-step__vertical">{s.verticalName(nowUnder.vertical)}</span>
              </div>
              <button type="button" role="menuitem" className="move-step__goal move-step__goal--out" data-parent-id="" onClick={stop(s.out)}>
                <span></span><span className="move-step__goal-title">Not under any goal</span><span></span>
              </button>
              <hr />
            </>
          ) : null}
          <div className="move-step__list">
            {s.candidates.value.slice(0, 60).map((target) => (
              <button key={target.id} type="button" role="menuitem" className="move-step__goal" data-parent-id={target.id}
                onClick={stop(() => s.under(target))}>
                <span className="move-step__square" style={{ background: target.color ?? '#d9d9dc' }}></span>
                <span className="move-step__goal-title">
                  {s.parts(target.title).map((part, i) => (part.match ? <strong key={i}>{part.text}</strong> : <Fragment key={i}>{part.text}</Fragment>))}
                </span>
                <span className="move-step__vertical">{s.verticalName(target.vertical)}</span>
              </button>
            ))}
          </div>
        </>
      ) : null}
    </div>
  )
})
