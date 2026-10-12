// What can be done with a report (docs/design/bug-reports.md), in two pills above the field, where Check again stands for a
// document (DocCheck.tsx): Send to developers, a link that opens a GitHub issue with the report in the browser (⌥ held, an email
// draft), and Improve it, which asks the agent for a design document in the report's own task. They stand for the report in
// front, and for the report the field's answer has just made, until the answer goes.
import { computed, reactive, ref, watch } from '../reactivity'
import { getDoc, type DocDetail } from './api'
import { agentChat, currentThread, openForGoal, send } from './agentChat'
import { isReportPath, reportKindOf } from './report'
import { chipLinks } from './chipLinks'
import { circleWords } from './circle'
import { docCard } from './docCard'
import { frontDocId } from './docComments'
import { sendLinks } from './reportSend'

/** The report the pills are about: the document in front when it is one, else the report the field's answer holds. */
export const reportDocId = computed<string | null>(() => {
  const front = frontDocId.value
  if (front && isReportPath(docCard(front)?.path)) return front
  const words = circleWords.value
  if (words?.kind !== 'answer') return null
  return chipLinks(words.text).find((chip) => chip.kind === 'doc' && isReportPath(docCard(chip.id)?.path))?.id ?? null
})

// It is read as it stands, and again whenever the person edits it: what goes is the document's text, not what was first made.
const read = reactive({ doc: null as DocDetail | null })
let reading = 0
async function load(id: string | null): Promise<void> {
  const mine = ++reading
  if (!id) {
    read.doc = null
    return
  }
  try {
    const doc = await getDoc(id)
    if (mine === reading) read.doc = doc
  } catch {
    if (mine === reading) read.doc = null
  }
}
watch(reportDocId, (id) => void load(id), { immediate: true })
if (typeof window !== 'undefined') {
  window.addEventListener('verticals:doc-edited', (event) => {
    const id = (event as CustomEvent<{ id?: string }>).detail?.id
    if (id && id === reportDocId.value) void load(id)
  })
}

export const report = computed(() => (read.doc && read.doc.id === reportDocId.value ? read.doc : null))
/** The task the report belongs to: the goal that links it (the report is its first document). */
export const reportTask = computed(() => report.value?.linked_goals[0] ?? null)
/** The two links, built from the document's text: the issue, and the email draft. The kind is the folder the report is in. */
export const links = computed(() => (report.value
  ? sendLinks(reportKindOf(report.value.path) ?? 'request', reportTask.value?.title || report.value.title || 'Report', report.value.body)
  : null))

/** ⌥ held: the pill is the email draft's, as a Mac's menu item changes while ⌥ is down. */
export const altHeld = ref(false)
if (typeof window !== 'undefined') {
  const hold = (event: KeyboardEvent): void => { altHeld.value = event.altKey }
  window.addEventListener('keydown', hold, true)
  window.addEventListener('keyup', hold, true)
  window.addEventListener('blur', () => { altHeld.value = false })
}

const improving = ref(false)
export const sendShown = computed(() => !!links.value)
export const improveShown = computed(() => !!reportTask.value && agentChat.available && !agentChat.running && !improving.value)
export const reportShown = computed(() => sendShown.value || improveShown.value)

/** What the agent is told. Its conversation is the task's, so the links are what it needs; how a design is written, where it
 *  goes and what happens once it is agreed are the chat's own instructions (desktop/chat/prompt-report.md). */
export function improveAsk(report: string, task: string): string {
  return `Improve it. ${report} is a report I made, in ${task}. Write the design document for the change it calls for, link it `
    + 'to that task, and say in two short lines that you are waiting for my comments.'
}

/** The pills stay away while the agent works on the design, so they do not flash back between the press and the turn. It is
 *  let go when the turn ends, or when none began (the message did not go, or nothing answered in 20 s). */
function holdUntilTheTurnEnds(): () => void {
  let began = false
  const done = (): void => {
    stop()
    clearTimeout(timer)
    improving.value = false
  }
  const stop = watch(() => agentChat.running, (running) => {
    if (running) began = true
    else if (began) done()
  })
  const timer = setTimeout(done, 20_000)
  return () => { if (!began) done() }
}

/** Improve it: the task's conversation (the one Discuss continues, or a new one about the task), and the agent's answer lands
 *  in the field with the design document as a chip, as Check again's does. */
export async function improveIt(): Promise<void> {
  const doc = report.value
  const task = reportTask.value
  if (!doc || !task || !agentChat.available || agentChat.running || improving.value) return
  improving.value = true
  const letGo = holdUntilTheTurnEnds()
  const name = (doc.title || doc.path).replace(/[[\]]/g, '')
  await openForGoal({ id: task.goal_id, title: task.title })
  agentChat.engaged = false
  await send(improveAsk(`[${name}](#doc/${doc.id})`, `[${task.title.replace(/[[\]]/g, '')}](#goal/${task.goal_id})`))
  // The message did not go (the gateway refused it): no turn will start, and the pills come back.
  if (!agentChat.running && currentThread.value?.status !== 'working') letGo()
}
