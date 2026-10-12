/* An older task in the Inbox's Earlier row: its square and words, and under them the
   column it left and the day it was written. A click opens the task; its square completes it; pressed and moved, it is
   carried (lib/inboxCarry.ts). */
import type { KeyboardEvent, MouseEvent } from 'react'
import { computed, onBeforeUnmount, onMounted, ref } from '../reactivity'
import { GoalAffordance } from '../kit-ext/goal-affordance/GoalAffordance'
import type { InboxGoal } from '../lib/api'
import { completeInboxGoal, leftOn } from '../lib/inbox'
import { isPrivate } from '../lib/privacy'
import { openWindow } from '../lib/windows'
import { pressCard, wasCarried } from '../lib/inboxCarry'
import { bindRef, cx, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './inboxTile.css'

interface Props {
  item: InboxGoal
}

export const InboxTile = tracked(function InboxTile({ item, ...attrs }: Props & Record<string, unknown>) {
  const s = useSetup({ item }, (props) => {
    const root = ref<HTMLElement | null>(null)
    const hidden = computed(() => isPrivate(props.item.id))

    function open(event: { currentTarget: EventTarget | null }): void {
      if (wasCarried()) return
      openWindow({ kind: 'goal', target: props.item.id, title: props.item.title }, event.currentTarget as Element)
    }

    // The tile's own native listener: pressCard takes the tile from the event's currentTarget,
    // which on a React event's nativeEvent is the root React listens on.
    const press = (event: PointerEvent) => pressCard(event, props.item)
    let bound: HTMLElement | null = null
    onMounted(() => {
      bound = root.value
      bound?.addEventListener('pointerdown', press)
    })
    onBeforeUnmount(() => bound?.removeEventListener('pointerdown', press))
    return { root, hidden, open }
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
        className: cx('inbox-tile', { 'inbox-tile--private': s.hidden.value }),
        'data-goal-id': item.id,
        'data-role': 'inbox-tile',
        role: 'button',
        tabIndex: 0,
        onClick: (event: MouseEvent) => s.open(event),
        onKeyDown,
      }, attrs)}
    >
      <div className="inbox-tile__row">
        <span className="inbox-tile__square" onClick={(event) => event.stopPropagation()}>
          <GoalAffordance kind="square" color={item.value_color} onToggle={(done: boolean) => { if (done) void completeInboxGoal(item.id) }} />
        </span>
        <span className="inbox-tile__words">{item.title}</span>
      </div>
      <p className="inbox-tile__left">{leftOn(item)}</p>
    </article>
  )
})
