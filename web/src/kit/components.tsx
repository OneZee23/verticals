/* The kit's components the app uses, in the kit's markup and classes. A parent's attributes fall through onto the root
   (bind.ts); a declared event is a prop the component calls. */
import { useLayoutEffect, useRef, type ElementType, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react'
import { cx, fallthrough, valueOf } from '../bind'

type Attrs = Record<string, unknown> & { className?: string; children?: ReactNode }

export function KButton({ primary = false, as = 'button', type = 'button', cta = null, caption = false, children, ...attrs }:
  Attrs & { primary?: boolean; as?: ElementType; type?: string; cta?: string | null; caption?: boolean }) {
  const Tag = as
  const own = {
    className: 'button' + (primary ? ' button--primary' : '') + (caption ? ' t-caption--bold' : ' t-subtitle'),
    type: as === 'button' ? type : undefined,
    'data-cta': cta ?? undefined,
  }
  return <Tag {...fallthrough(own, attrs)}>{children}</Tag>
}

const CARD_VARIANT = { static: '', interactive: ' card--interactive', link: ' card--link', shout: ' card--shout', heading: ' card--heading' }

export function KCard({ variant = 'static', href = '', tight = false, selectable = false, state = null, span = null, lead = false,
  dense = false, children, ...attrs }: Attrs & {
  variant?: keyof typeof CARD_VARIANT; href?: string; tight?: boolean; selectable?: boolean; state?: string | null
  span?: string | null; lead?: boolean; dense?: boolean
}) {
  const Tag = variant === 'link' ? 'a' : variant === 'heading' ? 'header' : 'div'
  const own = {
    className: 'card' + CARD_VARIANT[variant] + (selectable ? ' card--selectable' : '') + (tight ? ' card--tight' : '')
      + (span ? ` panel--${span}` : '') + (lead ? ' front__lead' : '') + (dense ? ' card--dense' : ''),
    href: variant === 'link' ? href : undefined,
    'data-state': variant === 'interactive' && state ? state : undefined,
  }
  return <Tag {...fallthrough(own, attrs)}>{children}</Tag>
}

export function KCardStack({ columns = false, dense = false, children, ...attrs }: Attrs & { columns?: boolean; dense?: boolean }) {
  const own = { className: cx('card-stack', columns ? 'card-stack--columns' : null, dense ? 'card-stack--dense' : null) }
  return <div {...fallthrough(own, attrs)}>{children}</div>
}

export function KChip({ pressed = false, onClick, children, ...attrs }:
  Attrs & { pressed?: boolean; value?: unknown; onClick?: (event: MouseEvent<HTMLButtonElement>) => void }) {
  const own = { className: 'chip', type: 'button', 'aria-pressed': pressed ? 'true' : 'false', onClick: (event: MouseEvent<HTMLButtonElement>) => onClick?.(event) }
  delete attrs.value
  return <button {...fallthrough(own, attrs)}>{children}</button>
}

export function KCheckbox({ label = '', modelValue = false, size = 's', 'onUpdate:modelValue': onUpdate, ...attrs }:
  Attrs & { label?: string; modelValue?: boolean; size?: string; 'onUpdate:modelValue'?: (value: boolean) => void }) {
  // `checked` is the element's property, set when the value changes: a click the parent leaves unanswered stays as the
  // hand left it.
  const input = useRef<HTMLInputElement | null>(null)
  useLayoutEffect(() => {
    if (input.current) input.current.checked = modelValue
  }, [modelValue])
  // The box's own `change`, as the kit's `@change`: after the click, not inside it as React's onChange.
  const update = useRef(onUpdate)
  update.current = onUpdate
  useLayoutEffect(() => {
    const el = input.current
    if (!el) return
    const onChange = () => update.current?.(el.checked)
    el.addEventListener('change', onChange)
    return () => el.removeEventListener('change', onChange)
  }, [])
  return (
    <label {...fallthrough({ className: cx('checkbox', `checkbox--size-${size}`) }, attrs)}>
      <input ref={input} className="checkbox__input" type="checkbox" />
      <span className="checkbox__box"></span>
      {label ? <span className="t-caption">{label}</span> : null}
    </label>
  )
}

export function KInlineAdd({ placeholder = 'Add…', onAdd, ...attrs }: Attrs & { placeholder?: string; onAdd?: (title: string) => void }) {
  function onKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (event.key !== 'Enter') return
    const el = event.currentTarget
    const title = el.value.trim()
    if (!title) return
    onAdd?.(title)
    el.value = ''
  }
  return <input {...fallthrough({ className: 'inline-add', type: 'text', placeholder, onKeyDown }, attrs)} />
}

export function KField({ label = '', modelValue = '', placeholder = '', type = 'text', textarea = false, row = false, fakeCaret = false,
  'onUpdate:modelValue': onUpdate, ...attrs }: Attrs & {
  label?: string; modelValue?: string; placeholder?: string; type?: string; textarea?: boolean; row?: boolean; fakeCaret?: boolean
  'onUpdate:modelValue'?: (value: string) => void
}) {
  const field = {
    className: 't-caption field__input',
    placeholder: placeholder || undefined,
    ...valueOf(modelValue, (event) => onUpdate?.(event.currentTarget.value)),
  }
  return (
    <label {...fallthrough({ className: row ? 'field field--row' : 'field' }, attrs)}>
      {label ? <span className="t-caption--bold field__label">{label}</span> : null}
      {textarea ? <textarea {...field} /> : <input {...field} type={type} />}
      {fakeCaret ? <span className="field__fake-caret" aria-hidden="true"></span> : null}
    </label>
  )
}

export function KCommentNew({ title = 'Add a comment', placeholder = 'Type a comment', modelValue = '', commitLabel = 'Commit',
  'onUpdate:modelValue': onUpdate, onCommit, ...attrs }: Attrs & {
  title?: string; placeholder?: string; modelValue?: string; commitLabel?: string
  'onUpdate:modelValue'?: (value: string) => void; onCommit?: (value: string) => void
}) {
  return (
    <div {...fallthrough({ className: 'card card--shout comment-new' }, attrs)}>
      <div className="card__heading"><h3 className="t-title">{title}</h3></div>
      <KField textarea placeholder={placeholder} modelValue={modelValue} onUpdate:modelValue={(value: string) => onUpdate?.(value)} />
      <button className="button button--primary t-subtitle" type="button" onClick={() => onCommit?.(modelValue)}>{commitLabel}</button>
    </div>
  )
}

export interface KCommentMessage {
  id: string
  body: string
  role?: string
}

export function KCommentThread({ title, state = 'minimized', archived = false, messages, ...attrs }: Attrs & {
  title: string; state?: string; archived?: boolean; messages: KCommentMessage[]
}) {
  const own = { className: 'card card--interactive comment-thread', 'data-state': state, 'data-archived': archived ? 'true' : undefined }
  return (
    <div {...fallthrough(own, attrs)}>
      <div className="card__heading"><h3 className="t-title">{title}</h3></div>
      <div className="card__collapsible">
        <div className="card__collapsible-inner">
          {messages.map((msg) => (
            <div key={msg.id} className="comment-msg" data-message-id={msg.id} data-author-role={msg.role === 'agent' ? 'agent' : undefined}>
              <p className="t-caption">{msg.body}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function KCommentStack({ children, ...attrs }: Attrs) {
  return <div {...fallthrough({ className: 'comment-stack' }, attrs)}>{children}</div>
}
