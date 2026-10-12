/* What a column shows while you type: "Nothing today." when its period has no
   match, then the matches of other periods under small grey headlines; under the last column, the note when the server
   cut the list. */
import type { MouseEvent as ReactMouseEvent } from 'react'
import { computed } from '../reactivity'
import { KCardStack } from '../kit'
import { GoalCard } from './GoalCard'
import { found, nothingIn, sectionsFor } from '../lib/finding'
import { commandFilter, serverMatches } from '../lib/commandFilter'
import { store } from '../store'
import type { GoalCardData } from '../types'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './findingSections.css'

interface Props {
  vertical: string
  periodKey: string | null
  shown: GoalCardData[]
}

export const FindingSections = tracked(function FindingSections(raw: Props & Record<string, unknown>) {
  const { vertical, periodKey, shown, ...attrs } = raw
  const s = useSetup({ vertical, periodKey, shown }, (props) => {
    const onBoard = computed(() => {
      const ids = new Set<string>()
      const visit = (goals: GoalCardData[]) => { for (const goal of goals) { ids.add(goal.id); visit(goal.children ?? []) } }
      visit(props.shown)
      return ids
    })
    const sections = computed(() => serverMatches.value
      ? sectionsFor(props.vertical, props.periodKey, serverMatches.value, found.result?.parents ?? {}, onBoard.value)
      : [])
    const planned = computed(() => props.shown.filter(goal => !goal.ghost))
    const cut = computed(() => props.vertical === 'life' && !!serverMatches.value && !!found.result?.truncated)

    /* A goal from another period opens where it lives: the words go and the board moves to it. Its square still ticks. */
    function open(event: ReactMouseEvent): void {
      const target = event.target as HTMLElement
      if (target.closest('[data-cap="complete"], [data-role="goal-actions-trigger"]')) return
      const id = target.closest<HTMLElement>('[data-goal-id]')?.dataset.goalId
      if (!id) return
      event.preventDefault()
      event.stopPropagation()
      commandFilter.text = ''
      void store.navigateToGoal(id)
    }

    function cardProps(goal: GoalCardData) {
      return {
        id: goal.id, parentId: goal.parentId, title: goal.title, done: goal.done, color: goal.color, vertical: goal.vertical,
        columnVertical: props.vertical, children: goal.children,
      }
    }
    return { sections, planned, cut, open, cardProps }
  })
  return (
    <div {...fallthrough({ className: 'finding', 'data-role': 'finding' }, attrs)}>
      {!s.planned.value.length ? <p className="finding__note" data-role="finding-nothing">{nothingIn(vertical)}</p> : null}
      {s.sections.value.map((section) => (
        <section key={section.key} className="finding__period" data-period-key={section.key}
          data-when={section.coming ? 'coming' : 'closed'}>
          <h3 className="finding__headline" data-role="finding-headline">{section.headline}</h3>
          <KCardStack dense onClickCapture={s.open}>
            {section.goals.map((goal) => <GoalCard key={goal.id} {...s.cardProps(goal)} />)}
          </KCardStack>
        </section>
      ))}
      {s.cut.value ? <p className="finding__note" data-role="finding-cut">The first 200 matches. Type more to narrow them.</p> : null}
    </div>
  )
})
