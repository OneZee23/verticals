// A change you can see is undone in place, its own movement played backwards (docs/design/board-undo.md). The board
// already draws the move of a tick (`lib/completionMotion.ts`) and the flight of a drop (`lib/dragSettle.ts`); a goal put
// back by undo or redo glides from the place it stood in to the place it now has, and the cards around it slide to make
// room, in one movement: the cards are read where they stand, the change is made, and each card that is somewhere else
// starts from where it was. A card that was not on the screen fades in. Under reduced motion, nothing.
//
// What moves is the card (`.goal-card`), as in `completionMotion.ts`: each carries its own background, which a row moved
// inside it would slide under. The goal the step is about, when it changes column, flies as a dropped goal does: a column
// clips what lies outside it, so a card sliding in from another column would come out of the column's edge. A copy of the
// card as it was stands where it stood and travels over the board, taking the look of the card it becomes as it goes (a card
// in the open column is bigger than one in a closed column: `lib/flightMorph.ts`), so it sits exactly on the real card, which
// has been hidden, and gives way to it in the one frame the flight ends: never two cards, never two titles. A goal that
// leaves fades out where it stood.
//
// A move the system starts lands exactly (kk-motion): the pace and the curve are the board's own tokens (`lib/motion.ts`),
// the ones a card moved by a tick uses.
import { nextTick } from '../reactivity'
import { legsOf } from './flightMorph'
import { reducedMotion, timing } from './motion'

const CARD = '.goal-card[data-goal-id]:not([data-ghost])'
/** The place that adds a goal at the foot of a column: it slides with the cards, or it would jump. */
const ADD = '.card-stack > .column-add-row'
/** The animation's name, so a second change turns a card from where it is, and a test can tell it from a tick's own. */
const GLIDE = 'undo-glide'

interface Spot {
  rect: DOMRect
  /** The column (or span) the card stands in. */
  column: string | null
}

/** A goal is found by its id; the foot of a column by itself. */
type Key = string | Element

const columnOf = (el: HTMLElement): string | null => el.closest<HTMLElement>('[data-vertical]')?.dataset.vertical ?? null

/** Where everything that can move stands. A goal drawn twice (a step, and its card in another column) counts once, where
 *  the first copy is. */
function readSpots(): Map<Key, Spot> {
  const spots = new Map<Key, Spot>()
  for (const card of document.querySelectorAll<HTMLElement>(CARD)) {
    const id = card.dataset.goalId
    if (id && card.getClientRects().length && !spots.has(id)) spots.set(id, { rect: card.getBoundingClientRect(), column: columnOf(card) })
  }
  for (const add of document.querySelectorAll<HTMLElement>(ADD)) {
    if (add.getClientRects().length) spots.set(add, { rect: add.getBoundingClientRect(), column: columnOf(add) })
  }
  return spots
}

/** A card with its looks written into it, so it keeps them wherever it is put; it answers no lookup for the real goal. */
function frozenCopy(card: HTMLElement): HTMLElement {
  const copy = card.cloneNode(true) as HTMLElement
  const sources = [card, ...card.querySelectorAll<HTMLElement>('*')]
  const copies = [copy, ...copy.querySelectorAll<HTMLElement>('*')]
  sources.forEach((node, index) => {
    const style = getComputedStyle(node)
    const target = copies[index]!
    for (const property of style) target.style.setProperty(property, style.getPropertyValue(property))
    target.style.pointerEvents = 'none'
    target.style.visibility = 'visible'
    for (const name of ['id', 'data-goal-id', 'data-row-key', 'data-role', 'data-cap']) target.removeAttribute(name)
  })
  return copy
}

/** The goal a step is about, as it stands before the change: a copy of its card, and where it is. */
interface Departure {
  copy: HTMLElement
  rect: DOMRect
}

function departureOf(id: string): Departure | null {
  const card = [...document.querySelectorAll<HTMLElement>(`${CARD}[data-goal-id="${CSS.escape(id)}"]`)].find((el) => el.getClientRects().length)
  return card ? { copy: frozenCopy(card), rect: card.getBoundingClientRect() } : null
}

/** The copy, placed where the card stood, over everything. */
function stand(from: Departure, id: string): HTMLElement {
  const { copy, rect } = from
  copy.dataset.flightFor = id
  copy.setAttribute('aria-hidden', 'true')
  Object.assign(copy.style, {
    position: 'fixed', left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px`,
    margin: '0', boxSizing: 'border-box', zIndex: '2147483647', transform: 'none', translate: 'none', scale: 'none',
  })
  document.body.appendChild(copy)
  return copy
}

/** The goal flies to its new column: the copy travels and grows into the card it becomes, and in the frame the flight ends it
 *  gives way to the card itself. Both are driven by the same clock, so the copy goes and the card comes in the same frame,
 *  with no help from a script that could be late; the card is out of sight until then. */
function fly(card: HTMLElement, id: string, from: Departure): void {
  const to = card.getBoundingClientRect()
  const copy = stand(from, id)
  const { duration = 300, easing } = timing('shape', 'play')
  const total = Number(duration)
  const legs = legsOf(copy, from.rect, card, to)
  const flights: Animation[] = []
  if (legs) {
    for (const [at, leg] of legs.entries()) {
      ;(leg.el as HTMLElement).style.transformOrigin = leg.origin
      const end = leg.radius ? { transform: leg.end, borderRadius: leg.radius } : { transform: leg.end }
      flights.push(leg.el.animate([{ transform: 'none' }, end], { duration: total, easing, fill: 'forwards', id: at === 0 ? GLIDE : `${GLIDE}-part` }))
    }
  } else {
    // Not the same card (one is being edited): the copy only travels, and the card is as it is when it arrives.
    flights.push(copy.animate(
      [{ translate: '0 0' }, { translate: `${to.left - from.rect.left}px ${to.top - from.rect.top}px` }],
      { duration: total, easing, id: GLIDE, fill: 'forwards' },
    ))
  }
  // Out of sight at the end, and the card in sight: one clock for both. `steps` holds the first value to the last instant.
  copy.animate([{ opacity: 1 }, { opacity: 0 }], { duration: total, easing: 'steps(1, end)', fill: 'forwards' })
  card.animate([{ visibility: 'hidden' }, { visibility: 'hidden' }], { duration: total })
  const land = (): void => copy.remove()
  flights[0]!.addEventListener('finish', land)
  flights[0]!.addEventListener('cancel', land)
}

/** A goal that leaves fades out where it stood while the cards close up. */
function leave(from: Departure, id: string): void {
  const copy = stand(from, id)
  const gone = copy.animate([{ opacity: 1 }, { opacity: 0 }], { ...timing('fade', 'small'), fill: 'forwards' })
  gone.addEventListener('finish', () => copy.remove())
  gone.addEventListener('cancel', () => copy.remove())
}

/** The goal the step is about travels over the cards it passes, as a goal checked off does (`goalCard.css`, `data-gliding`). */
function slide(el: HTMLElement, dx: number, dy: number, lead: boolean): void {
  for (const old of el.getAnimations()) if (old.id === 'row-glide' || old.id === GLIDE) old.cancel()
  const glide = el.animate([{ translate: `${dx}px ${dy}px` }, { translate: '0 0' }], { ...timing('shape', 'play'), id: GLIDE })
  if (!lead) return
  el.dataset.gliding = ''
  const land = (): void => {
    if (!el.getAnimations().some((other) => other.id === GLIDE && other !== glide)) delete el.dataset.gliding
  }
  glide.addEventListener('finish', land)
  glide.addEventListener('cancel', land)
}

const arrive = (el: HTMLElement): Animation => el.animate([{ opacity: 0 }, { opacity: 1 }], timing('rise', 'small'))

function play(before: Map<Key, Spot>, lead: string | null, departing: Departure | null): void {
  const now = readSpots()
  for (const [key, here] of now) {
    const el = typeof key === 'string' ? document.querySelector<HTMLElement>(`${CARD}[data-goal-id="${CSS.escape(key)}"]`) : (key as HTMLElement)
    if (!el) continue
    const was = before.get(key)
    if (!was) {
      arrive(el)
      continue
    }
    const dx = was.rect.left - here.rect.left
    const dy = was.rect.top - here.rect.top
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue
    if (key === lead && departing && here.column !== was.column) fly(el, key, departing)
    else if (here.column === was.column || typeof key !== 'string') slide(el, dx, dy, key === lead)
    else arrive(el) // a goal of the family that changed column with the one the step is about
  }
  if (lead && departing && !now.has(lead)) leave(departing, lead)
}

/** Whether anything stands somewhere other than `before` says, or was not drawn then. */
function moved(before: Map<Key, Spot>): boolean {
  const now = readSpots()
  if (now.size !== before.size) return true
  for (const [key, spot] of now) {
    const was = before.get(key)
    if (!was || Math.abs(was.rect.left - spot.rect.left) >= 1 || Math.abs(was.rect.top - spot.rect.top) >= 1) return true
  }
  return false
}

const frame = (): Promise<void> => new Promise((resolve) => requestAnimationFrame(() => resolve()))
/** About a second of frames: longer than any write takes, and then the glide is not worth waiting for. */
const GIVE_UP_FRAMES = 60

/** Runs `run` and plays the glide for the change it makes; `lead` is the goal the change is about. The change reaches the
 *  board at once when the write places the goal before it asks (a drag's landing) and with the answer when the board is
 *  loaded again; either way the first frame that draws a card somewhere else is the one the glide starts from, before that
 *  frame is painted, so nothing jumps. */
export async function glideThrough<T>(run: () => Promise<T>, lead: string | null = null): Promise<T> {
  if (reducedMotion() || typeof document === 'undefined') return run()
  const before = readSpots()
  const departing = lead ? departureOf(lead) : null
  let finished = false
  const job = run().finally(() => { finished = true })
  job.catch(() => undefined)
  // The first look is in the task that made the change: a board that moved as the key was handled is read once it is drawn,
  // before any frame, so no frame can show a card in its new place that the glide has not started from.
  await nextTick()
  for (let frames = 0; frames < GIVE_UP_FRAMES; frames += 1) {
    if (moved(before)) {
      play(before, lead, departing)
      break
    }
    if (finished) break
    await frame()
    await nextTick()
  }
  return job
}
