/* What an agent's message made or changed, one chip under another in the order the message links them
   (web/src/components/AgentChips.tsx, docs/design/agent-chips.md): a document by its first page, a goal by its square. */
import { DocChip } from './DocChip'
import { GoalChip } from './GoalChip'
import type { ChipLink } from '../lib/chipLinks'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import './agentChips.css'

interface Props {
  links: ChipLink[]
}

export const AgentChips = tracked(function AgentChips({ links, ...attrs }: Props & Record<string, unknown>) {
  return (
    <div {...fallthrough({ className: 'agent-chips', 'data-role': 'agent-chips' }, attrs)}>
      {links.map((link) => (link.kind === 'doc'
        ? <DocChip key={`${link.kind}:${link.id}`} id={link.id} label={link.label} dark />
        : <GoalChip key={`${link.kind}:${link.id}`} id={link.id} label={link.label} />))}
    </div>
  )
})
