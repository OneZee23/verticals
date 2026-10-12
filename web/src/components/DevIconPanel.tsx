/* The dev panel for icon sizes: a trigger and, open, the sliders. Two roots, so no
   attribute fallthrough. */
import type { FormEvent } from 'react'
import { flushNow, ref } from '../reactivity'
import { AppIcon } from './AppIcon'
import {
  devIcons,
  resetIconTuning,
  saveIconTuning,
  type IconTuning,
} from '../lib/devIcons'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './devIconPanel.css'

export const DevIconPanel = tracked(function DevIconPanel() {
  const s = useSetup({}, () => {
    const open = ref(false)

    const controls: Array<{
      key: keyof IconTuning
      label: string
      min: number
      max: number
      step?: number
    }> = [
      { key: 'base', label: 'UI icons', min: 10, max: 32 },
      { key: 'arrows', label: 'Arrows', min: 8, max: 28 },
      { key: 'search', label: 'Search', min: 12, max: 40 },
      { key: 'menu', label: 'Three dots size', min: 6, max: 24 },
      { key: 'menuStroke', label: 'Three dots weight', min: 0.8, max: 2.2, step: 0.1 },
    ]

    function update(key: keyof IconTuning, event: Event): void {
      const value = Number((event.target as HTMLInputElement).value)
      if (!Number.isFinite(value)) return
      devIcons[key] = value
      saveIconTuning()
    }
    return { open, controls, update }
  })

  // Controlled inputs: the new value is drawn before the event ends, or React puts the old one back.
  function onRange(key: keyof IconTuning, event: FormEvent<HTMLInputElement>): void {
    s.update(key, event.nativeEvent)
    flushNow()
  }

  return (
    <>
      <button
        type="button"
        className="dev-icon-panel__trigger"
        aria-label="Open icon settings"
        aria-expanded={s.open.value}
        onClick={() => { s.open.value = !s.open.value }}
      >Icons</button>

      {s.open.value ? (
        <aside className="dev-icon-panel" data-role="dev-icon-panel" aria-label="Icon settings">
          <header className="dev-icon-panel__header">
            <div>
              <strong>Icon settings</strong>
              <p>Live preview. Saved in this browser.</p>
            </div>
            <button type="button" className="dev-icon-panel__close" aria-label="Close icon settings" onClick={() => { s.open.value = false }}>
              <AppIcon name="x" size={16} />
            </button>
          </header>
          {s.controls.map((control) => (
            <div key={control.key} className="dev-icon-panel__row">
              <label htmlFor={`icon-${control.key}`}>{control.label}</label>
              <input
                id={`icon-${control.key}`}
                type="range"
                min={control.min}
                max={control.max}
                step={control.step ?? 1}
                value={devIcons[control.key]}
                onInput={(event) => onRange(control.key, event)}
              />
              <output>{`${devIcons[control.key]}${control.key === 'menuStroke' ? '' : 'px'}`}</output>
            </div>
          ))}
          <div className="dev-icon-panel__actions">
            <button type="button" onClick={() => resetIconTuning()}>Reset icons</button>
          </div>
        </aside>
      ) : null}
    </>
  )
})
