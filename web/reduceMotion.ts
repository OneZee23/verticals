import type { CSSOptions } from 'vite'

// Reduce Motion (docs/design/column-bounce.md), for both builds of the app (web/ and web-react/ vite.config.ts).
// The desktop app has a Reduce Motion item in its View menu. A web view can't
// be told to change `prefers-reduced-motion`, so the app puts its answer on <html>: `data-reduce-motion="on"` or "off". It
// puts nothing there while the person hasn't chosen, and a browser never does: there the system setting is the only switch.
// This PostCSS plugin (Vite already runs PostCSS; nothing is installed) makes every `@media (prefers-reduced-motion: reduce)`
// block of the page, the kit's included, answer to the app too. The block stays where it is and applies while there is no
// answer; a copy of its rules for the answer `on` follows it:
//
//   @media (prefers-reduced-motion: reduce) { .a { x } }
// becomes
//   @media (prefers-reduced-motion: reduce) { :where(:root:not([data-reduce-motion])) .a { x } }
//   :where(:root[data-reduce-motion=on]) .a { x }
//
// `:where` weighs nothing, so a copy has its original's specificity and stands at the same place of the cascade: the switch
// does what the system setting does, no more specific and no later. With the answer `off` neither applies, so the person's
// choice wins over macOS's. A selector that begins with `:root` or `html` takes the attribute on that same element. A form
// the copy can't follow fails the build, so no new rule can miss the switch quietly. Scripts ask `reducedMotion()`
// (src/lib/motion.ts); tests/static/test_reduce_motion_rules.py counts both.
type PostcssPlugin = NonNullable<Exclude<CSSOptions['postcss'], string | undefined>['plugins']>[number]
const ANSWER_ON = '[data-reduce-motion=on]'
const NO_ANSWER = ':not([data-reduce-motion])'
const REDUCE = /^\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)$/i

/** `selector` for the moments when the attribute stands as `state` (`ANSWER_ON` or `NO_ANSWER`). */
function whenAnswer(selector: string, state: string): string {
  const root = /^(?::root|html)(?![\w-])/i.exec(selector)
  return root ? `${root[0]}:where(${state})${selector.slice(root[0].length)}` : `:where(:root${state}) ${selector}`
}

/** What a reduced-motion query also asks for (a hover, say), or null when the copy can't follow its form: one
 *  `(prefers-reduced-motion: reduce)` and nothing else of its kind, joined only by `and`. */
function otherConditions(query: string): string[] | null {
  if (/,|\bor\b|^\s*(not|only)\b/i.test(query)) return null
  const terms = query.split(/\s+and\s+/i).map((term) => term.trim())
  const others = terms.filter((term) => !REDUCE.test(term))
  return terms.length - others.length === 1 && !others.some((term) => /prefers-reduced-motion/i.test(term)) ? others : null
}

export const reduceMotionRules: PostcssPlugin = {
  postcssPlugin: 'verticals-reduce-motion',
  Once(root) {
    root.walkAtRules('media', (media) => {
      if (!/prefers-reduced-motion/i.test(media.params)) return
      const others = otherConditions(media.params)
      if (!others) {
        throw media.error(`@media ${media.params}: the Reduce Motion switch follows only (prefers-reduced-motion: reduce), alone or joined by "and" (web/reduceMotion.ts)`)
      }
      if (media.parent?.type === 'rule' || (media.nodes ?? []).some((node) => node.type !== 'rule' && node.type !== 'comment')) {
        throw media.error('the Reduce Motion switch follows a reduced-motion block of style rules outside any rule, nothing else (web/reduceMotion.ts)')
      }
      const scope = (block: typeof media, state: string) => {
        for (const node of block.nodes ?? []) {
          if (node.type === 'rule') node.selectors = node.selectors.map((selector) => whenAnswer(selector, state))
        }
      }
      const copy = media.clone()
      scope(media, NO_ANSWER)
      scope(copy, ANSWER_ON)
      if (others.length) {
        copy.params = others.join(' and ')
        media.after(copy)
      } else {
        media.after(copy.nodes ?? [])
      }
    })
  },
}
