<script setup lang="ts">
// The tags above the field (docs/design-handoff S2.P2): the agent's (its slot), the docs and the Inbox. A view's tag
// pressed again goes back to the board. While the circle rests they stand centred over it, and under the pointer they
// grow from 28 to 38 px (docs/design/field-hover.md).
import AppIcon from './AppIcon.vue'
import { store } from '../store'

defineProps<{ shown: boolean }>()

const VIEWS = [
  { key: 'docs', name: 'Documents', label: 'Docs', icon: 'file' },
  { key: 'inbox', name: 'Inbox', label: 'Inbox', icon: 'inbox' },
] as const

function open(view: 'docs' | 'inbox'): void {
  store.closeGoal()
  store.setView(store.state.activeView === view ? 'verticals' : view)
}
</script>

<template>
  <div class="circle-tags" :class="{ 'is-shown': shown }" data-role="circle-tags">
    <slot name="agent" />
    <button
      v-for="view in VIEWS"
      :key="view.key"
      type="button"
      class="circle-tag"
      :class="{ 'is-current': store.state.activeView === view.key }"
      :data-tag="view.key"
      :aria-label="view.name"
      :aria-pressed="store.state.activeView === view.key"
      @click="open(view.key)"
    >
      <AppIcon :name="view.icon" :size="16" :stroke="2.2" />
      <span class="circle-tag__name">{{ view.label }}</span>
    </button>
  </div>
</template>

<style>
.circle-tags {
  /* The buttons' size. Under the pointer the field raises it (below); the agent's menu stands above whatever it is. */
  --vt-tag-size: 28px;
  position: relative;
  left: 0;
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding-left: 16px;
  opacity: 0;
  transform: translateY(6px);
  pointer-events: none;
  transition: opacity var(--vt-dur-close) ease-out, transform var(--vt-dur-close) var(--vt-ease-large),
    left var(--vt-dur-close) var(--vt-ease-large), translate var(--vt-dur-close) var(--vt-ease-large),
    padding-left var(--vt-dur-close) var(--vt-ease-large);
}
.circle-tags.is-shown, .circle-tags:focus-within {
  opacity: 1;
  transform: none;
  pointer-events: auto;
  transition-duration: var(--vt-dur-open);
}
/* While the circle rests the buttons stand centred over it; open, they sit at the field's left end and slide there as it
   widens (docs/design/field-hover.md). */
.circle-field[data-state='rest'] .circle-tags { left: 50%; translate: -50% 0; padding-left: 0; }
.circle-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--vt-tag-size);
  min-width: var(--vt-tag-size);
  box-sizing: border-box;
  padding: 0 6px;
  border: 0;
  border-radius: var(--vt-radius-tag);
  background: #000;
  color: #fff;
  font: 500 12px/16px var(--font-body);
  cursor: pointer;
  /* The way back from the pointer's size: 200 ms on the app's ease-out token. */
  transition: height var(--dur-base) var(--ease-out), min-width var(--dur-base) var(--ease-out),
    border-radius var(--dur-base) var(--ease-out);
}
/* Under the pointer: 38 px, still round, and in at once: no fade, no rise, no growing (settling back takes the timings
   above). Where the row stands still glides, as the field opens and closes under it. */
@media (hover: hover) and (pointer: fine) {
  .circle-field[data-pointed] .circle-tags {
    --vt-tag-size: var(--vt-tag-hover);
    transition-duration: 0s, 0s, var(--vt-dur-open), var(--vt-dur-open), var(--vt-dur-open);
  }
  .circle-field[data-pointed] .circle-tag { border-radius: calc(var(--vt-tag-hover) / 2); transition-duration: 0s; }
}
.circle-tag:hover, .circle-tag:focus-visible, .circle-tag.is-current { background: #2b2b2b; }
.circle-tag:focus-visible { outline: 2px solid #000; outline-offset: 2px; }
.circle-tag__name {
  max-width: 0;
  overflow: hidden;
  white-space: nowrap;
  opacity: 0;
  transition: max-width var(--vt-dur-open) var(--vt-ease-large), opacity var(--vt-dur-fade) ease-out,
    margin var(--vt-dur-open) var(--vt-ease-large);
}
.circle-tag:hover .circle-tag__name, .circle-tag:focus-visible .circle-tag__name {
  max-width: 80px;
  margin: 0 2px 0 4px;
  opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
  .circle-tags, .circle-tags.is-shown { transform: none; transition: none; }
  .circle-tag { transition: none; }
  .circle-tag__name { transition: opacity var(--vt-crossfade) linear; }
}
</style>
