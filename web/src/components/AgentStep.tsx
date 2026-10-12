/* The phrase of what the agent is doing, inside the field beside the turning line; a phrase stays at least 150 ms, so a
   fast turn never flickers. */
import { onBeforeUnmount, ref, watch } from '../reactivity'
import { agentChat } from '../lib/agentChat'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import { Transition } from '../Transition'
import './agentStep.css'

interface Props {
  shown: boolean
}

export const AgentStep = tracked(function AgentStep({ shown, ...attrs }: Props & Record<string, unknown>) {
  const s = useSetup({ shown }, (props) => {
    const words = ref(agentChat.step)
    let since = 0
    let timer: ReturnType<typeof setTimeout> | null = null
    watch(() => agentChat.step, (step) => {
      if (timer) clearTimeout(timer)
      const wait = Math.max(0, 150 - (performance.now() - since))
      timer = setTimeout(() => { words.value = step; since = performance.now() }, wait)
    })
    // It comes in with the phrase the agent is on, not the one it was on when it last stood here.
    watch(() => props.shown, (on) => {
      if (!on) return
      if (timer) clearTimeout(timer)
      words.value = agentChat.step
      since = performance.now()
    })
    onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
    return { words }
  })
  const own = { className: 'circle-field__step', 'data-role': 'agent-step', role: 'status', 'aria-live': 'polite' }
  return (
    <Transition name="agent-step">
      {shown ? (
        <span {...fallthrough(own, attrs)}>
          <Transition name="agent-step-words" mode="out-in">
            <span key={s.words.value} className="circle-field__step-words">{s.words.value}</span>
          </Transition>
        </span>
      ) : null}
    </Transition>
  )
})
