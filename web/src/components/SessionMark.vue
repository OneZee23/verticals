<script setup lang="ts">
/* The end of a task's card says what its sessions are doing (docs/design/task-sessions.md). While one works on the task, the
   field's own turning line, in a small black disc as the circle is; when one went on in Claude or Codex without a word to
   Verticals, that agent's own mark. Nothing in it comes from a model: the gateway sees a file's size and time on disk. The dots
   take the place when the card is pointed at, as they do from the date or the repeat mark. */
import { computed } from 'vue'
import { agentChat, agentOf, assetUrl, currentThread } from '../lib/agentChat'
import { agentName, ago, taskSessions } from '../lib/taskSessions'

const props = defineProps<{ goalId: string }>()

const known = computed(() => taskSessions.goals[props.goalId])
/* Verticals' own agent answering in a conversation about this task is known at once, before the gateway's next answer. */
const working = computed(() => !!known.value?.working || (agentChat.running && currentThread.value?.goal?.id === props.goalId))
const outside = computed(() => known.value?.outside ?? null)
const label = computed(() => {
  if (working.value) {
    const who = known.value?.sessions.find((session) => session.working)?.provider ?? currentThread.value?.provider
    return `${agentName(who ?? 'claude')} is working on this`
  }
  return outside.value ? `Continued in ${agentName(outside.value.provider)} · ${ago(outside.value.at, taskSessions.now)}` : ''
})
</script>

<template>
  <span
    v-if="working || outside"
    class="session-mark"
    data-role="session-mark"
    :data-state="working ? 'working' : 'outside'"
    :data-provider="working ? undefined : outside?.provider"
    role="img"
    :aria-label="label"
    :title="label"
  >
    <span v-if="working" class="session-mark__disc">
      <span class="circle-field__pivot is-turning"><span class="circle-field__line"></span></span>
    </span>
    <img v-else class="session-mark__agent" :src="assetUrl(agentOf(outside!.provider).image)" alt="">
  </span>
</template>

<style>
/* Where the dots are (GoalCardTools.vue), and in their place until the card is pointed at, its menu is open or it is the open
   goal, whose dots stay. The title leaves it room, so no word runs under it. */
.goal-card > .goal-card__row > .session-mark {
  position: absolute;
  top: 0;
  right: -3px;
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  pointer-events: none;
  opacity: 1;
  transition: opacity var(--vt-dur-fade) ease-out;
}
.goal-card.goal-card > .goal-card__row:has(> .session-mark) > .goal-card__text { padding-right: 30px; }
.goal-card:is(:hover, .goal-card--menu-open, .goal-card--landed-hover) > .goal-card__row > .session-mark,
.goal-card > .goal-card__row:has(.goal-actions__trigger:focus-visible) > .session-mark { opacity: 0; transition: none; }
/* The open card's dots stay, so the mark stands beside them. */
.goal-card.goal-card--detail-open > .goal-card__row > .session-mark { right: 21px; opacity: 1; }
/* The circle, small: the same black disc and white line, the line turning half a turn every 1.6 s as the field's does (circleField.css). */
.session-mark__disc { position: relative; display: block; width: 20px; height: 20px; border-radius: 50%; background: #000; }
.session-mark .circle-field__line { width: 2px; height: 9px; margin: -4.5px 0 0 -1px; border-radius: 1px; }
.session-mark__agent { display: block; width: 16px; height: 16px; }
@media (prefers-reduced-motion: reduce) {
  .session-mark .circle-field__pivot.is-turning { animation: none; }
}
</style>
