/* A field that commits on the native `change`: its value is the element's property, put back after each drawing where
   it differs. A controlled React field would undo each keystroke, and React's `onChange` fires on every input. */
import { useLayoutEffect, useRef, type ReactNode } from 'react'

interface ChangeFieldProps extends Record<string, unknown> {
  as?: 'input' | 'select'
  value: string | number | null | undefined
  onCommit: (event: Event) => void
  children?: ReactNode
}

export function ChangeField({ as: Tag = 'input', value, onCommit, ...rest }: ChangeFieldProps) {
  const el = useRef<HTMLInputElement & HTMLSelectElement>(null)
  const Field = Tag as 'input'
  const commit = useRef(onCommit)
  commit.current = onCommit
  useLayoutEffect(() => {
    const next = value == null ? '' : String(value)
    if (el.current && el.current.value !== next) el.current.value = next
  })
  useLayoutEffect(() => {
    const node = el.current
    if (!node) return
    const listener = (event: Event) => commit.current(event)
    node.addEventListener('change', listener)
    return () => node.removeEventListener('change', listener)
  }, [])
  return <Field ref={el} {...rest} />
}
