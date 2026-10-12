/* Which form of a column's name fits its room (docs/design/column-names.md): a name is never cut with "…". Each period
   gives its forms from the longest to the shortest (`lib/columnNames.ts`), and a header shows the first whose width, in
   the font its title is set in, is within the title's room.

   The room is the layout width of the title's row. A column that opens or closes is laid out at its final width at once
   and only drawn on its way there (`lib/familyMotion.ts`), and its header keeps that width through the move (`widen`), so
   the header reads its final room in the frame the layout changes, before anything is drawn, and chooses its words
   there, once: they never change in the middle of a movement, and no frame shows a form that doesn't fit. The header
   decides again when the layout changes (a window resized, a column opened or closed) and when the title font arrives.
   The shortest form of a name, which is shown whether it fits or not, may take a few px of the padding beside the room
   before the ellipsis shows (`--column-spill` in `ColumnHeader.tsx`); the fit itself never counts on them.

   A canvas measures the text: it shapes it as the layout does, to within a 64th of a pixel (1111 labels compared in
   Chrome: at most 0.016 px narrower), without writing a probe into the page for every form of every column. */

import { ref } from '../reactivity'

/** Counts the font loads: a width measured before a font arrived was another font's. */
export const fontEpoch = ref(0)

/** A 64th of a pixel, the layout's own unit, which the canvas's width may fall short of the layout's by. */
const SLACK = 1 / 64

const widths = new Map<string, number>()
let context: CanvasRenderingContext2D | null | undefined

if (typeof document !== 'undefined' && document.fonts) {
  document.fonts.addEventListener('loadingdone', () => {
    widths.clear()
    fontEpoch.value += 1
  })
}

/** The font `el` is set in, written the way a canvas takes it. */
export function fontOf(el: Element): string {
  const look = getComputedStyle(el)
  return `${look.fontStyle} ${look.fontWeight} ${look.fontSize} ${look.fontFamily}`
}

/** The width of `text` in `font`, in px. */
export function widthOf(text: string, font: string): number {
  const key = `${font}\n${text}`
  let width = widths.get(key)
  if (width === undefined) {
    context ??= document.createElement('canvas').getContext('2d')
    if (!context) return 0 // no canvas: the first form stands, and the ellipsis stays the last resort
    context.font = font
    width = context.measureText(text).width
    widths.set(key, width)
  }
  return width
}

/** The index of the first of `names`, longest first, that fits `room` px in `font`; the last, the shortest, when none does. */
export function fittest(names: readonly string[], room: number, font: string): number {
  for (let i = 0; i < names.length - 1; i += 1) if (widthOf(names[i], font) + SLACK <= room) return i
  return names.length - 1
}
