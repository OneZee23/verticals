/* The weeks under your hand: the spans in a row at the regular columns' width, the
   last one's edge showing, and the floating column wide over them at its side, 2 px from the window's edges. A step moves
   the row by one span and the spans past each edge come along; the floating column changes sides with motion. The board
   turns into the spans from the corner held, the held column's name dissolving into its date and the floating column
   lifting out of its place; they go back the same way. */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from '../reactivity'
import { Column } from './Column'
import { store } from '../store'
import { rowLeft, spanRow, spans, spanWidth } from '../lib/spans'
import { commandFilter } from '../lib/commandFilter'
import { ghostOf } from '../lib/ghost'
import { reducedMotion, timing } from '../lib/motion'
import { escape as leaveMove } from '../lib/moving'
import { bindRef, fallthrough, sx } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './spansBoard.css'

export const SpansBoard = tracked(function SpansBoard(attrs: Record<string, unknown>) {
  const s = useSetup({}, () => {
    const root = ref<HTMLElement | null>(null)
    const row = ref<HTMLElement | null>(null)
    const float = ref<HTMLElement | null>(null)
    const ghosts = ref<HTMLElement | null>(null)
    const width = computed(() => spanWidth())
    const left = computed(() => rowLeft())
    const floating = computed(() => store.columns.value.find((column) => column.vertical === spans.floating) ?? null)

    let floatingVertical: string | null = null

    function slideX(el: HTMLElement | null, from: number, ms: number): void {
      if (el && from) el.animate([{ transform: `translateX(${from}px)` }, { transform: 'translateX(0)' }], timing(ms, 'large'))
    }

    onMounted(() => {
      floatingVertical = spans.floating
      const intro = spans.intro
      spans.intro = null
      // Back from typing, or with reduced motion: the spans fade in.
      if (!intro || reducedMotion()) {
        root.value?.animate([{ opacity: 0 }, { opacity: 1 }], timing(intro ? 120 : 260, 'large'))
        return
      }
      const now = row.value?.querySelector<HTMLElement>('[data-span-now]')
      const shift = intro.held && now ? intro.held.left - now.getBoundingClientRect().left : 0
      ghosts.value?.appendChild(intro.ghost)
      intro.ghost.animate(
        [{ transform: 'none', opacity: 1, filter: 'blur(0)' }, { transform: `translateX(${-shift}px)`, opacity: 0, filter: 'blur(2px)' }],
        timing(400, 'large', { fill: 'forwards' }),
      ).onfinish = () => intro.ghost.remove()
      row.value?.animate([{ transform: `translateX(${shift}px)`, opacity: 0 }, { transform: 'none', opacity: 1 }], timing(400, 'large'))
      now?.querySelector('.column-header')?.animate(
        [{ opacity: 0, filter: 'blur(3px)' }, { opacity: 1, filter: 'blur(0)' }],
        timing(250, 'large'),
      )
      const to = float.value?.getBoundingClientRect()
      if (float.value && to && intro.float) {
        float.value.animate([{ transform: `translateX(${intro.float.left - to.left}px)`, boxShadow: 'none' }, { transform: 'none' }], timing(400, 'large'))
      }
    })

    /* The spans go back into the board the way they came: a still copy fades over the board, and the floating column
       flies back to its place in it; typing only fades them. */
    onBeforeUnmount(() => {
      const el = root.value
      if (!el) return
      const typing = !!commandFilter.text
      const ms = typing ? 260 : 400
      const ghost = ghostOf(el)
      ghost.style.zIndex = getComputedStyle(el).zIndex
      document.body.appendChild(ghost)
      ghost.animate([{ opacity: 1 }, { opacity: 0 }], timing(ms, 'large', { fill: 'forwards' })).onfinish = () => ghost.remove()
      if (typing || reducedMotion() || !floatingVertical) return
      const lifted = ghost.querySelector<HTMLElement>('.spans-board__float')
      const vertical = floatingVertical
      requestAnimationFrame(() => {
        const target = document.querySelector(`[data-role="column-strip"] > .pattern-vertical-board__column[data-vertical="${vertical}"]`)
        if (!lifted || !target) return
        const dx = target.getBoundingClientRect().left - lifted.getBoundingClientRect().left
        lifted.animate([{ transform: 'none' }, { transform: `translateX(${dx}px)`, boxShadow: 'none' }], timing(ms, 'large', { fill: 'forwards' }))
      })
    })

    /* The mode opened from a column's middle bar has no goal in the hand to cancel: Esc lets go of a pick and then ends
       it, as it does from the field, from anywhere on the screen. What has its own Esc keeps it: a drag cancels itself, a
       goal opened or a window, a menu and the text being typed take it first. */
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing) return
      if (store.state.drag.id || store.state.drag.pending || store.state.drag.settling || store.state.openGoalId !== null) return
      const target = event.target instanceof HTMLElement ? event.target : null
      if (target?.closest('input, textarea, select, [contenteditable="true"], [role="dialog"], [role="menu"]')) return
      if (leaveMove()) event.preventDefault()
    }
    onMounted(() => window.addEventListener('keydown', onKeyDown))
    onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))

    /* One span on or back: the row keeps its place for a frame, then slides by one span. */
    watch(() => spans.offset, async (now, was) => {
      if (was === undefined || now === was) return
      await nextTick()
      slideX(row.value, (now - was) * width.value, 300)
    })

    /* The floating column goes to the other side and the row makes room, both with motion. */
    watch(() => spans.side, async () => {
      const rowFrom = row.value?.getBoundingClientRect().left ?? 0
      const floatFrom = float.value?.getBoundingClientRect().left ?? 0
      await nextTick()
      slideX(row.value, rowFrom - (row.value?.getBoundingClientRect().left ?? rowFrom), 300)
      slideX(float.value, floatFrom - (float.value?.getBoundingClientRect().left ?? floatFrom), 300)
    }, { flush: 'pre' })

    return { root, row, float, ghosts, width, left, floating }
  })
  const width = s.width.value
  const floating = s.floating.value
  return (
    <div
      {...fallthrough({
        ref: bindRef(s.root),
        className: `spans-board spans-board--float-${spans.side}`,
        'data-role': 'spans-board',
        'data-vertical': spans.vertical ?? '',
        style: sx({ '--span-width': `${width}px` }),
      }, attrs)}
    >
      <div className="spans-board__view">
        <div
          ref={bindRef(s.row)}
          className="card-stack pattern-vertical-board pattern-vertical-board--flat spans-board__row"
          style={sx({ left: `${s.left.value}px`, width: `${spanRow.value.length * width}px` })}
          data-role="spans-row"
        >
          {spanRow.value.map((span) => span.column ? (
            <Column
              key={span.n}
              vertical={span.column.vertical}
              title={span.date}
              subLabel={span.how}
              end={span.end}
              goals={span.column.goals}
              periodKey={span.column.periodKey}
              addPlaceholder={span.column.addPlaceholder}
              span
              data-span-start={span.start}
              data-span-edge={span.edge ?? undefined}
              data-span-now={span.n === 0 ? '' : undefined}
            />
          ) : (
            <div key={span.n} className="spans-board__blank" aria-hidden="true"></div>
          ))}
        </div>
      </div>
      <div ref={bindRef(s.ghosts)} className="spans-board__ghosts" aria-hidden="true"></div>
      {floating ? (
        <div
          ref={bindRef(s.float)}
          className="card-stack pattern-vertical-board pattern-vertical-board--flat spans-board__float vt-shadow"
          data-role="spans-floating"
        >
          <Column
            vertical={floating.vertical}
            title={floating.title}
            subLabel={floating.subLabel}
            shorter={floating.shorter}
            label={floating.label}
            goals={floating.goals}
            periodKey={floating.periodKey}
            addPlaceholder={floating.addPlaceholder}
            active
            floating
          />
        </div>
      ) : null}
    </div>
  )
})
