// Verticals frontend build. Vue 3 SFCs consuming the private kit
// (@konstantinopolskii/design-system + @konstantinopolskii/vue, vendored — see web/vendor/) and
// nothing else: no router, no state library, no CSS framework. docs/BRIEF.md rule 8.
import { defineConfig, loadEnv, type CSSOptions } from 'vite'
import vue from '@vitejs/plugin-vue'

// Reduce Motion (docs/design/column-bounce.md). The desktop app has a Reduce Motion item in its View menu. A web view can't
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

const reduceMotionRules: PostcssPlugin = {
  postcssPlugin: 'verticals-reduce-motion',
  Once(root) {
    root.walkAtRules('media', (media) => {
      if (!/prefers-reduced-motion/i.test(media.params)) return
      const others = otherConditions(media.params)
      if (!others) {
        throw media.error(`@media ${media.params}: the Reduce Motion switch follows only (prefers-reduced-motion: reduce), alone or joined by "and" (vite.config.ts)`)
      }
      if (media.parent?.type === 'rule' || (media.nodes ?? []).some((node) => node.type !== 'rule' && node.type !== 'comment')) {
        throw media.error('the Reduce Motion switch follows a reduced-motion block of style rules outside any rule, nothing else (vite.config.ts)')
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

// WP-22: same-origin proxy for `/api/*` (and `/healthz`). `verticals/api/app.py` serves no static
// files and adds no CORSMiddleware on purpose (S-114) — the shipped topology is a real static
// server in front of `dist/` plus a real uvicorn subprocess, with nothing joining the two into one
// origin unless something here does it. `npm run dev` needs this for local development against a
// real backend; the `ui` test suite needs the identical config under `vite preview`
// (`docs/E2E.md` §6: "serves dist/ with a real static server" — `preview.proxy` is what makes
// that server also same-origin with the backend, without touching `verticals/api/app.py` at all).
// Target is an env var, not hardcoded: `tests/ui/conftest.py` starts uvicorn on a fresh ephemeral
// port per test run (same pattern as `tests/http/conftest.py::_free_port`) and points this at it.
export default defineConfig(({ mode }) => {
  // `tsconfig.json`'s `types` is scoped to `["vite/client"]` only (no `"node"`) — deliberately,
  // for a browser app that has exactly one Node-side line. Adding `@types/node` as a
  // devDependency for this alone would be a dependency for one global; a narrow cast reads it
  // instead. `globalThis.process` genuinely exists at runtime here — this file only ever runs
  // under Vite's own Node-hosted config loader, never bundled for the browser.
  const cwd = (globalThis as { process?: { cwd(): string } }).process?.cwd() ?? '.'
  const env = loadEnv(mode, cwd, '')
  const target = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'
  const proxy = {
    '/api': { target, changeOrigin: true },
    '/healthz': { target, changeOrigin: true },
  }
  return {
    plugins: [vue()],
    css: { postcss: { plugins: [reduceMotionRules] } },
    build: {
      // Keep the artifact deterministic and easy to serve statically (nginx, WP-29).
      outDir: 'dist',
      assetsDir: 'assets',
    },
    server: { proxy },
    preview: { proxy },
  }
})
