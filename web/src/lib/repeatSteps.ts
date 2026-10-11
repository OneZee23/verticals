// A tick of a repeating goal makes the goal's next occurrence on the server (`core/repeat.py`), so a tick taken back by ⌘Z
// leaves two goals where there was one. The step takes the occurrence back with the tick, when nobody has touched it since,
// and playing the tick again makes it again (docs/design/board-undo.md). Which goal it is, is not guessed: the server's
// answer to the tick names it (`next_occurrence`), and says nothing when the occurrence was already there, since only what
// the tick made is the tick's to take back.
import { ApiError, fetchGoalComments, getGoal, type GoalCard } from './api'
import type { Step } from './boardHistory'
import type { Outcome } from './boardRestore'
import { sendAway } from './goalSteps'

/** What the last tick of each goal made. The store notes the server's answer to every tick, those the person makes and those
 *  undo and redo make, and clears it for a tick that made nothing; whoever wrapped the tick takes it. */
const made = new Map<string, GoalCard>()

export function noteOccurrence(id: string, occurrence: GoalCard | null | undefined): void {
  if (occurrence) made.set(id, occurrence)
  else made.delete(id)
}

export function takeOccurrence(id: string): GoalCard | null {
  const occurrence = made.get(id) ?? null
  made.delete(id)
  return occurrence
}

/** Whether the occurrence is as the tick left it: not written to since (the server stamps every write), no steps added, no
 *  comment on it. */
async function untouched(occurrence: GoalCard): Promise<boolean> {
  const now = await getGoal(occurrence.id)
  if (now.updated_at !== occurrence.updated_at || now.children.length > 0) return false
  return (await fetchGoalComments(occurrence.id)).threads.length === 0
}

/** Sends the occurrence to the trash unless someone has touched it. `done`: it is gone, or was left on purpose. */
async function takeBack(occurrence: GoalCard): Promise<Outcome> {
  try {
    if (!(await untouched(occurrence))) return 'done'
  } catch (err) {
    return err instanceof ApiError && err.status === 404 ? 'done' : 'retry'
  }
  const outcome = await sendAway(occurrence.id, occurrence.title)
  return outcome === 'drop' ? 'done' : outcome // refused or gone already: nothing is left to take back
}

/** `step`, a tick, that also takes back the occurrence the tick made (`first`, from the server's answer; `null`: it made
 *  none, and the step is `step` as it is). */
export function withOccurrence(step: Step, first: GoalCard | null): Step {
  if (!first) return step
  let occurrence: GoalCard | null = first
  return {
    ...step,
    async undo(): Promise<Outcome> {
      const outcome = await step.undo()
      return outcome === 'done' && occurrence ? takeBack(occurrence) : outcome
    },
    async redo(): Promise<Outcome> {
      const outcome = await step.redo()
      // The tick played again made its own occurrence, under its own id, or found the one a person kept.
      if (outcome === 'done') occurrence = takeOccurrence(step.id)
      return outcome
    },
  }
}
