/* A component's setup: `useSetup(props, fn)` runs `fn` once, with `props` as an observable object that follows what the
   parent passes, so the store's composables (useCardLift, useGroupWash, ...) and a component's own computed and watch
   work inside it. What `fn` creates lives in one scope and stops when the component ends. The hooks run as Vue runs them:
   `onMounted` in the tick's post queue once its DOM is in place, `onBeforeUnmount` as it ends, `onUnmounted` in the post
   queue after it is gone, the deepest first; each in its scope, untracked. A component ends when React takes it away, or
   when a <Transition> child it is in starts to leave (src/leaving.ts). An error in setup or a hook is logged and the rest
   goes on, as in Vue. */
import { observable, untracked } from 'mobx'
import { useContext, useLayoutEffect, useRef } from 'react'
import { releaseRefs } from './bind'
import { LeavingContext } from './leaving'
import { effectScope, flushPre, owners, queuePostFlushCb, watch, type EffectScope, type Ref } from './reactivity'

interface Hooks {
  mounted: (() => void)[]
  beforeUnmount: (() => void)[]
  unmounted: (() => void)[]
}

const setups: Hooks[] = []

function current(hook: string): Hooks {
  const hooks = setups[setups.length - 1]
  if (!hooks) throw new Error(`${hook}() is called outside useSetup()`)
  return hooks
}

export function onMounted(fn: () => void): void {
  current('onMounted').mounted.push(fn)
}

export function onBeforeUnmount(fn: () => void): void {
  current('onBeforeUnmount').beforeUnmount.push(fn)
}

export function onUnmounted(fn: () => void): void {
  current('onUnmounted').unmounted.push(fn)
}

interface Made<P, T> {
  /** The component's number (tracked.ts), for its own watchers. */
  id: number | undefined
  props: P
  value: T
  scope: EffectScope
  hooks: Hooks
  ended: boolean
  /** Lets go of the leaving subtree it is in. */
  off?: () => void
}

/** Runs hooks as their component: its number for the watchers they make, its scope while it lives, its hooks for the
 *  ones they add, untracked. */
function runHooks(made: Made<unknown, unknown>, fns: (() => void)[]): void {
  if (made.id !== undefined) owners.push(made.id)
  setups.push(made.hooks)
  try {
    for (const fn of fns) {
      try {
        untracked(() => (made.scope.active ? made.scope.run(fn) : fn()))
      } catch (error) {
        console.error(error)
      }
    }
  } finally {
    setups.pop()
    if (made.id !== undefined) owners.pop()
  }
}

/** The component ends: its beforeUnmount hooks, its effects, its template refs; what is left (its unmounted hooks) runs
 *  after it is gone. */
function end(made: Made<unknown, unknown>): (() => void) | void {
  if (made.ended) return
  made.ended = true
  runHooks(made, made.hooks.beforeUnmount)
  made.scope.stop()
  if (made.id !== undefined) releaseRefs(made.id)
  return () => runHooks(made, made.hooks.unmounted)
}

/* The unmounted hooks of what React took away in one commit, run in the post queue: React ends a parent before its
   children, Vue's hooks run the children's first. */
const unmountedBatch: (() => void)[] = []
function flushUnmounted(): void {
  for (const fn of unmountedBatch.splice(0).reverse()) fn()
}

export function useSetup<P extends object, T>(props: P, setup: (props: P) => T): T {
  const made = useRef<Made<P, T> | null>(null)
  const leaving = useContext(LeavingContext)
  if (!made.current) {
    const hooks: Hooks = { mounted: [], beforeUnmount: [], unmounted: [] }
    const scope = effectScope(true)
    const reactiveProps = observable({ ...props }, undefined, { deep: false, proxy: true }) as P
    let value: T
    setups.push(hooks)
    try {
      // Setup reads what it needs once; the component draws from what its drawing reads, not from this.
      value = untracked(() => scope.run(() => setup(reactiveProps))) as T
    } catch (error) {
      console.error(error)
      value = {} as T
    } finally {
      setups.pop()
    }
    const m: Made<P, T> = { id: owners[owners.length - 1], props: reactiveProps, value, scope, hooks, ended: false }
    m.off = leaving?.on(() => end(m as Made<unknown, unknown>))
    made.current = m
  } else if (!made.current.ended) {
    const live = made.current.props as Record<string, unknown>
    for (const key of Object.keys(live)) if (!(key in props)) delete live[key]
    Object.assign(live, props)
    if (made.current.id !== undefined) flushPre(made.current.id)
  }
  useLayoutEffect(() => {
    const m = made.current! as Made<unknown, unknown>
    if (m.hooks.mounted.length) queuePostFlushCb(() => runHooks(m, m.hooks.mounted))
    return () => {
      m.off?.()
      const then = end(m)
      if (!then) return
      if (!unmountedBatch.length) queuePostFlushCb(flushUnmounted)
      unmountedBatch.push(then)
    }
  }, [])
  return made.current.value
}

/** A prop left undefined takes its default. Defaults are made once (a module constant), so an array or object default
 *  keeps one identity. */
export function withDefaults<P extends object, D extends Partial<P>>(props: P, defaults: D): P & Required<Pick<P, keyof D & keyof P>> {
  const out = { ...props } as Record<string, unknown>
  for (const [key, value] of Object.entries(defaults)) if (out[key] === undefined) out[key] = value
  return out as P & Required<Pick<P, keyof D & keyof P>>
}

/** `defineExpose()`: what a parent reaches through the component's ref (a `ref()` it passes as `expose`) once mounted. */
export function exposeTo<T>(target: { value: T | null } | undefined, api: T): void {
  if (!target) return
  onMounted(() => {
    target.value = api
  })
  onUnmounted(() => {
    if (target.value === api) target.value = null
  })
}

/** A native listener on a ref's element, for as long as the element is there, for a handler that needs the real event
 *  (its `currentTarget` is the element, `inputType`, a non-passive `wheel`). Inside useSetup. */
export function listen<K extends keyof HTMLElementEventMap>(
  target: Ref<HTMLElement | null>, type: K, handler: (event: HTMLElementEventMap[K]) => void, options?: AddEventListenerOptions,
): void {
  // Each element the ref reaches keeps it as long as it lives, as a template's `@event` does: a blur that fires as the
  // focused element is taken out is heard, and an element that still plays its leave still answers.
  watch(target, (el) => el?.addEventListener(type, handler as EventListener, options), { immediate: true, flush: 'sync' })
}
