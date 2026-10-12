/* The dev panel that tunes the deck live: a trigger and, open, the sliders. Two roots,
   so no attribute fallthrough. */
import type { FormEvent } from 'react'
import { flushNow, ref } from '../reactivity'
import { devDeck, resetDeckTuning, saveDeckTuning, type DeckTuning } from '../lib/devDeck'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './devDeckPanel.css'

export const DevDeckPanel = tracked(function DevDeckPanel() {
  const s = useSetup({}, () => {
    const open = ref(false)

    const controls: Array<{
      key: Exclude<keyof DeckTuning, 'use3D'>
      label: string
      min: number
      max: number
      step: number
      suffix: string
    }> = [
      { key: 'activeGapLeft', label: 'Active gap left', min: 0, max: 400, step: 1, suffix: 'px' },
      { key: 'activeGapRight', label: 'Active gap right', min: 0, max: 400, step: 1, suffix: 'px' },
      { key: 'dayWidth', label: 'Day width', min: 0, max: 600, step: 10, suffix: 'px' },
      { key: 'width', label: 'Card width', min: 10, max: 30, step: 1, suffix: 'vw' },
      { key: 'perspective', label: 'Perspective', min: 40, max: 5000, step: 10, suffix: 'px' },
      { key: 'rotateY', label: 'Rotate Y', min: 0, max: 70, step: 1, suffix: '°' },
      { key: 'rotateX', label: 'Rotate X', min: -45, max: 45, step: 1, suffix: '°' },
      { key: 'scale', label: 'Rest scale', min: 40, max: 100, step: 1, suffix: '%' },
      { key: 'activeRotateY', label: 'Active rotate Y', min: -10, max: 15, step: 1, suffix: '°' },
      { key: 'activeScale', label: 'Active scale', min: 60, max: 110, step: 1, suffix: '%' },
      { key: 'overlap', label: 'Overlap', min: 0, max: 30, step: 1, suffix: 'vw' },
      { key: 'offsetY', label: 'Rest vertical', min: -100, max: 100, step: 1, suffix: 'px' },
      { key: 'activeOffsetY', label: 'Active vertical', min: -100, max: 100, step: 1, suffix: 'px' },
    ]

    function update(key: Exclude<keyof DeckTuning, 'use3D'>, event: Event): void {
      const value = Number((event.target as HTMLInputElement).value)
      if (!Number.isFinite(value)) return
      devDeck[key] = value
      saveDeckTuning()
    }

    function toggle3D(event: Event): void {
      devDeck.use3D = (event.target as HTMLInputElement).checked
      saveDeckTuning()
    }
    return { open, controls, update, toggle3D }
  })

  // Controlled inputs: the new value is drawn before the event ends, or React puts the old one back.
  function onToggle3D(event: FormEvent<HTMLInputElement>): void {
    s.toggle3D(event.nativeEvent)
    flushNow()
  }
  function onRange(key: Exclude<keyof DeckTuning, 'use3D'>, event: FormEvent<HTMLInputElement>): void {
    s.update(key, event.nativeEvent)
    flushNow()
  }

  return (
    <>
      <button
        type="button"
        className="dev-deck-panel__trigger"
        aria-label="Open deck settings"
        aria-expanded={s.open.value}
        onClick={() => { s.open.value = !s.open.value }}
      >Deck</button>

      {s.open.value ? (
        <aside className="dev-deck-panel" data-role="dev-deck-panel" aria-label="Deck settings">
          <header className="dev-deck-panel__header">
            <div>
              <strong>Deck settings</strong>
              <p>Live preview only. Saved in this browser.</p>
            </div>
            <button type="button" className="dev-deck-panel__close" aria-label="Close deck settings" onClick={() => { s.open.value = false }}>×</button>
          </header>
          <label className="dev-deck-panel__toggle">
            <input type="checkbox" checked={devDeck.use3D} onChange={onToggle3D} />
            <span>3D transforms</span>
          </label>
          {s.controls.map((control) => (
            <div key={control.key} className="dev-deck-panel__row">
              <label htmlFor={`deck-${control.key}`}>{control.label}</label>
              <input
                id={`deck-${control.key}`}
                type="range"
                min={control.min}
                max={control.max}
                step={control.step}
                value={devDeck[control.key]}
                onInput={(event) => onRange(control.key, event)}
              />
              <output>{`${devDeck[control.key]}${control.suffix}`}</output>
            </div>
          ))}
          <div className="dev-deck-panel__actions">
            <button type="button" onClick={() => resetDeckTuning()}>Reset deck</button>
          </div>
        </aside>
      ) : null}
    </>
  )
})
