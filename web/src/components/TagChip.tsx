/* One pressable tag (S-125), on the kit's KChip: a chip picks, a tag only labels. `data-tag` carries the bare tag for
   tests; the `#` is CSS, never data. */
import { fallthrough } from '../bind'
import { KChip } from '../kit'
import './tagChip.css'

export function TagChip({ tag, pressed = false, onSelect, ...attrs }:
  { tag: string; pressed?: boolean; onSelect?: (tag: string) => void } & Record<string, unknown>) {
  return (
    <KChip {...fallthrough({ className: 'tag-chip', value: tag, pressed, 'data-tag': tag, onClick: () => onSelect?.(tag) }, attrs)}>
      {tag}
    </KChip>
  )
}
