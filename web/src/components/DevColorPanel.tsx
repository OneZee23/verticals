/* The dev panel for the value colours: a trigger and, open, a picker and an
   opacity per colour and role. Two roots, so no attribute fallthrough. */
import type { FormEvent } from 'react'
import { AppIcon } from './AppIcon'
import { flushNow, ref } from '../reactivity'
import {
  DEV_PALETTE,
  devPalette,
  resetDevPalette,
  saveDevPalette,
  type DevPaletteRole,
} from '../lib/devPalette'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './devColorPanel.css'

type PaletteKey = (typeof DEV_PALETTE)[number]['key']
const ROLES: DevPaletteRole[] = ['card', 'box', 'tick']

export const DevColorPanel = tracked(function DevColorPanel() {
  const s = useSetup({}, () => {
    const open = ref(false)
    const copied = ref(false)
    let copiedTimer: ReturnType<typeof setTimeout> | undefined

    function setColor(key: PaletteKey, role: DevPaletteRole, event: Event) {
      devPalette[key][role].color = (event.target as HTMLInputElement).value
      saveDevPalette()
    }

    function setOpacity(key: PaletteKey, role: DevPaletteRole, event: Event) {
      const input = event.target as HTMLInputElement
      const value = Math.max(0, Math.min(100, Number(input.value) || 0))
      input.value = String(value)
      devPalette[key][role].opacity = value / 100
      saveDevPalette()
    }

    async function copyColors(): Promise<void> {
      const lines = DEV_PALETTE.map((item) => {
        const values = (['card', 'box', 'tick'] as DevPaletteRole[]).map((role) => {
          const value = devPalette[item.key][role]
          return `${role}=${value.color} ${Math.round(value.opacity * 100)}%`
        })
        return `${item.label}: ${values.join(' | ')}`
      })
      const text = `Verticals developer colors\n${lines.join('\n')}`
      try {
        await navigator.clipboard.writeText(text)
      } catch {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        textarea.remove()
      }
      copied.value = true
      if (copiedTimer) clearTimeout(copiedTimer)
      copiedTimer = setTimeout(() => { copied.value = false }, 2000)
    }
    return { open, copied, setColor, setOpacity, copyColors }
  })

  // Controlled inputs: the new value is drawn before the event ends, or React puts the old one back.
  function onColor(key: PaletteKey, role: DevPaletteRole, event: FormEvent<HTMLInputElement>): void {
    s.setColor(key, role, event.nativeEvent)
    flushNow()
  }
  function onOpacity(key: PaletteKey, role: DevPaletteRole, event: FormEvent<HTMLInputElement>): void {
    s.setOpacity(key, role, event.nativeEvent)
    flushNow()
  }

  return (
    <>
      <button
        type="button"
        className="dev-color-panel__trigger"
        aria-label="Open developer color panel"
        aria-expanded={s.open.value}
        onClick={() => { s.open.value = !s.open.value }}
      >Colors</button>

      {s.open.value ? (
        <aside className="dev-color-panel" data-role="dev-color-panel" aria-label="Developer colors">
          <header className="dev-color-panel__header">
            <div>
              <strong>Developer colors</strong>
              <p>Live preview only. Saved in this browser.</p>
            </div>
            <button type="button" className="dev-color-panel__close" aria-label="Close color panel" onClick={() => { s.open.value = false }}><AppIcon name="x" size={16} /></button>
          </header>
          <div className="dev-color-panel__legend">
            <span>Card</span><span>Box</span><span>Tick</span>
          </div>
          {DEV_PALETTE.map((item) => (
            <div key={item.key} className="dev-color-panel__row">
              <span className="dev-color-panel__name">
                <i style={{ backgroundColor: item.source }} aria-hidden="true" />
                {` ${item.label}`}
              </span>
              {ROLES.map((role) => (
                <label key={role} className="dev-color-panel__picker">
                  <span className="sr-only">{`${item.label} ${role} color`}</span>
                  <input type="color" value={devPalette[item.key][role].color} onInput={(event) => onColor(item.key, role, event)} />
                  <span className="dev-color-panel__opacity-field">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="1"
                      inputMode="numeric"
                      value={Math.round(devPalette[item.key][role].opacity * 100)}
                      aria-label={`${item.label} ${role} opacity percentage`}
                      onInput={(event) => onOpacity(item.key, role, event)}
                    />
                    <small>%</small>
                  </span>
                </label>
              ))}
            </div>
          ))}
          <div className="dev-color-panel__actions">
            <button type="button" className="dev-color-panel__copy" onClick={() => void s.copyColors()}>{s.copied.value ? 'Copied' : 'Copy colours'}</button>
            <button type="button" className="dev-color-panel__reset" onClick={() => resetDevPalette()}>Reset selected colors</button>
          </div>
        </aside>
      ) : null}
    </>
  )
})
