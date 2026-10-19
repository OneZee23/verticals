/* Above the field while you move a goal: "Weeks" names the view, and the goal let go
   over the field waits beside it, the same card, out of its group. Picked, one springs up with its shadow and the other
   steps aside; the goal is dragged from here to its place. A task carried onto the field in the Inbox waits here as well,
   and the Inbox's own drag takes it out again. The pictures dropped on the window or pasted wait in the same row, after
   them (FieldPictures). */
import { computed, ref } from '../reactivity'
import { pressToDrag } from './CardDnd'
import { store } from '../store'
import { findGoal } from '../lib/boardIndex'
import { inbox } from '../lib/inbox'
import { carry, pressCard } from '../lib/inboxCarry'
import { goalLight } from '../lib/look'
import { isPrivate } from '../lib/privacy'
import { spanGoal, spans, VIEW_NAMES } from '../lib/spans'
import { moving, tap } from '../lib/moving'
import { pictures } from '../lib/reportPictures'
import { FieldPictures } from './FieldPictures'
import { bindRef, cx, fallthrough, sx } from '../bind'
import { tracked } from '../tracked'
import { listen, useSetup } from '../setup'
import './movingStack.css'

export const MovingStack = tracked(function MovingStack(attrs: Record<string, unknown>) {
  const s = useSetup({}, () => {
    const goalEl = ref<HTMLElement | null>(null)
    const view = computed(() => (spans.vertical ? VIEW_NAMES[spans.vertical] : null))
    /* The waiting goal is a card of the board or of the spans; a task from the Inbox has its title and its value's colour,
       which is the colour the board shows it in. */
    const task = computed(() => (moving.goalId ? inbox.goals.find((g) => g.id === moving.goalId) ?? null : null))
    const goal = computed(() => {
      const id = moving.goalId
      if (!id) return null
      const card = findGoal(store.state.board, id) ?? spanGoal(id)
      if (card) return { id, title: card.title, color: card.color }
      return task.value ? { id, title: task.value.title, color: task.value.value_color } : null
    })
    const lit = computed(() => goalLight(goal.value?.color) ?? {})
    const inHand = computed(() => !!goal.value && (store.state.drag.id === goal.value.id || carry.item?.id === goal.value.id))
    const hidden = computed(() => !!goal.value && isPrivate(goal.value.id))
    /* The goal's own card stays out of its group while it waits here (S5.P3.017); in the Inbox `lib/inbox.ts` leaves it out
       of its lists, and a copy in the hand is the same goal's. */
    const hideSource = computed(() => (moving.goalId && store.state.activeView !== 'inbox'
      ? `[data-goal-id="${CSS.escape(moving.goalId)}"]:not([data-parked]) { display: none !important; }` : ''))

    /* On the board the card is dragged as the board's are, its press handed to dnd-kit's sensor (CardDnd.tsx). */
    function pressGoal(event: PointerEvent): boolean {
      const id = goal.value?.id
      const row = goalEl.value?.querySelector<HTMLElement>('.goal-card__row')
      if (!id || !row) return false
      store.pointerDownCard(id, event.clientX, event.clientY, row.getBoundingClientRect(), event.pointerType, event.altKey)
      return true
    }
    function onGoalDown(event: PointerEvent): void {
      if (event.button !== 0) return
      // In the Inbox no board is in view to land it on: its own drag takes the card out, and lets it go back to its place.
      if (store.state.activeView === 'inbox' && task.value) pressCard(event, task.value)
      else pressToDrag(event, pressGoal)
    }
    // A native listener on the card: the Inbox's drag reads the event's currentTarget.
    listen(goalEl, 'pointerdown', onGoalDown)
    return { goalEl, view, goal, lit, inHand, hidden, hideSource }
  })

  const view = s.view.value
  const goal = s.goal.value
  if (!(view || goal || pictures.list.length)) return null
  const hideSource = s.hideSource.value
  return (
    <div {...fallthrough({
      className: cx('moving-stack', { 'moving-stack--holding': !!store.state.drag.id && !goal }),
      'data-role': 'moving-stack',
    }, attrs)}>
      {hideSource ? <style>{hideSource}</style> : null}
      {view ? (
        <button
          type="button"
          className={cx('moving-stack__view', { 'is-picked': moving.picked === 'view', 'is-aside': moving.picked === 'goal' })}
          data-role="moving-view"
          onClick={() => tap('view')}
        >{view}</button>
      ) : null}
      {goal ? (
        <div
          ref={bindRef(s.goalEl)}
          className={cx('moving-stack__goal', {
            'is-picked': moving.picked === 'goal', 'is-aside': moving.picked === 'view', 'is-in-hand': s.inHand.value,
            'goal-card--private': s.hidden.value,
          })}
          style={sx(s.lit.value)}
          data-goal-id={goal.id}
          data-parked=""
          data-role="moving-goal"
          onClick={() => tap('goal')}
        >
          <div className="goal-card__row moving-stack__row">
            <span className="moving-stack__box" aria-hidden="true"></span>
            <span className="goal-card__title-text moving-stack__title">{goal.title}</span>
          </div>
        </div>
      ) : null}
      {pictures.list.length ? <FieldPictures /> : null}
    </div>
  )
})
