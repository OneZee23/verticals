/* The notice where the field stands (docs/design/board-undo.md): one black pill saying what happened to which goal, with
   Undo, or a question (⌘Z asking whose change it meant) with its candidates as pills. Titles are cut in the text, never
   the words around them; the field is hidden while it stands. */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from '../reactivity'
import { editsText } from '../lib/boardHistory'
import { dismiss, hold, notice, release, type NoticeChoice, type Segment } from '../lib/fieldNotice'
import { cutTitle, glyphs } from '../lib/titleCut'
import { store } from '../store'
import { bindRef, cx, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import { Transition } from '../Transition'
import './fieldNotice.css'

/** Two lines at 15/22 with 9 px above and below: as tall as a pill whose words go on to a second line may be. */
const TWO_LINES = 62
/** A title cut on one line to fewer letters than this names no goal anyone can tell: its pill takes a second line instead. */
const MIN_LETTERS = 12

interface Title { key: string; text: string; length: number }

export const FieldNotice = tracked(function FieldNotice(attrs: Record<string, unknown>) {
  const s = useSetup({}, () => {
    const pill = ref<HTMLElement | null>(null)
    const line = ref<HTMLElement | null>(null)
    /** The pills of a question, when there is one. */
    const choiceEls = ref<HTMLElement[]>([])
    /** The titles as the notice shows them, by the place of their segment (`L:2` in the line, `1:2` in the second pill). */
    const cuts = ref<Record<string, string>>({})
    /** A question that does not fit on one row: its words on a row of their own, the pills under them. */
    const stacked = ref(false)
    /** The pills (by their place) that take a second line. */
    const wrapped = ref<Record<string, boolean>>({})
    let fitting = 0

    /* Each pill joins `choiceEls` as it mounts and leaves it as it goes. */
    function choiceRef(el: HTMLElement | null): (() => void) | undefined {
      if (!el) return undefined
      if (!choiceEls.value.includes(el)) choiceEls.value.push(el)
      return () => {
        const at = choiceEls.value.indexOf(el)
        if (at >= 0) choiceEls.value.splice(at, 1)
      }
    }

    const overflows = (el: HTMLElement): boolean => el.scrollWidth > el.clientWidth
    const runsOver = (el: HTMLElement): boolean => (wrapped.value[el.dataset.choice ?? ''] ? el.scrollHeight > TWO_LINES : overflows(el))

    /** The titles whole if they do not run over, else the longest start of them that does not, found by halving. `false`:
     *  another notice has come, or this one has gone. */
    async function shorten(mine: number, titles: Title[], spills: () => boolean): Promise<boolean> {
      const longest = Math.max(0, ...titles.map((title) => title.length))
      const cutTo = (keep: number): Record<string, string> =>
        Object.fromEntries(titles.map((title) => [title.key, cutTitle(title.text, Math.round((title.length * keep) / longest))]))
      cuts.value = { ...cuts.value, ...cutTo(longest) }
      await nextTick()
      if (mine !== fitting || !line.value) return false
      if (!spills()) return true
      let fits = 0
      let over = longest
      while (fits < over - 1) {
        const middle = Math.ceil((fits + over) / 2)
        cuts.value = { ...cuts.value, ...cutTo(middle) }
        await nextTick()
        if (mine !== fitting || !line.value) return false
        if (spills()) over = middle
        else fits = middle
      }
      cuts.value = { ...cuts.value, ...cutTo(fits) }
      await nextTick()
      return mine === fitting && !!line.value
    }

    /** Whether a title has been cut to fewer letters than `MIN_LETTERS`, or than all it has when it has fewer than that. */
    const cutTooShort = (titles: Title[]): boolean =>
      titles.some((title) => {
        const shown = cuts.value[title.key]
        return shown !== undefined && shown !== title.text && glyphs(shown).length - 1 < Math.min(MIN_LETTERS, title.length)
      })

    /* A question goes onto more rows before any title is cut, and then each pill is cut to its own row. Everything runs
       before the next frame, so the whole title is never drawn. */
    async function fit(): Promise<void> {
      const mine = (fitting += 1)
      cuts.value = {}
      stacked.value = false
      wrapped.value = {}
      await nextTick()
      const spills = (): boolean => !!line.value && (overflows(line.value) || choiceEls.value.some(runsOver))
      if (mine !== fitting || !line.value || !spills()) return
      const quotes = (segments: Segment[], where: string): Title[] =>
        segments.flatMap((part, at) => ('quote' in part ? [{ key: `${where}:${at}`, text: part.quote, length: glyphs(part.quote).length }] : []))
      if (!notice.choices.length) {
        await shorten(mine, quotes(notice.segments, 'L'), spills)
        return
      }
      stacked.value = true
      await nextTick()
      for (const [at, choice] of notice.choices.entries()) {
        const own = (): HTMLElement | undefined => choiceEls.value.find((el) => el.dataset.choice === String(at))
        const runsOverAlone = (): boolean => !!own() && runsOver(own()!)
        if (mine !== fitting) return
        if (!runsOverAlone()) continue
        const titles = quotes(choice.label, String(at))
        if (!(await shorten(mine, titles, runsOverAlone))) return
        if (own() && (overflows(own()!) || cutTooShort(titles))) {
          wrapped.value = { ...wrapped.value, [String(at)]: true }
          await nextTick()
          if (!(await shorten(mine, titles, runsOverAlone))) return
        }
      }
    }

    // `sync`: the field is shown again in the same task as the key that asks for it, or it could not take the focus.
    watch(() => notice.open, (open) => document.documentElement.toggleAttribute('data-field-notice', open), { immediate: true, flush: 'sync' })
    watch(() => notice.seq, () => { stacked.value = false; wrapped.value = {}; cuts.value = {} }, { flush: 'pre' })
    watch(() => notice.seq, () => void fit(), { flush: 'post' })
    const refit = (): void => { if (notice.open) void fit() }

    function act(): void {
      const action = notice.action
      dismiss()
      action?.run()
    }

    /** A pick of the question: the question goes, and what was picked is taken back. */
    function pick(choice: NoticeChoice): void {
      dismiss()
      choice.run()
    }

    /* A key that asks for the field (a letter, or ⌘K) puts the field back first: a hidden field cannot take the focus. */
    const asksForField = (event: KeyboardEvent): boolean => {
      const command = event.metaKey || event.ctrlKey
      if (event.altKey) return false
      return command ? event.key.toLowerCase() === 'k' : event.key.length === 1 && event.key !== ' '
    }

    /* Esc ends it, ahead of the field and of the windows. Inside a text field, and while a goal is in the hand, Esc is
       theirs. */
    function onKeyDown(event: KeyboardEvent): void {
      if (!notice.open || event.defaultPrevented || editsText(event.target)) return
      if (asksForField(event) && !store.state.drag.id && !store.state.drag.pending) dismiss()
      if (event.key !== 'Escape' || store.state.drag.id || store.state.drag.pending) return
      event.preventDefault()
      event.stopImmediatePropagation()
      dismiss()
    }
    /* A press anywhere but on the notice ends it; the press itself goes on to what it was aimed at. */
    function onPointerDown(event: PointerEvent): void {
      if (notice.open && !(event.target instanceof Node && pill.value?.contains(event.target))) dismiss()
    }

    onMounted(() => {
      window.addEventListener('keydown', onKeyDown, true)
      window.addEventListener('pointerdown', onPointerDown, true)
      window.addEventListener('resize', refit)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('keydown', onKeyDown, true)
      window.removeEventListener('pointerdown', onPointerDown, true)
      window.removeEventListener('resize', refit)
      document.documentElement.removeAttribute('data-field-notice')
    })
    return { pill, line, choiceRef, cuts, stacked, wrapped, act, pick }
  })

  const cuts = s.cuts.value
  const words = (segments: Segment[], where: string | number) =>
    segments.map((part, at) =>
      'text' in part ? (
        <span key={at} className="field-notice__text">{part.text}</span>
      ) : (
        <span key={at} className="field-notice__quote"><i>“</i><span className="field-notice__title">{cuts[`${where}:${at}`] ?? part.quote}</span><i>”</i></span>
      ),
    )
  const own = {
    ref: bindRef(s.pill),
    className: cx('field-notice', {
      'field-notice--bare': !notice.action && !notice.choices.length,
      'field-notice--question': notice.choices.length > 0,
      'field-notice--stacked': s.stacked.value && notice.choices.length > 0,
    }),
    'data-role': 'field-notice',
    role: 'status',
    'aria-live': 'polite',
    onPointerEnter: hold,
    onPointerLeave: release,
  }
  return (
    <Transition name="field-notice">
      {notice.open ? (
        <div {...fallthrough(own, attrs)}>
          <p ref={bindRef(s.line)} className="field-notice__line" data-role="field-notice-line">
            {words(notice.segments, 'L')}
          </p>
          {notice.choices.map((choice, at) => (
            <button
              key={at}
              ref={s.choiceRef}
              type="button"
              className={cx('field-notice__action field-notice__choice', { 'field-notice__choice--wrapped': s.wrapped.value[at] })}
              data-role="field-notice-choice"
              data-choice={at}
              onClick={() => s.pick(choice)}
            >
              {words(choice.label, at)}
            </button>
          ))}
          {notice.action ? (
            <button type="button" className="field-notice__action" data-role="field-notice-action" onClick={s.act}>
              {notice.action.label}
            </button>
          ) : null}
        </div>
      ) : null}
    </Transition>
  )
})
