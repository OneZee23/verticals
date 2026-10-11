<script setup lang="ts">
// A goal as one thing in a message (docs/design/agent-chips.md): the document chip's anatomy and type, with the goal's own
// square, as the board paints it, where the page is. On the right its title, two lines at most, and one grey line saying
// where it is and when ("Today · made just now", "Week · changed 2 min ago"). It stands on a message's black, as DocChip
// does there (`dark`), the field's answer and the agent's balloon alike. A click opens the goal as its window, as the
// Inbox opens one (S3.P2). The square is only drawn: it is the board's own box without its input, so a press on it is a
// press on the chip.
import { computed } from 'vue'
import '../kit-ext/goal-affordance/goal-affordance.css'
import { chipLine, useGoalChip, useNow } from '../lib/goalChip'
import { goalSquare } from '../lib/look'
import { openWindow } from '../lib/windows'

const props = defineProps<{ id: string; label?: string }>()

const { goal } = useGoalChip(() => props.id)
const now = useNow()
const gone = computed(() => goal.value === 'gone')
const data = computed(() => (goal.value && goal.value !== 'gone' ? goal.value : null))
/* Until the goal is read the chip has the words of the link that brought it. */
const name = computed(() => data.value?.title || props.label || 'Goal')
const line = computed(() => (gone.value ? 'Not on the board' : data.value ? chipLine(data.value, now.value) : ''))
const square = computed(() => {
  const { box, check } = goalSquare(data.value?.color)
  return { '--goal-affordance-background': box, '--goal-affordance-check-color': check }
})

function open(event: Event): void {
  if (gone.value) return
  openWindow({ kind: 'goal', target: props.id, title: name.value }, event.currentTarget as Element)
}
</script>

<template>
  <button type="button" class="goal-chip" data-role="goal-chip" :data-goal-id="id" :aria-disabled="gone || undefined" @click.stop="open">
    <span class="goal-chip__mark checkbox checkbox--size-s goal-affordance" aria-hidden="true">
      <span class="checkbox__box goal-affordance__square" :class="{ 'is-done': data?.done }" :style="square" data-role="goal-chip-square"></span>
    </span>
    <span class="goal-chip__text">
      <span class="goal-chip__name">{{ name }}</span>
      <span class="goal-chip__when" data-role="goal-chip-when">{{ line }}</span>
    </span>
  </button>
</template>

<style>
/* DocChip.vue's numbers in a message (`doc-chip--dark`), so the two kinds of chip are one form: the row, its gap, its two
   lines of type and its greys, on the balloon's black with no ground of its own. */
.goal-chip { box-sizing: border-box; display: flex; align-items: flex-start; gap: 14px; min-width: 0; margin: 0; padding: 0;
  border: 0; border-radius: 12px; background: transparent; color: #fff; text-align: left; font: inherit; cursor: pointer; }
/* The board's square, 16 px with the corners the Inbox's tiles give it, centred on the title's first line (22 px). */
.goal-chip__mark { flex: none; display: block; width: 16px; height: 16px; margin-top: 3px; }
.goal-chip__mark > .checkbox__box { width: 16px; height: 16px; min-width: 16px; min-height: 16px; border-radius: 4px; }
.goal-chip__mark > .goal-affordance__square.is-done { color: var(--goal-affordance-check-color); }
.goal-chip__mark > .goal-affordance__square.is-done::after { opacity: 1; }
.goal-chip__text { display: block; flex: 1; min-width: 0; }
.goal-chip__name { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  font: 500 15px/22px var(--font-body, Commissioner, system-ui, sans-serif); overflow-wrap: anywhere; }
.goal-chip__when { display: block; min-height: 22px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
  font: 400 13px/22px var(--font-body, Commissioner, system-ui, sans-serif); color: rgb(255 255 255 / 50%); }
.goal-chip:focus-visible { outline: 2px solid #007aff; outline-offset: 2px; }
.goal-chip[aria-disabled='true'] { cursor: default; }
</style>
