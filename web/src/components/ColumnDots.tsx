/* The dots (web/src/components/ColumnDots.tsx, docs/design-handoff S5.P2): while a goal is dragged they stand in a
   column's corner, in place of its period controls; resting the goal over them melts it in, and they grow and take its
   colours while the column's spans open. */
import { computed } from '../reactivity'
import { store } from '../store'
import { goalLight } from '../lib/look'
import { findGoal } from '../lib/boardIndex'
import { spanGoal, VIEW_NAMES, type SpanScale } from '../lib/spans'
import { dots } from '../lib/spansDrag'
import { cx, fallthrough, sx } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './columnDots.css'

interface Props {
  vertical: SpanScale
}

export const ColumnDots = tracked(function ColumnDots(raw: Props & Record<string, unknown>) {
  const { vertical, ...attrs } = raw
  const s = useSetup({ vertical }, (props) => {
    const held = computed(() => dots.held === props.vertical)
    const colours = computed(() => {
      const out: Record<string, string> = {}
      if (!held.value) return out
      const id = store.state.drag.id ?? dots.goalId
      const color = id ? (findGoal(store.state.board, id) ?? spanGoal(id))?.color ?? null : null
      const light = goalLight(color)
      if (light && color) Object.assign(out, { '--dot-full': color, '--dot-light': `rgb(${light['--vt-tint']})` })
      return out
    })
    return { held, colours }
  })
  return (
    <div
      {...fallthrough({
        className: cx('column-dots', { 'column-dots--held': s.held.value }),
        style: sx(s.colours.value),
        'data-role': 'column-dots',
        'data-dots-vertical': vertical,
        role: 'img',
        'aria-label': `Open ${VIEW_NAMES[vertical].toLowerCase()}`,
      }, attrs)}
    >
      <i className="column-dots__dot"></i><i className="column-dots__dot column-dots__dot--middle"></i><i className="column-dots__dot"></i>
    </div>
  )
})
