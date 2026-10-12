/* One line of facts under an opened goal's title: its date, its size for a week or day
   goal, its open comments and the way to the agent, in that order. Each fact is also the control that changes it: the date
   opens the schedule popup, the size its editor, the comments their sidebar (D255). "Discuss with agent" is the one action,
   so it is the one black word. */
import type { Ref as ReactRef } from 'react'
import { computed } from '../reactivity'
import { SchedulePopover } from './SchedulePopover'
import { ShotSizeFields } from '../kit-ext/shot-size-fields/ShotSizeFields'
import { store } from '../store'
import { agentChat as agentChatState } from '../lib/agentChat'
import { plannedPeriodLabel } from '../lib/schedule'
import { MONTH_NAMES, type VerticalScale } from '../lib/periods'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './goalFacts.css'

interface Props {
  id: string
  ref?: ReactRef<HTMLParagraphElement>
  className?: string
}

export const GoalFacts = tracked(function GoalFacts(raw: Props & Record<string, unknown>) {
  const { id, ...attrs } = raw
  const s = useSetup({ id }, (props) => {
    const goal = computed(() => (store.state.goalDetail?.id === props.id ? store.state.goalDetail : null))

    /* The app's own task says where it lives and when it was made: "Inbox · made Mon 28 Sep". */
    const made = computed(() => {
      const g = goal.value
      if (!g || g.vertical || g.origin !== 'app') return null
      const d = new Date(g.created_at)
      return `made ${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()]} ${d.getDate()} ${MONTH_NAMES[d.getMonth()]!.slice(0, 3)}`
    })
    const dateLabel = computed(() => {
      const g = goal.value
      if (!g?.vertical) return made.value ? 'Inbox' : 'Schedule'
      if (g.vertical === 'life') return 'Life'
      return plannedPeriodLabel(g)
    })
    const sized = computed(() => goal.value?.vertical === 'week' || goal.value?.vertical === 'day')

    const commentCount = computed(() => store.unresolvedCommentCount('goal', props.id))
    const commentsOpenHere = computed(() => {
      const c = store.state.comments
      return c.open && c.targetType === 'goal' && c.targetId === props.id
    })
    function toggleComments(): void {
      if (commentsOpenHere.value) store.closeCommentsPanel()
      else store.openCommentsPanel('goal', props.id)
    }

    /* Only where an agent exists. */
    const agentChat = computed(() => agentChatState.available)
    function discuss(): void {
      window.dispatchEvent(new CustomEvent('verticals:discuss-goal', { detail: { id: props.id } }))
    }

    function onSchedule(scale: VerticalScale, periodKey: string): void {
      void store.scheduleGoalTo(props.id, scale, periodKey)
    }
    return { goal, made, dateLabel, sized, commentCount, commentsOpenHere, toggleComments, agentChat, discuss, onSchedule }
  })

  const goal = s.goal.value
  if (!goal) return null
  const dateLabel = s.dateLabel.value
  const made = s.made.value
  const commentCount = s.commentCount.value
  const sep = <span className="goal-facts__sep" aria-hidden="true">·</span>
  return (
    <p {...fallthrough({ className: 'goal-facts', 'data-role': 'goal-facts' }, attrs)}>
      <SchedulePopover
        {...store.scheduleGrid.value.props}
        onSelect={s.onSchedule}
        onNavigate={store.navigateSchedule}
        onOpen={() => store.resetScheduleView()}
        trigger={({ open }) => (
          <button type="button" className="goal-facts__item" data-cap="schedule" aria-haspopup="menu" aria-expanded={open}>
            {dateLabel}
          </button>
        )}
      />
      {made ? (
        <>
          {sep}
          <span className="goal-facts__made" data-role="goal-made">{made}</span>
        </>
      ) : null}
      {s.sized.value ? (
        <>
          {sep}
          <ShotSizeFields
            className="goal-facts__size"
            expected={goal.size_expected}
            actual={goal.size_actual}
            onChangeExpected={(value) => store.updateGoal(id, { size_expected: value })}
          />
        </>
      ) : null}
      {commentCount > 0 ? (
        <>
          {sep}
          <button type="button" className="goal-facts__item" data-cap="open-comments" aria-expanded={s.commentsOpenHere.value}
            onClick={s.toggleComments}>
            {`${commentCount} ${commentCount === 1 ? 'comment' : 'comments'}`}
          </button>
        </>
      ) : null}
      {s.agentChat.value ? (
        <>
          {sep}
          <button type="button" className="goal-facts__item goal-facts__item--act" data-cap="discuss" onClick={s.discuss}>
            Discuss with agent
          </button>
        </>
      ) : null}
    </p>
  )
})
