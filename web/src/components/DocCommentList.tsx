/* All of a document's comments as a list over the field: the open ones first, the resolved ones under their own small
   heading; a row opens its comment at its words. */
import { Fragment } from 'react'
import { computed } from '../reactivity'
import { store } from '../store'
import { docThreads, threadWords } from '../lib/docComments'
import type { CommentThread } from '../lib/api'
import { cx, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './docCommentList.css'

interface Row {
  thread: CommentThread
  /** "Agent" when the last thing said is the agent's: the one author worth naming. */
  who: string
  words: string
  resolved: boolean
  /** The first resolved one, which the small heading stands over. */
  first: boolean
}

export const DocCommentList = tracked(function DocCommentList(attrs: Record<string, unknown>) {
  const s = useSetup({}, () => {
    const rows = computed<Row[]>(() => {
      const all = [
        ...docThreads.value.filter((thread) => thread.resolved_at === null),
        ...docThreads.value.filter((thread) => thread.resolved_at !== null),
      ]
      return all.map((thread, i) => {
        const last = thread.messages[thread.messages.length - 1]
        const resolved = thread.resolved_at !== null
        return {
          thread, who: last?.author === 'agent' ? 'Agent' : '', words: last?.body ?? '', resolved,
          first: resolved && (i === 0 || all[i - 1]!.resolved_at === null),
        }
      })
    })
    return { rows }
  })
  const own = { className: 'doc-list', 'data-role': 'doc-comments-list', role: 'group', 'aria-label': 'Comments' }
  return (
    <section {...fallthrough(own, attrs)}>
      {s.rows.value.map((row) => (
        <Fragment key={row.thread.id}>
          {row.first ? <h3 className="doc-list__head">Resolved</h3> : null}
          <button
            type="button"
            className={cx('doc-list__row', { 'doc-list__row--resolved': row.resolved })}
            data-role="doc-comments-row"
            data-thread-id={row.thread.id}
            onClick={() => store.openCard(row.thread.id)}
          >
            <span className="doc-list__words">{threadWords(row.thread)}</span>
            <span className="doc-list__said">{row.who ? <b>{row.who}</b> : null}{' ' + row.words}</span>
          </button>
        </Fragment>
      ))}
    </section>
  )
})
