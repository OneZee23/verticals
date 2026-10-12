/* Above the field: the count of the document's comments (a list of them on a press) and Check again, which hands the comments
   and edits to the agent; for a report, Send to developers and Improve it in the same row. It rises with the field and is
   out of the way while the conversation is open, a message is typed or a goal is moved. */
import { computed, onBeforeUnmount, onMounted, watch } from '../reactivity'
import { DocCommentList } from './DocCommentList'
import { store } from '../store'
import { agentChat } from '../lib/agentChat'
import { circle } from '../lib/circle'
import { commandFilter } from '../lib/commandFilter'
import { checkAgain, checkShown } from '../lib/checkAgain'
import { docThreads, followFrontDoc, frontDocId, openThreads } from '../lib/docComments'
import { altHeld, improveIt, improveShown, links, reportShown, sendShown } from '../lib/reportActions'
import { cx, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import { TransitionGroup } from '../Transition'
import './docCheck.css'

export const DocCheck = tracked(function DocCheck(attrs: Record<string, unknown>) {
  const s = useSetup({}, () => {
    const count = computed(() => openThreads.value.length)
    const resolved = computed(() => docThreads.value.length - count.value)
    /** The document has comments, and none of them is open. */
    const resolvedOnly = computed(() => count.value === 0 && resolved.value > 0)
    const hasThreads = computed(() => docThreads.value.length > 0)
    const label = computed(() => (resolvedOnly.value ? `${resolved.value} resolved` : `${count.value} ${count.value === 1 ? 'comment' : 'comments'}`))
    const name = computed(() => (resolvedOnly.value ? `${resolved.value} resolved ${resolved.value === 1 ? 'comment' : 'comments'}` : undefined))
    const out = computed(() => agentChat.open || !!commandFilter.text || circle.moving)
    const docPills = computed(() => !!frontDocId.value && (hasThreads.value || checkShown.value))
    const shown = computed(() => !out.value && (docPills.value || reportShown.value))
    const listOpen = computed(() => store.state.comments.listOpen)

    const stop = followFrontDoc()
    onBeforeUnmount(stop)
    // With nothing to stand over the list goes; with only resolved comments left it stays, and shows them.
    watch(shown, (now) => { if (!now) store.setCommentList(false) })

    function toggle(): void {
      store.setCommentList(!listOpen.value)
    }

    /* A pill that goes keeps its place while it fades, out of the row, so the one beside it glides to its new place at once. */
    function holdPlace(el: Element): void {
      const pill = el as HTMLElement
      const home = pill.offsetParent?.getBoundingClientRect()
      const box = pill.getBoundingClientRect()
      if (!home) return
      pill.style.left = `${box.left - home.left}px`
      pill.style.top = `${box.top - home.top}px`
    }

    /* The list goes with Esc, or a press anywhere but on it and its pill. Esc is taken before anything under it. */
    function onKey(event: KeyboardEvent): void {
      if (event.key !== 'Escape' || !listOpen.value || event.isComposing) return
      event.preventDefault()
      event.stopPropagation()
      store.setCommentList(false)
    }
    function onPointerDown(event: PointerEvent): void {
      if (!listOpen.value) return
      const target = event.target as Element | null
      if (target?.closest('[data-role="doc-comments-list"], [data-role="doc-comments-count"]')) return
      store.setCommentList(false)
    }
    onMounted(() => {
      window.addEventListener('keydown', onKey, true)
      document.addEventListener('pointerdown', onPointerDown, true)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('keydown', onKey, true)
      document.removeEventListener('pointerdown', onPointerDown, true)
    })

    return { resolvedOnly, hasThreads, label, name, shown, listOpen, toggle, holdPlace }
  })

  if (!s.shown.value) return null
  const listOpen = s.listOpen.value
  const hasThreads = s.hasThreads.value
  const resolvedOnly = s.resolvedOnly.value
  const send = sendShown.value ? links.value : null
  return (
    <div {...fallthrough({ className: 'doc-check', 'data-role': 'doc-check' }, attrs)}>
      <div className="doc-check__row">
        <TransitionGroup name="doc-check-pill" onBeforeLeave={s.holdPlace}>
          {hasThreads ? (
            <button
              key="count"
              type="button"
              className={cx('doc-check__pill doc-check__count', { 'doc-check__count--resolved': resolvedOnly })}
              data-role="doc-comments-count"
              aria-label={s.name.value}
              aria-expanded={listOpen}
              onClick={s.toggle}
            >{!resolvedOnly ? <i className="doc-check__dot" aria-hidden="true"></i> : null}{s.label.value}</button>
          ) : null}
          {checkShown.value ? (
            <button
              key="check"
              type="button"
              className="doc-check__pill doc-check__again"
              data-role="doc-check-again"
              onClick={() => void checkAgain()}
            >Check again</button>
          ) : null}
          {send ? (
            <a
              key="send"
              className="doc-check__pill doc-check__send"
              data-role="report-send"
              href={altHeld.value ? send.mail : send.issue}
              target="_blank"
              rel="noopener noreferrer"
              title="Opens a GitHub issue with this report for you to read and submit. Hold Option for an email draft."
            >{altHeld.value ? 'Send by email' : 'Send to developers'}</a>
          ) : null}
          {improveShown.value ? (
            <button
              key="improve"
              type="button"
              className="doc-check__pill doc-check__improve"
              data-role="report-improve"
              onClick={() => void improveIt()}
            >Improve it</button>
          ) : null}
        </TransitionGroup>
        {listOpen && hasThreads ? <DocCommentList /> : null}
      </div>
    </div>
  )
})
