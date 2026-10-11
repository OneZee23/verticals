// Where a document's comment stands for the words it is about (docs/design/doc-comments-inline.md): right under them, from
// their first letter, or right over them where the text ends and nothing fits below; and how far the document scrolls to
// bring both into view. `popover.ts` places a menu around its trigger in a room that stays still; this card stands in a
// room that scrolls, so the scroll is part of its place. Pure, like `popover.ts`: every rectangle is the viewport's.
import type { PopoverRect, PopoverSize } from './popover'

/** Air between the words and the card. */
export const CARD_GAP = 6
/** What the card keeps from the edges of the room it may stand in. */
const EDGE = 8
/** Where the words go in the visible text when the document has to go to them: this share of its height from the top. */
const SHARE = 0.3
/** The card's own padding, so the words and the card's first line start on one edge. */
const INSET = 12
/** The least height a card keeps when the room is short: its thread scrolls inside. */
const LEAST = 120

export interface Placed {
  /** The card's top-left corner, in the viewport once the document has scrolled by `scroll`. */
  x: number
  y: number
  /** How far the document scrolls (down is positive) to bring the words and their card into view; 0 when they are. */
  scroll: number
  side: 'top' | 'bottom'
  /** The card's height: its own, or the room there is when that is less. */
  height: number
}

/** `anchor` is the words (their first line's left edge, their whole height); `visible` is where text can be read (the
 *  scroller less the white foot the field stands on); `range` is how far the document can still scroll each way. */
export function placeOverWords(
  anchor: PopoverRect, card: PopoverSize, visible: PopoverRect, range: { min: number; max: number },
): Placed {
  const clamp = (by: number): number => Math.max(range.min, Math.min(range.max, by))
  const top = visible.y + EDGE
  const bottom = visible.y + visible.height - EDGE
  let scroll = 0
  // Out of the visible text, the words go to a third of the way down it.
  if (anchor.y < top || anchor.y + anchor.height > bottom) scroll = clamp(anchor.y - (visible.y + visible.height * SHARE))
  let y = anchor.y - scroll
  let below = bottom - (y + anchor.height + CARD_GAP)
  const above = y - CARD_GAP - top
  let height = card.height
  let side: 'top' | 'bottom' = 'bottom'
  if (height > below && height <= above) {
    side = 'top'
  } else if (height > below) {
    // Neither side holds it: the document goes on until the words are as high as they may be, then the thread scrolls inside.
    const more = clamp(scroll + Math.min(height - below, Math.max(0, y - top))) - scroll
    scroll += more
    y -= more
    below += more
    height = Math.min(height, Math.max(below, LEAST))
  }
  const x = Math.max(visible.x + EDGE, Math.min(anchor.x - INSET, visible.x + visible.width - card.width - EDGE))
  return {
    x, y: side === 'bottom' ? y + anchor.height + CARD_GAP : y - CARD_GAP - height, scroll, side, height,
  }
}
