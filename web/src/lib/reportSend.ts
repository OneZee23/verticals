// Send to developers (docs/design/bug-reports.md): the report as a link that opens a new GitHub issue in the browser, filled in
// with exactly what goes, for the person to read and submit themselves; or, with ⌥ held, as an email draft that does the same.
// What goes is the report's own text as it stands in its document, so a line the person took out of the document stays out.
// Nothing from the board goes but that text: the link is built here from the document and from nothing else.
//
// A bug reads as a bug and a request as a request: the issue link carries the repository's own label for each (`bug` and
// `enhancement`, GitHub's defaults, which the repository has), and the text itself differs by what the kind carries, the logs
// for a bug and none for a request. GitHub applies a label from a link only for someone who may label, and ignores it for
// anyone else, whose issue then waits for the maintainers to label it; the title is never changed.
//
// A link cannot carry pictures, so the issue ends with a line saying how many there were and to drag them into the box
// (the person still has them where they took them), and the document keeps them.
//
// A link has a length limit, which GitHub does not publish: its answer to a longer one is "414 URI Too Long", and reports of
// it start at about 8,000 characters. So a link is kept to `LINK_BUDGET`. When the report is longer, the oldest lines of the logs
// go first (the longer log first, so each keeps its newest lines), and the issue says how many; only when the logs are gone and
// the words alone are too long are the words cut, at a word, and the issue says so. The document is never changed by this.
import type { ReportKind } from './agentChat'

/** The new-issue page of Verticals' public repository. */
export const ISSUES_URL = 'https://github.com/konstantinopolskii/verticals/issues/new'
/** The repository's labels for each kind of report (`gh label list`: "Something isn't working", "New feature or request"). */
export const LABELS: Record<ReportKind, string> = { bug: 'bug', request: 'enhancement' }
/** Where the email draft goes. Empty: the draft opens without a recipient, for the person to address. Verticals' repository
 *  publishes no address; whoever ships a build that has one sets it here. */
export const DEVELOPERS_EMAIL = ''
/** The longest link this makes, in characters, ahead of the 8,000 or so at which GitHub starts to refuse. */
export const LINK_BUDGET = 6000
/** The longest title of an issue: a task's title can run to 250 characters, and the link has to carry it twice over. */
const TITLE_CHARS = 120

/** A picture of the report in the document: a line of its own, a data URL in it. */
const PICTURE_LINE = /^!\[[^\]]*\]\(data:image\/[a-z+.-]+;base64,[^)]*\)\s*$/
const LOG_HEADING = /^## .+ log$/
const LOG_LINE = /^`.*`$/

export interface Letter {
  kind: ReportKind
  title: string
  /** The report's text without its pictures, line by line. */
  lines: string[]
  /** How many pictures the document holds, which the link cannot. */
  pictures: number
  /** Older log lines left out to fit the link. */
  cut: number
  /** The words were cut short to fit. */
  shortened: boolean
}

const plural = (n: number, one: string, many = `${one}s`): string => (n === 1 ? one : many)

/** A title that fits a link: one line, a word boundary and an ellipsis when it is cut. */
export function issueTitle(title: string): string {
  const line = title.replace(/\s+/g, ' ').trim()
  if (line.length <= TITLE_CHARS) return line
  const cut = line.slice(0, TITLE_CHARS - 1)
  const at = cut.lastIndexOf(' ')
  return `${(at > 60 ? cut.slice(0, at) : cut).trimEnd()}…`
}

/** What goes: the document's text, its pictures counted and taken out. */
export function letterOf(kind: ReportKind, title: string, body: string): Letter {
  const all = body.replace(/\r\n?/g, '\n').split('\n')
  const lines = all.filter((line) => !PICTURE_LINE.test(line.trim()))
  return { kind, title: issueTitle(title), lines, pictures: all.length - lines.length, cut: 0, shortened: false }
}

/** The text of the issue or the email: the report, then what was left out of it. */
export function textOf(letter: Letter): string {
  const parts = [letter.lines.join('\n').replace(/\n{3,}/g, '\n\n').trim()]
  if (letter.shortened) parts.push('The words were cut short to fit this link.')
  if (letter.cut) parts.push(`${letter.cut} older log ${plural(letter.cut, 'line')} left out to fit this link.`)
  if (letter.pictures) {
    parts.push(`${letter.pictures} ${plural(letter.pictures, 'picture')}: drag ${letter.pictures === 1 ? 'it' : 'them'} into this box before you submit.`)
  }
  return parts.join('\n\n')
}

export function issueLink(letter: Letter): string {
  return `${ISSUES_URL}?${new URLSearchParams({ title: letter.title, body: textOf(letter), labels: LABELS[letter.kind] })}`
}
export function mailLink(letter: Letter): string {
  return `mailto:${DEVELOPERS_EMAIL}?subject=${encodeURIComponent(letter.title)}&body=${encodeURIComponent(textOf(letter))}`
}

/** The lines of each log in the text (inline-code lines under a "… log" heading), as indices into `lines`, oldest first. */
function logRuns(lines: string[]): number[][] {
  const runs: number[][] = []
  let current: number[] | null = null
  lines.forEach((line, index) => {
    if (LOG_HEADING.test(line)) {
      current = []
      runs.push(current)
    } else if (current && LOG_LINE.test(line)) {
      current.push(index)
    } else if (line.trim() && !/ left out\.$/.test(line)) {
      current = null
    }
  })
  return runs
}

/** The text without a log whose lines have all gone: its heading and the line that says how many entries were left out. */
function withoutEmptyLogs(lines: string[]): string[] {
  const gone = new Set<number>()
  lines.forEach((line, index) => {
    if (!LOG_HEADING.test(line)) return
    let end = index + 1
    while (end < lines.length && !lines[end]!.trim()) end += 1
    if (LOG_LINE.test(lines[end] ?? '')) return
    gone.add(index)
    if (/ left out\.$/.test(lines[end] ?? '')) gone.add(end)
  })
  return lines.filter((_, index) => !gone.has(index))
}

/** The letter cut to a link of at most `budget` characters, built by `link`. */
export function fit(letter: Letter, link: (letter: Letter) => string, budget = LINK_BUDGET): Letter {
  let current = { ...letter, lines: [...letter.lines] }
  while (link(current).length > budget) {
    const runs = logRuns(current.lines).filter((run) => run.length)
    if (!runs.length) break
    const longest = runs.reduce((a, b) => (b.length > a.length ? b : a))
    current.lines.splice(longest[0]!, 1)
    current.cut += 1
  }
  // The logs are gone (their headings with them) and the words alone are too long: the words are cut at a word.
  if (link(current).length > budget) {
    current = { ...current, lines: withoutEmptyLogs(current.lines), shortened: true }
    let words = current.lines.join('\n')
    while (link({ ...current, lines: [words] }).length > budget && words.length > 40) {
      const cut = words.slice(0, Math.floor(words.length * 0.9))
      const at = cut.lastIndexOf(' ')
      words = `${(at > cut.length * 0.6 ? cut.slice(0, at) : cut).trimEnd()}…`
    }
    current.lines = [words]
  }
  return current
}

/** Both links for a report's document: the issue and the email draft, each as long as its limit allows. */
export function sendLinks(kind: ReportKind, title: string, body: string): { issue: string; mail: string; letter: Letter } {
  const letter = letterOf(kind, title, body)
  const forIssue = fit(letter, issueLink)
  const forMail = fit(letter, mailLink)
  return { issue: issueLink(forIssue), mail: mailLink(forMail), letter: forIssue }
}
