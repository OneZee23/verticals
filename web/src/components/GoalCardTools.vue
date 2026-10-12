<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import { computed, ref } from 'vue'
import { KChip, KInlineAdd } from '@konstantinopolskii/vue'
import type { VerticalScale } from '../lib/periods'
import { isoDate, localDate, periodKeyFor } from '../lib/schedule'
import { playSound } from '../lib/sound'
import { store, todayIso } from '../store'
import { agentChat as agentChatState } from '../lib/agentChat'
import PopoverEngine from './PopoverEngine.vue'
import RepeatPopover from './RepeatPopover.vue'
import OpenInMenu from './OpenInMenu.vue'
import MoveStep, { type MoveStepName } from './MoveStep.vue'
import type { RepeatRule } from '../lib/api'

const props = defineProps<{
  id: string
  vertical?: string | null
  repeat?: RepeatRule | null
  /** The card is the open goal: its facts line already shows the date, the checkbox completes it and it is open, so
   *  the menu keeps only what the card doesn't show (KK, 27 Sep 2026, the cleaned-up card). */
  open?: boolean
}>()
const emit = defineEmits<{
  'open-change': [open: boolean]
}>()

const trigger = ref<HTMLButtonElement | null>(null)
const open = ref(false)
/* The Agent section: Discuss, Start work and Open in, only where an agent exists (docs/design-handoff S2.P1.023;
   docs/design/goal-menu.md, docs/design/task-sessions.md). The open card's facts line offers Discuss already, so that card's
   section holds the other two. */
const showAgent = computed(() => agentChatState.available)
function discuss() {
  window.dispatchEvent(new CustomEvent('verticals:discuss-goal', { detail: { id: props.id } }))
  closeMenu()
}
function startWork() {
  window.dispatchEvent(new CustomEvent('verticals:start-work', { detail: { id: props.id } }))
  closeMenu()
}
const fixedSameVerticalParent = computed(() => store.sameVerticalParentId(props.id))
const repeatVertical = computed(() => (props.vertical && props.vertical !== 'life' ? props.vertical : null))
/* A goal nested under a parent of its own vertical has no dates or parent of its own to change here (D179), so only its
   Repeat stays, under Reschedule, and the Move group is left out. */
const showReschedule = computed(() => !fixedSameVerticalParent.value || repeatVertical.value !== null)
function onOpen() {
  open.value = true
  emit('open-change', true)
}

function onClose() {
  open.value = false
  step.value = null
  emit('open-change', false)
}

function openMenu() {
  if (!open.value) trigger.value?.click()
}

function closeMenu() {
  if (open.value) trigger.value?.click()
}

/* Tomorrow and Next week move the goal at once; Date and Into a goal open a step in place (S5.P5.003, .008). */
const step = ref<MoveStepName | null>(null)
function day(offset: number): Date {
  const t = localDate(todayIso())
  return new Date(t.getFullYear(), t.getMonth(), t.getDate() + offset)
}
const tomorrow = computed(() => day(1))
const nextWeek = computed(() => { const t = day(0); return day(7 - ((t.getDay() + 6) % 7)) })
function moveToInbox() {
  void store.moveGoalToInbox(props.id)
  closeMenu()
}
function moveTo(scale: VerticalScale, date: Date) {
  void store.scheduleGoalQuick(props.id, scale, periodKeyFor(scale, date), isoDate(date))
  closeMenu()
}

/* Tags moved here from the open card's icon row. They are the open goal's, read off its loaded detail. */
const tags = computed(() => (store.state.goalDetail?.id === props.id ? store.state.goalDetail.tags : []))
function addTag(tag: string) {
  if (tags.value.includes(tag)) return
  void store.updateGoal(props.id, { tags: [...tags.value, tag] })
}
function removeTag(tag: string) {
  void store.updateGoal(props.id, { tags: tags.value.filter((t) => t !== tag) })
}

function remove() {
  playSound('goal_deleted')
  void store.removeGoal(props.id)
}

defineExpose({ openMenu })
</script>

<template>
  <!-- One place for the menu (KK, 27 Sep 2026: "it jumps here and there if i click on menu icon"): it hangs below the
       dots, starting at them, as a pull-down menu does on the Mac; it goes above only when there's no room below, and
       ends at the dots only in the last column. "Auto" picked whichever side had the most room, a different one per
       card, and picked again as the card under it moved. -->
  <PopoverEngine
    class="goal-card__tools"
    placement="bottom-start"
    surface-class="goal-actions__menu"
    :surface-attrs="{ 'data-role': 'goal-context-menu' }"
    @open="onOpen"
    @close="onClose"
  >
    <template #trigger="{ open: engineOpen }">
      <button
        ref="trigger"
        type="button"
        class="goal-actions__trigger"
        data-role="goal-actions-trigger"
        data-cap="reparent"
        aria-label="Goal actions"
        aria-haspopup="menu"
        :aria-expanded="engineOpen"
      >
        <AppIcon name="dots" data-cap="delete" :size="24" />
      </button>
    </template>

    <!-- A step (Date and its levels, Into a goal) takes the menu's place, with ‹ back (docs/design-handoff S5.P5.008, .039).
         Otherwise the menu groups its actions by what they change: the agent's work, when, where, and the goal itself,
         each group under a small grey word and a line from the one before (docs/design/goal-menu.md). A goal completes by
         its box and comments live in documents, so neither is here. -->
    <MoveStep v-if="step" :id="id" :step="step" @go="(next) => step = next" @done="closeMenu" />
    <div v-else class="goal-actions__content" data-role="goal-actions-menu">
      <div v-if="showAgent" class="goal-actions__section" data-menu-section="agent" role="group" aria-label="Agent">
        <p class="goal-actions__heading" aria-hidden="true">Agent</p>
        <button
          v-if="!props.open"
          type="button"
          role="menuitem"
          class="dropdown__item goal-actions__item"
          data-menu-item="discuss"
          @click="discuss"
        >Discuss</button>
        <button
          type="button"
          role="menuitem"
          class="dropdown__item goal-actions__item"
          data-menu-item="start-work"
          @click="startWork"
        >Start work</button>
        <OpenInMenu :id="id" @done="closeMenu" />
      </div>

      <div v-if="showReschedule" class="goal-actions__section" data-menu-section="reschedule" role="group" aria-label="Reschedule">
        <p class="goal-actions__heading" aria-hidden="true">Reschedule</p>
        <template v-if="!fixedSameVerticalParent">
          <button type="button" role="menuitem" class="dropdown__item goal-actions__item" data-move="tomorrow" data-cap="schedule"
            @click="moveTo('day', tomorrow)">Tomorrow</button>
          <button type="button" role="menuitem" class="dropdown__item goal-actions__item" data-move="next-week"
            @click="moveTo('week', nextWeek)">Next week</button>
          <button type="button" role="menuitem" class="dropdown__item goal-actions__item" data-move="date" @click.stop="step = 'date'">
            <span>Date</span><span data-role="submenu-arrow" aria-hidden="true"><AppIcon name="chevron-right" :size="14" /></span>
          </button>
        </template>
        <RepeatPopover
          v-if="repeatVertical"
          :id="id"
          :vertical="repeatVertical"
          :repeat="repeat ?? null"
        />
      </div>

      <div v-if="!fixedSameVerticalParent" class="goal-actions__section" data-menu-section="move" role="group" aria-label="Move">
        <p class="goal-actions__heading" aria-hidden="true">Move</p>
        <button type="button" role="menuitem" class="dropdown__item goal-actions__item" data-move="under" @click.stop="step = 'under'">
          <span>Into a goal</span><span data-role="submenu-arrow" aria-hidden="true"><AppIcon name="chevron-right" :size="14" /></span>
        </button>
        <button
          v-if="vertical"
          type="button"
          role="menuitem"
          class="dropdown__item goal-actions__item"
          data-move="inbox"
          data-action="inbox"
          @click="moveToInbox"
        >To Inbox</button>
      </div>

      <div v-if="props.open" class="goal-actions__section" data-menu-section="tags">
        <PopoverEngine
          nested
          data-action="tags"
          surface-class="goal-actions__submenu goal-actions__tags"
          :surface-attrs="{ 'data-role': 'tag-chips' }"
        >
          <template #trigger>
            <button type="button" role="menuitem" class="dropdown__item goal-actions__item">
              <span>Tags…</span>
              <span data-role="submenu-arrow" aria-hidden="true"><AppIcon name="chevron-right" :size="14" /></span>
            </button>
          </template>
          <div class="goal-actions__tags-panel">
            <div v-if="tags.length" class="chip-wrap">
              <KChip
                v-for="tag in tags"
                :key="tag"
                data-cap="set-tags"
                :aria-label="`Remove ${tag}`"
                @click="removeTag(tag)"
              >{{ tag }} <AppIcon name="x" :size="12" /></KChip>
            </div>
            <KInlineAdd data-cap="set-tags" placeholder="Add tag…" @add="addTag" />
          </div>
        </PopoverEngine>
      </div>

      <div class="goal-actions__section" data-menu-section="delete">
        <button
          type="button"
          role="menuitem"
          class="dropdown__item goal-actions__item goal-actions__item--danger"
          data-action="delete"
          data-cap="delete"
          @click="remove"
        >
          <AppIcon name="trash" data-icon="trash" />
          <span>Delete</span>
        </button>
      </div>
    </div>
  </PopoverEngine>
</template>

<style>
.goal-card > .goal-card__row .goal-card__tools {
  position: absolute;
  top: 0;
  /* The dots end 14 px from the colour's right edge, as the checkbox starts 14 px from its left. The row ends 6 px
     inside the colour, the button's centre 9 px inside the row. */
  right: -3px;
  display: block;
  width: 24px;
  height: 24px;
  opacity: 1;
  transition: opacity var(--motion-hover) cubic-bezier(.165, .84, .44, 1);
}
.goal-card:hover > .goal-card__row .goal-card__tools,
.goal-card--menu-open > .goal-card__row .goal-card__tools,
.goal-card--landed-hover > .goal-card__row .goal-card__tools,
.goal-card__tools:focus-within { transition: none; }
.goal-actions__trigger {
  position: absolute;
  z-index: 2;
  top: -1px;
  right: 0;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: currentColor;
  cursor: pointer;
  opacity: 0;
  user-select: none;
  -webkit-touch-callout: none;
  transition: opacity var(--motion-hover) cubic-bezier(.165, .84, .44, 1);
}
.goal-actions__trigger svg { display: block; fill: currentColor; }
.goal-actions__trigger:focus { outline: none; }
.goal-card:hover > .goal-card__row .goal-actions__trigger,
.goal-card--menu-open > .goal-card__row .goal-actions__trigger,
.goal-card--landed-hover > .goal-card__row .goal-actions__trigger,
.goal-actions__trigger:focus-visible {
  opacity: 1;
  transition: none;
}

.goal-actions__content {
  display: flex;
  flex-direction: column;
  min-width: 300px;
}
/* A group of the menu: a small grey word over its items (S5.P5.003), and a line from the group before it, with the same 8 px
   above and below as the lines inside a step (docs/design/goal-menu.md). */
.goal-actions__section { display: flex; flex-direction: column; }
.goal-actions__section + .goal-actions__section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0, 0, 0, .08);
}
.goal-actions__heading { margin: 2px 14px 2px; color: rgb(45 48 54 / 52%); font: 400 13px/18px var(--font-body); }
.goal-actions__item.goal-actions__item,
.goal-actions__submenu.goal-actions__submenu button {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  width: 100%;
  gap: 8px;
  padding: 4px 14px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  /* The menu's row style, 17 px at weight 500, as the week table's rows (docs/design-handoff S5.P5.016). */
  font-size: 17px;
  font-weight: 500;
  line-height: 24px;
  text-align: left;
  cursor: pointer;
}
.goal-actions__item:hover,
.goal-actions__item:focus,
.goal-actions__submenu button:hover,
.goal-actions__submenu button:focus {
  outline: none;
  background-color: rgba(0, 0, 0, .05);
}
.goal-actions__item[aria-disabled="true"],
.goal-actions__schedule button[aria-disabled="true"] { cursor: default; opacity: .5; }
.goal-actions__item > svg,
.goal-actions__item > [data-role="icon-spacer"] {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
}
.goal-actions__item > svg { fill: none; stroke: currentColor; stroke-width: 2.2; }
.goal-actions__item > [data-role="submenu-arrow"] { margin-left: auto; }
/* One text edge (KK, 27 Sep 2026, the cleaned-up card's menu): words only, so every item starts on one line; the arrow
   that opens a submenu stays at the right. */
.goal-actions__menu .goal-actions__item > svg,
.goal-actions__menu .goal-actions__item > [data-role="icon-spacer"] { display: none; }
.goal-actions__tags-panel { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-2); min-width: 180px; }
/* An open card shows its dots all the time: they are the way to its rarer actions. */
.goal-card--detail-open > .goal-card__row .goal-actions__trigger { opacity: 1; }
/* Delete shows its red (docs/design/goal-menu.md). The surface's `.Menu-floating.popover-engine__surface .dropdown__item`
   sets `color: inherit` on three classes, and painted over the single-class red for as long as this class has existed;
   these four outweigh it. */
.goal-actions__menu.popover-engine__surface .goal-actions__item.goal-actions__item--danger { color: #c93a5b; }
.goal-actions__submenu > div { display: flex; }
.goal-actions__submenu > div > button { white-space: nowrap; }
.goal-actions__days { display: grid !important; grid-template-columns: repeat(7, 1fr); }
/* Stepper rows: the pager arrows flank a label that stays a full-width menu item, so the row
   reads as one line rather than three buttons. Mirrors SchedulePopover's own stepper shape. */
.goal-actions__stepper {
  display: flex;
  align-items: center;
}
.goal-actions__stepper > .dropdown__item {
  flex: 1 1 auto;
  text-align: center;
}
.goal-actions__nav {
  flex: 0 0 auto;
  padding: 0 var(--space-2);
  border: 0;
  background: none;
  color: inherit;
  line-height: 1;
  cursor: pointer;
}
/* The submenu's full-width item rule caught the arrows too: each "‹" took the whole row and pushed the year or month
   and its "›" out of sight (KK's Reschedule screenshot, 27 Sep 2026). The arrows keep their own size; the label between
   them is centred. */
.goal-actions__submenu.goal-actions__submenu .goal-actions__nav {
  width: auto;
  padding: 4px 10px;
  justify-content: center;
}
.goal-actions__submenu.goal-actions__submenu .goal-actions__stepper > .dropdown__item { justify-content: center; }
.goal-actions__schedule-footer {
  display: flex;
  gap: var(--space-1);
  border-top: 0.5px solid var(--color-border);
}
.goal-actions__schedule-footer > .dropdown__item {
  flex: 1 1 0;
  text-align: center;
}
.goal-actions__days button { justify-content: center; padding-inline: 6px; }
</style>
