/* A goal's comments, docked to the window's right edge over the board: one instance at the app's root, not a modal; shut
   while the target is a document, whose comments open on their words. A resolved
   thread wears `data-resolved`, which the kit's own CSS collapses. */
import type { KeyboardEvent } from 'react'
import { computed, nextTick, reactive, ref, watch } from '../reactivity'
import { KCommentNew, KCommentStack, KCommentThread } from '../kit'
import { AppIcon } from './AppIcon'
import { store } from '../store'
import { windows } from '../lib/windows'
import type { CommentThread } from '../lib/api'
import { bindRef, cx, fallthrough, valueOf } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './commentsPanel.css'

const QUOTE_TITLE_MAX = 60

export const CommentsPanel = tracked(function CommentsPanel(attrs: Record<string, unknown>) {
  const s = useSetup({}, () => {
    const rootEl = ref<HTMLElement | null>(null)
    const newDraft = ref('')
    const replyDrafts = reactive<Record<string, string>>({})

    const threads = computed(() => store.state.comments.threads)
    const pendingAnchor = computed(() => store.state.comments.pendingAnchor)
    const targetType = computed(() => store.state.comments.targetType)

    function threadTitle(thread: CommentThread): string {
      const quote = thread.anchor?.quote.trim()
      if (quote) return quote.length > QUOTE_TITLE_MAX ? `${quote.slice(0, QUOTE_TITLE_MAX)}…` : quote
      return targetType.value === 'doc' ? 'Whole document' : 'Whole card'
    }

    function threadMessages(thread: CommentThread) {
      return thread.messages.map((m) => ({
        id: m.id,
        body: m.body,
        role: m.author === 'agent' ? 'agent' : undefined,
      }))
    }

    const composerTitle = computed(() => {
      if (pendingAnchor.value) return 'Comment on selection'
      return targetType.value === 'doc' ? 'Comment on this document' : 'Comment on this card'
    })

    async function commitNewThread(): Promise<void> {
      const body = newDraft.value
      if (!body.trim()) return
      const ok = await store.submitNewThread(body)
      if (ok) newDraft.value = ''
    }

    async function commitReply(threadId: string): Promise<void> {
      const body = replyDrafts[threadId] ?? ''
      if (!body.trim()) return
      const ok = await store.submitReply(threadId, body)
      if (ok) replyDrafts[threadId] = ''
    }

    function toggleResolve(thread: CommentThread): void {
      void store.setThreadResolved(thread.id, thread.resolved_at === null)
    }

    function close(): void {
      store.closeCommentsPanel()
    }

    // A highlight click sets `focusThreadId`: the thread's row scrolls into view once and the request clears, so a second
    // click on the same highlight scrolls again.
    watch(
      () => store.state.comments.focusThreadId,
      (id) => {
        if (!id) return
        void nextTick(() => {
          const row = rootEl.value?.querySelector(`[data-role="comment-thread-row"][data-thread-id="${id}"]`)
          row?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
          store.state.comments.focusThreadId = null
        })
      },
    )
    return { rootEl, newDraft, replyDrafts, threads, pendingAnchor, threadTitle, threadMessages, composerTitle, commitNewThread, commitReply, toggleResolve, close }
  })

  if (!(store.state.comments.open && store.state.comments.targetType !== 'doc')) return null
  const threads = s.threads.value
  const pendingAnchor = s.pendingAnchor.value
  const own = {
    ref: bindRef(s.rootEl),
    className: cx('comments-panel', { 'comments-panel--over-windows': windows.list.length > 0 }),
    'data-role': 'comments-panel',
    'aria-label': 'Comments',
  }
  return (
    <aside {...fallthrough(own, attrs)}>
      <div className="comments-panel__header">
        <span className="t-subtitle">Comments</span>
        <button
          type="button"
          className="comments-panel__close"
          data-role="comments-close"
          aria-label="Close comments"
          onClick={s.close}
        ><AppIcon name="x" size={16} /></button>
      </div>

      {pendingAnchor ? (
        <div className="comments-panel__anchor-preview" data-role="comments-pending-anchor">
          <span className="t-caption t-muted">Commenting on:</span>
          <span className="t-caption comments-panel__anchor-quote">{`“${pendingAnchor.quote}”`}</span>
          <button
            type="button"
            className="comments-panel__anchor-clear"
            aria-label="Comment on the whole card instead"
            onClick={() => store.clearPendingAnchor()}
          ><AppIcon name="x" size={12} /></button>
        </div>
      ) : null}

      <KCommentStack className="comments-panel__stack">
        <KCommentNew
          data-role="comments-new"
          title={s.composerTitle.value}
          placeholder="Write a comment…"
          commitLabel="Comment"
          modelValue={s.newDraft.value}
          onUpdate:modelValue={(value: string) => {
            s.newDraft.value = value
          }}
          onCommit={() => void s.commitNewThread()}
        />

        {store.state.comments.loading && !threads.length ? (
          <p className="t-caption t-muted comments-panel__state">{' Loading… '}</p>
        ) : !threads.length ? (
          <p className="t-caption t-muted comments-panel__state" data-role="comments-empty">{' No comments yet. '}</p>
        ) : null}

        {threads.map((thread) => (
          <div key={thread.id} className="comments-panel__thread-row" data-role="comment-thread-row" data-thread-id={thread.id}>
            <KCommentThread
              title={s.threadTitle(thread)}
              state="active"
              messages={s.threadMessages(thread)}
              data-role="comment-thread"
              data-thread-id={thread.id}
              data-resolved={thread.resolved_at ? 'true' : undefined}
            />
            <div className="comments-panel__thread-foot">
              <button
                type="button"
                className="comments-panel__resolve"
                data-role="comment-resolve-toggle"
                onClick={() => s.toggleResolve(thread)}
              >{thread.resolved_at ? 'Unresolve' : 'Resolve'}</button>
            </div>
            {!thread.resolved_at ? (
              <label className="field comment-thread__reply comments-panel__reply">
                <input
                  className="t-caption field__input"
                  type="text"
                  placeholder="Reply…"
                  data-role="comment-reply-input"
                  {...valueOf(s.replyDrafts[thread.id] ?? '', (event) => { s.replyDrafts[thread.id] = event.currentTarget.value })}
                  onKeyDown={(event: KeyboardEvent) => {
                    if (event.key !== 'Enter') return
                    event.preventDefault()
                    void s.commitReply(thread.id)
                  }}
                />
              </label>
            ) : null}
          </div>
        ))}
      </KCommentStack>
    </aside>
  )
})
