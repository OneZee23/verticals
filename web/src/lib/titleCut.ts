// A goal's title cut to fit the line that names it (docs/design/board-undo.md). The browser's own ellipsis
// (`text-overflow`) cuts at a pixel: when the cut lands after a space it leaves “the …” with a gap before the dots and one
// after them. This cuts the text itself, so the “…” stands right after the last letter that shows.

const segmenter = typeof Intl !== 'undefined' && 'Segmenter' in Intl ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }) : null

/** The characters a person sees as one: a letter with its accent, an emoji with its skin tone. */
export function glyphs(text: string): string[] {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text)
}

/** `text` cut to its first `keep` characters with “…” right after the last one that shows (never after a space); the text
 *  itself when `keep` takes all of it. */
export function cutTitle(text: string, keep: number): string {
  const all = glyphs(text)
  return keep >= all.length ? text : `${all.slice(0, Math.max(0, keep)).join('').trimEnd()}…`
}
