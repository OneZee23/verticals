<script setup lang="ts">
// The notice (docs/design/board-undo.md): a change that leaves your view is said where the field stands. One black pill,
// 64 px tall, one line at 15/22 in white saying what happened to which goal (the goal's title is cut with “…”, the words
// around it never are) and Undo as a white pill at its right end. It stays six seconds and the field comes back; Esc, or
// a click anywhere else, ends it sooner, and the pointer on it holds the time (`lib/fieldNotice.ts`). It lives in its own
// component so the field (`SearchBar.vue`) is not touched; the field is hidden while the notice is up, by one attribute on
// the page, so the two never stand in the same place.
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { editsText } from '../lib/boardHistory'
import { dismiss, hold, notice, release, type NoticeChoice, type Segment } from '../lib/fieldNotice'
import { cutTitle, glyphs } from '../lib/titleCut'
import { store } from '../store'

const pill = ref<HTMLElement | null>(null)
const line = ref<HTMLElement | null>(null)
/** The pills of a question (⌘Z asking whose change it meant), when there is one. */
const choiceEls = ref<HTMLElement[]>([])
/** The titles as the notice shows them, by the place of their segment (`L:2` in the line, `1:2` in the second pill): whole, or cut
 *  to fit. */
const cuts = ref<Record<string, string>>({})
let fitting = 0

const overflows = (el: HTMLElement): boolean => el.scrollWidth > el.clientWidth

/* A title that does not fit is cut in the text, so the “…” stands right after its last letter, with no space before it and
   the quote right after it (the browser's ellipsis cuts at a pixel and leaves gaps). The pill is as wide as its words up to
   its largest, so a line that overflows is one that is cut short: the longest start of the title that does not overflow is
   found by halving. Everything runs before the next frame, so the whole title is never drawn. */
async function fit(): Promise<void> {
  const mine = (fitting += 1)
  cuts.value = {}
  await nextTick()
  const spills = (): boolean => !!line.value && (overflows(line.value) || choiceEls.value.some(overflows))
  if (mine !== fitting || !line.value || !spills()) return
  const quotes = (segments: Segment[], where: string) =>
    segments.flatMap((part, at) => ('quote' in part ? [{ key: `${where}:${at}`, text: part.quote, length: glyphs(part.quote).length }] : []))
  const titles = [...quotes(notice.segments, 'L'), ...notice.choices.flatMap((choice, at) => quotes(choice.label, String(at)))]
  const longest = Math.max(0, ...titles.map((title) => title.length))
  // Two titles (“into”, “out of”) give up the same share of their length.
  const cutTo = (keep: number): Record<string, string> =>
    Object.fromEntries(titles.map((title) => [title.key, cutTitle(title.text, Math.round((title.length * keep) / longest))]))
  let fits = 0
  let over = longest
  while (fits < over - 1) {
    const middle = Math.ceil((fits + over) / 2)
    cuts.value = cutTo(middle)
    await nextTick()
    if (mine !== fitting || !line.value) return
    if (spills()) over = middle
    else fits = middle
  }
  cuts.value = cutTo(fits)
}

// `sync`: the field is shown again in the same task as the key that asks for it, or it could not take the focus (see below).
watch(() => notice.open, (open) => document.documentElement.toggleAttribute('data-field-notice', open), { immediate: true, flush: 'sync' })
watch(() => notice.seq, () => void fit(), { flush: 'post' })
const refit = (): void => { if (notice.open) void fit() }

function act(): void {
  const action = notice.action
  dismiss()
  action?.run()
}

/** A pick of the question: the question goes, and what was picked is taken back. */
function pick(choice: NoticeChoice): void {
  dismiss()
  choice.run()
}

/* A key that asks for the field (a letter, which is its first one, or ⌘K, `SearchBar.vue`) puts the field back first: it is
   hidden while the notice stands, and a hidden field cannot take the focus. */
const asksForField = (event: KeyboardEvent): boolean => {
  const command = event.metaKey || event.ctrlKey
  if (event.altKey) return false
  return command ? event.key.toLowerCase() === 'k' : event.key.length === 1 && event.key !== ' '
}

/* Esc ends it, ahead of the field (which would clear an answer behind it) and of the windows (the smaller thing goes
   first). Inside a text field, and while a goal is in the hand, Esc is theirs. */
function onKeyDown(event: KeyboardEvent): void {
  if (!notice.open || event.defaultPrevented || editsText(event.target)) return
  if (asksForField(event) && !store.state.drag.id && !store.state.drag.pending) dismiss()
  if (event.key !== 'Escape' || store.state.drag.id || store.state.drag.pending) return
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
  window.addEventListener('resize', refit)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown, true)
  window.removeEventListener('pointerdown', onPointerDown, true)
  window.removeEventListener('resize', refit)
  document.documentElement.removeAttribute('data-field-notice')
})
</script>

<template>
  <Transition name="field-notice">
    <div
      v-if="notice.open"
      ref="pill"
      class="field-notice"
      :class="{ 'field-notice--bare': !notice.action && !notice.choices.length, 'field-notice--question': notice.choices.length > 0 }"
      data-role="field-notice"
      role="status"
      aria-live="polite"
      @pointerenter="hold"
      @pointerleave="release"
    >
      <p ref="line" class="field-notice__line" data-role="field-notice-line">
        <template v-for="(part, at) in notice.segments" :key="at">
          <span v-if="'text' in part" class="field-notice__text">{{ part.text }}</span>
          <span v-else class="field-notice__quote"><i>“</i><span class="field-notice__title">{{ cuts[`L:${at}`] ?? part.quote }}</span><i>”</i></span>
        </template>
      </p>
      <button
        v-for="(choice, at) in notice.choices"
        :key="at"
        ref="choiceEls"
        type="button"
        class="field-notice__action field-notice__choice"
        data-role="field-notice-choice"
        @click="pick(choice)"
      >
        <template v-for="(part, place) in choice.label" :key="place">
          <span v-if="'text' in part" class="field-notice__text">{{ part.text }}</span>
          <span v-else class="field-notice__quote"><i>“</i><span class="field-notice__title">{{ cuts[`${at}:${place}`] ?? part.quote }}</span><i>”</i></span>
        </template>
      </button>
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
.field-notice--bare { padding-right: 28px; }
/* The question ⌘Z asks (docs/design/agent-answer-undo.md): "Take back" and the candidates as pills, which give up their titles,
   cut with “…”, before the words do. A pill is the notice's own button; it may shrink, which the button's `flex: none` below would
   not allow, so this stands on two classes. */
.field-notice--question { gap: 12px; max-width: min(640px, calc(100vw - 32px)); }
.field-notice--question .field-notice__line { flex: none; }
.field-notice__action.field-notice__choice { display: flex; align-items: center; flex: 0 1 auto; min-width: 0; overflow: hidden; white-space: pre; }
/* Nothing in the line shrinks: a title too long for it is cut in the text by the component (so the “…” stands right after
   its last letter), and `overflow` only keeps a line that still does not fit, in a very narrow window, off the button. */
.field-notice__line { display: flex; flex: 1 1 auto; min-width: 0; margin: 0; overflow: hidden; white-space: pre; }
.field-notice__text, .field-notice__quote { flex: none; }
.field-notice__quote { display: flex; }
.field-notice__quote > i { flex: none; font-style: normal; }
.field-notice__title { flex: none; white-space: pre; }
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
