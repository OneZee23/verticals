/* The dev panel for the goal column's layout: a trigger and, open, a slider,
   text field or select per CSS variable, by section. Two roots, so no attribute fallthrough. */
import { ChangeField } from '../ChangeField'
import type { FormEvent } from 'react'
import { AppIcon } from './AppIcon'
import { flushNow, ref } from '../reactivity'
import {
  GOAL_LAYOUT_SECTIONS,
  devGoalLayout,
  resetGoalLayout,
  saveGoalLayout,
  type GoalLayoutControl,
} from '../lib/devGoalLayout'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './devGoalLayoutPanel.css'

export const DevGoalLayoutPanel = tracked(function DevGoalLayoutPanel() {
  const s = useSetup({}, () => {
    const open = ref(false)

    function controlId(control: GoalLayoutControl): string {
      return `goal-layout-${control.variable.slice(2)}`
    }

    function update(control: GoalLayoutControl, event: Event): void {
      const input = event.target as HTMLInputElement | HTMLSelectElement
      if (control.kind === 'text') {
        if (!input.value.trim()) return
        devGoalLayout[control.variable] = input.value
      } else {
        const value = Number(input.value)
        if (!Number.isFinite(value)) return
        devGoalLayout[control.variable] = value
      }
      saveGoalLayout()
    }
    return { open, controlId, update }
  })

  // The slider is controlled: its new value is drawn before the event ends, or React puts the old one back.
  function onSlider(control: GoalLayoutControl, event: FormEvent<HTMLInputElement>): void {
    s.update(control, event.nativeEvent)
    flushNow()
  }

  return (
    <>
      <button
        type="button"
        className="dev-goal-layout-panel__trigger"
        aria-label="Open goal layout settings"
        aria-expanded={s.open.value}
        onClick={() => { s.open.value = !s.open.value }}
      >Layout</button>

      {s.open.value ? (
        <aside
          className="dev-goal-layout-panel"
          data-role="dev-goal-layout-panel"
          aria-label="Goal column layout"
        >
          <header className="dev-goal-layout-panel__header">
            <div>
              <strong>Goal column layout</strong>
              <p>Live preview. Saved in this browser.</p>
            </div>
            <button type="button" className="dev-goal-layout-panel__close" aria-label="Close goal layout settings" onClick={() => { s.open.value = false }}>
              <AppIcon name="x" size={16} />
            </button>
          </header>

          {GOAL_LAYOUT_SECTIONS.map((section) => (
            <details key={section.title} open={section.open}>
              <summary>{section.title}</summary>
              {section.controls.map((control) => (
                <div key={control.variable} className="dev-goal-layout-panel__row">
                  <label htmlFor={s.controlId(control)}>{control.label}</label>
                  {control.kind === 'slider' ? (
                    <input
                      id={s.controlId(control)}
                      type="range"
                      min={control.min}
                      max={control.max}
                      step={control.step}
                      value={devGoalLayout[control.variable]}
                      onInput={(event) => onSlider(control, event)}
                    />
                  ) : control.kind === 'text' ? (
                    <ChangeField
                      id={s.controlId(control)}
                      type="text"
                      value={devGoalLayout[control.variable]}
                      onCommit={(event) => s.update(control, event)}
                    />
                  ) : (
                    <ChangeField
                      as="select"
                      id={s.controlId(control)}
                      value={devGoalLayout[control.variable]}
                      onCommit={(event) => s.update(control, event)}
                    >
                      {control.options?.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </ChangeField>
                  )}
                  {control.kind === 'slider' ? <output>{`${devGoalLayout[control.variable]}${control.unit ?? ''}`}</output> : null}
                </div>
              ))}
            </details>
          ))}

          <button type="button" className="dev-goal-layout-panel__reset" onClick={() => resetGoalLayout()}>Reset layout</button>
        </aside>
      ) : null}
    </>
  )
})
