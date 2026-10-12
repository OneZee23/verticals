/* The right pane's history mode, in DocDetail's place while
   `store.state.docs.historyOpen`: the revision list, and once a row is clicked, that revision's text read-only. Restoring
   copies that text forward as a new revision and returns to the live document; the UI says so rather than implying a
   rewind. Never a modal. */
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { nextTick, watch, ref } from '../reactivity'
import { AppIcon } from './AppIcon'
import { store } from '../store'
import { internalLinkOf, renderBodyElement } from '../lib/bodyMarkdown'
import { bindRef, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './docsHistory.css'

export const DocsHistory = tracked(function DocsHistory(attrs: Record<string, unknown>) {
  const s = useSetup({}, () => {
    const bodyEl = ref<HTMLElement | null>(null)

    function paintRevisionBody(): void {
      void nextTick(() => {
        const revision = store.state.docs.viewingRevision
        if (bodyEl.value && revision) renderBodyElement(bodyEl.value, revision.body)
      })
    }
    watch(() => store.state.docs.viewingRevision?.revision, paintRevisionBody, { immediate: true })

    function onBodyClick(event: MouseEvent): void {
      const internal = internalLinkOf((event.target as HTMLElement).closest('a'))
      if (!internal) return
      event.preventDefault()
      void store.followBodyLink(internal)
    }

    function formatSavedAt(iso: string): string {
      return new Date(iso).toLocaleString()
    }
    return { bodyEl, onBodyClick, formatSavedAt }
  })

  const docs = store.state.docs
  const viewing = docs.viewingRevision
  return (
    <div {...fallthrough({ className: 'docs-history', 'data-role': 'docs-history' }, attrs)}>
      <div className="docs-history__toolbar">
        {viewing ? (
          <button type="button" className="docs-history__back" data-role="docs-history-back" onClick={() => store.backToHistoryList()}>
            <AppIcon name="arrow-left" size={14} />{' Back to history '}
          </button>
        ) : (
          <span className="t-caption t-muted">History</span>
        )}
        <button
          type="button"
          className="docs-history__close"
          data-role="docs-history-close"
          aria-label="Close history"
          onClick={() => store.closeHistory()}
        >
          <AppIcon name="x" size={16} />
        </button>
      </div>

      {docs.historyLoading ? (
        <p className="t-caption t-muted">Loading…</p>
      ) : viewing ? (
        <>
          <div className="docs-history__revision-meta">
            <p className="t-caption t-muted">{` Revision ${viewing.revision} · ${s.formatSavedAt(viewing.saved_at)}`}</p>
            <button
              type="button"
              className="docs-history__restore"
              data-role="docs-history-restore"
              onClick={() => void store.restoreRevision(store.state.docs.viewingRevision!.revision)}
            >Restore this revision (as a new revision)</button>
          </div>
          <h2 className="docs-history__revision-title">{viewing.title || '(untitled)'}</h2>
          <div
            ref={bindRef(s.bodyEl)}
            className="goal-detail__body"
            data-role="docs-history-body"
            data-hide-title={viewing.title ?? undefined}
            onClick={(event) => s.onBodyClick(event.nativeEvent)}
          ></div>
        </>
      ) : (
        <ul className="docs-history__list" data-role="docs-history-list">
          {docs.history && docs.history.length === 0 ? <li className="t-caption t-muted">{' No saved revisions yet. '}</li> : null}
          {(docs.history ?? []).map((rev) => (
            <li
              key={rev.revision}
              className="docs-history__row"
              data-role="docs-history-row"
              data-revision={rev.revision}
              role="button"
              tabIndex={0}
              onClick={() => void store.viewRevision(rev.revision)}
              onKeyDown={(event: ReactKeyboardEvent) => {
                if (event.key !== 'Enter') return
                event.preventDefault()
                void store.viewRevision(rev.revision)
              }}
            >
              <span className="docs-history__row-revision">{`Rev ${rev.revision}`}</span>
              <span className="docs-history__row-title">{rev.title || '(untitled)'}</span>
              <span className="docs-history__row-meta t-caption t-muted">{`${s.formatSavedAt(rev.saved_at)} · ${rev.body_length} chars `}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
})
