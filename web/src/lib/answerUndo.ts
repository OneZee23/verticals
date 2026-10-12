// An agent's answer has its own Undo (docs/design/agent-answer-undo.md), where the answer shows: in the field while it stands
// there, and on its message in the conversation. ⌘Z is the person's own: an answer is never a step of the board's history, and
// is taken back from the answer itself, or by a pick when ⌘Z cannot tell whose change was meant (`lib/boardHistory.ts`).
//
// The gateway marks each answer, the MCP server keeps what every write of it changed, and the page reads that record
// (`lib/answerNet.ts`) whenever it needs it, so an answer given while the window was closed has its Undo when the window opens.
// Undo puts back only what the answer wrote and is still as the answer left it, in the order the writes would be taken back:
//   1. what it deleted comes back from the server's trash, the last first (`core/trash.py`);
//   2. what it changed on goals that were there is set back, one kind of change at a time: a tick, a title, a move, a parent, a
//      place in the list. A kind that is not as the answer left it was changed by somebody since, and stays as it is
//      (`Target.expect`, `lib/boardRestore.ts`);
//   3. what it made goes to the trash, unless somebody has taken it up since: written to it (the server stamps every write), put
//      something under it, or commented on it. A made goal with steps goes whole or not at all.
// Redo does it the other way round, with the same care for what was changed since. What stayed is said in the field, in one line.
import { reactive } from 'vue'
import { toast } from '@konstantinopolskii/vue'
import { ApiError, fetchGoalComments, getGoal, restoreGoal, type BoardResponse, type GoalCard } from './api'
import { countOf, madeRoots, netOf, shot, structural, type Answer, type AnswerState, type Card, type Edit, type Net } from './answerNet'
import { announce, bindAnswers, historyPorts, nextSeq, runStep, seen, type Step } from './boardHistory'
import { holdings, settleAll, type Applied, type Outcome, type Target } from './boardRestore'
import { changeBetween } from './boardShots'
import type { Segment } from './fieldNotice'
import { sendAway } from './goalSteps'
import { addedWords, changeWords, deleteWords, putBackWords, removedWords } from './historyWords'
import { messageForError } from './scheduleFeedback'

export interface AnswerEntry {
  id: string
  /** The step that takes the answer back and does it again. It has the shape of a step of the board's history and never joins it. */
  step: Step
  /** How many goals the answer changed. */
  count: number
  /** The answer as one of the things ⌘Z may be asked to take back. */
  label: Segment[]
  state: AnswerState
  busy: boolean
  /** The order in which the page learned of the answer, among the person's own changes (`lib/boardHistory.ts`). */
  seq: number
}

export const answerUndo = reactive({ entries: {} as Record<string, AnswerEntry> })

// --- setting goals back ---------------------------------------------------------------------------------------------

/** The goal that follows a spot in the list it belongs to, as the board shows that list (the group `reorderWrite` reads in
 *  `lib/drag.ts`); `null`: it is last; `undefined`: the board does not show the list, so the goal goes to the end of it. */
function followerAt(board: BoardResponse | null, card: Card): string | null | undefined {
  if (!board) return undefined
  let group: GoalCard[] | undefined
  if (card.vertical === null && card.parent_id) {
    group = board.children[card.parent_id]?.filter((goal) => goal.vertical === null)
  } else {
    const column = board.columns.find((c) => c.vertical === card.vertical)
    if (column && (column.period_key ?? null) === (card.period_key ?? null)) {
      group = column.goals.filter((goal) => goal.vertical === card.vertical && (goal.period_key ?? null) === (card.period_key ?? null))
    }
  }
  if (!group) return undefined
  const after = group
    .filter((goal) => goal.id !== card.id && (goal.position > card.position || (goal.position === card.position && goal.id > card.id)))
    .sort((a, b) => a.position - b.position || a.id.localeCompare(b.id))
  return after[0]?.id ?? null
}

/** The goals of the answer's edits, each to be set to `to` where it still is as `from` says. A change made in the last write is
 *  taken back first, as the writes would be taken back; the goals of one write, the one they hang on first. The place in the list
 *  is told by the position the goal had, since nothing else of it is kept. */
function targets(edits: Edit[], direction: 'back' | 'forward', board: BoardResponse | null): Target[] {
  const ordered = [...edits].sort((a, b) =>
    (direction === 'back' ? b.last - a.last : a.first - b.first) || a.after.depth - b.after.depth || b.after.position - a.after.position)
  return ordered.map((edit) => {
    const [to, from] = direction === 'back' ? [edit.before, edit.after] : [edit.after, edit.before]
    const goal = shot(to, followerAt(board, to))
    const left = shot(from)
    return { shot: goal, change: { ...changeBetween(goal, left), slot: to.position !== from.position }, expect: left }
  })
}

// --- bringing goals back and sending them away --------------------------------------------------------------------

async function exists(id: string): Promise<boolean> {
  try {
    await getGoal(id)
    return true
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return false
    throw err
  }
}

const refused = (err: unknown): boolean => err instanceof ApiError && err.status > 0 && err.status < 500

/** Brings goals back from the trash with what was under them, in the order given. A goal that is back already is as it should
 *  be; one the trash no longer has is told once. */
async function bringBack(goals: Card[]): Promise<{ outcome: Outcome; brought: Card[]; lost: Card[] }> {
  let outcome: Outcome = 'done'
  const brought: Card[] = []
  const lost: Card[] = []
  for (const goal of goals) {
    try {
      await restoreGoal(goal.id)
      brought.push(goal)
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) continue // it is back already
      if (err instanceof ApiError && err.status === 404) {
        if (!(await exists(goal.id).catch(() => true))) {
          toast(`“${goal.title}” can’t be put back any more.`)
          lost.push(goal)
        }
        continue
      }
      toast(messageForError(err))
      if (!refused(err)) outcome = 'retry'
    }
  }
  return { outcome, brought, lost }
}

/** A timestamp as an instant to the microsecond, however the offset is spelled: the record and the API print the same
 *  moment in different words. */
function instant(stamp: string): string {
  const parts = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:?\d{2})?$/.exec(stamp)
  if (!parts) return stamp
  const zone = parts[3] ?? 'Z'
  const whole = Date.parse(`${parts[1]}${/^[+-]\d{4}$/.test(zone) ? `${zone.slice(0, 3)}:${zone.slice(3)}` : zone}`)
  return `${whole}.${(parts[2] ?? '').padEnd(6, '0')}`
}

/** Whether goals are as a write of the answer left them: all there, none written to since, nothing under them that the answer did
 *  not put there, no comment on them. A goal that is gone is not in the way. `null`: the server could not be reached. */
async function intact(cards: Card[]): Promise<boolean | null> {
  const ids = new Set(cards.map((card) => card.id))
  try {
    const checks = await Promise.all(cards.map(async (card) => {
      let now: Awaited<ReturnType<typeof getGoal>>
      try {
        now = await getGoal(card.id)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return true
        throw err
      }
      if (instant(now.updated_at) !== instant(card.updated_at) || now.children.some((kid) => !ids.has(kid.id))) return false
      return (await fetchGoalComments(card.id)).threads.length === 0
    }))
    return checks.every(Boolean)
  } catch {
    return null
  }
}

/** Sends goals the answer made to the trash, the last made first, each with what the answer made under it, unless somebody has
 *  taken it up. The ones it left are named. */
async function sendMadeAway(made: Card[]): Promise<{ outcome: Outcome; sent: Card[]; left: Card[] }> {
  const byId = new Map(made.map((card) => [card.id, card]))
  const rootOf = (card: Card): Card => {
    let at = card
    for (let hop = 0; at.parent_id && byId.has(at.parent_id) && hop < 64; hop += 1) at = byId.get(at.parent_id)!
    return at
  }
  let outcome: Outcome = 'done'
  const sent: Card[] = []
  const left: Card[] = []
  for (const root of madeRoots(made).reverse()) {
    const family = made.filter((card) => rootOf(card).id === root.id)
    const whole = await intact(family)
    if (whole === null) {
      outcome = 'retry'
    } else if (whole) {
      const away = await sendAway(root.id, root.title)
      if (away === 'retry') outcome = 'retry'
      else sent.push(root)
    } else {
      left.push(root)
    }
  }
  return { outcome, sent, left }
}

/** Sends goals the answer deleted away again, unless somebody has taken them up since they came back. */
async function sendRemovedAway(removed: Net['removed']): Promise<{ outcome: Outcome; sent: Card[]; left: Card[] }> {
  let outcome: Outcome = 'done'
  const sent: Card[] = []
  const left: Card[] = []
  for (const { root, members } of removed) {
    const whole = await intact(members)
    if (whole === null) {
      outcome = 'retry'
    } else if (whole && (await exists(root.id).catch(() => false))) {
      const away = await sendAway(root.id, root.title)
      if (away === 'retry') outcome = 'retry'
      else sent.push(root)
    } else if (!whole) {
      left.push(root)
    }
  }
  return { outcome, sent, left }
}

// --- the step ---------------------------------------------------------------------------------------------------------

/** What the answer is called when it is shown as one change in the field: the goal it is mostly about, and how many more. */
function wordsOf(net: Net, direction: 'undo' | 'redo', titleOf: (id: string) => string): Segment[] {
  const lead = net.edited.find(structural)
  const count = countOf(net)
  const more: Segment[] = count > 1 ? [{ text: ` and ${count - 1} more` }] : []
  if (lead || (!net.made.length && !net.removed.length)) {
    const edit = lead ?? net.edited[0]!
    return [
      ...(direction === 'undo'
        ? putBackWords(edit.before.title)
        : changeWords(shot(edit.before), shot(edit.after), titleOf) ?? [{ text: 'Changed ' }, { quote: edit.after.title }]),
      ...more,
    ]
  }
  if (net.made.length) {
    const title = madeRoots(net.made)[0]!.title
    return [...(direction === 'undo' ? removedWords(title) : addedWords(title)), ...more]
  }
  const { root, members } = net.removed[0]!
  return [...(direction === 'undo' ? putBackWords(root.title) : deleteWords(root.title, members.length - 1)), ...more]
}

/** The step for one answer, or `null` when it changed nothing the board keeps. */
export function answerStep(answer: Answer): Step | null {
  const net = netOf(answer)
  if (countOf(net) === 0) return null
  const titles = new Map<string, string>()
  for (const write of answer.writes) {
    for (const { id, before, after } of write.changes) titles.set(id, (after ?? before)!.title)
  }
  const titleOf = (id: string): string => titles.get(id) ?? 'a goal'
  const lead = net.edited.find(structural)?.after ?? net.made[0] ?? net.removed[0]?.root ?? net.edited[0]!.after
  const ids = [...net.edited.map((edit) => edit.after.id), ...madeRoots(net.made).map((card) => card.id), ...net.removed.map((gone) => gone.root.id)]
  let held: ReturnType<typeof holdings> | undefined

  async function run(direction: 'undo' | 'redo'): Promise<Applied> {
    const p = historyPorts()
    const back = direction === 'undo'
    const kept: Applied['kept'] = []
    const put: NonNullable<Applied['put']> = []
    let outcome: Outcome = 'done'
    const note = (more: Outcome): void => {
      if (more === 'retry') outcome = 'retry'
    }

    // 1. goals that were taken away come back (undo), or the goals the answer made come back from the trash (redo)
    const bringing = back ? [...net.removed.map((gone) => gone.root)].reverse() : madeRoots(net.made)
    const first = await bringBack(bringing)
    note(first.outcome)
    put.push(...first.brought)
    for (const card of first.lost) kept.push({ id: card.id, title: card.title })
    if (first.brought.length) await p.reloadBoard()

    // 2. what the answer changed on goals that were there
    const list = targets(net.edited, back ? 'back' : 'forward', p.board())
    const settled = await settleAll(p, list, back ? 'back' : 'forward', held)
    note(settled.outcome)
    put.push(...(settled.put ?? []))
    kept.push(...settled.kept)

    // 3. goals the answer made go (undo), or goals it deleted go again (redo)
    const last = back ? await sendMadeAway(net.made) : await sendRemovedAway(net.removed)
    note(last.outcome)
    put.push(...last.sent)
    for (const card of last.left) kept.push({ id: card.id, title: card.title })
    // What is said names the goal the answer is mostly about, if that one was put right, and counts the rest.
    put.sort((a, b) => Number(b.id === lead.id) - Number(a.id === lead.id))
    return { outcome, kept, set: put.length > 0, put }
  }

  return {
    id: lead.id,
    title: lead.title,
    glides: () => true,
    inView: () => ids.every((id) => seen(id)),
    words: (direction) => wordsOf(net, direction, titleOf),
    prepare: (direction) => {
      const p = historyPorts()
      held = holdings(p, targets(net.edited, direction === 'undo' ? 'back' : 'forward', p.board()))
    },
    undo: () => run('undo'),
    redo: () => run('redo'),
  }
}

// --- the answers the page knows -----------------------------------------------------------------------------------------

/** Whether the desktop gateway is there to ask: the web build has none. */
let gateway = false

export function answersAvailable(on: boolean): void {
  gateway = on
}

function post<T>(path: string, body: unknown): Promise<T | null> {
  return fetch(`/__chat/${path}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
    .then((res) => (res.ok ? (res.json() as Promise<T>) : null))
    .catch(() => null)
}

/** Reads the answers that have ended: the ones the page did not know are given their place among the person's own changes, in
 *  the order they ended. An answer that changed nothing the board keeps has nothing to take back and is not here. */
export async function refreshAnswers(): Promise<void> {
  if (!gateway) return
  const got = await post<{ answers?: Answer[] }>('answers', {})
  for (const answer of got?.answers ?? []) {
    const known = answerUndo.entries[answer.id]
    if (known) {
      if (!known.busy) known.state = answer.state
      continue
    }
    const step = answerStep(answer)
    if (!step) continue
    const net = netOf(answer)
    const count = countOf(net)
    const words = step.words('redo') ?? []
    answerUndo.entries[answer.id] = {
      id: answer.id, step, count, state: answer.state, busy: false, seq: nextSeq(),
      label: count === 1 ? [...words, { text: ' by the agent' }] : [{ text: `${count} changes by the agent` }],
    }
  }
}

/** Takes the answer back, or does it again: from its Undo, and from the pick ⌘Z asks for. */
async function work(id: string, direction: 'undo' | 'redo'): Promise<void> {
  const entry = answerUndo.entries[id]
  if (!entry || entry.busy) return
  entry.busy = true
  try {
    const ran = await runStep(entry.step, direction)
    if (ran.outcome === 'retry') return
    const spent = ran.outcome === 'drop' || (!!ran.applied?.kept.length && !ran.applied.set)
    entry.state = spent ? 'spent' : direction === 'undo' ? 'undone' : 'standing'
    void post('answer-state', { answer: id, state: entry.state })
    await announce(entry.step, direction, ran.applied, { undo: () => void takeBack(id), redo: () => void putBack(id) })
  } finally {
    entry.busy = false
  }
}

export const takeBack = (id: string): Promise<void> => work(id, 'undo')
export const putBack = (id: string): Promise<void> => work(id, 'redo')

/** The answers that stand, that the page learned of after `seq`, in the order it did. */
function standingAfter(seq: number): AnswerEntry[] {
  return Object.values(answerUndo.entries).filter((entry) => entry.state === 'standing' && entry.seq > seq).sort((a, b) => a.seq - b.seq)
}

bindAnswers({
  refresh: refreshAnswers,
  standingAfter: (seq) => standingAfter(seq).map((entry) => ({ id: entry.id, label: entry.label })),
  takeBack,
})
