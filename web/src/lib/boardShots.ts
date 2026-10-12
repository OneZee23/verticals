// What a gesture can change on one goal, written down before it and after it (docs/design/board-undo.md). A step of the
// board's history is a list of these pairs; undo and redo set a goal back to one of them (`lib/boardRestore.ts`).
//
// Read from the board payload, never from the server: the payload is what the person sees and what the gesture just
// changed, so a shot taken after a write already holds the server's answer (`reconcile`, or the reload some writes make).
// Pure reads, no state, the way `lib/boardIndex.ts` is.

import type { BoardResponse, GoalCard, RepeatRule } from './api'
import { findGoal, siblingIds, subtreeIds } from './boardIndex'

export interface Shot {
  id: string
  title: string
  done: boolean
  repeat: RepeatRule | null
  tags: string[]
  foil: boolean
  size_expected: string[] | null
  parent_id: string | null
  vertical: string | null
  anchor_date: string | null
  period_key: string | null
  /** For the Inbox shelf and the words of a notice; `null` for a goal that has a date. */
  parked_from_vertical: string | null
  position: number
  /** The goal that follows this one in its list, in the order the server keeps (`null`: it is last). `undefined`: not
   *  known, because the goal was not on the board when the shot was taken. */
  before: string | null | undefined
}

/** The fields a PATCH sets, apart from `done`, which has its own write (a tick). */
export const PATCH_FIELDS = ['title', 'repeat', 'tags', 'foil', 'size_expected'] as const
export type PatchField = (typeof PATCH_FIELDS)[number]

/** The goal after `id` in the list the server orders it in: its column (the scheduled ones, ghosts left out, since they
 *  belong to another period) or its parent's list. The same group `reorderWrite` in `lib/drag.ts` reads, so a slot named
 *  here is a slot a drop could have named. */
function successor(board: BoardResponse, goal: GoalCard): string | null {
  const group = siblingIds(board, goal.id)
    .map((id) => findGoal(board, id))
    .filter((g): g is GoalCard => !!g && g.vertical === goal.vertical && (g.period_key ?? null) === (goal.period_key ?? null))
    .sort((a, b) => a.position - b.position || a.id.localeCompare(b.id))
  const at = group.findIndex((g) => g.id === goal.id)
  return at === -1 ? null : group[at + 1]?.id ?? null
}

/** One goal's shot from its card; `before` as the caller knows it (`undefined` for a card not read from the board). */
export function shotOfCard(card: Omit<GoalCard, 'owner'>, before: string | null | undefined): Shot {
  return {
    id: card.id,
    title: card.title,
    done: card.done_at !== null,
    repeat: card.repeat ? JSON.parse(JSON.stringify(card.repeat)) : null,
    tags: [...card.tags],
    foil: card.foil,
    size_expected: card.size_expected ? [...card.size_expected] : null,
    parent_id: card.parent_id,
    vertical: card.vertical,
    anchor_date: card.anchor_date,
    period_key: card.period_key,
    parked_from_vertical: card.parked_from_vertical,
    position: card.position,
    before,
  }
}

/** `id`'s shot, or `null` when the board does not carry it (another period, deleted, not loaded). */
export function shotOf(board: BoardResponse | null, id: string): Shot | null {
  const goal = board ? findGoal(board, id) : undefined
  return board && goal ? shotOfCard(goal, successor(board, goal)) : null
}

/** The shots of `id` first and, with `family`, of every goal under it that the board carries (a move of a goal moves its
 *  steps with it, and the server may move more). */
export function shotsOf(board: BoardResponse | null, id: string, family: boolean): Shot[] {
  const first = shotOf(board, id)
  const out = first ? [first] : []
  if (family) {
    for (const kid of subtreeIds(board, id)) {
      if (kid === id) continue
      const shot = shotOf(board, kid)
      if (shot) out.push(shot)
    }
  }
  return out
}

const same = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b)

/** Which of the patchable fields differ. */
export function differingFields(a: Shot, b: Shot): PatchField[] {
  return PATCH_FIELDS.filter((field) => !same(a[field], b[field]))
}
export const doneDiffers = (a: Shot, b: Shot): boolean => a.done !== b.done
export const parentDiffers = (a: Shot, b: Shot): boolean => a.parent_id !== b.parent_id
export const placeDiffers = (a: Shot, b: Shot): boolean =>
  a.vertical !== b.vertical || a.anchor_date !== b.anchor_date || (a.period_key ?? null) !== (b.period_key ?? null)
/** Both slots known and different. */
export const slotDiffers = (a: Shot, b: Shot): boolean =>
  a.before !== undefined && b.before !== undefined && a.before !== b.before

/** What a step changed on one goal. Undo and redo set back only these, so what someone else changed on the goal since (the
 *  agent, a second window) is not undone with it. */
export interface Change {
  done: boolean
  fields: PatchField[]
  parent: boolean
  place: boolean
  slot: boolean
}

export function changeBetween(a: Shot, b: Shot): Change {
  return { done: doneDiffers(a, b), fields: differingFields(a, b), parent: parentDiffers(a, b), place: placeDiffers(a, b), slot: slotDiffers(a, b) }
}

/** Whether a gesture changed anything at all in `a` → `b` (the order counts only when it can be told). */
export function changed(a: Shot, b: Shot): boolean {
  return doneDiffers(a, b) || differingFields(a, b).length > 0 || parentDiffers(a, b) || placeDiffers(a, b) || slotDiffers(a, b)
}
