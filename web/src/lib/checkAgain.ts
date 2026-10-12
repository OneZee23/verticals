// "Check again" (docs/design/doc-comments-inline.md). It took the place of "Ready?" (Inbox and Documents redesign, round 5,
// frames m4–m5, and round 8; KK 6–7 Oct 2026: "When commenting or editing document, I believe we should have some sort of a
// button black that will prompt agent to acknowledge edits … Not GO, but Go? It should question user, if he edited …
// Ready?"): when the document in front has something to hand over, a black pill beside the count of its comments, above
// the field. Two things are something: an edit or a comment of this session (kept in memory; ignored, it goes when the
// document closes, as "Ready?" did), and an open comment nobody has answered, whose last word is yours (the threads are on
// the server, so a reload or a reopened document keeps it). A click is your yes: the comments and the edits go to the
// agent in one message, and its answer lands in the field (S2.P4) in two lines. When its turn has ended the document and
// its comments are read again: the words the agent rewrote are lit green (lib/docChanges.ts), and the comments it answered
// stop counting, so the pill goes unless one is left unanswered. After "Check again" on a morning report, its task is done.
import { computed, reactive, watch } from 'vue'
import { fetchDocRevision, getDoc } from './api'
import { agentChat, currentThread, newThread, send } from './agentChat'
import { flushPending } from './beforeQuit'
import { commandFilter } from './commandFilter'
import { rewritten } from './docChanges'
import { frontDocId, unansweredThreads } from './docComments'
import { MORNING_FOLDER, MORNING_TITLE } from './morning'
import { windows } from './windows'
import { store } from '../store'

/** `docs`: the documents with a comment or an edit of this session that has not been handed over. `busy`: the documents
 *  being handed over, from the press until the agent's turn is over and the document and its comments are read again. */
export const check = reactive({ docs: [] as string[], busy: [] as string[] })
const free = (id: string): void => { check.busy = check.busy.filter((other) => other !== id) }

if (typeof window !== 'undefined') {
  window.addEventListener('verticals:doc-edited', (event) => {
    const detail = (event as CustomEvent<{ id?: string; by?: string }>).detail
    // An agent's own rewrite is not an edit of yours to hand back to it.
    if (detail?.by === 'agent') return
    const id = detail?.id
    if (id && !check.docs.includes(id)) check.docs.push(id)
  })
}

const shownIds = computed(() => {
  const ids = new Set(windows.list.filter((w) => w.kind === 'doc').map((w) => w.target))
  if (store.state.docs.currentId) ids.add(store.state.docs.currentId)
  return ids
})
// A document closed with its edits unsaid: the question goes with it.
watch(shownIds, (shown) => { check.docs = check.docs.filter((id) => shown.has(id)) })

/** The document in front has something to hand over: an edit or a comment of this session, or an open comment nobody has
 *  answered. */
const waiting = computed(() => {
  const id = frontDocId.value
  return !!id && (check.docs.includes(id) || unansweredThreads.value.length > 0)
})

/** "Check again" is offered: there is something to hand over, an agent to hand it to, and the field is free. It stays away
 *  from a document being handed over, so it does not flash back between the press and the turn, or at the turn's end before
 *  the comments the agent answered are read. */
export const checkShown = computed(() => {
  const id = frontDocId.value
  return !!id && waiting.value && !check.busy.includes(id) && agentChat.available && !commandFilter.text && !agentChat.running && !agentChat.open
})

/** What the agent is told. It starts a conversation of its own, so the message carries all it needs. */
export function checkAsk(link: string): string {
  return `Check again. I commented on or edited ${link}. Read its open comments and its latest versions to see what I `
    + 'edited, and act on them. A comment in a report\'s "Your comment" goes on its goal, verbatim, and its cell is '
    + 'cleared. Any other comment: change only the words it is about and reply on it; I resolve it myself. Answer in two '
    + 'short lines: what you changed, what you left and why.'
}

/** The longest an agent's turn is waited for before the document is let be. */
const TURN_LIMIT_MS = 15 * 60_000

export async function checkAgain(): Promise<void> {
  const id = frontDocId.value
  // A second press while the first is being handed over is the same press.
  if (!id || check.busy.includes(id) || !waiting.value) return
  check.busy.push(id)
  let following = false
  try {
    // What you wrote is saved first, so the agent reads it and the copy compared afterwards is the one it started from.
    await flushPending()
    const doc = await getDoc(id).catch(() => null)
    // The document could not be read: nothing was sent, and the pill stays for another press.
    if (!doc) return
    check.docs = check.docs.filter((other) => other !== id)
    delete rewritten[id]
    const name = (doc.title || doc.path).replace(/[[\]]/g, '')
    newThread()
    agentChat.engaged = false
    const letGo = followTurn(id, doc.revision)
    following = true
    // The message did not go (the gateway refused it): no turn will start, and the pill comes back.
    void send(checkAsk(`[${name}](#doc/${doc.id})`)).then(() => {
      if (!agentChat.running && currentThread.value?.status !== 'working') letGo()
    })
    // A morning report gone through has nothing left to wait for: its open task is done. The one task is linked to every
    // morning's report (core/morning.py), so only the report of the day it stands in finishes it, not an earlier one
    // (docs/design/agent-fixes.md, fix 2).
    if (!doc.path.startsWith(`${MORNING_FOLDER}/`)) return
    for (const link of doc.linked_goals) {
      const goal = store.state.board?.columns.flatMap((c) => c.goals).find((g) => g.id === link.goal_id)
      if (goal && goal.title === MORNING_TITLE && goal.done_at === null && doc.path === `${MORNING_FOLDER}/${goal.anchor_date}.md`) {
        void store.completeGoal(goal.id, true)
      }
    }
  } finally {
    if (!following) free(id)
  }
}

/** Waits for the agent's turn to end, then reads the document and its comments again. Nothing is lit when the owner wrote
 *  in the document meanwhile: the new revisions are then not all the agent's, and the app cannot tell whose. Returns the
 *  way to give up following (the turn never started). */
function followTurn(id: string, base: number): () => void {
  let began = false
  let touched = false
  // A save of the text is the owner's hand in it (a comment or a reply is not: it leaves the words as they are).
  const own = (event: Event): void => {
    const detail = (event as CustomEvent<{ id?: string; by?: string; doc?: unknown }>).detail
    if (detail?.id === id && detail.by !== 'agent' && detail.doc) touched = true
  }
  window.addEventListener('verticals:doc-edited', own)
  const stopFollowing = (): void => {
    stop()
    clearTimeout(timer)
    window.removeEventListener('verticals:doc-edited', own)
  }
  const giveUp = (): void => {
    stopFollowing()
    free(id)
  }
  const stop = watch(() => agentChat.running, (running) => {
    if (running) {
      began = true
      return
    }
    if (!began) return
    stopFollowing()
    // The pill stays away until the reading is done: the comments the agent answered stop counting first.
    void readAgain(id, base, touched).finally(() => free(id))
  })
  const timer = setTimeout(giveUp, TURN_LIMIT_MS)
  // A turn that has begun is followed to its end; one that never began (the message did not go) is let go.
  return () => { if (!began) giveUp() }
}

async function readAgain(id: string, base: number, touched: boolean): Promise<void> {
  const shown = windows.list.some((w) => w.kind === 'doc' && w.target === id) || store.state.docs.currentId === id
  if (!shown) return
  try {
    const [fresh, before] = await Promise.all([getDoc(id), fetchDocRevision(id, base)])
    if (fresh.revision !== base) {
      if (!touched) rewritten[id] = { before: before.body }
      // The window shows the saved copy (DocWindowBody.vue); Documents shows it by being opened again.
      window.dispatchEvent(new CustomEvent('verticals:doc-edited', {
        detail: { id, title: fresh.title, path: fresh.path, doc: fresh, linksFresh: true, by: 'agent' },
      }))
      if (store.state.docs.currentId === id) await store.openDoc(id)
    }
  } catch {
    // The document or its history could not be read: it stays as it is, and the next look reads it again.
  }
  // Its replies in the comments, and the ones it resolved: what it answered stops counting.
  try {
    if (store.state.comments.targetType === 'doc' && store.state.comments.targetId === id) await store.loadCommentsFor('doc', id)
  } catch {
    // The comments stay as they were.
  }
}
