// "Check again" (docs/design/doc-comments-inline.md). It took the place of "Ready?" (Inbox and Documents redesign, round 5,
// frames m4–m5, and round 8; KK 6–7 Oct 2026: "When commenting or editing document, I believe we should have some sort of a
// button black that will prompt agent to acknowledge edits … Not GO, but Go? It should question user, if he edited …
// Ready?"): after a comment or an edit in the document in front, a black pill beside the count of its comments, above the
// field. A click is your yes: the comments and the edits go to the agent in one message, and its answer lands in the field
// (S2.P4) in two lines. When its turn has ended the document is read again, and the words the agent rewrote are lit green
// in it (lib/docChanges.ts). Ignored, the question goes when the document closes. After "Check again" on a morning
// report, its task is done.
import { computed, reactive, watch } from 'vue'
import { fetchDocRevision, getDoc } from './api'
import { agentChat, newThread, send } from './agentChat'
import { flushPending } from './beforeQuit'
import { commandFilter } from './commandFilter'
import { rewritten } from './docChanges'
import { frontDocId } from './docComments'
import { MORNING_FOLDER, MORNING_TITLE } from './morning'
import { windows } from './windows'
import { store } from '../store'

/** The documents with a comment or an edit that has not been handed over. */
export const check = reactive({ docs: [] as string[] })

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

/** "Check again" is offered: the document in front has a comment or an edit to hand over, there is an agent to hand it to,
 *  and the field is free. */
export const checkShown = computed(() => {
  const id = frontDocId.value
  return !!id && agentChat.available && check.docs.includes(id) && !commandFilter.text && !agentChat.running && !agentChat.open
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
  if (!id || !check.docs.includes(id)) return
  // What you wrote is saved first, so the agent reads it and the copy compared afterwards is the one it started from.
  await flushPending()
  check.docs = check.docs.filter((other) => other !== id)
  const doc = await getDoc(id).catch(() => null)
  if (!doc) return
  delete rewritten[id]
  const name = (doc.title || doc.path).replace(/[[\]]/g, '')
  newThread()
  agentChat.engaged = false
  void send(checkAsk(`[${name}](#doc/${doc.id})`))
  followTurn(id, doc.revision)
  // A morning report gone through has nothing left to wait for: its open task is done.
  if (!doc.path.startsWith(`${MORNING_FOLDER}/`)) return
  for (const link of doc.linked_goals) {
    const goal = store.state.board?.columns.flatMap((c) => c.goals).find((g) => g.id === link.goal_id)
    if (goal && goal.title === MORNING_TITLE && goal.done_at === null) void store.completeGoal(goal.id, true)
  }
}

/** Waits for the agent's turn to end, then reads the document again and lights what it rewrote. Nothing is lit when the
 *  owner wrote in the document meanwhile: the new revisions are then not all the agent's, and the app cannot tell whose. */
function followTurn(id: string, base: number): void {
  let began = false
  let touched = false
  const own = (event: Event): void => {
    const detail = (event as CustomEvent<{ id?: string; by?: string }>).detail
    if (detail?.id === id && detail.by !== 'agent') touched = true
  }
  window.addEventListener('verticals:doc-edited', own)
  const done = (): void => {
    stop()
    clearTimeout(timer)
    window.removeEventListener('verticals:doc-edited', own)
  }
  const stop = watch(() => agentChat.running, (running) => {
    if (running) {
      began = true
      return
    }
    if (!began) return
    done()
    void lightWhatChanged(id, base, touched)
  })
  const timer = setTimeout(done, TURN_LIMIT_MS)
}

async function lightWhatChanged(id: string, base: number, touched: boolean): Promise<void> {
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
    // Its replies in the comments, and the ones it resolved.
    if (store.state.comments.targetType === 'doc' && store.state.comments.targetId === id) await store.loadCommentsFor('doc', id)
  } catch {
    // The document or its history could not be read: it stays as it is, and the next look reads it again.
  }
}
