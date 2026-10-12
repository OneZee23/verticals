/* A drawn subtree whose components end while its DOM stays: a <Transition> child that leaves. When the leave starts,
   each component under it ends as Vue unmounts one: its beforeUnmount hooks run, its effects stop, its template refs let
   go, and nothing in it draws again; its unmounted hooks follow in the tick's post queue. Its elements keep their
   listeners and play the leave; React takes them away when it ends. */
import { createContext } from 'react'
import { queuePostFlushCb } from './reactivity'

/** What a component does as it ends; what it returns runs in the post queue, the deepest first. */
type End = () => (() => void) | void

export class Leaving {
  left = false
  private readonly ends = new Set<End>()

  on(end: End): () => void {
    this.ends.add(end)
    return () => {
      this.ends.delete(end)
    }
  }

  leave(): void {
    if (this.left) return
    this.left = true
    const after: (() => void)[] = []
    for (const end of [...this.ends]) {
      const then = end()
      if (then) after.push(then)
    }
    if (after.length) queuePostFlushCb(() => {
      for (const fn of after.reverse()) fn()
    })
  }
}

export const LeavingContext = createContext<Leaving | null>(null)
