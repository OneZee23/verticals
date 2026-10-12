/* A goal as one thing in a message (web/src/components/GoalChip.tsx, docs/design/agent-chips.md): the document chip's
   anatomy and type with the goal's own square where the page is, its title in two lines at most, and one grey line saying
   where it is and when ("Today · made just now"). A click opens the goal as its window, as the Inbox opens one. The square
   is only drawn, the board's box without its input, so a press on it is a press on the chip. In privacy mode a private
   goal's title is hidden as the board hides it (lib/privacy.ts). */
import type { MouseEvent } from 'react'
import { computed } from '../reactivity'
import { chipLine, useGoalChip, useNow } from '../lib/goalChip'
import { goalSquare } from '../lib/look'
import { isPrivate } from '../lib/privacy'
import { openWindow } from '../lib/windows'
import { cx, fallthrough, sx } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import '../kit-ext/goal-affordance/goal-affordance.css'
import './goalChip.css'

interface Props {
  id: string
  label?: string
}

export const GoalChip = tracked(function GoalChip(raw: Props & Record<string, unknown>) {
  const { id, label, ...attrs } = raw
  const s = useSetup({ id, label }, (props) => {
    const { goal } = useGoalChip(() => props.id)
    const now = useNow()
    const gone = computed(() => goal.value === 'gone')
    /* The board's own rule: privacy mode is on and the goal is one it hides (a private goal and everything under it). */
    const hidden = computed(() => isPrivate(props.id))
    const data = computed(() => (goal.value && goal.value !== 'gone' ? goal.value : null))
    /* Until the goal is read the chip has the words of the link that brought it. */
    const name = computed(() => data.value?.title || props.label || 'Goal')
    const line = computed(() => (gone.value ? 'Not on the board' : data.value ? chipLine(data.value, now.value) : ''))
    const square = computed(() => {
      const { box, check } = goalSquare(data.value?.color)
      return { '--goal-affordance-background': box, '--goal-affordance-check-color': check }
    })

    function open(event: { currentTarget: EventTarget | null }): void {
      if (gone.value) return
      openWindow({ kind: 'goal', target: props.id, title: name.value }, event.currentTarget as Element)
    }
    return { gone, hidden, data, name, line, square, open }
  })
  const data = s.data.value
  return (
    <button
      {...fallthrough({
        type: 'button',
        className: cx('goal-chip', { 'goal-chip--private': s.hidden.value }),
        'data-role': 'goal-chip',
        'data-goal-id': id,
        'aria-disabled': s.gone.value ? 'true' : undefined,
        onClick: (event: MouseEvent<HTMLButtonElement>) => {
          event.stopPropagation()
          s.open(event)
        },
      }, attrs)}
    >
      <span className="goal-chip__page" aria-hidden="true">
        <span className="goal-chip__mark checkbox checkbox--size-s goal-affordance">
          <span
            className={cx('checkbox__box goal-affordance__square', { 'is-done': data?.done })}
            style={sx(s.square.value)}
            data-role="goal-chip-square"
          ></span>
        </span>
      </span>
      <span className="goal-chip__text">
        <span className="goal-chip__name">{s.name.value}</span>
        <span className="goal-chip__when" data-role="goal-chip-when">{s.line.value}</span>
      </span>
    </button>
  )
})
