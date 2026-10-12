<script setup lang="ts">
/* Deliberately NOT KCardHeading: that component wraps output in div.card__heading, which carries
   its own margin-top (--space-2) and left/right padding (--card-inset-x) — exactly what the A7
   kit commit replaced with .pattern-vertical-board__header{padding:24px 8px 0 12px} to hit the
   measured baseline offset. Using KCardHeading here would double up padding and throw off the
   probe. A7's own commit message says as much: reuse the kit's .t-title/.t-caption utilities
   directly, no new/reused component wrapper. */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fittest, fontEpoch, fontOf } from '../lib/fitName'
import type { NameForm } from '../types'

const props = withDefaults(defineProps<{
  title: string
  subLabel?: string
  /** The same name in shorter forms, longest first: the header shows the first that fits its room, so a name is never
   *  cut with "…" (docs/design/column-names.md, `lib/fitName.ts`). */
  shorter?: NameForm[]
  /** A span's end, after its date (docs/design-handoff S5.P1.014). */
  end?: string
}>(), { subLabel: '', shorter: () => [], end: '' })

const emit = defineEmits<{ form: [form: NameForm] }>()

/* The name's room is the width of its row, which a column that opens, closes or is resized changes in the frame its
   layout does: the observer reports it before that frame is drawn, and the form that fits is chosen there, never while
   the column moves. (The row, not the title: the title is a few px wider than its room, see `--column-spill` below.) */
const rowEl = ref<HTMLElement | null>(null)
const titleEl = ref<HTMLElement | null>(null)
const room = ref(0)
let watcher: ResizeObserver | null = null
onMounted(() => {
  if (!rowEl.value || typeof ResizeObserver === 'undefined') return
  watcher = new ResizeObserver((entries) => { room.value = entries[entries.length - 1].contentRect.width })
  watcher.observe(rowEl.value)
})
onBeforeUnmount(() => watcher?.disconnect())

const forms = computed<NameForm[]>(() => [{ name: props.title, kind: props.subLabel }, ...props.shorter])
const shown = computed<NameForm>(() => {
  fontEpoch.value // chosen again once the title font has arrived
  const all = forms.value
  if (all.length === 1 || !titleEl.value || room.value <= 0) return all[0]
  return all[fittest(all.map((form) => form.name), room.value, fontOf(titleEl.value))]
})
/* The line pinned at the column's top says the same words once the name has scrolled under it, so it is told which form
   fits (docs/design/column-bars.md). */
watch(shown, (form) => emit('form', form), { immediate: true })
</script>

<template>
  <header class="pattern-vertical-board__header column-header">
    <div v-if="shown.kind" class="column-header__period-row">
      <p class="t-caption column-header__sub-label">{{ shown.kind }}</p>
    </div>
    <div ref="rowEl" class="column-header__title-row">
      <!-- A shorter form on screen still has the full name for a screen reader. -->
      <h3 ref="titleEl" class="t-title" :aria-label="shown === forms[0] ? undefined : title">{{ shown.name }}<span v-if="end" class="column-header__end" data-role="span-end">{{ end }}</span></h3>
    </div>
  </header>
</template>

<style>
/* The kind sits above the column's name, the period (docs/design/column-names.md). Keep both rows inside the compact
   header; the name remains single-line and ellipsized so narrow columns do not push the board out of alignment.

   The form that fits is chosen against the room of the row (`lib/fitName.ts`). A name whose shortest form is still a
   little wider than that, "Apr–May" at 134.8 px in a room of 134, or a kind line like "Week · May ’27", may take up to
   `--column-spill` of the 12 px of padding to its right (and of the kind row's 36) before it is cut with "…". */
.column-header.column-header {
  --column-spill: 8px;
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: 24px 40px;
  gap: 0;
  align-content: start;
  overflow: hidden;
}
.column-header__period-row,
.column-header__title-row {
  grid-column: 1;
}
.column-header__period-row {
  grid-row: 1;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
  padding-right: 36px;
  overflow: hidden;
}
.column-header__sub-label {
  margin: 0 calc(-1 * var(--column-spill)) 0 0;
  overflow: hidden;
  color: rgb(45 48 54 / 52%);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.column-header__title-row {
  grid-row: 2;
  display: block;
  width: 100%;
  position: relative;
  top: -6px;
}
.column-header__title-row > .t-title {
  display: block;
  width: calc(100% + var(--column-spill));
  min-width: 0;
  line-height: 40px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text);
}
.column-header__end {
  margin-left: 10px;
  color: #b3b4b7;
  font-size: 17px;
  font-weight: 700;
}
</style>
