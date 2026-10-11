// Setting a goal back to a shot (docs/design/board-undo.md): what undo and redo do. A step of the board's history holds
// the shots of the goals it changed; this module makes the board and the server match a shot again, through the writes
// the board already makes (a tick, a patch, a schedule with a slot, a reparent, a reorder), each with its optimistic
// placement, so the live feed, the epoch guard and the motion are the ones that exist. It writes nothing of its own kind.
//
// It looks at what the goal is now and does only what differs, in an order that stays legal:
//   1. the fields (done, title, repeat, tags, foil, expected size);
//   2. the structure: the parent and the period. A goal stays at or below its parent's scale, so which of the two goes
//      first depends on the gesture being taken back: the period first when undoing, the parent first when redoing
//      (the order the gestures made them in), and the other order when the server refuses the first with a 422;
//   3. the slot, last, because it only means something in the group the goal is in by then.
// A goal's steps follow it on the server; they are set back after it, the last in the list first, so the goal each one
// stands before is already where it belongs.

import { toast } from '@konstantinopolskii/vue'
import {
  ApiError, getGoal, patchGoal, reparentGoal, scheduleGoal,
  type BoardResponse, type UpdatePatch,
} from './api'
import { findGoal } from './boardIndex'
import { reorderPlacement, reparentPlacement, schedulePlacement } from './boardPlacement'
import {
  differingFields, doneDiffers, parentDiffers, placeDiffers, shotOf, shotOfCard, slotDiffers, type Shot,
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

async function setFields(ports: RestorePorts, now: Shot, target: Shot): Promise<void> {
  const onBoard = !!findGoal(ports.board(), target.id)
  if (doneDiffers(now, target)) {
    if (onBoard) await ports.completeGoal(target.id, target.done)
    else await patchGoal(target.id, { done: target.done })
  }
  const fields = differingFields(now, target)
  if (fields.length) {
    const patch = Object.fromEntries(fields.map((field) => [field, target[field]])) as UpdatePatch
    if (onBoard) await ports.updateGoal(target.id, patch)
    else await patchGoal(target.id, patch)
  }
}

async function setPlace(ports: RestorePorts, target: Shot): Promise<void> {
  const board = ports.board()
  const id = target.id
  const vertical = target.vertical as VerticalScale | null
  if (vertical === null) {
    const placement = schedulePlacement(board, id, { vertical: null, periodKey: null }, null)
    try {
      const updated = await scheduleGoal(id, null, null)
      if (placement) placement.reconcile(updated)
      else await ports.reloadBoard() // no place for it on the board: the board is loaded again, as a drop there does
    } catch (err) {
      placement?.rollback()
      throw err
    }
    return
  }
  const slot = target.before ?? null
  const ordering = scheduleOrdering(board, id, { insertBeforeId: slot, vertical, periodKey: target.period_key })
  const placement = schedulePlacement(board, id, { vertical, periodKey: target.period_key }, target.anchor_date, slot)
  try {
    const updated = await scheduleGoal(id, vertical, target.anchor_date, ordering ?? undefined)
    placement?.reconcile(updated)
    // No column for it on the board, or the server moved steps with the goal or clamped some: the board asks again.
    if (!placement || updated.descendants_clamped > 0) await ports.reloadBoard()
  } catch (err) {
    placement?.rollback()
    throw err
  }
}

async function setParent(ports: RestorePorts, target: Shot): Promise<void> {
  const placement = reparentPlacement(ports.board(), target.id, target.parent_id)
  try {
    const updated = await reparentGoal(target.id, target.parent_id)
    if (placement) placement.reconcile(updated)
    else await ports.reloadBoard()
  } catch (err) {
    placement?.rollback()
    throw err
  }
}

/** The goal the shot says follows it, when that goal is still in the group it is in now; otherwise the end of the list. */
function slotInGroup(board: BoardResponse | null, target: Shot, now: Shot): string | null {
  if (!target.before) return null
  const next = findGoal(board, target.before)
  return next && next.vertical === now.vertical && (next.period_key ?? null) === (now.period_key ?? null) ? next.id : null
}

async function setSlot(ports: RestorePorts, target: Shot, now: Shot): Promise<void> {
  const board = ports.board()
  const target_ = { insertBeforeId: slotInGroup(board, target, now) }
  const write = reorderWrite(board, target.id, target_)
  if (!write) return
  const placement = reorderPlacement(board, target.id, target_)
  try {
    placement?.reconcile(await patchGoal(target.id, write.patch))
  } catch (err) {
    placement?.rollback()
    throw err
  }
}

/** What came of setting one goal: it is as the shot says, the server no longer has it, or a write did not take (the store's
 *  own verbs tell the person why, and keep what they showed). */
type Settled = 'done' | 'gone' | 'failed'

const fieldsDiffer = (a: Shot, b: Shot): boolean => doneDiffers(a, b) || differingFields(a, b).length > 0

/** Sets one goal to `target`. */
async function settleOne(ports: RestorePorts, target: Shot, direction: 'back' | 'forward'): Promise<Settled> {
  let now = await currentShot(ports, target.id)
  if (!now) return 'gone'
  if (fieldsDiffer(now, target)) {
    await setFields(ports, now, target)
    now = (await currentShot(ports, target.id)) ?? now
    // The tick and the patch are the store's own verbs, which keep their failures to themselves: the goal is not as it
    // should be, so the server is asked whether it is there at all.
    if (fieldsDiffer(now, target)) return (await currentShot(ports, target.id, true)) ? 'failed' : 'gone'
  }

  now = (await currentShot(ports, target.id)) ?? now
  const parent = parentDiffers(now, target)
  const place = placeDiffers(now, target)
  if (parent && place) {
    let [first, second] = direction === 'back' ? [setPlace, setParent] : [setParent, setPlace]
    try {
      await first(ports, target)
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 422) throw err
      ;[first, second] = [second, first]
      await first(ports, target)
    }
    await second(ports, target)
  } else if (place) await setPlace(ports, target)
  else if (parent) await setParent(ports, target)

  now = (await currentShot(ports, target.id)) ?? now
  if (slotDiffers(now, target)) await setSlot(ports, target, now)
  return 'done'
}

/** Sets the goals of a step to `targets` (the one the gesture was about first). */
export async function settleShots(ports: RestorePorts, targets: Shot[], direction: 'back' | 'forward'): Promise<Outcome> {
  const [head, ...rest] = targets
  if (!head) return 'done'
  try {
    const first = await settleOne(ports, head, direction)
    if (first === 'gone') {
      toast(`“${head.title}” is gone, so this can’t be taken back.`)
      return 'drop'
    }
    if (first === 'failed') {
      await ports.reloadBoard()
      return 'retry'
    }
    for (const shot of [...rest].sort((a, b) => b.position - a.position)) await settleOne(ports, shot, direction)
    return 'done'
  } catch (err) {
    toast(messageForError(err))
    await ports.reloadBoard()
    return err instanceof ApiError && err.status > 0 && err.status < 500 ? 'drop' : 'retry'
  }
}
