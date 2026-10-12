/* <Transition> and <TransitionGroup> as Vue's (runtime-core's BaseTransition, runtime-dom's resolveTransitionProps and
   TransitionGroup), with the classes the app's CSS is written for.

   Entering: `name-enter-from` and `-enter-active` before the descendants' mounted hooks, `onEnter` after them; two frames
   later `-enter-from` gives way to `-enter-to`, and the classes go when the transition ends (its computed durations, or
   `duration`). Leaving: the child stays drawn and its own element plays the `-leave-*` run, still answering the pointer,
   while its components end as Vue unmounts them (src/leaving.ts); React takes it away when the leave ends. The leave
   starts in the commit before anything new is put in, as Vue's patch unmounts before it mounts. `css={false}` leaves it
   to the hooks; a hook that takes `done` decides when it ends. A child that comes back while its old one still leaves ends
   that leave at once; `mode="out-in"` lets the old one leave before the new one comes. The child's root element is
   reached through its `ref`, so a component child forwards `ref` to its root.

   The transition classes an element wears are kept on it (as Vue's `_vtc`) and drawn into its class too, so React drawing
   that class again keeps them. */
import { cloneElement, isValidElement, useInsertionEffect, useLayoutEffect, useReducer, useRef, useContext, type ReactElement, type ReactNode, type Ref } from 'react'
import { flushSync } from 'react-dom'
import { attachRef, releaseRefsIn } from './bind'
import { Leaving, LeavingContext } from './leaving'
import { queuePostFlushCb } from './reactivity'

type Hook = (el: HTMLElement) => void
type DoneHook = (el: HTMLElement, done: () => void) => void

export interface TransitionProps {
  name?: string
  css?: boolean
  duration?: number | { enter: number; leave: number }
  mode?: 'out-in' | 'in-out' | 'default'
  appear?: boolean
  onBeforeEnter?: Hook
  onEnter?: Hook | DoneHook
  onAfterEnter?: Hook
  onEnterCancelled?: Hook
  onBeforeLeave?: Hook
  onLeave?: Hook | DoneHook
  onAfterLeave?: Hook
  onLeaveCancelled?: Hook
  children?: ReactNode
}

/** What TransitionGroup gives each of its children's Transitions. */
interface Grouped {
  /** The group starts the leave, in its own commit, before anything new is put in. */
  starter: (start: () => void) => void
  /** The element drawn, for the group's moves. */
  onNode: (node: Marked | null) => void
  /** The element of the same key still leaving, if any. */
  leavingTwin: () => Marked | null
}

const ENTER_CB = Symbol('enterCb')
const LEAVE_CB = Symbol('leaveCb')
const MOVE_CB = Symbol('moveCb')
const VTC = Symbol('vtc')
const END_ID = Symbol('endId')

type Marked = HTMLElement & {
  [ENTER_CB]?: (cancelled?: boolean) => void
  [LEAVE_CB]?: (cancelled?: boolean) => void
  [MOVE_CB]?: ((event?: TransitionEvent) => void) | null
  [VTC]?: Set<string>
  [END_ID]?: number
  _enterCancelled?: boolean
  _isLeaving?: boolean
}

/* --- the classes, and React drawing them ------------------------------------------------------------------------- */

/** The Transition that draws each live element, to draw it again when its transition classes change. */
const drawers = new WeakMap<Element, Drawer>()
interface Drawer {
  redraw: () => void
  dirty: boolean
}
/** Set while a Transition's own effect runs: a change of class then draws in that commit. */
let inEffect = 0

function sync(el: Element): void {
  const drawer = drawers.get(el)
  if (!drawer) return
  if (inEffect) {
    drawer.dirty = true
    return
  }
  flushSync(() => drawer.redraw())
}

function addTransitionClass(el: Marked, cls: string): void {
  cls.split(/\s+/).forEach((c) => c && el.classList.add(c))
  ;(el[VTC] ??= new Set()).add(cls)
  sync(el)
}

function removeTransitionClass(el: Marked, cls: string): void {
  cls.split(/\s+/).forEach((c) => c && el.classList.remove(c))
  const vtc = el[VTC]
  if (vtc) {
    vtc.delete(cls)
    if (!vtc.size) el[VTC] = undefined
  }
  sync(el)
}

function effect(fn: () => void): void {
  inEffect++
  try {
    fn()
  } finally {
    inEffect--
  }
}

/* --- timing ------------------------------------------------------------------------------------------------------ */

const nextFrame = (fn: () => void) => requestAnimationFrame(() => requestAnimationFrame(fn))
const forceReflow = () => document.body.offsetHeight
const hasExplicitCallback = (hook: Hook | DoneHook | undefined) => !!hook && hook.length > 1

function toMs(s: string): number {
  if (s === 'auto') return 0
  return Number(s.slice(0, -1).replace(',', '.')) * 1e3
}
function getTimeout(delays: string[], durations: string[]): number {
  while (delays.length < durations.length) delays = delays.concat(delays)
  return Math.max(...durations.map((d, i) => toMs(d) + toMs(delays[i]!)))
}

function getTransitionInfo(el: Element): { type: 'transition' | 'animation' | null; timeout: number; propCount: number; hasTransform: boolean } {
  const styles = window.getComputedStyle(el)
  const list = (key: string) => ((styles as unknown as Record<string, string>)[key] || '').split(', ')
  const transitionDurations = list('transitionDuration')
  const transitionTimeout = getTimeout(list('transitionDelay'), transitionDurations)
  const animationDurations = list('animationDuration')
  const animationTimeout = getTimeout(list('animationDelay'), animationDurations)
  const timeout = Math.max(transitionTimeout, animationTimeout)
  const type = timeout > 0 ? (transitionTimeout > animationTimeout ? 'transition' : 'animation') : null
  const propCount = type ? (type === 'transition' ? transitionDurations.length : animationDurations.length) : 0
  const hasTransform = type === 'transition' && /\b(?:transform|all)(?:,|$)/.test(list('transitionProperty').toString())
  return { type, timeout, propCount, hasTransform }
}

let endId = 0
function whenTransitionEnds(el: Marked, explicitTimeout: number | undefined, resolve: () => void): void {
  const id = (el[END_ID] = ++endId)
  const resolveIfNotStale = () => {
    if (id === el[END_ID]) resolve()
  }
  if (explicitTimeout != null) {
    setTimeout(resolveIfNotStale, explicitTimeout)
    return
  }
  const { type, timeout, propCount } = getTransitionInfo(el)
  if (!type) {
    resolve()
    return
  }
  const endEvent = `${type}end`
  let ended = 0
  const end = () => {
    el.removeEventListener(endEvent, onEnd)
    resolveIfNotStale()
  }
  const onEnd = (event: Event) => {
    if (event.target === el && ++ended >= propCount) end()
  }
  setTimeout(() => {
    if (ended < propCount) end()
  }, timeout + 1)
  el.addEventListener(endEvent, onEnd)
}

/* --- one child --------------------------------------------------------------------------------------------------- */

interface Entry {
  id: string
  key: string
  element: ReactElement
  leaving: boolean
  /** Its enter was looked at (played, or not, on the first drawing). */
  entered: boolean
  leaveStarted: boolean
  /** Enter hooks on its first drawing. */
  animate: boolean
  node: Marked | null
  ref: (node: HTMLElement | null) => () => void
  release?: () => void
  signal: Leaving
  /** The props it was last drawn with; a leaving child keeps them, so nothing in it draws again. */
  props?: { ref: Entry['ref']; className?: string }
}

let nextEntryKey = 0

function originalRef(entry: Entry): Ref<HTMLElement | null> | undefined {
  return (entry.element.props as { ref?: Ref<HTMLElement | null> }).ref
}

const typeIds = new WeakMap<object, number>()
let nextTypeId = 0
function identity(element: ReactElement): string {
  const type = element.type as unknown
  let name: string
  if (typeof type === 'string') name = type
  else {
    if (!typeIds.has(type as object)) typeIds.set(type as object, ++nextTypeId)
    name = `#${typeIds.get(type as object)}`
  }
  return `${name}:${element.key ?? ''}`
}

/** Its child's components end with its leave; one inside another leaving child ends with that one. */
function Keep({ entry, children }: { entry: Entry; children: ReactNode }): ReactNode {
  const outer = useContext(LeavingContext)
  const linked = useRef<(() => void) | null>(null)
  if (outer && !linked.current) linked.current = outer.on(() => entry.signal.leave())
  useLayoutEffect(() => () => linked.current?.(), [])
  return <LeavingContext.Provider value={entry.signal}>{children}</LeavingContext.Provider>
}

/** Drawn beside a child while it stays: when it goes, its removal in the commit starts the leave. */
function Gone({ onGone }: { onGone: () => void }): null {
  const latest = useRef(onGone)
  latest.current = onGone
  useInsertionEffect(() => () => latest.current(), [])
  return null
}

interface State {
  entries: Entry[]
  mounted: boolean
  unmounting: boolean
  props: TransitionProps & { grouped?: Grouped }
  drawer: Drawer
  /** Done after the commit that takes a finished leave away. */
  afterRemoved: (() => void)[]
}

export function Transition(props: TransitionProps & { grouped?: Grouped }): ReactNode {
  const [, redraw] = useReducer((count: number) => count + 1, 0)
  const self = useRef<State | null>(null)
  if (!self.current) self.current = { entries: [], mounted: false, unmounting: false, props, drawer: { redraw, dirty: false }, afterRemoved: [] }
  const st = self.current
  st.props = props
  st.drawer.redraw = redraw

  const child = isValidElement(props.children) ? props.children : null
  const id = child ? identity(child) : null
  const live = st.entries.find((entry) => !entry.leaving)
  if (live && live.id === id) live.element = child!
  else {
    if (live) live.leaving = true
    const waiting = props.mode === 'out-in' && st.entries.some((entry) => entry.leaving)
    if (child && id && !waiting) {
      const entry: Entry = {
        id, key: `${id}#${++nextEntryKey}`, element: child, leaving: false, entered: false, leaveStarted: false,
        animate: st.mounted || !!props.appear, node: null, signal: new Leaving(),
        // One callback per entry, so React hands it the node once.
        ref: (node) => {
          if (node) {
            entry.node = node as Marked
            drawers.set(node, st.drawer)
            if (!entry.leaving) entry.release = attachRef(originalRef(entry), node)
            props.grouped?.onNode(entry.node)
          }
          return () => {
            entry.release?.()
            entry.release = undefined
            if (node) drawers.delete(node)
          }
        },
      }
      st.entries.push(entry)
    }
  }

  props.grouped?.starter(() => {
    for (const entry of st.entries) if (entry.leaving && !entry.leaveStarted) start(entry)
  })

  useInsertionEffect(() => () => {
    st.unmounting = true
  }, [])

  useLayoutEffect(() => {
    effect(() => {
      for (const entry of st.entries) {
        if (entry.entered || entry.leaving) continue
        entry.entered = true
        if (entry.animate) beforeEnter(entry)
      }
    })
    st.mounted = true
    const after = st.afterRemoved.splice(0)
    for (const fn of after) fn()
    if (st.drawer.dirty) {
      st.drawer.dirty = false
      redraw()
    }
  })

  /** The child's leave, from the commit that took it away: its components end, then its element leaves. */
  function start(entry: Entry): void {
    if (entry.leaveStarted || st.unmounting) return
    entry.leaveStarted = true
    // As Vue unmounts it: the parent's ref to it goes, its components end (their beforeUnmount hooks still see their
    // refs), then every template ref on and in its element lets go.
    entry.release?.()
    entry.release = undefined
    entry.signal.leave()
    if (entry.node) {
      drawers.delete(entry.node)
      releaseRefsIn(entry.node)
    }
    effect(() => leave(entry))
  }

  /** Takes a child away, then `after` once React has. */
  function remove(entry: Entry, after: () => void): void {
    st.entries = st.entries.filter((other) => other !== entry)
    st.afterRemoved.push(after)
    if (inEffect) queueMicrotask(() => flushSync(redraw))
    else flushSync(redraw)
  }

  function beforeEnter(entry: Entry): void {
    const p = st.props
    const el = entry.node
    if (!el) return
    // The same child still leaving ends its leave at once.
    for (const old of st.entries) if (old !== entry && old.leaving && old.id === entry.id) old.node?.[LEAVE_CB]?.()
    p.grouped?.leavingTwin()?.[LEAVE_CB]?.()
    p.onBeforeEnter?.(el)
    if (p.css !== false) {
      const name = p.name ?? 'v'
      addTransitionClass(el, `${name}-enter-from`)
      addTransitionClass(el, `${name}-enter-active`)
    }
    queuePostFlushCb(() => enter(entry))
  }

  function enter(entry: Entry): void {
    const el = entry.node
    if (!el || entry.leaving) return
    const p = st.props
    let called = false
    el[ENTER_CB] = (cancelled) => {
      if (called) return
      called = true
      if (cancelled) {
        if (p.css !== false) finishEnter(el, true)
        p.onEnterCancelled?.(el)
      } else p.onAfterEnter?.(el)
      el[ENTER_CB] = undefined
    }
    const done = () => el[ENTER_CB]?.(false)
    if (p.css === false) {
      if (p.onEnter) {
        ;(p.onEnter as DoneHook)(el, done)
        if (!hasExplicitCallback(p.onEnter)) done()
      } else done()
      return
    }
    const name = p.name ?? 'v'
    const duration = typeof p.duration === 'object' ? p.duration.enter : p.duration
    const resolve = () => finishEnter(el, false, done)
    ;(p.onEnter as DoneHook | undefined)?.(el, resolve)
    nextFrame(() => {
      removeTransitionClass(el, `${name}-enter-from`)
      addTransitionClass(el, `${name}-enter-to`)
      if (!hasExplicitCallback(p.onEnter)) whenTransitionEnds(el, duration, resolve)
    })
  }

  function finishEnter(el: Marked, cancelled: boolean, done?: () => void): void {
    const name = st.props.name ?? 'v'
    el._enterCancelled = cancelled
    removeTransitionClass(el, `${name}-enter-to`)
    removeTransitionClass(el, `${name}-enter-active`)
    done?.()
  }

  function leave(entry: Entry): void {
    const p = st.props
    const el = entry.node
    if (!el) {
      remove(entry, () => undefined)
      return
    }
    el[ENTER_CB]?.(true)
    p.onBeforeLeave?.(el)
    let called = false
    el[LEAVE_CB] = (cancelled) => {
      if (called) return
      called = true
      el[LEAVE_CB] = undefined
      remove(entry, () => {
        if (cancelled) {
          if (p.css !== false) finishLeave(el)
          p.onLeaveCancelled?.(el)
        } else p.onAfterLeave?.(el)
      })
    }
    const done = () => el[LEAVE_CB]?.(false)
    if (p.css === false) {
      if (p.onLeave) {
        ;(p.onLeave as DoneHook)(el, done)
        if (!hasExplicitCallback(p.onLeave)) done()
      } else done()
      return
    }
    const name = p.name ?? 'v'
    const duration = typeof p.duration === 'object' ? p.duration.leave : p.duration
    el._isLeaving = true
    const resolve = () => finishLeave(el, done)
    addTransitionClass(el, `${name}-leave-from`)
    if (!el._enterCancelled) {
      forceReflow()
      addTransitionClass(el, `${name}-leave-active`)
    } else {
      addTransitionClass(el, `${name}-leave-active`)
      forceReflow()
    }
    nextFrame(() => {
      if (!el._isLeaving) return
      removeTransitionClass(el, `${name}-leave-from`)
      addTransitionClass(el, `${name}-leave-to`)
      if (!hasExplicitCallback(p.onLeave)) whenTransitionEnds(el, duration, resolve)
    })
    ;(p.onLeave as DoneHook | undefined)?.(el, resolve)
  }

  function finishLeave(el: Marked, done?: () => void): void {
    const name = st.props.name ?? 'v'
    el._isLeaving = false
    removeTransitionClass(el, `${name}-leave-from`)
    removeTransitionClass(el, `${name}-leave-to`)
    removeTransitionClass(el, `${name}-leave-active`)
    done?.()
  }

  const drawn: ReactNode[] = []
  for (const entry of st.entries) {
    if (!entry.leaving) {
      const own = (entry.element.props as { className?: string }).className
      const vtc = entry.node?.[VTC]
      const classes = vtc ? [...vtc].join(' ') : ''
      const className = classes ? (own ? `${own} ${classes}` : classes) : undefined
      if (!entry.props || entry.props.className !== className) entry.props = className === undefined ? { ref: entry.ref } : { ref: entry.ref, className }
    }
    drawn.push(
      <Keep key={entry.key} entry={entry}>
        {cloneElement(entry.element as ReactElement<{ ref?: Ref<HTMLElement | null>; className?: string }>, entry.props ?? { ref: entry.ref })}
      </Keep>,
    )
    if (!entry.leaving && !props.grouped) drawn.push(<Gone key={`gone:${entry.key}`} onGone={() => start(entry)} />)
  }
  return drawn
}

/* --- a list ------------------------------------------------------------------------------------------------------ */

function hasCSSTransform(el: Marked, moveClass: string): boolean {
  const container = el.parentNode
  if (!container) return false
  const clone = el.cloneNode() as HTMLElement
  el[VTC]?.forEach((cls) => cls.split(/\s+/).forEach((c) => c && clone.classList.remove(c)))
  moveClass.split(/\s+/).forEach((c) => c && clone.classList.add(c))
  clone.style.display = 'none'
  container.appendChild(clone)
  const { hasTransform } = getTransitionInfo(clone)
  container.removeChild(clone)
  return hasTransform
}

/* <TransitionGroup> without a tag: each keyed child enters and leaves as in <Transition>; one that left stays where it
   stood until its leave ends; one added after the group's first drawing enters. When the list is drawn again, the children
   of the last drawing that moved glide from where they stood, wearing `name-move` (when that class has a transition on
   transform), and any enter or move still running ends first. */
export function TransitionGroup({ children, onAfterLeave, ...props }: Omit<TransitionProps, 'mode'>): ReactNode {
  const [, redraw] = useReducer((count: number) => count + 1, 0)
  // `drawn` is the key React knows it by: one that comes back while its old one still leaves is a new one.
  const shown = useRef<{ key: string; drawn: string; element: ReactElement; leaving: boolean; late: boolean }[]>([])
  const first = useRef(true)
  const nodes = useRef(new Map<string, Marked>()).current
  const starters = useRef(new Map<string, () => void>()).current
  const unmounting = useRef(false)
  const latest = useRef(props)
  latest.current = props

  // Where the children of the last drawing stand now, before this one is put in.
  const prev = shown.current.filter((entry) => !entry.leaving).flatMap((entry) => {
    const el = nodes.get(entry.drawn)
    return el?.isConnected ? [{ el, from: el.getBoundingClientRect() }] : []
  })

  const now = (Array.isArray(children) ? children.flat() : [children]).filter(isValidElement) as ReactElement[]
  const keys = new Set(now.map((element) => String(element.key)))
  const before = shown.current
  const next: typeof before = now.map((element) => {
    const key = String(element.key)
    const old = before.find((entry) => entry.key === key && !entry.leaving)
    return { key, drawn: old ? old.drawn : `${key}#${++nextEntryKey}`, element, leaving: false, late: old ? old.late : !first.current }
  })
  before.forEach((entry, index) => {
    if (keys.has(entry.key) && !entry.leaving) return
    const after = before.slice(0, index).reverse().find((other) => next.some((n) => n.key === other.key))
    const at = after ? next.findIndex((n) => n.key === after.key) + 1 : 0
    next.splice(at, 0, { ...entry, leaving: true })
  })
  shown.current = next
  const wasFirst = first.current
  first.current = false

  useInsertionEffect(() => () => {
    unmounting.current = true
  }, [])

  useLayoutEffect(() => {
    if (wasFirst || !prev.length) return
    const moveClass = `${latest.current.name ?? 'v'}-move`
    if (!hasCSSTransform(prev[0]!.el, moveClass)) return
    effect(() => {
      for (const { el } of prev) {
        el[MOVE_CB]?.()
        el[ENTER_CB]?.()
      }
      const moved = prev.filter(({ el, from }) => {
        const to = el.getBoundingClientRect()
        const dx = from.left - to.left
        const dy = from.top - to.top
        if (!dx && !dy) return false
        const s = el.style
        let scaleX = el.offsetWidth ? to.width / el.offsetWidth : 1
        let scaleY = el.offsetHeight ? to.height / el.offsetHeight : 1
        if (!Number.isFinite(scaleX) || scaleX === 0) scaleX = 1
        if (!Number.isFinite(scaleY) || scaleY === 0) scaleY = 1
        if (Math.abs(scaleX - 1) < 0.01) scaleX = 1
        if (Math.abs(scaleY - 1) < 0.01) scaleY = 1
        s.transform = `translate(${dx / scaleX}px,${dy / scaleY}px)`
        s.transitionDuration = '0s'
        return true
      })
      forceReflow()
      for (const { el } of moved) {
        const s = el.style
        addTransitionClass(el, moveClass)
        s.transform = s.transitionDuration = ''
        const cb = (el[MOVE_CB] = (event?: TransitionEvent) => {
          if (event && event.target !== el) return
          if (!event || event.propertyName.endsWith('transform')) {
            el.removeEventListener('transitionend', cb)
            el[MOVE_CB] = null
            removeTransitionClass(el, moveClass)
          }
        })
        el.addEventListener('transitionend', cb)
      }
    })
    for (const { el } of prev) {
      const drawer = drawers.get(el)
      if (drawer?.dirty) {
        drawer.dirty = false
        drawer.redraw()
      }
    }
  })

  const drawn: ReactNode[] = []
  for (const entry of next) {
    drawn.push(
      <Transition
        key={entry.drawn}
        {...props}
        appear={entry.late}
        grouped={{
          starter: (start) => starters.set(entry.drawn, start),
          onNode: (node) => {
            if (node) nodes.set(entry.drawn, node)
          },
          leavingTwin: () => {
            const twin = shown.current.find((other) => other.key === entry.key && other.leaving && other.drawn !== entry.drawn)
            return twin ? nodes.get(twin.drawn) ?? null : null
          },
        }}
        onAfterLeave={(el) => {
          onAfterLeave?.(el)
          shown.current = shown.current.filter((other) => other.drawn !== entry.drawn)
          nodes.delete(entry.drawn)
          starters.delete(entry.drawn)
          redraw()
        }}
      >
        {entry.leaving ? null : entry.element}
      </Transition>,
    )
    if (!entry.leaving) {
      drawn.push(<Gone key={`gone:${entry.drawn}`} onGone={() => {
        if (!unmounting.current) starters.get(entry.drawn)?.()
      }} />)
    }
  }
  return drawn
}
