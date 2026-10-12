/* The mascot of the carried box's empty room: when the box keeps its place and
   the filter leaves part of it empty, a faint dashed circle with the mascot's line stands there, looking at the pointer,
   and says why the box is emptier; where the room is too low for the circle, its words stand alone. A click makes it
   blink, hop and squash, and say what it did, then ask you to stop. Mouse only: no keyboard stop, no label, and nothing
   it does touches the board. */
import { useCallback, type Ref as ReactRef } from 'react'
import { computed, onBeforeUnmount, ref, watch, type Ref } from '../reactivity'
import { reducedMotion } from '../lib/motion'
import { bindRef, cx, fallthrough, sx } from '../bind'
import { tracked } from '../tracked'
import { exposeTo, useSetup } from '../setup'
import './carriedMascot.css'

export interface CarriedMascotApi {
  /** The heights the mascot needs: with its circle, and its words alone. */
  need(): { circle: number; words: number }
}

interface Props {
  on: boolean
  words: string | null
  circle: boolean
  expose?: Ref<CarriedMascotApi | null>
  ref?: ReactRef<HTMLDivElement>
  className?: string
}

const POKES = [
  'Layout fix deployed', 'Edge case, handled', 'Please stop clicking', 'Don\'t touch me, please', 'I am focused on the layout',
  'Please', 'Don\'t', 'It can ruin the layout', 'Please', 'I can see you clicking',
]
const LINE = 10.8 // px: the line is this tall; blinking it shrinks it to a dot as wide as it is
const DOT = 1.8
const ORB = 29 // px: the circle, as in the styles

/** The root's own element ref and the parent's `ref` on one element, as one stable callback. */
function useRootRef(own: Ref<HTMLElement | null>, outer: ReactRef<HTMLDivElement> | undefined): (node: HTMLDivElement | null) => void {
  return useCallback((node: HTMLDivElement | null) => {
    own.value = node
    if (typeof outer === 'function') outer(node)
    else if (outer) outer.current = node
  }, [own, outer])
}

export const CarriedMascot = tracked(function CarriedMascot(raw: Props) {
  const { on, words, circle, expose, ref: outer, ...attrs } = raw
  const s = useSetup({ on, words, circle, expose }, (props) => {
    const poked = ref<string | null>(null)
    const text = computed(() => poked.value ?? props.words ?? '')
    const gap = ref<HTMLElement | null>(null)
    const orb = ref<HTMLElement | null>(null)
    const line = ref<HTMLElement | null>(null)
    const words = ref<HTMLElement | null>(null)
    let pokes = 0

    function need(): { circle: number; words: number } {
      const w = words.value?.offsetHeight ?? 16
      return { circle: ORB + 4 + w + 8, words: w }
    }
    exposeTo(props.expose, { need })

    /** The line leans toward the pointer, up to 5 px, the farther the pointer the more. */
    function look(event: PointerEvent): void {
      const el = orb.value
      const mark = line.value
      if (!el || !mark) return
      const r = el.getBoundingClientRect()
      const dx = event.clientX - (r.left + r.width / 2)
      const dy = event.clientY - (r.top + r.height / 2)
      const d = Math.hypot(dx, dy) || 1
      const k = Math.min(1, d / 120) * 5
      mark.style.transform = `translate(${((dx / d) * k).toFixed(1)}px, ${((dy / d) * k).toFixed(1)}px)`
    }

    watch(() => props.on, (on) => {
      if (on) {
        poked.value = null
        pokes = 0
        window.addEventListener('pointermove', look, { passive: true })
      } else {
        window.removeEventListener('pointermove', look)
      }
    }, { immediate: true })
    // another goal, another story: it tells that first again
    watch(() => props.words, () => { poked.value = null; pokes = 0 })
    onBeforeUnmount(() => window.removeEventListener('pointermove', look))

    function poke(): void {
      const i = pokes
      pokes += 1
      // it explains first, then keeps asking: from the third line on, the asking goes round
      poked.value = POKES[i < POKES.length ? i : 2 + ((i - 2) % (POKES.length - 2))]!
      const el = orb.value
      const mark = line.value
      if (reducedMotion() || !el || !mark) return
      words.value?.animate([{ opacity: 0, transform: 'translateY(3px)' }, { opacity: 1, transform: 'none' }],
        { duration: 160, easing: 'cubic-bezier(.2, 0, 0, 1)' })
      // the blink: the line closes into a dot and opens again; it never fades
      mark.animate([
        { height: `${LINE}px`, marginTop: `${-LINE / 2}px` },
        { height: `${DOT}px`, marginTop: `${-DOT / 2}px`, offset: 0.28 },
        { height: `${DOT}px`, marginTop: `${-DOT / 2}px`, offset: 0.5 },
        { height: `${LINE}px`, marginTop: `${-LINE / 2}px` },
      ], { duration: 300, easing: 'cubic-bezier(.2, 0, 0, 1)' })
      // the hop: as high as the room over the circle allows, never into the plans above; a tight place only squashes
      const from = getComputedStyle(el).transform
      const room = gap.value ? el.getBoundingClientRect().top - gap.value.getBoundingClientRect().top : 12
      const tight = room < 9
      const up = tight ? 0 : Math.min(12, room - 6)
      const out = 'cubic-bezier(.2, .7, .3, 1)'
      const fall = 'cubic-bezier(.5, 0, .9, .6)'
      el.animate([
        { transform: from === 'none' ? 'translateY(0) scale(1, 1)' : from, offset: 0, easing: out },
        { transform: `translateY(-${up}px) scale(.94, ${tight ? 1 : 1.08})`, offset: 0.3, easing: fall },
        { transform: 'translateY(0) scale(1.14, .86)', offset: 0.5, easing: out },
        { transform: `translateY(-${(up / 4).toFixed(1)}px) scale(.97, ${tight ? 1 : 1.04})`, offset: 0.72, easing: fall },
        { transform: 'translateY(0) scale(1.03, .97)', offset: 0.88, easing: out },
        { transform: 'translateY(0) scale(1, 1)', offset: 1 },
      ], { duration: 640 })
    }
    return { text, gap, orb, line, words, poke }
  })
  const rootRef = useRootRef(s.gap, outer)
  return (
    <div
      {...fallthrough({
        ref: rootRef,
        className: cx('carried-gap', { 'carried-gap--on': on, 'carried-gap--words': !circle }),
        'data-role': 'carried-gap',
        'aria-hidden': 'true',
      }, attrs)}
    >
      <div className="carried-gap__mascot">
        <div ref={bindRef(s.orb)} className="carried-gap__orb" data-role="carried-mascot" style={sx(circle ? null : { display: 'none' })}
          onClick={() => s.poke()}><i ref={bindRef(s.line)}></i></div>
        <p ref={bindRef(s.words)} className="carried-gap__words" data-role="carried-words">{s.text.value}</p>
      </div>
    </div>
  )
})
