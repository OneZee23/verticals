<script setup lang="ts">
// The step (docs/design-handoff S2.P3; docs/design/morning-quality.md): while the agent works, one fixed phrase of what it is
// doing, written inside the field beside the turning line. The field widens into a pill for it (SearchBar.vue); the phrase
// used to stand in a bubble above the circle. A phrase stays at least 150 ms, so a fast turn never flickers.
import { onBeforeUnmount, ref, watch } from 'vue'
import { agentChat } from '../lib/agentChat'

const props = defineProps<{ shown: boolean }>()

const words = ref(agentChat.step)
let since = 0
let timer: ReturnType<typeof setTimeout> | null = null
watch(() => agentChat.step, (step) => {
  if (timer) clearTimeout(timer)
  const wait = Math.max(0, 150 - (performance.now() - since))
  timer = setTimeout(() => { words.value = step; since = performance.now() }, wait)
})
// It comes in with the phrase the agent is on, not the one it was on when it last stood here.
watch(() => props.shown, (on) => {
  if (!on) return
  if (timer) clearTimeout(timer)
  words.value = agentChat.step
  since = performance.now()
})
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
</script>

<template>
  <Transition name="agent-step">
    <span v-if="shown" class="circle-field__step" data-role="agent-step" role="status" aria-live="polite">
      <Transition name="agent-step-words" mode="out-in">
        <span :key="words" class="circle-field__step-words">{{ words }}</span>
      </Transition>
    </span>
  </Transition>
</template>

<style>
/* From 78 px, the circle's half and the room the turning line needs, to 52 px from the right end, where the stop square
   stands once the hand is on the field. A name too long for the room ends in an ellipsis. */
.circle-field__step {
  position: absolute;
  left: 78px;
  right: 52px;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  overflow: hidden;
  color: #fff;
  font: 400 15px/22px var(--font-body);
  white-space: nowrap;
  pointer-events: none;
}
.circle-field__step-words { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
/* The words come in once the black has begun to widen, and go before it narrows. */
.agent-step-enter-active { transition: opacity var(--vt-dur-fade) ease-out 140ms; }
.agent-step-leave-active { transition: opacity 75ms linear; }
.agent-step-enter-from, .agent-step-leave-to { opacity: 0; }
.agent-step-words-enter-active, .agent-step-words-leave-active { transition: opacity 75ms linear; }
.agent-step-words-enter-from, .agent-step-words-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) {
  .agent-step-enter-active { transition: opacity var(--vt-crossfade) linear; }
  .agent-step-words-enter-active, .agent-step-words-leave-active { transition: none; }
}
</style>
