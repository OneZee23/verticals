// The goal that flies from one column to another takes the look of the card it becomes on the way (docs/design/board-undo.md).
// A card in the open column is bigger than one in a closed column, and not by one factor: its text, its checkbox, the gap
// between them and its padding are each set by their own value. So the card is not one rectangle that scales. Each part of
// the copy that paints something (the text, the checkbox, an icon, a chip) goes from where it stands to where its own
// counterpart in the real card stands, in one transform, and the card behind them goes from its box to the real card's box
// the same way. All of them take the flight's own time and curve, so at the end the copy sits exactly on the real card and
// can give way to it in one frame, and no frame draws two titles.
//
// The parts are matched by their place in the two cards (the same component draws both). When they are not the same card
// (one is being edited, a title stands on another number of lines) nothing can be matched and the copy only travels.

/** One part of the copy and the transform that takes it onto its counterpart. */
export interface Leg {
  el: Element
  /** Where the part turns and grows from: its text's first corner, or its own corner. */
  origin: string
  end: string
  /** For a part that is a box with rounded corners: the radius that renders as the real card's once it has grown. */
  radius?: string
}

/** Where a part stands now (`x0`, `y0`), where it will stand (`x1`, `y1`), and by how much it grows: a point `p` of the part
 *  goes to `(x1, y1) + scale * (p - (x0, y0))`. A part without a mapping of its own is carried by its parent's. */
interface Place {
  sx: number
  sy: number
  x0: number
  y0: number
  x1: number
  y1: number
}

const MIN = 0.5
const empty = (box: DOMRect): boolean => box.width < MIN || box.height < MIN

/** Whether the element has words of its own (text directly in it, not in a part inside it). */
function hasText(el: Element): boolean {
  return [...el.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && !!node.textContent?.trim())
}

/** The box the words take, not the element's: a box in a column of another width is another shape, the words are not. */
function wordsRange(el: Element): Range {
  const range = document.createRange()
  range.selectNodeContents(el)
  return range
}

const lineCount = (el: Element): number => new Set([...wordsRange(el).getClientRects()].map((rect) => Math.round(rect.top))).size

/** Whether the element paints something that has to travel by itself: words, a leaf (a box, an icon) or a surface. A part
 *  of an icon goes with the icon. A wrapper paints nothing and goes with what it holds. */
function paints(el: Element): boolean {
  if (el.parentElement?.closest('svg')) return false
  const style = getComputedStyle(el)
  if (style.display === 'none') return false
  if (!el.children.length || el.tagName === 'svg' || hasText(el)) return true
  const fill = style.backgroundColor
  return (fill !== 'rgba(0, 0, 0, 0)' && fill !== 'transparent') || style.backgroundImage !== 'none' || style.boxShadow !== 'none'
}

const fontSize = (el: Element): number => Number.parseFloat(getComputedStyle(el).fontSize)

/** The corner radius in pixels when it is one, else `null` (a percentage, a mix). */
function radiusOf(el: Element): number | null {
  const value = getComputedStyle(el).borderTopLeftRadius
  return value.endsWith('px') ? Number.parseFloat(value) : null
}

/** The legs for `copy`, standing where the card stood (`from`), to take it onto `card`, where it now stands (`to`); the
 *  first leg is the copy itself. `null` when the two are not the same card. The copy must be in the page and not yet moving. */
export function legsOf(copy: HTMLElement, from: DOMRect, card: HTMLElement, to: DOMRect): Leg[] | null {
  if (empty(from) || empty(to)) return null
  const mine = [copy, ...copy.querySelectorAll('*')]
  const theirs = [card, ...card.querySelectorAll('*')]
  if (mine.length !== theirs.length || mine.some((el, at) => el.tagName !== theirs[at]!.tagName)) return null

  // A part can only be transformed when it is a box: a word that runs in a line turns into one where it stands.
  for (const el of mine) {
    if (el instanceof HTMLElement && !el.children.length && getComputedStyle(el).display === 'inline') el.style.display = 'inline-block'
  }

  const root: Place = { sx: to.width / from.width, sy: to.height / from.height, x0: from.left, y0: from.top, x1: to.left, y1: to.top }
  const legs: Leg[] = [{ el: copy, origin: '0 0', end: `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${root.sx}, ${root.sy})` }]
  const index = new Map<Element, number>(mine.map((el, at) => [el, at]))
  const places: Place[] = [root]

  for (let at = 1; at < mine.length; at += 1) {
    const el = mine[at]!
    const other = theirs[at]!
    const parent = places[index.get(el.parentElement!)!]!
    places[at] = parent
    if (!paints(el)) continue

    const words = hasText(el)
    if (words && lineCount(el) !== lineCount(other)) return null
    const now = words ? wordsRange(el).getBoundingClientRect() : el.getBoundingClientRect()
    const then = words ? wordsRange(other).getBoundingClientRect() : other.getBoundingClientRect()
    if (empty(now) || empty(then)) continue
    // Words grow with their type (the box they stand in is another shape); a box grows to the box it becomes.
    const size = fontSize(other) / fontSize(el)
    const sx = words ? size : then.width / now.width
    const sy = words ? size : then.height / now.height

    // Where the part has to stand before its parent's own movement carries it to where it goes.
    const x = parent.x0 + (then.left - parent.x1) / parent.sx
    const y = parent.y0 + (then.top - parent.y1) / parent.sy
    const own = el.getBoundingClientRect()
    const leg: Leg = {
      el,
      origin: `${now.left - own.left}px ${now.top - own.top}px`,
      end: `translate(${x - now.left}px, ${y - now.top}px) scale(${sx / parent.sx}, ${sy / parent.sy})`,
    }
    const before = radiusOf(el)
    const after = radiusOf(other)
    if (!words && before !== null && after !== null && before !== after) leg.radius = `${after / ((sx + sy) / 2)}px`
    legs.push(leg)
    places[at] = { sx, sy, x0: now.left, y0: now.top, x1: then.left, y1: then.top }
  }
  return legs
}
