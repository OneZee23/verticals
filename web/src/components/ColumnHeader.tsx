/* A column's name: the longest form of it that fits the row's room, chosen in the
   frame the room changes, never cut with "…" (lib/fitName.ts). Not KCardHeading: its padding is not this header's. */
import { computed, onBeforeUnmount, onMounted, ref, watch } from '../reactivity'
import { fittest, fontEpoch, fontOf } from '../lib/fitName'
import type { NameForm } from '../types'
import { bindRef, fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup, withDefaults } from '../setup'
import './columnHeader.css'

interface Props {
  title: string
  subLabel?: string
  /** The same name in shorter forms, longest first. */
  shorter?: NameForm[]
  /** A span's end, after its date. */
  end?: string
  onForm?: (form: NameForm) => void
}
const DEFAULTS = { subLabel: '', shorter: [] as NameForm[], end: '' }

export const ColumnHeader = tracked(function ColumnHeader(raw: Props & Record<string, unknown>) {
  const { title, subLabel, shorter, end, onForm, ...attrs } = withDefaults(raw, DEFAULTS)
  const props = { title, subLabel, shorter, end, onForm }
  const s = useSetup(props, (props) => {
    const rowEl = ref<HTMLElement | null>(null)
    const titleEl = ref<HTMLElement | null>(null)
    const room = ref(0)
    let watcher: ResizeObserver | null = null
    onMounted(() => {
      if (!rowEl.value || typeof ResizeObserver === 'undefined') return
      watcher = new ResizeObserver((entries) => { room.value = entries[entries.length - 1]!.contentRect.width })
      watcher.observe(rowEl.value)
    })
    onBeforeUnmount(() => watcher?.disconnect())

    const forms = computed<NameForm[]>(() => [{ name: props.title, kind: props.subLabel }, ...props.shorter])
    const shown = computed<NameForm>(() => {
      void fontEpoch.value // chosen again once the title font has arrived
      const all = forms.value
      if (all.length === 1 || !titleEl.value || room.value <= 0) return all[0]!
      return all[fittest(all.map((form) => form.name), room.value, fontOf(titleEl.value))]!
    })
    // The line pinned at the column's top says the same words once the name has scrolled under it.
    watch(shown, (form) => props.onForm?.(form), { immediate: true })
    return { rowEl, titleEl, forms, shown }
  })
  const shown = s.shown.value
  return (
    <header {...fallthrough({ className: 'pattern-vertical-board__header column-header' }, attrs)}>
      {shown.kind ? (
        <div className="column-header__period-row">
          <p className="t-caption column-header__sub-label">{shown.kind}</p>
        </div>
      ) : null}
      <div ref={bindRef(s.rowEl)} className="column-header__title-row">
        {/* A shorter form on screen still has the full name for a screen reader. */}
        <h3 ref={bindRef(s.titleEl)} className="t-title" aria-label={shown === s.forms.value[0] ? undefined : props.title}>
          {shown.name}
          {props.end ? <span className="column-header__end" data-role="span-end">{props.end}</span> : null}
        </h3>
      </div>
    </header>
  )
})
