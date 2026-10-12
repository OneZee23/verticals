<script setup lang="ts">
// Above the field while you move a goal (docs/design-handoff S5.P3, S5.P4): "Weeks" names the view, and the goal let go
// over the field waits beside it, the same card, out of its group. Picked, one springs up with its shadow and the other
// steps aside; the goal is dragged from here to its place. A task carried onto the field in the Inbox waits here as well,
// the same card with no view's name beside it, and the Inbox's own drag takes it out again (docs/design/inbox-carry-stack.md).
// The pictures dropped on the window or pasted wait in the same row, after them (FieldPictures.vue; docs/design/bug-reports.md).
import { computed } from 'vue'
import { store } from '../store'
import { findGoal } from '../lib/boardIndex'
import { inbox } from '../lib/inbox'
import { carry, pressCard } from '../lib/inboxCarry'
import { goalLight } from '../lib/look'
import { isPrivate } from '../lib/privacy'
import { spanGoal, spans, VIEW_NAMES } from '../lib/spans'
import { moving, tap } from '../lib/moving'
import { pictures } from '../lib/reportPictures'
import FieldPictures from './FieldPictures.vue'

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
/* The goal's own card stays out of its group while it waits here (S5.P3.017); in the Inbox `lib/inbox.ts` leaves it out of
   its lists, and a copy in the hand is the same goal's. */
const hideSource = computed(() => (moving.goalId && store.state.activeView !== 'inbox'
  ? `[data-goal-id="${CSS.escape(moving.goalId)}"]:not([data-parked]) { display: none !important; }` : ''))

function onGoalDown(event: PointerEvent): void {
  const id = goal.value?.id
  if (!id || event.button !== 0) return
  // In the Inbox no board is in view to land it on: its own drag takes the card out, and lets it go back to its place.
  if (store.state.activeView === 'inbox' && task.value) {
    pressCard(event, task.value)
    return
  }
  const row = (event.currentTarget as HTMLElement).querySelector<HTMLElement>('.goal-card__row')
  if (!row) return
  store.pointerDownCard(id, event.clientX, event.clientY, row.getBoundingClientRect(), event.pointerType, event.altKey)
}
</script>

<template>
  <div v-if="view || goal || pictures.list.length" class="moving-stack" :class="{ 'moving-stack--holding': !!store.state.drag.id && !goal }" data-role="moving-stack">
    <component :is="'style'" v-if="hideSource">{{ hideSource }}</component>
    <button
      v-if="view"
      type="button"
      class="moving-stack__view"
      :class="{ 'is-picked': moving.picked === 'view', 'is-aside': moving.picked === 'goal' }"
      data-role="moving-view"
      @click="tap('view')"
    >{{ view }}</button>
    <div
      v-if="goal"
      class="moving-stack__goal"
      :class="{ 'is-picked': moving.picked === 'goal', 'is-aside': moving.picked === 'view', 'is-in-hand': inHand, 'goal-card--private': hidden }"
      :style="lit"
      :data-goal-id="goal.id"
      data-parked
      data-role="moving-goal"
      @pointerdown="onGoalDown"
      @click="tap('goal')"
    >
      <div class="goal-card__row moving-stack__row">
        <span class="moving-stack__box" aria-hidden="true"></span>
        <span class="goal-card__title-text moving-stack__title">{{ goal.title }}</span>
      </div>
    </div>
    <FieldPictures v-if="pictures.list.length" />
  </div>
</template>

<style>
/* "Weeks": 36 px, 18 px corners, black, words 15/20 at 500; the goal is its card at 12 px, lit softly green from under;
   they stand 8 px apart on one baseline, 4 px in from the field's left (S5.P3.006, .043). Its width is the room it has once
   the field has widened (the field's width is its target, set at once), not the room left in a field that has not yet:
   the card has the lines it will have in every frame of the widening. At rest the room is the one it always had: the
   field's width less 8 px, or less 4 px and the buttons when they stand at its left end. */
.moving-stack {
  position: absolute;
  left: calc(50% - var(--moving-field-width, 300px) / 2 + 4px + var(--moving-tags-shift, 0px));
  bottom: 8px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
  width: max-content;
  max-width: calc(var(--moving-field-width, 300px) - max(8px, 4px + var(--moving-tags-shift, 0px)));
  transition: left 200ms var(--vt-ease-large);
  pointer-events: auto;
}
.moving-stack__view {
  flex: none;
  height: 36px;
  padding: 0 16px;
  border: 0;
  border-radius: 18px;
  background: #000;
  color: #fff;
  font: 500 15px/20px var(--font-body);
  cursor: pointer;
}
.moving-stack__goal {
  min-width: 0;
  max-width: 220px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgb(var(--vt-pale, 240, 240, 240));
  box-shadow: 0 6px 24px -8px rgba(var(--vt-tint, 200, 200, 200), .9);
  cursor: grab;
  touch-action: none;
}
.moving-stack__row { display: flex; align-items: flex-start; gap: 10px; }
.moving-stack__box { flex: none; width: 14px; height: 14px; margin-top: 2px; border-radius: 3px; background: rgb(var(--vt-tint, 210, 210, 210)); }
.moving-stack__title {
  display: -webkit-box;
  overflow: hidden;
  color: #000;
  font: 500 12px/18px var(--font-body);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.moving-stack__goal.is-in-hand { visibility: hidden; }
/* Picked: 14% bigger and 10 px higher on a spring, a strong shadow in its colour; the other steps aside (S5.P4.007). */
.moving-stack__view,
.moving-stack__goal { transition: transform var(--vt-lift-picked-ms) var(--vt-ease-large), box-shadow var(--vt-lift-picked-ms) ease; }
.moving-stack__view.is-aside,
.moving-stack__goal.is-aside { transition-timing-function: var(--vt-ease-sway); }
.moving-stack__view.is-picked { transform: translateY(var(--vt-lift-picked-rise)) scale(var(--vt-lift-picked-scale)); box-shadow: 0 16px 26px -6px rgb(0 0 0 / 45%), 0 46px 100px -12px rgb(0 0 0 / 35%); }
.moving-stack__goal.is-picked {
  transform: translateY(var(--vt-lift-picked-rise)) scale(var(--vt-lift-picked-scale));
  background: rgb(var(--vt-tint, 220, 220, 220));
  box-shadow: 0 16px 26px -6px rgba(var(--vt-tint, 200, 200, 200), .62), 0 46px 100px -12px rgba(var(--vt-tint, 200, 200, 200), .62);
}
.moving-stack__view.is-aside { transform: translateX(-12px); }
.moving-stack__goal.is-aside { transform: translateX(14px); }
@media (prefers-reduced-motion: reduce) {
  .moving-stack__view, .moving-stack__goal, .moving-stack { transition: none; }
}
</style>
