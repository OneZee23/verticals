/* A source's state at the top of its window (web/src/components/SourceStrip.tsx; docs/design/sources.md; lib/sources.ts):
   what its check last found, the check in words (for a check that waits, the exact text you are approving), and the one
   thing to do: Approve a check that waits for you, Fix a source that stopped answering. Nothing else here; the document
   under it is the source's own page. */
import { computed, onMounted, ref, watch } from '../reactivity'
import { KButton } from '../kit'
import { agentChat } from '../lib/agentChat'
import { approve, detailOf, fixSource, loadSources, noteOf, sourceOf } from '../lib/sources'
import { store } from '../store'
import { cx, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './sourceStrip.css'

interface Props {
  id: string
}

export const SourceStrip = tracked(function SourceStrip(raw: Props & Record<string, unknown>) {
  const { id, ...attrs } = raw
  const s = useSetup({ id }, (props) => {
    const source = computed(() => sourceOf(props.id))
    const note = computed(() => (source.value ? noteOf(source.value) : null))
    /* Sentence case in the window; the tile says it in lower case under the name. */
    const head = computed(() => (note.value ? note.value.text.charAt(0).toUpperCase() + note.value.text.slice(1) : ''))
    const detail = computed(() => (source.value ? detailOf(source.value) : ''))
    const canFix = computed(() => source.value?.status === 'red' && agentChat.available)

    const busy = ref(false)
    const problem = ref('')
    async function onApprove(): Promise<void> {
      if (!source.value || busy.value) return
      busy.value = true
      problem.value = ''
      const result = await approve(source.value)
      busy.value = false
      if (result === 'changed') problem.value = 'The check changed while you read it. Read it again.'
      else if (result === 'failed') problem.value = 'Could not approve. Try again.'
    }
    onMounted(() => void loadSources())
    // An answer to the check rings the board's bell (the same one a goal's change rings): read the state again.
    watch(() => store.state.board, () => void loadSources())
    return { source, note, head, detail, canFix, busy, problem, onApprove }
  })
  const source = s.source.value
  const note = s.note.value
  if (!(source && note)) return null
  return (
    <div {...fallthrough({ className: 'source-strip', 'data-role': 'source-strip', 'data-state': source.status, 'data-why': source.why ?? undefined }, attrs)}>
      <div className="source-strip__text">
        <p className={cx('source-strip__state', { 'source-strip__state--red': note.tone === 'red' })} data-role="source-strip-state">{s.head.value}</p>
        {s.detail.value ? <p className="source-strip__detail" data-role="source-strip-detail">{s.detail.value}</p> : null}
        {source.summary ? <p className="source-strip__check" data-role="source-strip-check">{source.summary}</p> : null}
        {s.problem.value ? <p className="source-strip__problem" data-role="source-strip-problem" role="status">{s.problem.value}</p> : null}
      </div>
      {source.needs_approval ? (
        <KButton primary data-role="source-approve" disabled={s.busy.value} onClick={() => void s.onApprove()}>Approve</KButton>
      ) : s.canFix.value ? (
        <KButton primary data-role="source-fix" onClick={() => fixSource(source)}>Fix</KButton>
      ) : null}
    </div>
  )
})
