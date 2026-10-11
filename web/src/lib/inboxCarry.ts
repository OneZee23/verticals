// Carrying a task in the Inbox onto the field (Inbox and Documents redesign, round 5, frames c2–c3). Press a card or a row
// and move it past 10 px: it follows the hand, as the Inbox's tile. Held over the field, the field becomes the pill that
// takes it (S5.P3.002); let go there and it waits in the field as a goal does in Move (docs/design/inbox-carry-stack.md):
// `park` hands it to `lib/moving.ts`, `MovingStack.vue` draws the card, and Backspace, Tab, Esc and typing work on it as
// they do on the board. Let go anywhere else, or Esc, and it goes back to its place. The card waiting in the field is
// carried out by the same press: no board is in view to land it on, so the Inbox's drag takes it.
import { reactive } from 'vue'
import type { InboxGoal } from './api'
import { moving, park, unpark } from './moving'

const THRESHOLD = 10
const TILE_HEIGHT = 92

export const carry = reactive({
  item: null as InboxGoal | null,
  /** Where the card is drawn while it moves: its top-left corner in the window. */
  x: 0,
  y: 0,
  width: 0,
  /** Held over the field. */
  over: false,
})

let start: { x: number; y: number; dx: number; dy: number; item: InboxGoal; width: number } | null = null
/** A press that became a carry is not a click. The next press clears it: a carry let go elsewhere swallows no later click. */
let carried = false
export const wasCarried = (): boolean => { const was = carried; carried = false; return was }

function overField(x: number, y: number): boolean {
  const shape = document.querySelector<HTMLElement>('.circle-field__shape')?.getBoundingClientRect()
  return !!shape && x >= shape.left - 24 && x <= shape.right + 24 && y >= shape.top - 24 && y <= shape.bottom + 24
}

function onMove(event: PointerEvent): void {
  if (!start) return
  if (!carry.item) {
    if (Math.hypot(event.clientX - start.x, event.clientY - start.y) < THRESHOLD) return
    carry.item = start.item
    carry.width = start.width
    carried = true
  }
  carry.x = event.clientX - start.dx
  carry.y = event.clientY - start.dy
  carry.over = overField(event.clientX, event.clientY)
  event.preventDefault()
}

function finish(keep: boolean): void {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  window.removeEventListener('pointercancel', onCancel)
  window.removeEventListener('keydown', onKey, true)
  const item = carry.item
  if (item) {
    // Let go over the field it waits there; anywhere else, or on Esc, it goes back to its place, from the field too
    // (S5.P4.008): a key reaches no release of the board's, so this does it.
    if (keep && carry.over) park(item.id)
    else if (moving.goalId === item.id) unpark()
  }
  carry.item = null
  carry.over = false
  start = null
}
function onUp(): void { finish(true) }
function onCancel(): void { finish(false) }
function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && carry.item) { event.preventDefault(); event.stopPropagation(); finish(false) }
}

export function pressCard(event: PointerEvent, item: InboxGoal): void {
  if (event.button !== 0 || (event.target as HTMLElement).closest('.goal-affordance')) return
  carried = false
  const card = event.currentTarget as HTMLElement
  const box = card.getBoundingClientRect()
  // In the hand a task is the Inbox's tile, a quarter of the desk, held where it was taken: from the desk, and from the
  // card waiting in the field.
  const desk = document.querySelector('.inbox-desk')
  const width = desk ? (desk.clientWidth - 92 - 48) / 4 : box.width
  const dx = Math.min(event.clientX - box.left, width - 24)
  const dy = Math.min(event.clientY - box.top, TILE_HEIGHT - 24)
  start = { x: event.clientX, y: event.clientY, dx, dy, item, width }
  window.addEventListener('pointermove', onMove, { passive: false })
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onCancel)
  window.addEventListener('keydown', onKey, true)
}
