// A report from pictures (docs/design/bug-reports.md). The person drops pictures on the window, says what happened in the field
// and presses ↵: the report comes first, as a document with the pictures, their words, the app's version and the last lines
// of the app's and the agent's logs, and its task is made with it, so the report is the task's first document. The answer
// shows both as chips (docs/design/agent-chips.md). Nothing here asks the agent: pictures of that size are not for a model to
// carry through a tool call, and what the logs may say is decided in code, not by a model (desktop/chat/report_facts.py).
// Then, if asked: Send to developers and Improve it (lib/reportActions.ts).
import { agentChat } from './agentChat'
import { commandFilter } from './commandFilter'
import { createDoc, createGoal, deleteDoc } from './api'
import { loadInbox, wordsToGoal } from './inbox'
import { encodePictures } from './reportImages'
import { clearPictures, pictures } from './reportPictures'
import { isoDate } from './schedule'
import { messageForError } from './scheduleFeedback'
import { toast } from '@konstantinopolskii/vue'

/** Reports are documents in this folder: that is how the app knows one when it is in front (lib/reportActions.ts). */
export const REPORT_FOLDER = 'reports/bugs'
export const isReportPath = (path: string | null | undefined): boolean => !!path && path.startsWith(`${REPORT_FOLDER}/`)

/** What the gateway knows of the app (desktop/chat/report_facts.py): the version, the Mac and the cleaned tails of the logs. */
export interface ReportFacts {
  version: string
  system: string
  appLog: string[]
  appLeftOut: number
  agentLog: string[]
  agentLeftOut: number
}

/** The facts, or none: the web build has no gateway, and a report is still worth making without its logs. */
export async function readFacts(): Promise<ReportFacts | null> {
  try {
    const res = await fetch('/__report/facts')
    if (!res.ok) return null
    const facts = await res.json() as Partial<ReportFacts>
    return typeof facts.version === 'string' && Array.isArray(facts.appLog) && Array.isArray(facts.agentLog) ? facts as ReportFacts : null
  } catch {
    return null
  }
}

const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`

/** A log under its heading, as the document draws it: one inline-code line each (a document has no code block), then how
 *  many entries the app left out, if any. */
function logSection(heading: string, lines: string[], leftOut: number): string {
  if (!lines.length && !leftOut) return ''
  const shown = lines.map((line) => `\`${line.replace(/`/g, "'")}\``)
  return [`## ${heading}`, ...shown, leftOut ? `${plural(leftOut, 'entry', 'entries')} left out.` : ''].filter(Boolean).join('\n')
}

/** The report as a document's text: their words first, then the pictures, the version, the logs. A picture is a data URL in
 *  the text, as a screenshot pasted into a document is (lib/bodyMarkdown.ts). */
export function reportBody(words: string, sources: string[], facts: ReportFacts | null): string {
  const parts = [words.trim()]
  if (sources.length) parts.push(sources.map((src, index) => `![Picture ${index + 1}](${src})`).join('\n'))
  if (facts) {
    parts.push(`Verticals ${facts.version}, ${facts.system}`)
    parts.push(logSection('App log', facts.appLog, facts.appLeftOut), logSection('Agent log', facts.agentLog, facts.agentLeftOut))
  }
  return parts.filter(Boolean).join('\n\n')
}

/** "Report — 12 October 2026, 14:05": what it is, and when, as the morning report is named. */
export function reportTitle(at: Date): string {
  const day = at.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
  const time = at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })
  return `Report — ${day}, ${time}`
}
const reportPath = (at: Date): string => {
  const two = (n: number) => String(n).padStart(2, '0')
  return `${REPORT_FOLDER}/${isoDate(at)}-${two(at.getHours())}${two(at.getMinutes())}${two(at.getSeconds())}.md`
}

const noBrackets = (text: string): string => text.replace(/[[\]]/g, '')

/** What the field says once the report is made: how many pictures are in it, and the two chips. */
function answer(docTitle: string, docId: string, taskTitle: string, taskId: string, put: number, left: number): string {
  const said = put ? `Report made with ${plural(put, 'picture')}.` : 'Report made.'
  const missed = left ? ` ${left} did not fit in a document.` : ''
  return `${said}${missed}\n\n[${noBrackets(docTitle)}](#doc/${docId})\n[${noBrackets(taskTitle)}](#goal/${taskId})`
}

/** The person said what happened: the report and its task come at once, or neither does. */
export async function makeReport(words: string): Promise<void> {
  const said = words.trim()
  if (!said || !pictures.list.length || pictures.sending) return
  const files = pictures.list.map((picture) => picture.file)
  pictures.sending = true
  try {
    const [facts, encoded] = await Promise.all([readFacts(), encodePictures(files)])
    const at = new Date()
    const title = reportTitle(at)
    const path = reportPath(at)
    const doc = await createDoc({ path, title, body: reportBody(said, encoded.sources, facts) })
    const task = wordsToGoal(said)
    let goal
    try {
      goal = await createGoal({ title: task.title, body: `[${noBrackets(title)}](doc:${path})` })
    } catch (error) {
      // The task did not come: the report is not left on its own.
      await deleteDoc(doc.id).catch(() => undefined)
      throw error
    }
    clearPictures()
    commandFilter.text = ''
    // The answer lands in the field, as an agent's does: with the conversation open, or the keys still in the field, it would
    // have no place to land (the field is the open one while it has them).
    agentChat.open = false
    ;(document.activeElement as HTMLElement | null)?.blur()
    agentChat.answer = { text: answer(title, doc.id, goal.title, goal.id, encoded.sources.length, encoded.left), at: Date.now() }
    await loadInbox()
  } catch (error) {
    // The pictures and the words stay where they are, and another press tries again.
    commandFilter.text = said
    toast(`The report was not made. ${messageForError(error)}`, { action: 'Try again', onAction: () => void makeReport(said) })
  } finally {
    pictures.sending = false
  }
}
