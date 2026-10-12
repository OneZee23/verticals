/* A document as a page on the desk: the document's own top, its window's one-line head
   and its title over its first words, set at the window's 720 px and drawn at the page's size, so its text is the page's
   texture. */
import { computed, onMounted, ref, watch } from '../reactivity'
import { AppIcon } from './AppIcon'
import type { DeskDoc } from '../lib/api'
import { renderBodyElement } from '../lib/bodyMarkdown'
import { shortDay } from '../lib/docsDesk'
import { bindRef, cx, fallthrough, sx } from '../bind'
import { tracked } from '../tracked'
import { useSetup, withDefaults } from '../setup'
import './docPage.css'

interface Props {
  doc: Pick<DeskDoc, 'title' | 'path' | 'excerpt' | 'updated_at'>
  width?: number
  /** The width the page is set at before it is drawn at `width`: the window's 720 on the desk, a narrow 300 for a page
   *  waiting on the circle, so its title reads. */
  measure?: number
  facts?: string
}
const DEFAULTS = { width: 120, measure: 720, facts: '' }

export const DocPage = tracked(function DocPage(raw: Props & Record<string, unknown>) {
  const { doc, width, measure, facts, ...attrs } = withDefaults(raw, DEFAULTS)
  const s = useSetup({ doc, width, measure, facts }, (props) => {
    const body = ref<HTMLElement | null>(null)

    function render(): void {
      const el = body.value
      if (!el) return
      el.replaceChildren()
      // The title stands large above; a first "# title" line in the text would say it twice.
      renderBodyElement(el, props.doc.excerpt.replace(/^\s*#\s[^\n]*\n?/, ''))
    }
    /* The page's one line of facts: in the window's head on a desk page; under the title on a narrow page waiting on
       the circle. */
    const line = computed(() => props.facts || `edited ${shortDay(props.doc.updated_at)}`)
    onMounted(render)
    watch(() => props.doc.excerpt, render)
    return { body, line }
  })

  const own = {
    className: 'doc-page',
    style: sx({ width: `${width}px`, height: `${Math.round(width * 4 / 3)}px` }),
    'aria-hidden': 'true',
  }
  return (
    <div {...fallthrough(own, attrs)}>
      <div
        className={cx('doc-page__in', { 'doc-page__in--narrow': measure < 720 })}
        style={sx({ width: `${measure}px`, height: `${Math.round(measure * 4 / 3)}px`, transform: `scale(${width / measure})` })}
      >
        {measure >= 720 ? <div className="doc-page__bar"><AppIcon name="file" size={16} />{s.line.value}</div> : null}
        <div className="doc-page__text">
          <h1>{doc.title || doc.path}</h1>
          {measure < 720 ? <p className="doc-page__facts">{s.line.value}</p> : null}
          <div ref={bindRef(s.body)}></div>
        </div>
      </div>
    </div>
  )
})
