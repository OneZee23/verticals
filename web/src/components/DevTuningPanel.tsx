/* The dev panel for every motion and look knob: a trigger and, open, a slider or
   text field per knob, by section. Two roots, so no attribute fallthrough. */
import type { FormEvent } from 'react'
import { AppIcon } from './AppIcon'
import { flushNow, ref } from '../reactivity'
import { knobSections, resetKnobs, setKnob, tuning, type Knob } from '../lib/tuning'
import { ChangeField } from '../ChangeField'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './devTuningPanel.css'

export const DevTuningPanel = tracked(function DevTuningPanel() {
  const s = useSetup({}, () => {
    const open = ref(false)

    function update(knob: Knob, event: Event): void {
      const input = event.target as HTMLInputElement
      if (typeof knob.value === 'number') {
        const value = Number(input.value)
        if (Number.isFinite(value)) setKnob(knob.key, value)
      } else if (input.value.trim()) {
        setKnob(knob.key, input.value.trim())
      }
    }
    return { open, update }
  })

  // The slider is controlled: its new value is drawn before the event ends, or React puts the old one back.
  function onRange(knob: Knob, event: FormEvent<HTMLInputElement>): void {
    s.update(knob, event.nativeEvent)
    flushNow()
  }

  return (
    <>
      <button
        type="button"
        className="dev-tuning-panel__trigger"
        aria-label="Open motion settings"
        aria-expanded={s.open.value}
        onClick={() => { s.open.value = !s.open.value }}
      >Motion</button>

      {s.open.value ? (
        <aside className="dev-tuning-panel" data-role="dev-tuning-panel" aria-label="Motion and look settings">
          <header className="dev-tuning-panel__header">
            <div>
              <strong>Motion and look</strong>
              <p>Live preview. Saved in this browser.</p>
            </div>
            <button type="button" className="dev-tuning-panel__close" aria-label="Close motion settings" onClick={() => { s.open.value = false }}>
              <AppIcon name="x" size={16} />
            </button>
          </header>

          {knobSections.map((section) => (
            <details key={section.title}>
              <summary>{section.title}</summary>
              {section.knobs.map((knob) => (
                <div key={knob.key} className="dev-tuning-panel__row">
                  <label htmlFor={`tuning-${knob.key}`}>{knob.label}</label>
                  {typeof knob.value === 'number' ? (
                    <>
                      <input
                        id={`tuning-${knob.key}`}
                        type="range"
                        min={knob.min}
                        max={knob.max}
                        step={knob.step}
                        value={tuning[knob.key]}
                        onInput={(event) => onRange(knob, event)}
                      />
                      <output>{`${tuning[knob.key]}${knob.unit ?? ''}`}</output>
                    </>
                  ) : (
                    <ChangeField
                      id={`tuning-${knob.key}`}
                      type="text"
                      value={tuning[knob.key]}
                      onCommit={(event) => s.update(knob, event)}
                    />
                  )}
                </div>
              ))}
            </details>
          ))}

          <button type="button" className="dev-tuning-panel__reset" onClick={() => resetKnobs()}>Reset motion and look</button>
        </aside>
      ) : null}
    </>
  )
})
