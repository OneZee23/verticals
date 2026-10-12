/* A goal's shot size: one line saying the plan and what it took, a
   popover with the plan as a compact field ("1x45-120"); the field is saved as it loses focus. */
import type { KeyboardEvent } from 'react'
import { computed, ref, watch } from '../../reactivity'
import { fallthrough, model } from '../../bind'
import { tracked } from '../../tracked'
import { useSetup } from '../../setup'
import { PopoverEngine } from '../../components/PopoverEngine'
import './shotSizeFields.css'

interface Props {
  expected: string[] | null
  actual: string[] | null
  onChangeExpected?: (value: string | null) => void
}

const compactToken = (token: string) => token === '<5m' ? token : token.replace(/m$/, '')
function formatCompact(shots: string[] | null): string {
  if (!shots?.length) return ''
  const counts = new Map<string, number>()
  for (const shot of shots) counts.set(shot, (counts.get(shot) ?? 0) + 1)
  return [...counts].map(([shot, count]) => `${count}x${compactToken(shot)}`).join(' ')
}

const HUMAN_SHOTS: Record<string, string> = {
  '<5m': '5-min',
  '10-15m': '15-min',
  '45-120m': 'long',
  '240-480m': 'deep',
}

function formatHuman(shots: string[] | null): string {
  if (!shots?.length) return ''
  const counts = new Map<string, number>()
  for (const shot of shots) counts.set(shot, (counts.get(shot) ?? 0) + 1)
  return [...counts].map(([shot, count]) => {
    const name = HUMAN_SHOTS[shot] ?? compactToken(shot)
    return `${count} × ${name} shot${count === 1 ? '' : 's'}`
  }).join(' + ')
}

export const ShotSizeFields = tracked(function ShotSizeFields(raw: Props & Record<string, unknown>) {
  const { expected, actual, onChangeExpected, ...attrs } = raw
  const s = useSetup({ expected, actual, onChangeExpected }, (props) => {
    const summary = computed(() => {
      const expected = formatHuman(props.expected)
      const actual = formatHuman(props.actual)
      if (!expected && !actual) return 'Set shot size…'
      if (!expected) return `Actual ${actual}`
      return actual ? `${expected}, actual ${actual}` : expected
    })

    const draft = ref(formatCompact(props.expected))
    watch(() => props.expected, (value) => { draft.value = formatCompact(value) })

    function commit() {
      const value = draft.value.trim()
      if (value !== formatCompact(props.expected)) props.onChangeExpected?.(value || null)
    }

    /* A native `blur` listener on the input itself: the popover closing takes the focused field out of the page, and the
       blur that fires then reaches a native listener, where React drops events that arrive during its commit. */
    const input = ref<HTMLInputElement | null>(null)
    watch(input, (node) => node?.addEventListener('blur', commit), { flush: 'sync' })
    return { summary, draft, input }
  })

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'Enter') return
    event.preventDefault()
    ;(event.target as HTMLInputElement).blur()
  }

  return (
    <section {...fallthrough({ className: 'shot-size-fields', 'data-role': 'size-fields' }, attrs)}>
      <PopoverEngine
        placement="top-start"
        fixedWidth={260}
        surfaceClass="shot-size-fields__popover"
        trigger={({ open }) => (
          <button
            type="button"
            className="shot-size-fields__summary"
            data-role="size-summary"
            aria-label="Edit shot size"
            aria-expanded={String(open) as 'true' | 'false'}
          >{s.summary.value}</button>
        )}
      >
        <label className="shot-size-fields__field">
          <span className="shot-size-fields__label">Plan</span>
          <input
            {...model(s.draft, s.input)}
            className="shot-size-fields__input"
            data-role="size-expected"
            placeholder="1x45-120"
            onKeyDown={onKeyDown}
          />
        </label>
        {actual?.length ? (
          <p className="shot-size-fields__actual" data-role="size-actual">
            <span>Actual</span>
            <strong>{formatHuman(actual)}</strong>
          </p>
        ) : null}
      </PopoverEngine>
    </section>
  )
})
