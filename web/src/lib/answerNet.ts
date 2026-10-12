// What an agent's answer changed on the board, goal by goal (docs/design/agent-answer-undo.md). The desktop gateway marks each
// answer, the MCP server keeps what every write of it changed, each goal as it was and as it was left, and the page reads that
// record (`POST /__chat/answers`). Nothing here is guessed from a diff of the board: the record says what the writes did, so
// what somebody else changed meanwhile can be told from what the answer wrote.
//
// The writes of an answer are put together goal by goal: what a goal was before the answer's first write to it and what it was
// after the last. From that:
//   made     a goal the answer made, and left;
//   removed  a goal the answer deleted, with what was under it;
//   edited   a goal that was there before and after, changed in a way the board's history keeps (`lib/boardShots.ts`).
// Pure: no state, no network.
import type { GoalCard } from './api'
import { changeBetween, changed, shotOfCard, type Shot } from './boardShots'

/** A goal as the server printed it into the record: the board's card, without its owner. */
export type Card = Omit<GoalCard, 'owner'>

export interface Recorded {
  id: string
  before: Card | null
  after: Card | null
}

export interface Write {
  seq: number
  at: number
  tool: string
  /** The goal a delete named; what was under it is in `changes`. */
  root: string | null
  changes: Recorded[]
}

/** What became of an answer: it stands, it was taken back, or it could not be and is let go. */
export type AnswerState = 'standing' | 'undone' | 'spent'

export interface Answer {
  id: string
  session: string
  started_at: number
  ended_at: number | null
  truncated: boolean
  state: AnswerState
  writes: Write[]
}

export interface Edit {
  before: Card
  after: Card
  /** The first and the last write of the answer that changed the goal. */
  first: number
  last: number
}

/** A goal the answer deleted and everything that went with it, as they stood when it went. */
export interface Gone {
  root: Card
  members: Card[]
}

export interface Net {
  made: Card[]
  removed: Gone[]
  edited: Edit[]
}

export const shot = (card: Card, follower?: string | null): Shot => shotOfCard(card, follower)

/** Whether the answer left a goal in a way the history keeps. The place in the list counts, which the shots alone cannot tell. */
const differs = (a: Card, b: Card): boolean => changed(shot(a), shot(b)) || a.position !== b.position

export function netOf(answer: Answer): Net {
  const first = new Map<string, { card: Card | null; seq: number }>()
  const last = new Map<string, { card: Card | null; seq: number }>()
  const order: string[] = []
  for (const write of answer.writes) {
    for (const { id, before, after } of write.changes) {
      if (!first.has(id)) {
        first.set(id, { card: before, seq: write.seq })
        order.push(id)
      }
      last.set(id, { card: after, seq: write.seq })
    }
  }
  const made: Card[] = []
  const edited: Edit[] = []
  for (const id of order) {
    const was = first.get(id)!
    const now = last.get(id)!
    if (!was.card && now.card) made.push(now.card)
    else if (was.card && now.card && differs(was.card, now.card)) {
      edited.push({ before: was.card, after: now.card, first: was.seq, last: now.seq })
    }
  }
  // A goal the answer made and then deleted itself is nothing to put back; a delete names the root of what it took.
  const removed: Gone[] = []
  for (const write of answer.writes) {
    if (write.tool !== 'delete' || !write.root || !first.get(write.root)?.card) continue
    const root = write.changes.find((c) => c.id === write.root)?.before
    if (root) removed.push({ root, members: write.changes.flatMap((c) => (c.before ? [c.before] : [])) })
  }
  return { made, removed, edited }
}

/** The goals of `made` that nothing else the answer made stands over. */
export function madeRoots(made: Card[]): Card[] {
  const ids = new Set(made.map((card) => card.id))
  return made.filter((card) => !card.parent_id || !ids.has(card.parent_id))
}

/** How many goals the answer changed: the goals it made (with what it made under them as one), the goals it deleted (with what was
 *  under them as one), and the goals it edited. */
export const countOf = (net: Net): number => madeRoots(net.made).length + net.removed.length + net.edited.length

/** Whether a goal is somewhere else, or under something else, than it was: the changes a goal flies for. */
export function structural(edit: Edit): boolean {
  const change = changeBetween(shot(edit.before), shot(edit.after))
  return change.parent || change.place
}
