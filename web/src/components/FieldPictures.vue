<script setup lang="ts">
// The pictures waiting above the field (docs/design/bug-reports.md), in the stack a goal let go over the field waits in
// (MovingStack.vue hosts both): 56 px tall, 8 px corners, 8 px apart, from the field's left end. The room they have is the
// field's width as it will be, which the field sets at once (--moving-field-width, --moving-tags-shift), so what overlaps is
// decided by CSS from those and the stack's own width, and the field's widening moves nothing under them: past a few they
// lie over each other, each less than the one before, and any number still fits.
//
// The one under the pointer lifts out of the others, bigger, as a picture on a table is held up to look at. What the pointer is
// on is the picture's place in the row, not the lifted picture, which lies over its neighbours and lets the pointer through:
// moving along the row lifts one after the other, none in the way of the next. A press picks it (Backspace picks the last):
// it stays lifted, with a small cross on its corner to take it off. A press leaves the keys where they are, in the field:
// the focus is what keeps the tags standing at the stack's left end, and the stack must not slide under the hand.
import AppIcon from './AppIcon.vue'
import { PICTURE_HEIGHT, pictures, removePicture, stackWidth, tapPicture, tileWidth } from '../lib/reportPictures'
</script>

<template>
  <div
    class="field-pictures"
    :class="{ 'is-sending': pictures.sending }"
    :style="{ '--stack': `${stackWidth(pictures.list)}px`, '--n': pictures.list.length, '--h': `${PICTURE_HEIGHT}px` }"
    data-role="field-pictures"
  >
    <div
      v-for="(picture, index) in pictures.list"
      :key="picture.id"
      class="field-pictures__item"
      :class="{ 'is-picked': pictures.picked === picture.id }"
      :style="{ '--w': `${tileWidth(picture)}px` }"
      data-role="field-picture"
    >
      <button
        type="button"
        class="field-pictures__hit"
        :aria-label="`Picture ${index + 1} of ${pictures.list.length}, ${picture.name}`"
        :aria-pressed="pictures.picked === picture.id"
        @mousedown.prevent
        @click.stop="tapPicture(picture.id)"
      ></button>
      <span class="field-pictures__pic" aria-hidden="true"><img :src="picture.url" alt="" draggable="false" decoding="async"></span>
      <button
        type="button"
        class="field-pictures__remove"
        :aria-label="`Take picture ${index + 1} off`"
        :tabindex="pictures.picked === picture.id ? 0 : -1"
        data-role="field-picture-remove"
        @mousedown.prevent
        @click.stop="removePicture(picture.id)"
      ><AppIcon name="x" :size="12" :stroke="2.8" /></button>
    </div>
  </div>
</template>

<style>
.field-pictures {
  /* What the field leaves the stack: its width less 4 px at the left (or the tags and 8 px) and 4 at the right, and 440 at
     the most (STACK_MAX). Over it, the pictures overlap by as much as it takes: (stack - room) shared by the n - 1 joints. */
  --room: min(440px, calc(var(--moving-field-width, 300px) - max(8px, 4px + var(--moving-tags-shift, 0px))));
  --overlap: max(0px, calc((var(--stack) - var(--room)) / max(1, var(--n) - 1)));
  --lift: 2.6;
  display: flex;
  flex: none;
  align-items: flex-end;
  width: min(var(--stack), var(--room));
  height: var(--h);
  transition: opacity var(--vt-dur-fade) ease-out;
}
.field-pictures.is-sending { opacity: .45; pointer-events: none; }
/* The place of a picture in the row: what the pointer is on, and what a press and the keys speak for. */
.field-pictures__item {
  position: relative;
  flex: none;
  width: var(--w);
  height: var(--h);
  margin-left: calc(8px - var(--overlap));
}
.field-pictures__item:first-child { margin-left: 0; }
.field-pictures__hit {
  position: absolute;
  inset: 0;
  z-index: 1;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
}
.field-pictures__hit:focus-visible { outline: 2px solid #000; outline-offset: 2px; }
/* The picture itself lifts and scales from its bottom edge, over its neighbours, and lets the pointer through. */
.field-pictures__pic {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: 8px;
  background: #f2f2f4;
  /* A hairline to keep each picture's edge where they overlap, and a near shadow (the window's wide glow would pile up
     under fourteen pictures into a cloud). */
  box-shadow: 0 0 0 .5px rgba(var(--vt-ink), .14), 0 5px 14px -7px rgba(var(--vt-ink), .26);
  pointer-events: none;
  transform-origin: 50% 100%;
  transition: transform var(--vt-dur-close) var(--vt-ease-large), box-shadow var(--vt-dur-close) var(--vt-ease-large),
    border-radius var(--vt-dur-close) var(--vt-ease-large);
}
.field-pictures__pic img { display: block; width: 100%; height: 100%; object-fit: contain; }
/* The cross stands on the lifted picture's top right corner, where the lifted picture is (scaled from its bottom). */
.field-pictures__remove {
  position: absolute;
  top: calc(-1 * var(--h) * (var(--lift) - 1) - 6px - 11px);
  right: calc(-1 * var(--w) * (var(--lift) - 1) / 2 - 11px);
  z-index: 3;
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 11px;
  background: #000;
  color: #fff;
  box-shadow: 0 0 0 2px #fff;
  opacity: 0;
  pointer-events: none;
  cursor: pointer;
  transition: opacity var(--vt-dur-fade) ease-out;
}
.field-pictures__remove:focus-visible { outline: 2px solid #000; outline-offset: 3px; }
/* Lifted, a picture lies over the others (one stacking order for the whole row, so the rule is on the picture). */
.field-pictures__item.is-picked .field-pictures__pic, .field-pictures__hit:focus-visible + .field-pictures__pic {
  z-index: 2;
  transform: translateY(-6px) scale(var(--lift));
  /* The picture is scaled, and so are its corners and its shadow: both are given as they are to look at, over the scale. */
  border-radius: calc(10px / var(--lift));
  box-shadow: 0 0 0 calc(.5px / var(--lift)) rgba(var(--vt-ink), .14),
    0 calc(14px / var(--lift)) calc(30px / var(--lift)) calc(-10px / var(--lift)) rgba(var(--vt-ink), .32);
  transition-duration: var(--vt-dur-open);
}
.field-pictures__item.is-picked .field-pictures__remove { opacity: 1; pointer-events: auto; }
/* Under the pointer, at once and as the pointer moves along them; they settle back when it leaves. */
@media (hover: hover) and (pointer: fine) {
  .field-pictures__item:hover .field-pictures__pic {
    z-index: 2;
    transform: translateY(-6px) scale(var(--lift));
    border-radius: calc(10px / var(--lift));
    box-shadow: 0 0 0 calc(.5px / var(--lift)) rgba(var(--vt-ink), .14),
      0 calc(14px / var(--lift)) calc(30px / var(--lift)) calc(-10px / var(--lift)) rgba(var(--vt-ink), .32);
    transition-duration: var(--vt-dur-open);
  }
  .field-pictures__remove:hover { background: #2b2b2b; }
}
@media (prefers-reduced-motion: reduce) {
  .field-pictures__pic { transition: none; }
  .field-pictures, .field-pictures__remove { transition: opacity var(--vt-crossfade) linear; }
}
</style>
