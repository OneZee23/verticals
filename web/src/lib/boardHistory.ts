// The board's history (docs/design/board-undo.md): one step for each change you made, in memory, from the moment the app
// opened. ⌘Z takes the last step back and ⇧⌘Z plays the last one taken back forward again; a new change empties what
// could still be played forward. A reload empties it all: "since the app opened".
//
// A step is made by `track` around a write the store makes (a tick, a patch, a move, a reparent), or by the delete in
// `lib/goalDelete.ts`; it holds the shots of the goals before and after (`lib/boardShots.ts`) and sets them back through
// `lib/boardRestore.ts`. Undo and redo write through the store's own verbs, never through `track`, so they record nothing.
//
// What a step says when its change leaves the view is `lib/historyWords.ts`; where it says it is `lib/fieldNotice.ts`.
import { nextTick } from 'vue'
import { toast } from '@konstantinopolskii/vue'
import { findGoal } from './boardIndex'
import { currentShot, settleShots, type Outcome, type RestorePorts, type Target } from './boardRestore'
import { changeBetween, changed, parentDiffers, placeDiffers, shotOf, shotsOf, slotDiffers, type Shot } from './boardShots'
import { dismiss, say, type Segment } from './fieldNotice'
import { changeWords, putBackWords } from './historyWords'
import { messageForError } from './scheduleFeedback'
import { glideThrough } from './undoGlide'

export interface Step {
  /** The goal the step is about. */
  id: string
  /** The words for a notice when the change leaves the view; `null` when there is nothing to say. `redo` is the change
   *  as it was first made, so it is also what is said when it was just made. */
  words(direction: 'undo' | 'redo'): Segment[] | null
  /** Whether goals move on the board when the step is applied, so the rows glide (`lib/undoGlide.ts`). */
  glides(direction: 'undo' | 'redo'): boolean
  undo(): Promise<Outcome>
  redo(): Promise<Outcome>
}

export interface HistoryPorts extends RestorePorts {
  /** A goal in the hand: the keys wait for it to land. */
  busy: () => boolean
}

/** More than anyone goes back; the oldest steps go first. */
const LIMIT = 500

const done: Step[] = []
const undone: Step[] = []
let ports: HistoryPorts | null = null

/** The store binds its own verbs once, as `bindSpansDrag` does for the spans. */
export function bindBoardHistory(p: HistoryPorts): void {
  ports = p
}

/** The bound verbs, for the modules that make steps of their own (`lib/goalSteps.ts`). */
export function historyPorts(): HistoryPorts {
  if (!ports) throw new Error('the board history is not bound to the store')
  return ports
}

/** A goal the app took away itself (a request written in the Inbox that goes on as a conversation) has no step to take back. */
export function forgetStep(id: string): void {
  for (const list of [done, undone]) {
    for (let at = list.length - 1; at >= 0; at -= 1) if (list[at]!.id === id) list.splice(at, 1)
  }
}

// --- one at a time -----------------------------------------------------------------------------------------------

let chain: Promise<void> = Promise.resolve()
function enqueue(job: () => Promise<void>): Promise<void> {
  const next = chain.then(job, job)
  chain = next.catch(() => undefined)
  return next
}

/** Writes the person started that have not finished: a ⌘Z pressed in their wake waits for them to be steps. */
const writing = new Set<Promise<unknown>>()

// --- seeing --------------------------------------------------------------------------------------------------------

interface Box { left: number; top: number; right: number; bottom: number }

/** Whether the middle of `el` is inside the window and inside every ancestor that clips it (a column that scrolls, a stack
 *  folded shut): what is cut off is not in your view. */
function inView(el: HTMLElement): boolean {
  const rect = el.getBoundingClientRect()
  if (!el.getClientRects().length) return false
  const x = rect.left + rect.width / 2
  const y = rect.top + rect.height / 2
  const clip: Box = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight }
  for (let up = el.parentElement; up && up !== document.body; up = up.parentElement) {
    const style = getComputedStyle(up)
    if (style.overflowX === 'visible' && style.overflowY === 'visible') continue
    const box = up.getBoundingClientRect()
    clip.left = Math.max(clip.left, box.left)
    clip.top = Math.max(clip.top, box.top)
    clip.right = Math.min(clip.right, box.right)
    clip.bottom = Math.min(clip.bottom, box.bottom)
  }
  return x >= clip.left && x <= clip.right && y >= clip.top && y <= clip.bottom
}

/** Whether the board (or the Inbox) shows the goal in view now. */
export function seen(id: string): boolean {
  const card = `.goal-card[data-goal-id="${CSS.escape(id)}"]:not([data-ghost]), :is(.inbox-card, .inbox-tile)[data-goal-id="${CSS.escape(id)}"]`
  return [...document.querySelectorAll<HTMLElement>(card)].some(inView)
}

const frame = (): Promise<void> => new Promise((resolve) => requestAnimationFrame(() => resolve()))

/** A change that leaves your view is said in the field; one you can see is not. The board has drawn the change by the
 *  time this looks, and the check is what is on the screen, so it holds for every kind of change. */
async function announce(step: Step, direction: 'undo' | 'redo'): Promise<void> {
  await nextTick()
  await frame()
  if (typeof document === 'undefined' || seen(step.id)) return
  const words = step.words(direction)
  if (!words) return
  say(words, direction === 'redo'
    ? { label: 'Undo', run: () => void undo() }
    : { label: 'Redo', run: () => void redo() })
}

// --- steps ---------------------------------------------------------------------------------------------------------

/** Puts a step on the history: what could be played forward is gone, and the change is said if it left the view. */
export function record(step: Step): void {
  dismiss() // a notice still up is about an older step, and its Undo would take this one back
  done.push(step)
  if (done.length > LIMIT) done.shift()
  undone.length = 0
  void announce(step, 'redo')
}

function goalTitle(id: string): string {
  const board = ports?.board() ?? null
  const hit = findGoal(board, id)
  if (hit) return hit.title
  for (const chain of Object.values(board?.ancestors ?? {})) {
    const ancestor = chain.find((a) => a.id === id)
    if (ancestor) return ancestor.title
  }
  return 'a goal'
}

interface Pair {
  before: Shot
  after: Shot
}

/** The step for goals that went from `before` to `after`. `mainId` is the one the gesture was about. */
function editStep(pairs: Pair[], mainId: string): Step {
  const first = (targets: Target[]): Target[] => [...targets.filter((t) => t.shot.id === mainId), ...targets.filter((t) => t.shot.id !== mainId)]
  const befores = pairs.map((p) => ({ shot: p.before, change: changeBetween(p.before, p.after) }))
  const afters = pairs.map((p) => ({ shot: p.after, change: changeBetween(p.after, p.before) }))
  const main = pairs.find((p) => p.before.id === mainId) ?? pairs[0]!
  const structural = pairs.some(({ before, after }) => parentDiffers(before, after) || placeDiffers(before, after) || slotDiffers(before, after))
  return {
    id: mainId,
    glides: () => structural,
    words: (direction) => direction === 'undo'
      ? putBackWords(main.before.title)
      : changeWords(main.before, main.after, goalTitle),
    undo: () => settleShots(ports!, first(befores), 'back'),
    redo: () => settleShots(ports!, first(afters), 'forward'),
  }
}

/** Runs a write that makes its own step (a delete): the keys wait for it, as for any write, and the step it hands back
 *  goes on the history once the write has finished. `null`: it changed nothing, or failed. */
export function makeStep(run: () => Promise<Step | null>): Promise<void> {
  const job = run().then((step) => {
    if (step) record(step)
  })
  writing.add(job)
  const forget = (): void => void writing.delete(job)
  job.then(forget, forget)
  return job
}

/** The shots of `before`'s goals as the board holds them now. */
function readAfter(p: HistoryPorts, before: Shot[]): Map<string, Shot> {
  const board = p.board()
  const now = new Map<string, Shot>()
  for (const shot of before) {
    const hit = shotOf(board, shot.id)
    if (hit) now.set(shot.id, hit)
  }
  return now
}

/** Runs a write the person started (`run` is the store's own verb) and, once it has finished, records what it changed on
 *  `id`, and with `family` on everything under it that the board carries. A write that failed, or changed nothing, is not a
 *  step. `extend` adds to the step what only the write knows (the occurrence a tick made, `lib/repeatSteps.ts`). */
export function track(id: string, run: () => Promise<void>, family = false, extend?: (step: Step) => Step): Promise<void> {
  const p = ports
  if (!p) return run()
  return makeStep(async () => {
    const before = shotsOf(p.board(), id, family)
    await run()
    const head = before[0]
    if (!head || head.id !== id) return null // the goal was not on the board when the gesture began
    let after = readAfter(p, before)
    const seenNow = after.get(id)
    if (!seenNow || !changed(head, seenNow)) {
      // The goal left the board, or the board has not heard of the change (a move into a period it does not show waits for
      // the change feed): the server knows. The board is loaded again before the change is said, so that what is on the
      // screen when the line is chosen is what the change left.
      const now = await currentShot(p, id, true).catch(() => null)
      if (!now || !changed(head, now)) return null
      if (seenNow) {
        await p.reloadBoard()
        after = readAfter(p, before)
      }
      if (!after.has(id) || !changed(head, after.get(id)!)) after.set(id, now)
    }
    const pairs = before.flatMap((shot) => {
      const there = after.get(shot.id)
      return there && changed(shot, there) ? [{ before: shot, after: there }] : []
    })
    if (!pairs.some((pair) => pair.before.id === id)) return null
    const step = editStep(pairs, id)
    return extend ? extend(step) : step
  })
}

// --- undo and redo -------------------------------------------------------------------------------------------------

/** A step that could not be done is kept for another try, and given up on the second: the person has been told why, and the
 *  steps behind it should not wait on it for ever. */
const failures = new WeakMap<Step, number>()

async function apply(direction: 'undo' | 'redo'): Promise<void> {
  await Promise.allSettled([...writing])
  const from = direction === 'undo' ? done : undone
  const to = direction === 'undo' ? undone : done
  const step = from.pop()
  if (!step) return
  dismiss() // whatever a notice offered is being done now
  const run = (): Promise<Outcome> => (direction === 'undo' ? step.undo() : step.redo())
  let outcome: Outcome
  try {
    outcome = step.glides(direction) ? await glideThrough(run, step.id) : await run()
  } catch (err) {
    toast(messageForError(err))
    outcome = 'retry'
  }
  if (outcome === 'retry') {
    const tries = (failures.get(step) ?? 0) + 1
    failures.set(step, tries)
    if (tries >= 2) outcome = 'drop'
  }
  if (outcome === 'done') to.push(step)
  else if (outcome === 'retry') from.push(step)
  if (outcome === 'done') await announce(step, direction)
}

export function undo(): Promise<void> {
  return enqueue(() => apply('undo'))
}

export function redo(): Promise<void> {
  return enqueue(() => apply('redo'))
}

// --- the keys ------------------------------------------------------------------------------------------------------

const APPLE = typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent)
const NOT_TEXT = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file', 'image'])

/** Where ⌘Z means the field's own undo: a text input, a text area, a select, anything editable. A checkbox you have just
 *  ticked keeps the focus and is not one of them. */
export function editsText(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target instanceof HTMLInputElement) return !NOT_TEXT.has(target.type)
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true
  return target.isContentEditable
}

/** ⌘Z / ⇧⌘Z on a Mac, Ctrl+Z / Ctrl+Shift+Z elsewhere. The Z is the key's letter, so a layout that has it elsewhere (QWERTZ)
 *  still means its own Z; a layout with no Latin letter on the key (Cyrillic) is read by the key's place, as `privacy.ts` does. */
export function historyKey(event: KeyboardEvent): 'undo' | 'redo' | null {
  const isZ = /^[a-z]$/i.test(event.key) ? event.key.toLowerCase() === 'z' : event.code === 'KeyZ'
  if (event.altKey || !isZ) return null
  const modifier = APPLE ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey
  return modifier ? (event.shiftKey ? 'redo' : 'undo') : null
}

/** Listens on the window; returns the function that stops it. */
export function startHistoryKeys(): () => void {
  const onKeyDown = (event: KeyboardEvent): void => {
    const action = historyKey(event)
    if (!action || event.defaultPrevented || event.isComposing || event.repeat) return
    // Inside a text field the keys stay the field's own, and a goal in the hand waits to land.
    if (editsText(event.target) || ports?.busy()) return
    event.preventDefault()
    void (action === 'undo' ? undo() : redo())
  }
  window.addEventListener('keydown', onKeyDown)
  return () => window.removeEventListener('keydown', onKeyDown)
}
