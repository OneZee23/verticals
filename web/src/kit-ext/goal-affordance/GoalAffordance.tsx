/* A goal's square or milestone ring: the kit's small checkbox in the
   goal's colours; a press on it completes the goal and never reaches the card under it. */
import type { MouseEvent } from 'react'
import { computed, onMounted, ref, watch } from '../../reactivity'
import { goalSquare } from '../../lib/look'
import { bindRef, cx, fallthrough, sx } from '../../bind'
import { tracked } from '../../tracked'
import { listen, useSetup, withDefaults } from '../../setup'
import './goal-affordance.css'

interface Props {
  kind: 'square' | 'ring'
  checked?: boolean
  done?: number
  total?: number
  color?: string | null
  onToggle?: (value: boolean) => void
}
const DEFAULTS = { checked: false, done: 0, total: 0, color: null }

export const GoalAffordance = tracked(function GoalAffordance(raw: Props & Record<string, unknown>) {
  const { kind, checked, done, total, color, onToggle, ...attrs } = withDefaults(raw, DEFAULTS)
  const s = useSetup({ kind, checked, done, total, color, onToggle }, (props) => {
    const input = ref<HTMLInputElement | null>(null)
    const label = ref<HTMLLabelElement | null>(null)
    // Stopped where it happens, so no listener on the card under it hears the press.
    listen(label, 'pointerdown', (event) => event.stopPropagation())

    function onChange(event: Event) {
      props.onToggle?.((event.target as HTMLInputElement).checked)
    }

    const squareStyle = computed(() => {
      const { box, check } = goalSquare(props.color)
      return {
        '--goal-affordance-background': box,
        '--goal-affordance-hover-background': box,
        '--goal-affordance-check-color': check,
        '--goal-affordance-hover-check-color': '#000000',
      }
    })

    // The box's `checked` property is set only when the prop changes, and a click is left alone: a box the parent doesn't
    // answer (the Inbox's) stays ticked, where a controlled React input would be put back.
    onMounted(() => {
      if (input.value) input.value.checked = props.checked
    })
    watch(() => props.checked, (value) => {
      if (input.value) input.value.checked = value
    }, { flush: 'post' })
    return { input, label, onChange, squareStyle }
  })
  return (
    <label
      {...fallthrough({
        className: cx('checkbox checkbox--size-s goal-affordance', `goal-affordance--${kind}`),
        'data-role': kind === 'ring' ? 'milestone-ring' : 'leaf-square',
        'data-cap': 'complete',
        role: 'checkbox',
        'aria-checked': String(checked),
        'aria-label': kind === 'ring' ? `Milestone progress ${done} of ${total}` : 'Mark complete',
        onClick: (event: MouseEvent) => event.stopPropagation(),
        ref: bindRef(s.label),
      }, attrs)}
    >
      <input ref={bindRef(s.input)} type="checkbox" className="checkbox__input" onChange={(event) => s.onChange(event.nativeEvent)} />
      <span className="checkbox__box goal-affordance__square" data-role="checkbox-box" aria-hidden="true" style={sx(s.squareStyle.value)} />
    </label>
  )
})
