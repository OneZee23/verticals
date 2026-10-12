/* A desk's head, the Inbox's or Documents': its title, what the desk adds beside it
   (children, the slot), and × back to the board. */
import type { ReactNode } from 'react'
import { AppIcon } from './AppIcon'
import { store } from '../store'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import './deskHead.css'

interface Props {
  title: string
  children?: ReactNode
}

export const DeskHead = tracked(function DeskHead({ title, children, ...attrs }: Props & Record<string, unknown>) {
  return (
    <header {...fallthrough({ className: 'desk-head', 'data-role': 'desk-head' }, attrs)}>
      <h1 className="t-title desk-head__title">{title}</h1>
      {children}
      <button type="button" className="desk-head__close" data-role="desk-close" aria-label={`Close ${title}`} onClick={() => store.setView('verticals')}>
        <AppIcon name="x" size={16} />
      </button>
    </header>
  )
})
