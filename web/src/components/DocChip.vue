<script setup lang="ts">
// A document as one thing in a list (Inbox and Documents redesign, rounds 9–10; .local-design/inbox-and-docs/final, "A
// document as a chip"): its own first page on the left, as tall as three lines (50 × 67), and on the right its name, two
// lines at most, and when it was edited, from the top. In a message it sits on the balloon's black; in the Inbox it is a
// ghost on the desk until the pointer brings it to life. A click opens the document as a window (S3.P4). A source (the
// Inbox's Sources row, lib/sources.ts) is a document too: the line under its name is its state, "checked 07:00", and in red
// "not answering since 06:00", where a document says when it was edited.
import { computed } from 'vue'
import DocPage from './DocPage.vue'
import { docCard, type DocCard } from '../lib/docCard'
import { whenEdited } from '../lib/docsDesk'
import { openWindow } from '../lib/windows'

const props = defineProps<{ id: string; doc?: DocCard | null; dark?: boolean; label?: string; note?: string; tone?: 'ok' | 'grey' | 'red' }>()

const card = computed(() => props.doc ?? docCard(props.id))
/* A document with no title is called by its file's name. */
const name = computed(() => card.value?.title || card.value?.path.split('/').pop() || props.label || 'Document')

function open(event: Event): void {
  openWindow({ kind: 'doc', target: props.id, title: name.value }, event.currentTarget as Element)
}
</script>

<template>
  <button type="button" class="doc-chip" :class="{ 'doc-chip--dark': dark }" data-role="doc-chip" :data-doc-id="id" @click.stop="open">
    <span class="doc-chip__page"><DocPage v-if="card" :doc="card" :width="50" /></span>
    <span class="doc-chip__text">
      <span class="doc-chip__name">{{ name }}</span>
      <span v-if="note" class="doc-chip__when" :class="{ 'doc-chip__when--red': tone === 'red' }" data-role="source-state" :data-tone="tone">{{ note }}</span>
      <span v-else-if="card" class="doc-chip__when">{{ whenEdited(card.updated_at) }}</span>
    </span>
  </button>
</template>

<style>
.doc-chip { box-sizing: border-box; display: flex; align-items: flex-start; gap: 14px; min-width: 0; margin: 0; padding: 12px 16px 12px 12px;
  border: 0; border-radius: 12px; background: transparent; color: #000; text-align: left; font: inherit; cursor: default;
  box-shadow: inset 0 0 0 1px rgb(45 48 54 / 5%);
  transition: background-color 200ms ease, box-shadow 200ms ease, transform 200ms var(--vt-ease-large); }
.doc-chip__page { flex: none; display: block; width: 50px; height: 67px; }
.doc-chip__page > .doc-page { border-radius: 3px; box-shadow: 0 0 0 .5px rgb(16 18 32 / 12%); }
.doc-chip__text { display: block; flex: 1; min-width: 0; }
.doc-chip__name { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  font: 500 15px/22px var(--font-body, Commissioner, system-ui, sans-serif); overflow-wrap: anywhere; }
.doc-chip__when { display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
  font: 400 13px/22px var(--font-body, Commissioner, system-ui, sans-serif); color: rgb(45 48 54 / 60%); }
/* A source that stopped answering: the one coloured line in the Inbox (the app's one red, the danger item's). */
.doc-chip__when.doc-chip__when--red { color: #c93a5b; }
/* Under the pointer it turns white and comes alive at once; it settles back in 200 ms. */
@media (hover: hover) and (pointer: fine) {
  .doc-chip:not(.doc-chip--dark):hover { background: #fff; transform: translateY(-1px); transition-duration: 0s;
    box-shadow: 0 0 0 .5px rgb(16 18 32 / 5%), 0 1px 3px rgb(16 18 32 / 4%), 0 8px 22px -12px rgb(16 18 32 / 14%); }
}
.doc-chip:focus-visible { outline: 2px solid #007aff; outline-offset: 2px; }
/* In a message: on the balloon's black, no ground of its own, the words white. */
.doc-chip--dark { padding: 0; box-shadow: none; color: #fff; cursor: pointer; }
.doc-chip--dark .doc-chip__page > .doc-page { box-shadow: none; }
.doc-chip--dark .doc-chip__when { color: rgb(255 255 255 / 50%); }
@media (prefers-reduced-motion: reduce) { .doc-chip { transition: none; } }
</style>
