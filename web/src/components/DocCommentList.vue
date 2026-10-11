<script setup lang="ts">
/* All of a document's comments, as a list over the field (docs/design/doc-comments-inline.md: "The count opens all the
   comments as a list over the field; a click on one takes you to its words"). The open ones first, in the order they were
   made; the resolved ones after, under their own small heading, so an unresolved one can still be reached. A row is the
   words the comment is about and the last thing said on it; a click closes the list and takes the window to those words,
   where the comment opens (DocCommentCard.vue). */
import { computed } from 'vue'
import { store } from '../store'
import { docThreads, threadWords } from '../lib/docComments'
import type { CommentThread } from '../lib/api'

interface Row {
  thread: CommentThread
  /** "Agent" when the last thing said is the agent's: the one author worth naming. */
  who: string
  words: string
  resolved: boolean
  /** The first resolved one, which the small heading stands over. */
  first: boolean
}

const rows = computed<Row[]>(() => {
  const all = [
    ...docThreads.value.filter((thread) => thread.resolved_at === null),
    ...docThreads.value.filter((thread) => thread.resolved_at !== null),
  ]
  return all.map((thread, i) => {
    const last = thread.messages[thread.messages.length - 1]
    const resolved = thread.resolved_at !== null
    return {
      thread, who: last?.author === 'agent' ? 'Agent' : '', words: last?.body ?? '', resolved,
      first: resolved && (i === 0 || all[i - 1]!.resolved_at === null),
    }
  })
})
</script>

<template>
  <section class="doc-list" data-role="doc-comments-list" role="group" aria-label="Comments">
    <template v-for="row in rows" :key="row.thread.id">
      <h3 v-if="row.first" class="doc-list__head">Resolved</h3>
      <button
        type="button"
        class="doc-list__row"
        :class="{ 'doc-list__row--resolved': row.resolved }"
        data-role="doc-comments-row"
        :data-thread-id="row.thread.id"
        @click="store.openCard(row.thread.id)"
      >
        <span class="doc-list__words">{{ threadWords(row.thread) }}</span>
        <span class="doc-list__said"><b v-if="row.who">{{ row.who }}</b> {{ row.words }}</span>
      </button>
    </template>
  </section>
</template>

<style>
/* Over the pair, 8 px clear of it, on its middle (the circle's: one axis for all of it, and on a phone the sheet cannot leave
   the screen): a white sheet at the card's depth (the hairline and the near pool of `vt-shadow--small`; the far halo would
   grey the text behind it), 360 px wide or the screen less 12 px each side, its rows 14/20 and 13/18, the way the Documents
   desk sets a name and its line. It scrolls inside when there are many. */
.doc-list {
  position: absolute;
  left: calc(50% - min(180px, (100vw - 24px) / 2));
  bottom: calc(100% + 8px);
  box-sizing: border-box;
  width: min(360px, calc(100vw - 24px));
  max-height: min(420px, 50vh);
  padding: 6px;
  overflow-y: auto;
  overscroll-behavior: contain;
  border-radius: 14px;
  background: #fff;
  color: #000;
  box-shadow: var(--vt-shadow-hair), var(--vt-near-small) rgba(var(--vt-ink), var(--vt-shadow-grey-near));
  font: 400 14px/20px var(--font-body);
  animation: doc-list-in var(--vt-dur-open) var(--vt-ease-large) backwards;
  transform-origin: 50% 100%;
  pointer-events: auto;
}
@keyframes doc-list-in { from { opacity: 0; transform: translateY(4px) scale(.98); } }
@media (prefers-reduced-motion: reduce) { .doc-list { animation: doc-list-fade var(--vt-crossfade) linear backwards; } }
@keyframes doc-list-fade { from { opacity: 0; } }
.doc-list__row {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
@media (hover: hover) and (pointer: fine) { .doc-list__row:hover { background: rgb(0 0 0 / 5%); } }
.doc-list__row:focus-visible { outline: 2px solid #000; outline-offset: -2px; }
.doc-list__words { overflow: hidden; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.doc-list__said { overflow: hidden; color: rgb(0 0 0 / 55%); font: 400 13px/18px var(--font-body); text-overflow: ellipsis; white-space: nowrap; }
.doc-list__said b { color: rgb(0 0 0 / 80%); font-weight: 500; }
.doc-list__head { margin: 8px 10px 2px; color: rgb(0 0 0 / 45%); font: 500 11px/16px var(--font-body); }
.doc-list__row--resolved .doc-list__words { color: rgb(0 0 0 / 55%); font-weight: 400; }
</style>
