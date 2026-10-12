/* An agent answer's own Undo, in the look of the notice's Undo; pressed, it takes the answer back and becomes Redo. */
import type { MouseEvent } from 'react'
import { computed } from '../reactivity'
import { answerUndo, putBack, takeBack } from '../lib/answerUndo'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup, withDefaults } from '../setup'
import './answerUndo.css'

interface Props {
  answer?: string | null
  /** The pill is on the answer's message, which stays in front while the answer is taken back. */
  stays?: boolean
}
const DEFAULTS = { stays: false }

export const AnswerUndo = tracked(function AnswerUndo(raw: Props & Record<string, unknown>) {
  const { answer, stays, ...attrs } = withDefaults(raw, DEFAULTS)
  const s = useSetup({ answer, stays }, (props) => {
    const entry = computed(() => (props.answer ? answerUndo.entries[props.answer] : undefined))
    const undone = computed(() => entry.value?.state === 'undone')

    function press(): void {
      if (entry.value) void (undone.value ? putBack(entry.value.id, props.stays) : takeBack(entry.value.id, props.stays))
    }
    return { entry, undone, press }
  })
  const entry = s.entry.value
  if (!entry || entry.state === 'spent') return null
  const own = {
    type: 'button',
    className: 'field-notice__action answer-undo',
    'data-role': 'answer-undo',
    'data-state': entry.state,
    disabled: entry.busy,
    onClick: (event: MouseEvent) => {
      event.stopPropagation()
      s.press()
    },
  }
  return <button {...fallthrough(own, attrs)}>{s.undone.value ? 'Redo' : 'Undo'}</button>
})
