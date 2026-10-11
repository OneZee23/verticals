// Verticals.app awaits `window.verticalsBeforeQuit()` before it stops the backend, so edits still
// waiting out their debounce reach the API first (desktop/macos/Verticals.swift).
type Flush = () => Promise<unknown> | void

declare global {
  interface Window { verticalsBeforeQuit?: () => Promise<unknown> }
}

const flushes = new Set<Flush>()

/** Waits for every save still in its debounce, or in flight, to reach the API. */
export const flushPending = (): Promise<unknown> => Promise.all([...flushes].map((flush) => flush()))

window.verticalsBeforeQuit = flushPending

/** Registers a pending-save flush for the app's quit; returns the unregister. */
export function onBeforeQuit(flush: Flush): () => void {
  flushes.add(flush)
  return () => { flushes.delete(flush) }
}
