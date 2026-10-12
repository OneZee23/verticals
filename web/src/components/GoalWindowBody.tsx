/* A goal in a window: going deeper's opened card, in full, in its colour, drawn in
   the window instead of its column. It holds the open goal while it is in front, and gives it back when it goes. */
import { computed, onBeforeUnmount, watch } from '../reactivity'
import { GoalCard } from './GoalCard'
import { store } from '../store'
import { closeWindow, windows } from '../lib/windows'
import type { GoalCardData } from '../types'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './goalWindowBody.css'

interface Props {
  id: string
  front: boolean
}

export const GoalWindowBody = tracked(function GoalWindowBody({ id, front, ...attrs }: Props & Record<string, unknown>) {
  const s = useSetup({ id, front }, (props) => {
    const hostKey = computed(() => `window:root:0:${props.id}`)

    watch(() => [props.id, props.front] as const, ([id, front]) => {
      if (front && (store.state.openGoalId !== id || store.state.openGoalVertical !== 'window')) {
        void store.openGoal(id, 'window', hostKey.value)
      }
    }, { immediate: true })
    /* A step opened inside the window becomes the window's goal. */
    watch(() => [store.state.openGoalId, store.state.openGoalVertical] as const, ([id, vertical]) => {
      if (!props.front || vertical !== 'window' || !id || id === props.id) return
      const win = windows.list.find((w) => w.kind === 'goal' && w.target === props.id)
      if (win) { win.target = id; win.key = `goal:${id}` }
    })
    /* The address left the goal (Back, a view's tag): the window goes with it. */
    watch(() => store.state.openGoalId, (id, was) => {
      if (!props.front || id !== null || was !== props.id) return
      const win = windows.list.find((w) => w.kind === 'goal' && w.target === props.id)
      if (win) closeWindow(win.key)
    })
    onBeforeUnmount(() => {
      if (store.state.openGoalVertical === 'window' && store.state.openGoalId === props.id) store.closeGoal()
    })

    const detail = computed(() => (store.state.goalDetail?.id === props.id ? store.state.goalDetail : null))
    const steps = computed<GoalCardData[]>(() => (detail.value?.children ?? []).map((child) => ({
      id: child.id,
      parentId: child.parent_id,
      title: child.title,
      done: child.done_at !== null,
      color: detail.value?.color ?? null,
      vertical: child.vertical,
      repeat: child.repeat,
    })))
    return { detail, steps }
  })
  const detail = s.detail.value
  const steps = s.steps.value
  return (
    <div {...fallthrough({ className: 'goal-window', 'data-role': 'goal-window', 'data-goal-id-window': id }, attrs)}>
      {detail ? (
        <GoalCard
          id={id}
          title={detail.title}
          done={!!detail.done_at}
          color={detail.color}
          vertical={detail.vertical}
          repeat={detail.repeat}
          children={steps}
          subgoalCount={steps.length}
          columnVertical="window"
        />
      ) : (
        <p className="goal-window__loading">Loading…</p>
      )}
    </div>
  )
})
