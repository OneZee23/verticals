// The words you selected on the page, for the agent (docs/design/agent-fixes.md, fix 5). The prompt promises them ("any
// text they selected") and the first chat script sent them; moving the conversation into the app dropped them. Turning to
// the field moves the focus and the page's selection with it, so the selection is remembered as it is made. A press
// anywhere but the field lets it go, and the message you send takes it once.

const MAX = 2000

let held = ''

/** The selection's words, unless it stands in a text field (the field's own draft is not page text). */
function selected(): string {
  const active = document.activeElement
  if (active instanceof HTMLTextAreaElement || active instanceof HTMLInputElement) return ''
  return (window.getSelection()?.toString() ?? '').trim().slice(0, MAX)
}

function remember(): void {
  const words = selected()
  if (words) held = words
}

function release(event: PointerEvent): void {
  const target = event.target instanceof Element ? event.target : null
  if (!target?.closest('.circle-field')) held = ''
}

if (typeof document !== 'undefined') {
  document.addEventListener('selectionchange', remember)
  document.addEventListener('pointerdown', release, true)
}

/** What you selected, for the message you send now; it goes once. */
export function takeSelection(): string {
  const words = held
  held = ''
  return words
}
