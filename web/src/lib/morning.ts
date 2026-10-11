// The morning report (Inbox and Documents redesign, round 8; KK 7 Oct 2026: "Morning report should be agent based since it
// additionally should check integrations that user has"). At 07:00 by your clock, or when the app opens if it was closed
// then, the app asks the agent for the day's report once, in a conversation of its own; the server decides which ask is
// the day's one (POST /api/morning), so no second window or cleared cache asks again. In the desktop app that one turn
// also reaches your own connected tools, read-only (desktop/chat/prompt-morning.md). The agent writes the report as one
// document and links it to its task, the one open "Morning report" task, which the server has made or moved to today
// (core/morning.py), then answers in two lines with the document linked; the answer
// stands in the field with the report's page (SearchBar.vue). No rule writes a report: without an agent there is none.
import { beginMorning } from './api'
import { agentChat, newThread, send } from './agentChat'
import { commandFilter } from './commandFilter'

/** The hour the report is asked for (KK's round 2 call "rule time": 07:00 until he names another). */
export const MORNING_HOUR = 7
export const MORNING_TITLE = 'Morning report'
export const MORNING_FOLDER = 'reports/morning'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
/** "7 October 2026", the report's title day. */
export function longDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[(m ?? 1) - 1]} ${y}`
}

export function morningAsk(today: string, taskId: string): string {
  return `Make my morning report for ${today}, following the morning report guide in your instructions. Save it as the `
    + `document ${MORNING_FOLDER}/${today}.md titled "${MORNING_TITLE} — ${longDay(today)}" and link it to its task, `
    + `"${MORNING_TITLE}" (id ${taskId}), which is in Day for today already. Then answer in two short lines and link the `
    + `document.`
}

/** Why the app may ask now: an agent is there and you are not busy with it. */
const free = () => agentChat.available && !agentChat.running && !agentChat.open && !commandFilter.text

function ask(today: string, taskId: string): void {
  newThread()
  void send(morningAsk(today, taskId), { morning: true }, { sources: 'connected' })
}

let looking = false
/** A day the server gave us that was not asked at once because you were busy by the time it answered. */
let owed: { day: string; task: string } | null = null

/** Asked on start and every few minutes: once the hour has come and an agent is there, the day's report is asked for
 *  once. The server decides which ask is the day's one (POST /api/morning), not a flag in this browser, so a second
 *  window, a restart or a cleared cache never asks again; it also makes or moves the one open "Morning report" task to
 *  today, and the ask names it (docs/design/agent-fixes.md, fixes 3 and 2). Not while you talk with the agent or type:
 *  then it waits for the next look. */
export async function ensureMorning(today: string, now: Date = new Date()): Promise<boolean> {
  if (now.getHours() < MORNING_HOUR || !free() || looking) return false
  if (owed && owed.day === today) {
    const { task } = owed
    owed = null
    ask(today, task)
    return true
  }
  owed = null
  looking = true
  try {
    const { asked, task_id: task } = await beginMorning(today)
    if (!asked || !task) return false
    // The day is ours now; if you began to talk while the server answered, it waits for the next look.
    if (!free()) { owed = { day: today, task }; return false }
    ask(today, task)
    return true
  } catch {
    return false
  } finally {
    looking = false
  }
}
