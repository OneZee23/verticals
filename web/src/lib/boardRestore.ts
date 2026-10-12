// Setting a goal back to a shot (docs/design/board-undo.md): what undo and redo do. A step of the board's history holds
// the shots of the goals it changed; this module makes the board and the server match a shot again, through the writes
// the board already makes (a tick, a patch, a schedule with a slot, a reparent, a reorder), each with its optimistic
// placement, so the live feed, the epoch guard and the motion are the ones that exist. It writes nothing of its own kind.
//
// It looks at what the goal is now and does only what differs, and of that only what the step changed (`Change`), in an
// order that stays legal:
//   1. the fields (done, title, repeat, tags, foil, expected size);
//   2. the structure: the parent and the period. A goal stays at or below its parent's scale, so which of the two goes
//      first depends on the gesture being taken back: the period first when undoing, the parent first when redoing
//      (the order the gestures made them in), and the other order when the server refuses the first with a 422;
//   3. the slot, last, because it only means something in the group the goal is in by then.
// A goal's steps follow it on the server; they are set back after it, the last in the list first, so the goal each one
// stands before is already where it belongs.
//
// A step puts a goal back only where the goal still holds what the step left. What somebody else has changed since (an
// agent working in the background, another window) stays as it is now, and the step's other changes still go back. What is
// compared is what the person sees: the done mark, the title and the other fields, the parent and the period. The place in
// the list is not: it shifts whenever a neighbour moves, so it is set only while the goal stands in the group the step left
// it in. What stayed is handed back, for the notice to say.

import { toast } from '@konstantinopolskii/vue'
import {
  ApiError, getGoal, patchGoal, reparentGoal, scheduleGoal,
  type BoardResponse, type UpdatePatch,
} from './api'
import { findGoal } from './boardIndex'
import { reorderPlacement, reparentPlacement, schedulePlacement } from './boardPlacement'
import {
  differingFields, doneDiffers, parentDiffers, placeDiffers, shotOf, shotOfCard, slotDiffers, type Change, type Shot,
} from './boardShots'
import { reorderWrite, scheduleOrdering } from './drag'
import type { VerticalScale } from './periods'
import { messageForError } from './scheduleFeedback'

export interface RestorePorts {
  /** The board the person sees, with the spans that may be open over it. */
  board: () => BoardResponse | null
  /** The store's own tick and patch, so their motion and their reloads stay. */
  completeGoal: (id: string, done: boolean) => Promise<void>
  updateGoal: (id: string, patch: UpdatePatch) => Promise<void>
  reloadBoard: () => Promise<void>
}

/** `done`: the board and the server hold the shots. `drop`: it cannot be done any more (the goal is gone, the server
 *  refused); the person has been told, and the step leaves the history. `retry`: the server could not be reached; the
 *  step stays, for another try. */
export type Outcome = 'done' | 'drop' | 'retry'

/** A goal to set to a shot, and what of it the step changed. `expect` is the goal as the step left it, for the step to hold
 *  it against (see the head of this file); a target with none is set as it stands. */
export interface Target {
  shot: Shot
  change: Change
  expect?: Shot
}

/** What a step did: the outcome, the goals that have something the step changed that was changed since (it stays as it is
 *  now), and whether anything was written at all. */
export interface Applied {
  outcome: Outcome
  kept: { id: string; title: string }[]
  set: boolean
}

const nothing = (outcome: Outcome): Applied => ({ outcome, kept: [], set: false })

/** The part of what the step changed that is still the step's to set, and whether something it changed stays because it was
 *  changed since (and is not already what the step wants). */
function holding(asked: Change, now: Shot, expect: Shot | undefined, target: Shot): { change: Change; kept: boolean } {
  if (!expect) return { change: asked, kept: false }
  const moved = differingFields(now, expect)
  const change: Change = {
    done: asked.done && !doneDiffers(now, expect),
    fields: asked.fields.filter((field) => !moved.includes(field)),
    parent: asked.parent && !parentDiffers(now, expect),
    place: asked.place && !placeDiffers(now, expect),
    // The slot only means something in the group the step left the goal in.
    slot: asked.slot && !placeDiffers(now, expect) && !parentDiffers(now, expect),
  }
  const wanted = differingFields(now, target)
  const kept =
    (asked.done && !change.done && doneDiffers(now, target)) ||
    asked.fields.some((field) => moved.includes(field) && wanted.includes(field)) ||
    (asked.parent && !change.parent && parentDiffers(now, target)) ||
    (asked.place && !change.place && placeDiffers(now, target))
  return { change, kept }
}

/** A goal's shot as it stands: from the board, or from the server when the board does not carry it, or when `fresh` asks
 *  for the server (the board may not have heard of a change yet). `null`: gone. */
export async function currentShot(ports: RestorePorts, id: string, fresh = false): Promise<Shot | null> {
  const onBoard = fresh ? null : shotOf(ports.board(), id)
  if (onBoard) return onBoard
  try {
    return shotOfCard(await getGoal(id), undefined)
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null
    throw err
  }
}

/** The fields of the step that are not as the shot says. */
const fieldsToSet = (now: Shot, target: Shot, change: Change) => differingFields(now, target).filter((field) => change.fields.includes(field))
const fieldsDiffer = (now: Shot, target: Shot, change: Change): boolean =>
  (change.done && doneDiffers(now, target)) || fieldsToSet(now, target, change).length > 0

async function setFields(ports: RestorePorts, now: Shot, target: Shot, change: Change): Promise<void> {
  const onBoard = !!findGoal(ports.board(), target.id)
  if (change.done && doneDiffers(now, target)) {
    if (onBoard) await ports.completeGoal(target.id, target.done)
    else await patchGoal(target.id, { done: target.done })
  }
  const fields = fieldsToSet(now, target, change)
  if (fields.length) {
    const patch = Object.fromEntries(fields.map((field) => [field, target[field]])) as UpdatePatch
    if (onBoard) await ports.updateGoal(target.id, patch)
    else await patchGoal(target.id, patch)
  }
}

/** What a setter waits for between the board's move and the write: the server's word that the goal still holds what the step
 *  left. `false`: it does not, and the move is taken back. Without one the write goes at once. */
type Hold = () => Promise<boolean>

async function setPlace(ports: RestorePorts, target: Shot, hold?: Hold): Promise<boolean> {
  const board = ports.board()
  const id = target.id
  const vertical = target.vertical as VerticalScale | null
  if (vertical === null) {
    const placement = schedulePlacement(board, id, { vertical: null, periodKey: null }, null)
    if (hold && !(await hold())) {
      placement?.rollback()
      return false
    }
    try {
      const updated = await scheduleGoal(id, null, null)
      if (placement) placement.reconcile(updated)
      else await ports.reloadBoard() // no place for it on the board: the board is loaded again, as a drop there does
    } catch (err) {
      placement?.rollback()
      throw err
    }
    return true
  }
  const slot = target.before ?? null
  const ordering = scheduleOrdering(board, id, { insertBeforeId: slot, vertical, periodKey: target.period_key })
  const placement = schedulePlacement(board, id, { vertical, periodKey: target.period_key }, target.anchor_date, slot)
  if (hold && !(await hold())) {
    placement?.rollback()
    return false
  }
  try {
    const updated = await scheduleGoal(id, vertical, target.anchor_date, ordering ?? undefined)
    placement?.reconcile(updated)
    // No column for it on the board, or the server moved steps with the goal or clamped some: the board asks again.
    if (!placement || updated.descendants_clamped > 0) await ports.reloadBoard()
  } catch (err) {
    placement?.rollback()
    throw err
  }
  return true
}

async function setParent(ports: RestorePorts, target: Shot, hold?: Hold): Promise<boolean> {
  const placement = reparentPlacement(ports.board(), target.id, target.parent_id)
  if (hold && !(await hold())) {
    placement?.rollback()
    return false
  }
  try {
    const updated = await reparentGoal(target.id, target.parent_id)
    if (placement) placement.reconcile(updated)
    else await ports.reloadBoard()
  } catch (err) {
    placement?.rollback()
    throw err
  }
  return true
}

/** The goal the shot says follows it, when that goal is still in the group it is in now; otherwise the end of the list. */
function slotInGroup(board: BoardResponse | null, target: Shot, now: Shot): string | null {
  if (!target.before) return null
  const next = findGoal(board, target.before)
  return next && next.vertical === now.vertical && (next.period_key ?? null) === (now.period_key ?? null) ? next.id : null
}

async function setSlot(ports: RestorePorts, target: Shot, now: Shot, hold?: Hold): Promise<boolean> {
  const board = ports.board()
  const target_ = { insertBeforeId: slotInGroup(board, target, now) }
  const write = reorderWrite(board, target.id, target_)
  if (!write) return false
  const placement = reorderPlacement(board, target.id, target_)
  if (hold && !(await hold())) {
    placement?.rollback()
    return false
  }
  try {
    placement?.reconcile(await patchGoal(target.id, write.patch))
  } catch (err) {
    placement?.rollback()
    throw err
  }
  return true
}

/** What came of setting one goal: it is as the shot says, the server no longer has it, or a write did not take (the store's
 *  own verbs tell the person why, and keep what they showed). */
type Settled = 'done' | 'gone' | 'failed'

interface One {
  settled: Settled
  /** Something the step changed was changed since, and stays as it is now. */
  kept: boolean
  /** Something was written. */
  set: boolean
  /** The goal's title as it stands. */
  title: string
}

/** The server's word on each goal a step holds against something, asked now and answered when it is. The board may not have heard
 *  yet of what an agent did a moment ago (it hears after a pause), and a goal put back over that would be a change nobody asked
 *  for. Asked as the step begins, and waited for only where a write would go: what the person sees moves in the key's own
 *  breath, whatever the answer's timing. `null`: the goal is gone. */
export function holdings(ports: RestorePorts, targets: Target[]): Map<string, Promise<Shot | null>> {
  const held = new Map<string, Promise<Shot | null>>()
  for (const target of targets) {
    if (!target.expect) continue
    const word = currentShot(ports, target.shot.id, true)
    word.catch(() => undefined) // whoever waits for it hears of a failure; one nobody waits for is not an unhandled one
    held.set(target.shot.id, word)
  }
  return held
}

/** What a goal must still hold for the step to set one thing of it. The slot only means something in the group the step left the
 *  goal in. */
function holds(now: Shot, expect: Shot, aspect: 'place' | 'parent' | 'slot'): boolean {
  if (aspect === 'place') return !placeDiffers(now, expect)
  if (aspect === 'parent') return !parentDiffers(now, expect)
  return !placeDiffers(now, expect) && !parentDiffers(now, expect)
}

/** Sets one goal to the shot, as far as the step changed it and the goal still holds what the step left. */
async function settleOne(
  ports: RestorePorts, { shot: target, change: asked, expect }: Target, direction: 'back' | 'forward',
  held?: Map<string, Promise<Shot | null>>,
): Promise<One> {
  const id = target.id
  const word = (): Promise<Shot | null> => held?.get(id) ?? currentShot(ports, id, true)
  // The board is what the person sees, and a move starts from it at once; the writes wait for the server's word. A tick or a title
  // is written by the store's own verbs the moment they are called, and a goal the board does not carry has nothing to move: for
  // those the server's word comes first.
  const seen = expect ? shotOf(ports.board(), id) : null
  let now = seen && !asked.done && !asked.fields.length ? seen : await (expect ? word() : currentShot(ports, id))
  if (!now) return { settled: 'gone', kept: false, set: false, title: target.title }
  const preview = !!expect && now === seen
  const hold = (aspect: 'place' | 'parent' | 'slot'): Hold | undefined =>
    preview ? async () => { const there = await word(); return !!there && holds(there, expect!, aspect) } : undefined
  const first = holding(asked, now, expect, target)
  const { change } = first
  let kept = first.kept
  let title = now.title
  let set = false
  if (fieldsDiffer(now, target, change)) {
    set = true
    await setFields(ports, now, target, change)
    now = (await currentShot(ports, id)) ?? now
    // The tick and the patch are the store's own verbs, which keep their failures to themselves: the goal is not as it
    // should be, so the server is asked whether it is there at all.
    if (fieldsDiffer(now, target, change)) return { settled: (await currentShot(ports, id, true)) ? 'failed' : 'gone', kept, set, title }
  }

  now = (await currentShot(ports, id)) ?? now
  const parent = change.parent && parentDiffers(now, target)
  const place = change.place && placeDiffers(now, target)
  if (parent && place) {
    const moves = { place: () => setPlace(ports, target, hold('place')), parent: () => setParent(ports, target, hold('parent')) }
    let [one, other] = direction === 'back' ? [moves.place, moves.parent] : [moves.parent, moves.place]
    let wrote: boolean
    try {
      wrote = await one()
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 422) throw err
      ;[one, other] = [other, one]
      wrote = await one()
    }
    set = (await other()) || wrote || set
  } else if (place) {
    set = (await setPlace(ports, target, hold('place'))) || set
  } else if (parent) {
    set = (await setParent(ports, target, hold('parent'))) || set
  }

  now = (await currentShot(ports, id)) ?? now
  if (change.slot && slotDiffers(now, target)) set = (await setSlot(ports, target, now, hold('slot'))) || set

  if (preview) {
    // The server's word on what stayed: what the board showed may have been a moment behind.
    const there = await word()
    if (!there) return { settled: 'gone', kept: false, set, title }
    kept = holding(asked, there, expect, target).kept
    title = there.title
  }
  return { settled: 'done', kept, set, title }
}

/** Sets the goals of a step to `targets` (the one the gesture was about first). */
export async function settleShots(
  ports: RestorePorts, targets: Target[], direction: 'back' | 'forward', held?: Map<string, Promise<Shot | null>>,
): Promise<Applied> {
  const [head, ...rest] = targets
  if (!head) return nothing('done')
  try {
    const first = await settleOne(ports, head, direction, held)
    if (first.settled === 'gone') {
      toast(`“${head.shot.title}” is gone, so this can’t be taken back.`)
      return nothing('drop')
    }
    if (first.settled === 'failed') {
      await ports.reloadBoard()
      return nothing('retry')
    }
    const kept = first.kept ? [{ id: head.shot.id, title: first.title }] : []
    let set = first.set
    for (const target of [...rest].sort((a, b) => b.shot.position - a.shot.position)) {
      const one = await settleOne(ports, target, direction, held)
      if (one.kept) kept.push({ id: target.shot.id, title: one.title })
      set ||= one.set
    }
    return { outcome: 'done', kept, set }
  } catch (err) {
    toast(messageForError(err))
    await ports.reloadBoard()
    return nothing(err instanceof ApiError && err.status > 0 && err.status < 500 ? 'drop' : 'retry')
  }
}
