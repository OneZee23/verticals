/* A task written today, in the Inbox's centre: its goal above it at a step's size, or
   "Looking for its goal…" in grey while the agent looks. A click opens the task; its square completes it; pressed and
   moved, it is carried (lib/inboxCarry.ts). */
import type { KeyboardEvent, MouseEvent } from 'react'
import { computed, onBeforeUnmount, onMounted, ref } from '../reactivity'
import { GoalAffordance } from '../kit-ext/goal-affordance/GoalAffordance'
import type { InboxGoal } from '../lib/api'
import { completeInboxGoal } from '../lib/inbox'
import { goalWashInk } from '../lib/goalColor'
import { devPaletteFor, rgbaFromHex } from '../lib/devPalette'
import { isPrivate } from '../lib/privacy'
import { openWindow } from '../lib/windows'
import { pressCard, wasCarried } from '../lib/inboxCarry'
import { bindRef, cx, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup, withDefaults } from '../setup'
import './inboxCard.css'

interface Props {
  item: InboxGoal
  finding?: boolean
}
const DEFAULTS = { finding: false }

export const InboxCard = tracked(function InboxCard(raw: Props & Record<string, unknown>) {
  const { item, finding, ...attrs } = withDefaults(raw, DEFAULTS)
  const s = useSetup({ item, finding }, (props) => {
    const root = ref<HTMLElement | null>(null)
    const color = computed(() => (props.finding ? null : props.item.value_color))
    /* The goal's square takes the value's colour as the board paints it (GoalAffordance). */
    const mark = computed(() => {
      if (!color.value) return '#e5e5e5'
      const box = devPaletteFor(color.value)?.box
      return box ? rgbaFromHex(box.color, box.opacity) : `rgb(${goalWashInk(color.value).washRgb})`
    })
    const hidden = computed(() => isPrivate(props.item.id))

    function open(event: { currentTarget: EventTarget | null }): void {
      if (wasCarried()) return
      openWindow({ kind: 'goal', target: props.item.id, title: props.item.title }, event.currentTarget as Element)
    }

    // The card's own native listener: pressCard takes the card from the event's currentTarget,
    // which on a React event's nativeEvent is the root React listens on.
    const press = (event: PointerEvent) => pressCard(event, props.item)
    let bound: HTMLElement | null = null
    onMounted(() => {
      bound = root.value
      bound?.addEventListener('pointerdown', press)
    })
    onBeforeUnmount(() => bound?.removeEventListener('pointerdown', press))
    return { root, color, mark, hidden, open }
  })

  function onKeyDown(event: KeyboardEvent): void {
    if (event.key !== 'Enter') return
    event.preventDefault()
    s.open(event)
  }

  return (
    <article
      {...fallthrough({
        ref: bindRef(s.root),
        className: cx('inbox-card', { 'inbox-card--private': s.hidden.value }),
        'data-goal-id': item.id,
        'data-role': 'inbox-card',
        role: 'button',
        tabIndex: 0,
        onClick: (event: MouseEvent) => s.open(event),
        onKeyDown,
      }, attrs)}
    >
      {finding || item.parent ? (
        <div className={cx('inbox-card__goal', { 'inbox-card__goal--finding': finding })}>
          <i className="inbox-card__mark" style={{ background: s.mark.value }} aria-hidden="true"></i>
          {finding
            ? <span data-role="inbox-finding">Looking for its goal…</span>
            : <span data-role="inbox-goal">{item.parent!.title}</span>}
        </div>
      ) : null}
      <div className="inbox-card__row">
        <span className="inbox-card__square" onClick={(event) => event.stopPropagation()}>
          <GoalAffordance kind="square" color={s.color.value} onToggle={(done: boolean) => { if (done) void completeInboxGoal(item.id) }} />
        </span>
        <p className="inbox-card__words">{item.title}</p>
      </div>
    </article>
  )
})
