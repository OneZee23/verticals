/* A goal's links: one list, the conversation Discuss with agent continues first, then
   the rest by their latest change, three in view and "N more". Each row has one mark for its kind: the agent's own on a
   conversation, the file on a document, the globe on a web page. A conversation's row says when it last moved, and the
   arrow at its end opens it where it lives. */
import type { MouseEvent } from 'react'
import { computed, ref } from '../reactivity'
import { agentChat, agentOf, assetUrl } from '../lib/agentChat'
import { agentName, ago, openSession, sessionsOf, sessionWhen, taskSessions, type TaskSession } from '../lib/taskSessions'
import { openWindow } from '../lib/windows'
import { cx, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import { AppIcon } from './AppIcon'
import './goalLinks.css'

export interface LinkedDoc { key: string; path: string; title: string; updated: string | null; open: () => void; from?: string }

interface Props { goalId: string; goalTitle: string; body: string; docs: LinkedDoc[]; inWindow: boolean }

type Row = {
  key: string; kind: 'conversation' | 'doc' | 'page'; title: string; at: number; mark?: string; note?: string; doc?: string
  inherited?: boolean; open: (from: Element) => void
  /** A session's row: when it last moved, in words, and the way to open it where it lives. */
  when?: string; where?: { label: string; open: () => void }
}

export const GoalLinks = tracked(function GoalLinks(raw: Props & Record<string, unknown>) {
  const { goalId, goalTitle, body, docs, inWindow, ...attrs } = raw
  const s = useSetup({ goalId, goalTitle, body, docs, inWindow }, (props) => {
    /* The task's sessions: what the gateway knows, with the conversations this browser has kept for it, newest first. */
    const conversations = computed(() => {
      const found = new Map<string, TaskSession & { listed: boolean }>()
      for (const thread of agentChat.threads) {
        if (thread.goal?.id === props.goalId) {
          found.set(thread.id, { session: thread.id, provider: thread.provider, title: thread.title, movedAt: thread.updatedAt, outside: false, working: false, listed: false })
        }
      }
      for (const session of agentChat.available ? sessionsOf(props.goalId) : []) {
        const known = found.get(session.session)
        found.set(session.session, { ...session, title: known?.title || session.title || props.goalTitle, movedAt: Math.max(known?.movedAt ?? 0, session.movedAt), listed: true })
      }
      return [...found.values()].sort((a, b) => b.movedAt - a.movedAt)
    })

    const pages = computed(() => {
      const seen = new Set<string>()
      const out: { url: string; title: string }[] = []
      for (const m of props.body.matchAll(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(?<![(\w])(https?:\/\/[^\s<)\]]+[^\s<).,;:!?'"\]])/g)) {
        const url = m[2] ?? m[3]!
        if (seen.has(url)) continue
        seen.add(url)
        out.push({ url, title: m[1] ?? new URL(url).hostname })
      }
      return out
    })

    const rows = computed<Row[]>(() => {
      const talk = conversations.value.map((c): Row => ({
        key: `c:${c.session}`, kind: 'conversation', title: c.title || props.goalTitle, at: c.movedAt, mark: assetUrl(agentOf(c.provider).image),
        when: c.listed ? sessionWhen(c) : ago(c.movedAt, taskSessions.now),
        open: () => window.dispatchEvent(new CustomEvent('verticals:discuss-goal', { detail: { id: props.goalId, session: c.session, provider: c.provider } })),
        where: c.listed ? { label: `Open in ${agentName(c.provider)}`, open: () => void openSession(c) } : undefined,
      }))
      const docs = props.docs.map((d): Row => ({
        key: `d:${d.key}`, kind: 'doc', title: d.title, at: d.updated ? Date.parse(d.updated) : 0, note: d.from ? `from ${d.from}` : undefined,
        doc: d.path, inherited: !!d.from,
        open: (from) => {
          if (props.inWindow) openWindow({ kind: 'doc', target: d.key, title: d.title }, from)
          else d.open()
        },
      }))
      const web = pages.value.map((p): Row => ({
        key: `p:${p.url}`, kind: 'page', title: p.title, at: 0,
        open: (from) => {
          if (props.inWindow) openWindow({ kind: 'page', target: p.url, title: p.title }, from)
          else window.open(p.url, '_blank', 'noopener')
        },
      }))
      const [first, ...others] = talk
      return [...(first ? [first] : []), ...[...others, ...docs, ...web].sort((a, b) => b.at - a.at)]
    })

    const all = ref(false)
    const shown = computed(() => (all.value ? rows.value : rows.value.slice(0, 3)))
    function when(at: number): string {
      if (!at) return ''
      return new Date(at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
    }
    return { rows, all, shown, when }
  })

  const rows = s.rows.value
  if (!rows.length) return null
  return (
    <div {...fallthrough({ className: 'goal-links', 'data-role': 'goal-links' }, attrs)}>
      <ul className="goal-links__list">
        {s.shown.value.map((row) => (
          <li key={row.key} className="goal-links__item">
            <button type="button" className={cx('goal-links__row', { 'goal-links__row--inherited': row.inherited })} data-link-kind={row.kind}
              data-link={row.key} data-doc={row.doc} data-inherited={row.inherited ? 'true' : undefined}
              onClick={(event: MouseEvent<HTMLButtonElement>) => row.open(event.currentTarget)}>
              {row.mark ? (
                <img className="goal-links__mark" alt="" src={row.mark} />
              ) : row.kind === 'doc' ? (
                <AppIcon className="goal-links__mark" name="file" size={14} />
              ) : (
                <AppIcon className="goal-links__mark" name="world" size={14} />
              )}
              <span className="goal-links__title">{row.title}</span>
              {row.note ? <span className="goal-links__note">{row.note}</span> : null}
              <span className="goal-links__date" data-role={row.when ? 'session-when' : undefined}>{row.when ?? s.when(row.at)}</span>
            </button>
            {row.where ? (
              <button type="button" className="goal-links__open" data-role="open-session" aria-label={row.where.label} title={row.where.label}
                onClick={() => row.where!.open()}><AppIcon name="arrow-up-right" size={16} /></button>
            ) : null}
          </li>
        ))}
      </ul>
      {rows.length > 3 ? (
        <button type="button" className="goal-links__more" data-role="goal-links-more" onClick={() => { s.all.value = !s.all.value }}>
          {s.all.value ? 'Show fewer' : `${rows.length - 3} more`}
        </button>
      ) : null}
    </div>
  )
})
