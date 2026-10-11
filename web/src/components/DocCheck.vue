<script setup lang="ts">
/* Above the field, while a document is in front (docs/design/doc-comments-inline.md; the owner, round 2 of the agent flows:
   "a pill above the black field with amount of comments … the suggested button like Check again or something"): a pill
   with the number of the document's open comments, which opens them all as a list, and beside it Check again, which hands
   the comments and the edits to the agent (lib/checkAgain.ts) and took the place of the "Ready?" the circle used to ask.
   Check again is the one black pill, as the field is; the count is the light one, in the yellow its words are marked with.

   Its own component, apart from the field (SearchBar.vue): it stands where the conversation keeps clear of the field, 12 px
   over its top, and rises with it as the field grows or its tags come in (`--vt-field-height`, `--vt-tags-lift`); it
   is out of the way while the conversation is open, a message is typed or a goal is moved. Nothing stands here with no
   comment to count and nothing to hand over. */
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import DocCommentList from './DocCommentList.vue'
import { store } from '../store'
import { agentChat } from '../lib/agentChat'
import { circle } from '../lib/circle'
import { commandFilter } from '../lib/commandFilter'
import { checkAgain, checkShown } from '../lib/checkAgain'
import { followFrontDoc, frontDocId, openThreads } from '../lib/docComments'

const count = computed(() => openThreads.value.length)
const label = computed(() => `${count.value} ${count.value === 1 ? 'comment' : 'comments'}`)
const out = computed(() => agentChat.open || !!commandFilter.text || circle.moving)
const shown = computed(() => !!frontDocId.value && !out.value && (count.value > 0 || checkShown.value))
const listOpen = computed(() => store.state.comments.listOpen)

const stop = followFrontDoc()
onBeforeUnmount(stop)
// With nothing left to count (the last one resolved, the document gone from the front) the list has nothing to stand over.
watch(shown, (now) => { if (!now) store.setCommentList(false) })

function toggle(): void {
  store.setCommentList(!listOpen.value)
}

/* A pill that goes keeps its place while it fades, out of the row, so the one beside it glides to its new place at once. */
function holdPlace(el: Element): void {
  const pill = el as HTMLElement
  const home = pill.offsetParent?.getBoundingClientRect()
  const box = pill.getBoundingClientRect()
  if (!home) return
  pill.style.left = `${box.left - home.left}px`
  pill.style.top = `${box.top - home.top}px`
}

/* The list goes with Esc, or a press anywhere but on it and its pill. Esc is taken before anything under it (a window,
   the field), as a comment's card takes it. */
function onKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !listOpen.value || event.isComposing) return
  event.preventDefault()
  event.stopPropagation()
  store.setCommentList(false)
}
function onPointerDown(event: PointerEvent): void {
  if (!listOpen.value) return
  const target = event.target as Element | null
  if (target?.closest('[data-role="doc-comments-list"], [data-role="doc-comments-count"]')) return
  store.setCommentList(false)
}
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  document.addEventListener('pointerdown', onPointerDown, true)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey, true)
  document.removeEventListener('pointerdown', onPointerDown, true)
})
</script>

<template>
  <div v-if="shown" class="doc-check" data-role="doc-check">
    <div class="doc-check__row">
      <TransitionGroup name="doc-check-pill" @before-leave="holdPlace">
        <button
          v-if="count > 0"
          key="count"
          type="button"
          class="doc-check__pill doc-check__count"
          data-role="doc-comments-count"
          :aria-expanded="listOpen"
          @click="toggle"
        ><i class="doc-check__dot" aria-hidden="true"></i>{{ label }}</button>
        <button
          v-if="checkShown"
          key="check"
          type="button"
          class="doc-check__pill doc-check__again"
          data-role="doc-check-again"
          @click="checkAgain"
        >Check again</button>
      </TransitionGroup>
      <DocCommentList v-if="listOpen && count > 0" />
    </div>
  </div>
</template>

<style>
/* The pair, centred over the circle (the sketch's), 12 px over the circle's top as the conversation stands, and as high
   again as the field has grown and the tags have come in. The row lets the pointer through; its pills do not. */
.doc-check {
  position: fixed;
  left: 50%;
  bottom: calc(24px + 84px + 12px);
  z-index: 300;
  width: max-content;
  max-width: calc(100vw - 24px);
  transform: translate(-50%, calc(-1 * (var(--vt-field-height, 84px) - 84px + var(--vt-tags-lift, 0px))));
  transition: transform var(--vt-dur-close) var(--vt-ease-large);
  font-family: var(--font-body);
  pointer-events: none;
}
.doc-check__row { position: relative; display: flex; align-items: flex-end; justify-content: center; gap: 8px; }
/* The pill is the pill above the field the moving view already is: 36 px, 18 px corners, 15/20 at 500. */
.doc-check__pill {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 8px;
  box-sizing: border-box;
  height: 36px;
  padding: 0 16px;
  border: 0;
  border-radius: 18px;
  font: 500 15px/20px var(--font-body);
  white-space: nowrap;
  cursor: pointer;
  pointer-events: auto;
  transition: transform var(--vt-dur-step) var(--vt-ease-large), background var(--vt-dur-fade) ease-out;
}
.doc-check__pill:active { transform: scale(.97); }
.doc-check__pill:focus-visible { outline: 2px solid #000; outline-offset: 2px; }
/* The count is light, so Check again is the one thing that is heavy: white, with its own edge on the white foot (a hairline and
   one soft pool in the shadows' own ink). */
.doc-check__count {
  background: #fff;
  color: #000;
  box-shadow: 0 0 0 .5px rgba(var(--vt-ink), .14), 0 8px 20px -10px rgba(var(--vt-ink), .35);
}
.doc-check__dot { flex: none; width: 10px; height: 10px; border-radius: 5px; background: var(--color-goal-yellow, #ecce32); }
.doc-check__again { background: #000; color: #fff; }
@media (hover: hover) and (pointer: fine) {
  .doc-check__count:hover, .doc-check__count[aria-expanded='true'] { background: #f5f5f7; }
  .doc-check__again:hover { background: #2b2b2b; }
}
/* A pill comes in from 6 px under its place, as the tags do, and the other makes room by gliding. */
.doc-check-pill-enter-active { transition: opacity var(--vt-dur-open) var(--vt-ease-large), transform var(--vt-dur-open) var(--vt-ease-large); }
.doc-check-pill-leave-active { position: absolute; transition: opacity var(--vt-dur-fade) ease-out; }
.doc-check-pill-move { transition: transform var(--vt-dur-open) var(--vt-ease-large); }
.doc-check-pill-enter-from { opacity: 0; transform: translateY(6px); }
.doc-check-pill-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) {
  .doc-check { transition: none; }
  .doc-check-pill-enter-active, .doc-check-pill-leave-active { transition: opacity var(--vt-crossfade) linear; }
  .doc-check-pill-move { transition: none; }
  .doc-check-pill-enter-from { transform: none; }
  .doc-check__pill, .doc-check__pill:active { transition: background var(--vt-crossfade) linear; transform: none; }
}
</style>
