/* The desktop app's page zoom buttons. */
import { ref } from '../reactivity'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './devZoomPanel.css'

export const DevZoomPanel = tracked(function DevZoomPanel(attrs: Record<string, unknown>) {
  const s = useSetup({}, () => {
    // The desktop app's page zoom (desktop/macos/Verticals.swift); a browser has its own ⌘+ and shows no buttons.
    type ZoomWindow = Window & {
      webkit?: { messageHandlers?: { zoom?: { postMessage(value: number): void } } }
      verticalsPageZoom?: number
    }
    const host = window as ZoomWindow
    const bridge = host.webkit?.messageHandlers?.zoom
    const STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2]
    const zoom = ref(host.verticalsPageZoom ?? 1)

    function set(value: number): void {
      zoom.value = value
      bridge?.postMessage(value)
    }

    function step(direction: 1 | -1): void {
      const next = direction > 0
        ? STEPS.find((s) => s > zoom.value + 0.001)
        : [...STEPS].reverse().find((s) => s < zoom.value - 0.001)
      if (next !== undefined) set(next)
    }
    return { bridge, STEPS, zoom, set, step }
  })
  if (!s.bridge) return null
  const zoom = s.zoom.value
  return (
    <div {...fallthrough({ className: 'dev-zoom', role: 'group', 'aria-label': 'Zoom' }, attrs)}>
      <button type="button" aria-label="Zoom out" disabled={zoom <= s.STEPS[0]!} onClick={() => s.step(-1)}>−</button>
      <button type="button" className="dev-zoom__value" title="Actual size" onClick={() => s.set(1)}>{`${Math.round(zoom * 100)}%`}</button>
      <button type="button" aria-label="Zoom in" disabled={zoom >= s.STEPS[s.STEPS.length - 1]!} onClick={() => s.step(1)}>+</button>
    </div>
  )
})
