// A report from pictures (docs/design/bug-reports.md): something is wrong, or could be better. The person drops pictures on the
// window, says what they see and what they want in the field and presses ↵. The report comes first, as a document with their
// words, the pictures and the app's version; its task is made with it, so the report is the task's first document, and the
// answer shows both as chips (docs/design/agent-chips.md). Then, if asked: Send to developers and Improve it (lib/reportActions.ts).
//
// The words say which kind it is, and the agent tells (desktop/chat/report_kind.py), so there is nothing to pick before sending.
// Something that went wrong, a bug, also carries the last lines of the app's and the agent's logs; something that could be
// better, a request, carries none. When the agent cannot tell, is slow or is not there, it is a request: that shape loses nothing.
// The agent gets the words and nothing else. Pictures of that size are not for a model to carry through a tool call, and what the
// logs may say is decided in code, not by a model (desktop/chat/report_facts.py).
import { agentChat, reportKind, type ReportKind } from './agentChat'
import { commandFilter } from './commandFilter'
import { createDoc, createGoal, deleteDoc } from './api'
import { loadInbox, wordsToGoal } from './inbox'
import { encodePictures } from './reportImages'
import { clearPictures, pictures } from './reportPictures'
import { isoDate } from './schedule'
import { messageForError } from './scheduleFeedback'
import { toast } from '@konstantinopolskii/vue'

export type { ReportKind }

/** Reports are documents in these folders, by kind: that is how the app knows one when it is in front, and which kind it is
 *  (lib/reportActions.ts). */
export const REPORT_FOLDERS: Record<ReportKind, string> = { bug: 'reports/bugs', request: 'reports/requests' }
export function reportKindOf(path: string | null | undefined): ReportKind | null {
  if (!path) return null
  return (Object.keys(REPORT_FOLDERS) as ReportKind[]).find((kind) => path.startsWith(`${REPORT_FOLDERS[kind]}/`)) ?? null
}
export const isReportPath = (path: string | null | undefined): boolean => reportKindOf(path) !== null

/** What the gateway knows of the app (desktop/chat/report_facts.py): the version, the Mac and the cleaned tails of the logs. */
export interface ReportFacts {
  version: string
  system: string
  appLog: string[]
  appLeftOut: number
  agentLog: string[]
  agentLeftOut: number
}

/** The facts, or none: the web build has no gateway, and a report is still worth making without them. Without `logs` (a
 *  request has none) the gateway opens no log. */
export async function readFacts(logs: boolean): Promise<ReportFacts | null> {
  try {
    const res = await fetch(`/__report/facts${logs ? '' : '?logs=0'}`)
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

/** The report as a document's text: their words first, then the pictures, the version, and the logs when there are any (a
 *  request is made without). A picture is a data URL in the text, as a screenshot pasted into a document is
 *  (lib/bodyMarkdown.ts). */
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
const reportPath = (at: Date, kind: ReportKind): string => {
  const two = (n: number) => String(n).padStart(2, '0')
  return `${REPORT_FOLDERS[kind]}/${isoDate(at)}-${two(at.getHours())}${two(at.getMinutes())}${two(at.getSeconds())}.md`
}

const noBrackets = (text: string): string => text.replace(/[[\]]/g, '')

/** What the field says once the report is made: what is in it (the pictures, and the log lines when there are any), and the
 *  two chips. */
function answer(docTitle: string, docId: string, taskTitle: string, taskId: string, put: number, left: number, logs: boolean): string {
  const held = [put ? plural(put, 'picture') : '', logs ? 'the last log lines' : ''].filter(Boolean)
  const said = held.length ? `Report made with ${held.join(' and ')}.` : 'Report made.'
  const missed = left ? ` ${left} did not fit in a document.` : ''
  return `${said}${missed}\n\n[${noBrackets(docTitle)}](#doc/${docId})\n[${noBrackets(taskTitle)}](#goal/${taskId})`
}

/** The person said what they see and what they want: the report and its task come at once, or neither does. */
export async function makeReport(words: string): Promise<void> {
  const said = words.trim()
  if (!said || !pictures.list.length || pictures.sending) return
  const files = pictures.list.map((picture) => picture.file)
  pictures.sending = true
  try {
    // The agent tells the kind while the pictures are drawn smaller; a bug has the logs asked for, a request does not.
    const [kind, encoded] = await Promise.all([reportKind(said), encodePictures(files)])
    const facts = await readFacts(kind === 'bug')
    const at = new Date()
    const title = reportTitle(at)
    const path = reportPath(at, kind)
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
    // The field is empty already (↵ took the words); it holds them only when a failed report is tried again. Words typed
    // since are the person's next ones and stay.
    if (commandFilter.text.trim() === said) commandFilter.text = ''
    // The answer lands in the field, as an agent's does: with the conversation open, or the keys still in the field, it would
    // have no place to land (the field is the open one while it has them).
    agentChat.open = false
    ;(document.activeElement as HTMLElement | null)?.blur()
    const logs = !!facts && facts.appLog.length + facts.agentLog.length > 0
    agentChat.answer = { text: answer(title, doc.id, goal.title, goal.id, encoded.sources.length, encoded.left, logs), at: Date.now() }
    await loadInbox()
  } catch (error) {
    // The pictures and the words stay where they are, and another press tries again.
    commandFilter.text = said
    toast(`The report was not made. ${messageForError(error)}`, { action: 'Try again', onAction: () => void makeReport(said) })
  } finally {
    pictures.sending = false
  }
}
