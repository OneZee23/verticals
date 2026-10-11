<script setup lang="ts">
// The period bars, | ||| | (docs/design/column-bars.md): Verticals pages a column with vertical bars, its own sign, in place of
// ← • →. The three in the middle are the mode button, the middle one dark: a week in each column for Week, the mode a
// dragged goal opens on the column's corner (`lib/spansDrag.ts`). Under the pointer a bar comes at each side and steps
// the column to the period before and after. All three are buttons, named by the column's kind for the keyboard and
// assistive tech: "Previous week", "Week mode", "Next week".
import { computed } from 'vue'

const props = defineProps<{ kind: string }>()
const emit = defineEmits<{ step: [direction: -1 | 1]; mode: [] }>()
const noun = computed(() => props.kind.toLowerCase())
</script>

<template>
  <!-- The sign's middle stands where it does with or without its sides; each button's own box reaches outward from its
       bars, so the three never overlap. -->
  <div class="column-bars" data-cap="period-nav">
    <button
      class="column-bars__button column-bars__button--prev column-bars__button--side"
      type="button"
      :aria-label="`Previous ${noun}`"
      data-cap="period-prev"
      @click="emit('step', -1)"
    ><span class="column-bars__mark"><i class="column-bars__bar"></i></span></button>
    <button
      class="column-bars__button column-bars__button--mode"
      type="button"
      :aria-label="`${kind} mode`"
      data-cap="period-mode"
      @click="emit('mode')"
    ><span class="column-bars__mark"><i class="column-bars__bar"></i><i class="column-bars__bar column-bars__bar--ink"></i><i class="column-bars__bar"></i></span></button>
    <button
      class="column-bars__button column-bars__button--next column-bars__button--side"
      type="button"
      :aria-label="`Next ${noun}`"
      data-cap="period-next"
      @click="emit('step', 1)"
    ><span class="column-bars__mark"><i class="column-bars__bar"></i></span></button>
  </div>
</template>

<style>
/* Drawn to the kind line's type, the caption at 15/24 in Commissioner: its caps are 10.7 px tall and stand on a baseline
   18 px under the top of the line's row, 22 px under the column's top. A bar is 11 px tall, standing on that baseline,
   and 2 px wide, a little heavier than the type's stems; 3 px between the bars of the sign, 6 px to the bars at its sides
   (inner smaller than outer, twice). The colours are the dots' in a column's corner (ColumnDots.vue): the board's ink,
   and its light grey.

   The middle of the sign, 12 px wide, is 22 px in from the column's right edge and never moves: the bar that comes at
   its right brings the 14 px margin the kind line's left margin matches, and the sign stays under the pointer that
   arrived on it. The buttons' boxes are as tall as the line, 28 px, and 15 to 18 px wide, reaching out from their
   bars; a coarse pointer gets 44 px of height. */
.column-bars {
  position: absolute;
  z-index: 12; /* over the line pinned at the slide's top (11, ColumnLine.vue) */
  top: var(--board-under-bar, 0px);
  right: 22px;
  width: 12px;
  height: var(--column-line);
}
.column-bars__button {
  position: absolute;
  top: 0;
  display: flex;
  align-items: flex-start;
  box-sizing: border-box;
  height: var(--column-line);
  margin: 0;
  padding: 11px 0 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.column-bars__button--mode { left: -3px; width: 18px; justify-content: center; }
.column-bars__button--prev { right: calc(100% + 3px); width: 17px; padding-right: 3px; justify-content: flex-end; }
.column-bars__button--next { left: calc(100% + 3px); width: 15px; padding-left: 3px; justify-content: flex-start; }
@media (pointer: coarse) {
  .column-bars__button { height: 44px; }
}
/* The mark is the bars and 4 px around them, which only a keyboard's focus shows, in the 8% of ink the old arrows showed
   theirs in. */
.column-bars__mark {
  display: flex;
  gap: 3px;
  padding: 4px;
  margin: -4px;
  border-radius: 4px;
}
.column-bars__bar {
  flex: none;
  width: 2px;
  height: 11px;
  border-radius: 1px;
  background: #d3d4d7;
  /* instant in, smooth back: the look under the pointer comes at once and fades back with the pointer's leaving */
  transition: background-color var(--motion-bars) var(--vt-ease-large);
}
.column-bars__bar--ink { background: #2d3036; }
.column-bars__button:focus-visible { outline: none; }
/* Pressed, a bar looks as it does in a keyboard's focus: it answers at the press, on a touch screen too, where nothing
   hovers; the action itself fires on release over the same button. */
.column-bars__button:focus-visible .column-bars__bar,
.column-bars__button:active .column-bars__bar { background: #2d3036; transition: none; }
.column-bars__button:focus-visible .column-bars__mark,
.column-bars__button:active .column-bars__mark { background: rgb(45 48 54 / 8%); }
/* Nothing hovers on a touch screen, so the side bars stay in view there; where a pointer can hover they come with it:
   at once, and fade back in 200 ms (none under reduced motion, where the token is 0). Held in view by a keyboard's focus
   (a mouse's leaves the pointer's way alone). */
@media (hover: hover) and (pointer: fine) {
  .column-bars__button--side {
    opacity: 0;
    pointer-events: none;
    transition: opacity var(--motion-bars) var(--vt-ease-large);
  }
  .pattern-vertical-board__column:hover .column-bars__button--side,
  .column-bars:has(:focus-visible) .column-bars__button--side {
    opacity: 1;
    pointer-events: auto;
    transition: none;
  }
  .column-bars__button:hover .column-bars__bar { background: #2d3036; transition: none; }
}
/* A search that finds nothing turns the board off, the bars with the column's names (FindingSections.vue). */
.pattern-vertical-board--nothing-found .column-bars {
  opacity: var(--goal-off-opacity);
  filter: grayscale(var(--goal-off-grey));
}
</style>
