/* The line pinned at a column's top (web/src/components/ColumnLine.tsx, docs/design/column-bars.md): when the column
   scrolls it stays at its top on white while the goals fade out under it over 14 px, and the period bars (ColumnBars)
   stand on it. At the column's top it says the kind ("Week"); once the big name has scrolled under it, the period
   ("5–11 Oct"), in the words the header chose for its room. It is the first child of the slide that scrolls and listens
   to that slide itself. It also says where its words end, so the left box of the sign at the column's right can grow
   into the room they leave and no further. */
import { useCallback, type Ref as ReactRef } from 'react'
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from '../reactivity'
import { fontEpoch, fontOf, widthOf } from '../lib/fitName'
import { bindRef, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './columnLine.css'

interface Props {
  /** The kind, as the header's kind row says it: "Week", "Week · Dec ’27". */
  kind: string
  /** The period, the form of the big name that fits, with what the kind line carried: "5–11 Oct", "Wed", "21–27 · Dec". */
  name: string
  /** Where the words end, in px from the column's left: the longer of the kind and the period, in their own type. */
  onWords?: (end: number) => void
  ref?: ReactRef<HTMLDivElement>
}

/* The big name stands on a baseline 55 px under the column's top, its descenders reach 61, and the line ends at 28. At 27
   px of scroll its caps are under the line, at 32 nearly all of its descenders: the period takes the kind's place then.
   Going back it is held down to 28, 4 px sooner than it came, so a column resting at the edge doesn't flicker. */
const NAMED_AT = 32
const HOLD = 4
/** The fade under the line grows with the scroll over its own height, 14 px. */
const FADE = 14
/** The words stand 14 px in from the column's left (`.column-line__words`). */
const WORDS_LEFT = 14

/** The root is the line's own element ref and the parent's `ref` at once. */
function useRootRef(own: Ref<HTMLElement | null>, outer: ReactRef<HTMLDivElement> | undefined): (node: HTMLDivElement | null) => void {
  return useCallback((node: HTMLDivElement | null) => {
    bindRef(own)(node)
    if (typeof outer === 'function') outer(node)
    else if (outer) outer.current = node
  }, [own, outer])
}

export const ColumnLine = tracked(function ColumnLine({ ref: outer, ...raw }: Props & Record<string, unknown>) {
  const { kind, name, onWords, ...attrs } = raw
  const s = useSetup({ kind, name, onWords }, (props) => {
    const line = ref<HTMLElement | null>(null)
    const kindWord = ref<HTMLElement | null>(null)
    const nameWord = ref<HTMLElement | null>(null)
    const named = ref(false)
    let slide: HTMLElement | null = null

    /** A canvas measures the words, as the header's fit does (lib/fitName.ts), and again when a font arrives. */
    function reachWords(): void {
      if (!kindWord.value || !nameWord.value) return
      const kind = widthOf(props.kind, fontOf(kindWord.value))
      const name = widthOf(props.name, fontOf(nameWord.value))
      props.onWords?.(WORDS_LEFT + Math.max(kind, name))
    }
    watch([() => props.kind, () => props.name, fontEpoch], reachWords)

    /** The fade follows the scroll on the line itself, a frame at a time and without a render; the words change only at
     *  the thresholds. */
    function scrolled(): void {
      if (!slide) return
      const top = slide.scrollTop
      line.value?.style.setProperty('--line-fade', String(Math.min(1, Math.max(0, top / FADE))))
      const now = top >= (named.value ? NAMED_AT - HOLD : NAMED_AT)
      if (now !== named.value) named.value = now
    }
    onMounted(() => {
      slide = line.value?.parentElement ?? null
      slide?.addEventListener('scroll', scrolled, { passive: true })
      scrolled()
      reachWords()
    })
    onBeforeUnmount(() => slide?.removeEventListener('scroll', scrolled))
    return { line, kindWord, nameWord, named }
  })
  const rootRef = useRootRef(s.line, outer as ReactRef<HTMLDivElement> | undefined)
  // A click on the line's words is a click on the header they cover (Column).
  return (
    <div
      {...fallthrough({
        ref: rootRef,
        className: 'column-line',
        'data-role': 'column-line',
        'data-state': s.named.value ? 'period' : 'kind',
      }, attrs)}
    >
      <div className="column-line__words">
        <p ref={bindRef(s.kindWord)} className="column-line__kind" data-role="column-line-kind" aria-hidden="true">{kind}</p>
        <p ref={bindRef(s.nameWord)} className="column-line__name" data-role="column-line-name" aria-hidden="true">{name}</p>
      </div>
    </div>
  )
})
