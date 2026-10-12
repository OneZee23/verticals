// The comments of the document in front (docs/design/doc-comments-inline.md): which document the pills above the field
// speak for, its threads and how many are open, and the one place that keeps the comments slice on it. The slice holds one
// target at a time (`lib/comments.ts`); a document in front is that target.
import { computed, watch } from '../reactivity'
import { store } from '../store'
import { frontWindow } from './windows'
import type { CommentThread } from './api'

/** The document in front: the window in the centre when it is one, else the document Documents shows by itself (opened
 *  by its address or a link). A goal's window in front, or no document at all, is none. */
export const frontDocId = computed<string | null>(() => {
  const win = frontWindow.value
  if (win) return win.kind === 'doc' ? win.target : null
  const docs = store.state.docs
  return store.state.activeView === 'docs' && !docs.historyOpen && docs.current ? docs.current.id : null
})

/** Its threads, in the order they were made; none while the slice holds another target. */
export const docThreads = computed<CommentThread[]>(() => {
  const id = frontDocId.value
  const comments = store.state.comments
  return id && comments.targetType === 'doc' && comments.targetId === id ? comments.threads : []
})

export const openThreads = computed(() => docThreads.value.filter((thread) => thread.resolved_at === null))

/** The open comments nobody has answered: the last thing said on them is the person's. The threads are on the server, so
 *  this is still true after a reload or a reopened document (lib/checkAgain.ts offers Check again for them). */
export const unansweredThreads = computed(() => openThreads.value.filter((thread) => thread.messages[thread.messages.length - 1]?.author === 'human'))

/** What the list and the card call a comment's words: the quote, or the whole page when it has none. */
export function threadWords(thread: CommentThread): string {
  return thread.anchor?.quote.trim() || 'Whole document'
}

/** Keeps the comments slice on the document in front, and what stood open for the one before it shut. A goal's docked
 *  panel is a goal's alone: it goes when a document comes to the front. Returns the way to stop. */
export function followFrontDoc(): () => void {
  return watch(frontDocId, (id) => {
    store.closeCard()
    store.setCommentList(false)
    if (!id) return
    store.closeCommentsPanel()
    const comments = store.state.comments
    if (comments.targetType !== 'doc' || comments.targetId !== id) void store.loadCommentsFor('doc', id)
  }, { immediate: true })
}
