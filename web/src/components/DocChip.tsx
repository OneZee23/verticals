/* A document as one thing in a list: its own first page on the left (50 × 67), its name
   and when it was edited on the right, or for a source its state ("checked 07:00", in red "not answering since 06:00").
   On a message's black (`dark`) or a ghost on the Inbox desk. A click opens the document as a window. */
import type { MouseEvent } from 'react'
import { computed } from '../reactivity'
import { DocPage } from './DocPage'
import { docCard, type DocCard } from '../lib/docCard'
import { whenEdited } from '../lib/docsDesk'
import { openWindow } from '../lib/windows'
import { cx, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup, withDefaults } from '../setup'
import './docChip.css'

interface Props {
  id: string
  doc?: DocCard | null
  dark?: boolean
  label?: string
  note?: string
  tone?: 'ok' | 'grey' | 'red'
}
const DEFAULTS = { dark: false }

export const DocChip = tracked(function DocChip(raw: Props & Record<string, unknown>) {
  const { id, doc, dark, label, note, tone, ...attrs } = withDefaults(raw, DEFAULTS)
  const s = useSetup({ id, doc, dark, label, note, tone }, (props) => {
    const card = computed(() => props.doc ?? docCard(props.id))
    /* A document with no title is called by its file's name. */
    const name = computed(() => card.value?.title || card.value?.path.split('/').pop() || props.label || 'Document')

    function open(event: Pick<Event, 'currentTarget'>): void {
      openWindow({ kind: 'doc', target: props.id, title: name.value }, event.currentTarget as Element)
    }
    return { card, name, open }
  })
  const card = s.card.value
  function onClick(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation()
    s.open(event)
  }
  return (
    <button {...fallthrough({ type: 'button', className: cx('doc-chip', { 'doc-chip--dark': dark }), 'data-role': 'doc-chip', 'data-doc-id': id, onClick }, attrs)}>
      <span className="doc-chip__page">{card ? <DocPage doc={card} width={50} /> : null}</span>
      <span className="doc-chip__text">
        <span className="doc-chip__name">{s.name.value}</span>
        {note ? (
          <span className={cx('doc-chip__when', { 'doc-chip__when--red': tone === 'red' })} data-role="source-state" data-tone={tone}>{note}</span>
        ) : card ? (
          <span className="doc-chip__when">{whenEdited(card.updated_at)}</span>
        ) : null}
      </span>
    </button>
  )
})
