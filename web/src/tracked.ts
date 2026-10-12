/* A React component that reads the store: it draws again when anything its last drawing read has changed (a MobX
   reaction tracks the drawing), once per tick, in its place in src/reactivity.ts's queue; equal props draw nothing.
   It is numbered when first drawn, a parent before its children. Once it ends in a leaving subtree (src/leaving.ts) it
   draws no more. An error in its drawing is logged and it draws nothing, the rest of the page staying, as in Vue. */
import { Reaction, untracked } from 'mobx'
import { memo, useContext, useEffect, useReducer, useRef, type MemoExoticComponent, type ReactNode } from 'react'
import { LeavingContext } from './leaving'
import { nextUid, owners, queueJob } from './reactivity'

export function tracked<P extends object>(render: (props: P) => ReactNode): MemoExoticComponent<(props: P) => ReactNode> {
  function Tracked(props: P): ReactNode {
    const [, redraw] = useReducer((count: number) => count + 1, 0)
    const uid = useRef(0)
    if (!uid.current) uid.current = nextUid()
    const left = useRef(false)
    const job = useRef<(() => void) | null>(null)
    if (!job.current) job.current = () => {
      if (!left.current) redraw()
    }
    const reads = useRef<Reaction | null>(null)
    if (!reads.current && !left.current) {
      // Even a change made while it draws (its own props, say) draws it again: a reaction left stale hears nothing more
      // until it tracks again. The second drawing has the same props and changes nothing.
      reads.current = new Reaction(render.name || 'Tracked', () => queueJob('render', job.current!, uid.current))
    }
    const leaving = useContext(LeavingContext)
    const off = useRef<(() => void) | null>(null)
    if (leaving && !off.current) off.current = leaving.on(() => {
      left.current = true
      reads.current?.dispose()
      reads.current = null
    })
    useEffect(() => {
      if (!reads.current && !left.current) redraw() // mounted again after a cleanup: draw once more to read again
      return () => {
        off.current?.()
        off.current = null
        reads.current?.dispose()
        reads.current = null
      }
    }, [])
    let drawn: ReactNode = null
    let failed: { error: unknown } | null = null
    const draw = () => {
      try {
        drawn = render(props)
      } catch (error) {
        failed = { error }
      }
    }
    owners.push(uid.current)
    try {
      if (reads.current) reads.current.track(draw)
      else untracked(draw)
    } finally {
      owners.pop()
    }
    if (failed) {
      console.error((failed as { error: unknown }).error)
      return null
    }
    return drawn
  }
  Tracked.displayName = render.name || 'Tracked'
  return memo(Tracked)
}
