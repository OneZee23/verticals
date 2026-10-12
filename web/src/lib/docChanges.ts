// What an agent rewrote in a document (docs/design/doc-comments-inline.md, "Check again"): the words the new text has and
// the old text had not, lit green in the open document until its owner writes in it. The app can tell because
// `core/docs.py` keeps every revision of a document, append-only, and `fetchDocRevision` reads one back: the copy from
// before the agent's turn and the copy after it are both rendered the way the page renders a body, and compared block by
// block (a paragraph, a list item, a cell, a heading); the blocks that differ are compared word by word. Only what the
// new text has is lit. A passage the agent cut leaves nothing to light.
import { reactive } from 'vue'
import { renderBodyElement } from './bodyMarkdown'
import { wrapRange, type FlatTextNode } from './commentAnchor'

export const REWRITTEN_CLASS = 'doc-rewritten'

/** The text each open document had before an agent's turn, by the document's id: its words are lit while this stands. */
export const rewritten = reactive<Record<string, { before: string }>>({})

/** A run of unchanged words this short between two changed ones is lit with them: one rewritten phrase, not confetti. */
const GAP = 2
/** The most cells of a comparison table: past it a changed passage is lit whole, rather than compared. */
const MAX_CELLS = 9_000_000

const BLOCKS = 'p, li, h1, h2, h3, h4, h5, h6, td, th, blockquote, pre'
const WORD = /[\p{L}\p{N}]+(?:['’][\p{L}\p{N}]+)*|[^\s\p{L}\p{N}]/gu

interface Block {
  text: string
  nodes: FlatTextNode[]
}
interface Word {
  text: string
  block: number
  start: number
  end: number
}
export interface Range {
  block: number
  start: number
  end: number
}

/** The text of a rendered body, one entry per block in reading order: the text nodes whose nearest block is the same
 *  element, with their places in the block's text. */
function blocksOf(root: HTMLElement): Block[] {
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const byBlock = new Map<Element, Block>()
  const out: Block[] = []
  for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
    const text = node.nodeValue ?? ''
    if (!text) continue
    const home = node.parentElement?.closest(BLOCKS) ?? root
    let block = byBlock.get(home)
    if (!block) {
      block = { text: '', nodes: [] }
      byBlock.set(home, block)
      out.push(block)
    }
    block.nodes.push({ node, start: block.text.length, end: block.text.length + text.length })
    block.text += text
  }
  return out
}

/** The index pairs of a longest common subsequence of `a` and `b`, or null when they are too long to compare. */
function common(a: string[], b: string[]): Array<[number, number]> | null {
  let head = 0
  while (head < a.length && head < b.length && a[head] === b[head]) head++
  let tail = 0
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++
  const pairs: Array<[number, number]> = []
  for (let i = 0; i < head; i++) pairs.push([i, i])
  const n = a.length - head - tail
  const m = b.length - head - tail
  if (n > 0 && m > 0) {
    if (n * m > MAX_CELLS) return null
    const cols = m + 1
    // The length of the longest common run of a[head + i ..] and b[head + j ..]; neither side is longer than 3000 here,
    // since the table stays under MAX_CELLS, so a run always fits in 16 bits.
    const table = new Uint16Array((n + 1) * cols)
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        table[i * cols + j] = a[head + i] === b[head + j]
          ? table[(i + 1) * cols + j + 1]! + 1
          : Math.max(table[(i + 1) * cols + j]!, table[i * cols + j + 1]!)
      }
    }
    let i = 0
    let j = 0
    while (i < n && j < m) {
      if (a[head + i] === b[head + j]) {
        pairs.push([head + i, head + j])
        i++
        j++
      } else if (table[(i + 1) * cols + j]! >= table[i * cols + j + 1]!) {
        i++
      } else {
        j++
      }
    }
  }
  for (let k = 0; k < tail; k++) pairs.push([a.length - tail + k, b.length - tail + k])
  return pairs
}

function wordsIn(texts: string[], from: number, to: number): Word[] {
  const out: Word[] = []
  for (let block = from; block < to; block++) {
    for (const match of texts[block]!.matchAll(WORD)) {
      const start = match.index ?? 0
      out.push({ text: match[0], block, start, end: start + match[0].length })
    }
  }
  return out
}

/** A short run of unchanged words between two changed ones in the same block is lit with them. */
function smooth(words: Word[], changed: boolean[]): void {
  let k = 0
  while (k < words.length) {
    if (changed[k]) {
      k++
      continue
    }
    let end = k
    while (end < words.length && !changed[end]) end++
    const same = k > 0 && end < words.length && words[k - 1]!.block === words[end]!.block
      && words[k]!.block === words[k - 1]!.block && words[end - 1]!.block === words[end]!.block
    if (same && end - k <= GAP) for (let x = k; x < end; x++) changed[x] = true
    k = end
  }
}

/** The places in the new text's blocks that the old text did not have: whole blocks that were not there, and the words
 *  of a block that was not the same, each place a run of words in one block. */
export function changedRanges(before: string[], after: string[]): Range[] {
  const blocks = common(before, after) ?? []
  const ranges: Range[] = []
  const group = (i0: number, i1: number, j0: number, j1: number): void => {
    if (j0 >= j1) return
    const now = wordsIn(after, j0, j1)
    const was = i0 < i1 ? wordsIn(before, i0, i1) : []
    const pairs = was.length && now.length ? common(was.map((w) => w.text), now.map((w) => w.text)) : []
    const kept = new Set((pairs ?? []).map(([, k]) => k))
    const changed = now.map((_, k) => !kept.has(k))
    smooth(now, changed)
    for (let k = 0; k < now.length; k++) {
      if (!changed[k]) continue
      const word = now[k]!
      const last = ranges[ranges.length - 1]
      if (last && last.block === word.block && k > 0 && changed[k - 1] && now[k - 1]!.block === word.block) last.end = word.end
      else ranges.push({ block: word.block, start: word.start, end: word.end })
    }
  }
  let i = 0
  let j = 0
  for (const [pi, pj] of blocks) {
    group(i, pi, j, pj)
    i = pi + 1
    j = pj + 1
  }
  group(i, before.length, j, after.length)
  return ranges
}

/** Takes the light off: the marks come out and the text stays. */
export function clearRewritten(container: HTMLElement): void {
  for (const mark of Array.from(container.querySelectorAll<HTMLElement>(`mark.${REWRITTEN_CLASS}`))) {
    const parent = mark.parentNode
    if (!parent) continue
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark)
    parent.removeChild(mark)
  }
  container.normalize()
}

/** Lights the words of the document drawn in `container` that its text from before (`before`, markdown) did not have. */
export function lightRewritten(container: HTMLElement, before: string): void {
  clearRewritten(container)
  const probe = container.ownerDocument.createElement('div')
  renderBodyElement(probe, before)
  const now = blocksOf(container)
  const ranges = changedRanges(blocksOf(probe).map((block) => block.text), now.map((block) => block.text))
  // Last place first in each block: a split shortens the node to the part before it (commentAnchor.ts::wrapRange).
  for (const range of ranges.reverse()) {
    wrapRange(now[range.block]!.nodes, range.start, range.end, () => {
      const mark = container.ownerDocument.createElement('mark')
      mark.className = REWRITTEN_CLASS
      return mark
    })
  }
}
