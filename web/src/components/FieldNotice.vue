<script setup lang="ts">
// The notice (docs/design/board-undo.md): a change that leaves your view is said where the field stands. One black pill,
// 64 px tall, one line at 15/22 in white saying what happened to which goal (the goal's title is cut with “…”, the words
// around it never are) and Undo as a white pill at its right end. It stays six seconds and the field comes back; Esc, or
// a click anywhere else, ends it sooner, and the pointer on it holds the time (`lib/fieldNotice.ts`). It lives in its own
// component so the field (`SearchBar.vue`) is not touched; the field is hidden while the notice is up, by one attribute on
// the page, so the two never stand in the same place.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { editsText } from '../lib/boardHistory'
import { dismiss, hold, notice, release } from '../lib/fieldNotice'
import { store } from '../store'

const pill = ref<HTMLElement | null>(null)

watch(() => notice.open, (open) => document.documentElement.toggleAttribute('data-field-notice', open), { immediate: true })

function act(): void {
  const action = notice.action
  dismiss()
  action?.run()
}

/* Esc ends it, ahead of the field (which would clear an answer behind it) and of the windows (the smaller thing goes
   first). Inside a text field, and while a goal is in the hand, Esc is theirs. */
function onKeyDown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !notice.open || event.defaultPrevented) return
  if (editsText(event.target) || store.state.drag.id || store.state.drag.pending) return
  event.preventDefault()
  event.stopImmediatePropagation()
  dismiss()
}
/* A press anywhere but on the notice ends it; the press itself goes on to what it was aimed at. */
function onPointerDown(event: PointerEvent): void {
  if (notice.open && !(event.target instanceof Node && pill.value?.contains(event.target))) dismiss()
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown, true)
  window.addEventListener('pointerdown', onPointerDown, true)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown, true)
  window.removeEventListener('pointerdown', onPointerDown, true)
  document.documentElement.removeAttribute('data-field-notice')
})
</script>

<template>
  <Transition name="field-notice">
    <div
      v-if="notice.open"
      ref="pill"
      class="field-notice"
      data-role="field-notice"
      role="status"
      aria-live="polite"
      @pointerenter="hold"
      @pointerleave="release"
    >
      <p class="field-notice__line" data-role="field-notice-line">
        <template v-for="(part, at) in notice.segments" :key="at">
          <span v-if="'text' in part" class="field-notice__text">{{ part.text }}</span>
          <span v-else class="field-notice__quote"><i>“</i><span class="field-notice__title">{{ part.quote }}</span><i>”</i></span>
        </template>
      </p>
      <button v-if="notice.action" type="button" class="field-notice__action" data-role="field-notice-action" @click="act">
        {{ notice.action.label }}
      </button>
    </div>
  </Transition>
</template>

<style>
.field-notice {
  position: fixed;
  z-index: 300;
  /* Centred with auto margins, not a transform, so the entrance can scale the pill about its centre and nothing drifts. */
  left: 0;
  right: 0;
  /* The circle's centre: the notice stands where the circle does and the same height from the bottom (24 + (84 - 64) / 2). */
  bottom: 34px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 20px;
  width: fit-content;
  max-width: min(560px, calc(100vw - 32px));
  height: 64px;
  margin: 0 auto;
  padding: 0 12px 0 28px;
  border-radius: var(--vt-radius-field);
  background: #000;
  color: #fff;
  font: 400 15px/22px var(--font-body);
}
.field-notice__line { display: flex; flex: 1 1 auto; min-width: 0; margin: 0; white-space: pre; }
.field-notice__text { flex: none; }
.field-notice__quote { display: flex; flex: 0 1 auto; min-width: 0; }
.field-notice__quote > i { flex: none; font-style: normal; }
.field-notice__title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.field-notice__action {
  flex: none;
  height: 40px;
  padding: 0 20px;
  border: 0;
  border-radius: 20px;
  background: #fff;
  color: #000;
  font: 500 15px/22px var(--font-body);
  cursor: pointer;
}
/* A press gives a little and comes back (kk-motion); the hover look only where there is a pointer to hover. */
.field-notice__action { transition: scale 100ms var(--vt-ease-small), background-color var(--vt-dur-fade) ease-out; }
.field-notice__action:active { scale: .97; }
@media (hover: hover) and (pointer: fine) { .field-notice__action:hover { background: #ececf0; } }
.field-notice__action:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }

/* The field is hidden while the notice stands where it stands: it fades out as the pill comes in and fades back as the pill
   goes. `visibility` also takes its children out of the pointer's reach (they set `pointer-events` themselves). */
.circle-field { transition: opacity var(--vt-dur-fade) ease-out; }
html[data-field-notice] .circle-field {
  opacity: 0;
  visibility: hidden;
  transition: opacity var(--vt-dur-fade) ease-out, visibility 0s linear var(--vt-dur-fade);
}

/* In: the pill comes up from nearly full size with the fade, quicker than a window (a notice is a small thing). Out: a
   fifth quicker, the same way (kk-motion). Under reduced motion, a crossfade and no scale. */
.field-notice-enter-active { transition: opacity var(--vt-dur-rise) var(--vt-ease-small), scale var(--vt-dur-rise) var(--vt-ease-small); }
.field-notice-leave-active { transition: opacity var(--vt-dur-fade) var(--vt-ease-small), scale var(--vt-dur-fade) var(--vt-ease-small); }
.field-notice-enter-from, .field-notice-leave-to { opacity: 0; scale: 0.95; }
@media (prefers-reduced-motion: reduce) {
  .field-notice-enter-active, .field-notice-leave-active { transition: opacity var(--vt-crossfade) linear; }
  .field-notice-enter-from, .field-notice-leave-to { scale: 1; }
}
</style>
