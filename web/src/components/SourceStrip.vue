<script setup lang="ts">
// A source's state at the top of its window (docs/design/sources.md; lib/sources.ts): what its check last found, the check
// in words (for a check that waits, the exact text you are approving), and the one thing to do: Approve a check that waits
// for you, Fix a source that stopped answering. Nothing else here; the document under it is the
// source's own page.
import { computed, onMounted, ref, watch } from 'vue'
import { KButton } from '@konstantinopolskii/vue'
import { agentChat } from '../lib/agentChat'
import { approve, detailOf, fixSource, loadSources, noteOf, sourceOf } from '../lib/sources'
import { store } from '../store'

const props = defineProps<{ id: string }>()
const source = computed(() => sourceOf(props.id))
const note = computed(() => (source.value ? noteOf(source.value) : null))
/* Sentence case in the window; the tile says it in lower case under the name. */
const head = computed(() => (note.value ? note.value.text.charAt(0).toUpperCase() + note.value.text.slice(1) : ''))
const detail = computed(() => (source.value ? detailOf(source.value) : ''))
const canFix = computed(() => source.value?.status === 'red' && agentChat.available)

const busy = ref(false)
const problem = ref('')
async function onApprove(): Promise<void> {
  if (!source.value || busy.value) return
  busy.value = true
  problem.value = ''
  const result = await approve(source.value)
  busy.value = false
  if (result === 'changed') problem.value = 'The check changed while you read it. Read it again.'
  else if (result === 'failed') problem.value = 'Could not approve. Try again.'
}
onMounted(() => void loadSources())
// An answer to the check rings the board's bell (the same one a goal's change rings): read the state again.
watch(() => store.state.board, () => void loadSources())
</script>

<template>
  <div v-if="source && note" class="source-strip" data-role="source-strip" :data-state="source.status" :data-why="source.why ?? undefined">
    <div class="source-strip__text">
      <p class="source-strip__state" :class="{ 'source-strip__state--red': note.tone === 'red' }" data-role="source-strip-state">{{ head }}</p>
      <p v-if="detail" class="source-strip__detail" data-role="source-strip-detail">{{ detail }}</p>
      <p v-if="source.summary" class="source-strip__check" data-role="source-strip-check">{{ source.summary }}</p>
      <p v-if="problem" class="source-strip__problem" data-role="source-strip-problem" role="status">{{ problem }}</p>
    </div>
    <KButton v-if="source.needs_approval" primary data-role="source-approve" :disabled="busy" @click="onApprove">Approve</KButton>
    <KButton v-else-if="canFix" primary data-role="source-fix" @click="fixSource(source)">Fix</KButton>
  </div>
</template>

<style>
/* At the document's own margin, over its title; a hairline under it groups the three lines with the button. */
.source-strip { display: flex; align-items: flex-start; gap: 16px; margin: 6px 24px 8px; padding: 0 0 16px; border-bottom: 1px solid rgb(45 48 54 / 8%); }
.source-strip__text { flex: 1; min-width: 0; }
.source-strip__text p { margin: 0; overflow-wrap: anywhere; }
.source-strip__state { font: 500 15px/22px var(--font-body, Commissioner, system-ui, sans-serif); color: #000; }
.source-strip__state.source-strip__state--red { color: #c93a5b; }
.source-strip__detail { font: 400 15px/22px var(--font-body, Commissioner, system-ui, sans-serif); color: #000; }
.source-strip__check, .source-strip__problem { margin-top: 2px; font: 400 13px/20px var(--font-body, Commissioner, system-ui, sans-serif); color: rgb(45 48 54 / 60%); }
.source-strip__problem.source-strip__problem { color: #c93a5b; }
/* The one thing to do is the kit's primary button (black, white label), by its text's width: the kit's is full width. */
.source-strip .button.button { flex: none; width: auto; padding: var(--space-2) var(--space-4); }
</style>
