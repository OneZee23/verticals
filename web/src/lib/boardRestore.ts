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

interface One {
  settled: Settled
  /** Something the step changed was changed since, and stays as it is now. */
  kept: boolean
  /** Something was written. */
  set: boolean
  /** The goal's title as it stands. */
  title: string
}

/** What each goal holds now, asked of the server: the board may not have heard yet of what an agent did a moment ago, and a goal
 *  put back over it would be a change nobody asked for. Asked before the step is applied, so that the board moves in the same
 *  breath as the key and not a round trip later. `null`: the goal is gone. */
export async function holdings(ports: RestorePorts, targets: Target[]): Promise<Map<string, Shot | null>> {
  const held = new Map<string, Shot | null>()
  await Promise.all(targets.filter((target) => target.expect).map(async (target) => {
    held.set(target.shot.id, await currentShot(ports, target.shot.id, true))
  }))
  return held
}

/** Sets one goal to the shot, as far as the step changed it and the goal still holds what the step left. */
async function settleOne(
  ports: RestorePorts, { shot: target, change: asked, expect }: Target, direction: 'back' | 'forward', held?: Map<string, Shot | null>,
): Promise<One> {
  let now = held?.has(target.id) ? held.get(target.id) ?? null : await currentShot(ports, target.id, !!expect)
  if (!now) return { settled: 'gone', kept: false, set: false, title: target.title }
  const { change, kept } = holding(asked, now, expect, target)
  const title = now.title
  let set = false
  if (fieldsDiffer(now, target, change)) {
    set = true
    await setFields(ports, now, target, change)
    now = (await currentShot(ports, target.id)) ?? now
    // The tick and the patch are the store's own verbs, which keep their failures to themselves: the goal is not as it
    // should be, so the server is asked whether it is there at all.
    if (fieldsDiffer(now, target, change)) return { settled: (await currentShot(ports, target.id, true)) ? 'failed' : 'gone', kept, set, title }
  }

  now = (await currentShot(ports, target.id)) ?? now
  const parent = change.parent && parentDiffers(now, target)
  const place = change.place && placeDiffers(now, target)
  if (parent && place) {
    set = true
    let [first, second] = direction === 'back' ? [setPlace, setParent] : [setParent, setPlace]
    try {
      await first(ports, target)
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 422) throw err
      ;[first, second] = [second, first]
      await first(ports, target)
    }
    await second(ports, target)
  } else if (place) {
    set = true
    await setPlace(ports, target)
  } else if (parent) {
    set = true
    await setParent(ports, target)
  }

  now = (await currentShot(ports, target.id)) ?? now
  if (change.slot && slotDiffers(now, target)) {
    set = true
    await setSlot(ports, target, now)
  }
  return { settled: 'done', kept, set, title }
}

/** Sets the goals of a step to `targets` (the one the gesture was about first). */
export async function settleShots(
  ports: RestorePorts, targets: Target[], direction: 'back' | 'forward', held?: Map<string, Shot | null>,
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
