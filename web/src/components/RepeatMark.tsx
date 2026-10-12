/* The recurrence mark glued to the last word of a card's title: 15 x 14 px, 8 px gap,
   `rgba(45,48,54,.3)` on the reference. */
import { AppIcon } from './AppIcon'
import { fallthrough } from '../bind'
import './repeatMark.css'

export function RepeatMark(attrs: Record<string, unknown>) {
  return (
    <AppIcon
      name="repeat"
      label="Repeating goal"
      {...fallthrough({ className: 'goal-card__repeat', 'data-role': 'repeat-indicator' }, attrs)}
    />
  )
}
