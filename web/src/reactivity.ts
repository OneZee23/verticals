/* The store's reactivity, on MobX: `reactive`, `ref`, `computed`, `watch`, `watchEffect` and `effectScope` for store.ts,
   lib/ and the components' setups, and the order of a tick. After a change, in one microtask and component by component,
   parents first: pre-render watchers (`flush: 'pre'`, the default), then the component's drawing (components wrapped in
   `tracked()`); then `flush: 'post'` watchers and `queuePostFlushCb` jobs; `nextTick` resolves after all of it.
   `flush: 'sync'` runs at the change itself. Lifecycle hooks belong to useSetup() (src/setup.ts). */
import { flushSync } from 'react-dom'
import { _getGlobalState, computed as mobxComputed, configure, isObservable, observable, Reaction, untracked } from 'mobx'

export { onBeforeUnmount, onMounted, onUnmounted } from './setup'

// Writes come from anywhere (event handlers, fetch callbacks, watchers), as the store was written for; objects and arrays
// are proxies, so new keys and indexes are observed too.
configure({ enforceActions: 'never', useProxies: 'always' })

type Phase = 'pre' | 'render' | 'post'

/* Components are numbered as they are made, a parent before its children, The tick's queue runs in
   that order: a component's pre-render watchers, then its drawing, then the next component's. A child that its parent's
   drawing took away never runs its own watchers, since its scope has stopped by then. Watchers made outside a component
   run first. `flush: 'post'` jobs follow the whole queue. */
let lastUid = 0
export function nextUid(): number {
  return ++lastUid
}
/** The component being set up or drawn now, whose watchers take its number. */
export const owners: number[] = []
function owner(): number | undefined {
  return owners[owners.length - 1]
}

interface Queued {
  job: () => void
  id: number
  render: boolean
}
const queue: Queued[] = []
const queued = new Set<() => void>()
const post = new Set<() => void>()
let flushing: Promise<void> | null = null

function run(job: () => void, render: boolean): void {
  try {
    if (render) flushSync(job)
    else job()
  } catch (error) {
    console.error(error) // one job's error does not stop the tick
  }
}

function flush(): void {
  try {
    while (queue.length || post.size) {
      while (queue.length) {
        const next = queue.shift()!
        queued.delete(next.job)
        run(next.job, next.render)
      }
      for (const job of [...post]) {
        post.delete(job)
        run(job, false)
      }
    }
  } finally {
    flushing = null
  }
}

/** This tick's queue now: a field's own input has to be drawn before the event is over. */
export function flushNow(): void {
  if (queue.length || post.size) flush()
}

/** Runs `job` once in this tick's `phase`, in its component's place, however often it is queued before then. */
export function queueJob(phase: Phase, job: () => void, id = owner()): void {
  if (phase === 'post') post.add(job)
  else if (!queued.has(job)) {
    const render = phase === 'render'
    const entry = { job, id: id ?? (render ? Infinity : -1), render }
    let at = queue.length
    while (at > 0 && (queue[at - 1]!.id > entry.id || (queue[at - 1]!.id === entry.id && queue[at - 1]!.render && !render))) at--
    queue.splice(at, 0, entry)
    queued.add(job)
  }
  flushing ??= Promise.resolve().then(flush)
}

/** A component's pre-render watchers, by its number. */
const preWatchers = new Map<number, Set<{ watcher: Reaction; job: () => void }>>()

/** A component's own pre-render watchers now, untracked: one whose props changed runs them before it draws. Its props
 *  are written while its drawing is tracked, so a watcher they made stale is still waiting for that to end. */
export function flushPre(id: number): void {
  const mine = queue.filter((entry) => entry.id === id && !entry.render).map((entry) => entry.job)
  for (const job of mine) {
    queue.splice(queue.findIndex((entry) => entry.job === job), 1)
    queued.delete(job)
  }
  for (const { watcher, job } of preWatchers.get(id) ?? []) if (watcher.isScheduled && !mine.includes(job)) mine.push(job)
  if (!mine.length) return
  untracked(() => {
    for (const job of mine) run(job, false)
  })
}

export function queuePostFlushCb(job: () => void): void {
  queueJob('post', job)
}

export function nextTick<T = void>(fn?: () => T): Promise<Awaited<T>> {
  // After the tick's flush, as Vue's: the one queued now, or, inside a MobX batch whose reactions have not queued theirs
  // yet, the one they will queue when it ends.
  const done = _getGlobalState().inBatch > 0
    ? Promise.resolve().then(() => flushing ?? undefined)
    : flushing ?? Promise.resolve()
  return (fn ? done.then(fn) : done) as Promise<Awaited<T>>
}

/* --- values ------------------------------------------------------------------------------------------------------- */

export interface Ref<T = any> {
  value: T
}
export interface ComputedRef<T = any> {
  readonly value: T
}
export type ShallowRef<T = any> = Ref<T>
export type WatchSource<T = any> = Ref<T> | ComputedRef<T> | (() => T)
export type WatchStopHandle = () => void
export interface WatchHandle extends WatchStopHandle {
  stop(): void
}

const REF = Symbol('ref')

class RefImpl<T> implements Ref<T> {
  readonly [REF] = true
  private readonly box
  constructor(value: T, deep: boolean) {
    this.box = observable.box(value, { deep })
  }
  get value(): T {
    return this.box.get()
  }
  set value(value: T) {
    this.box.set(value)
  }
}

class ComputedImpl<T> implements ComputedRef<T> {
  readonly [REF] = true
  private keeper: Reaction | null = null
  constructor(private readonly cell: { get(): T }, private readonly scope: Scope | undefined) {}
  get value(): T {
    // Cached from its first read until what it read changes, observed or not: a reaction that never runs again keeps it
    // observed for as long as its scope lives, so a read recomputes only after a change.
    if (this.scope?.active && !this.keeper) {
      const keeper = new Reaction('computed', () => undefined)
      this.keeper = keeper
      this.scope.add(() => keeper.dispose())
      keeper.track(() => this.cell.get())
    }
    return this.cell.get()
  }
}

function isRef(value: unknown): value is Ref | ComputedRef {
  return !!value && typeof value === 'object' && REF in value
}

/** A deep observable: nested objects, arrays, maps and sets are observed as they are reached and assigned. */
export function reactive<T extends object>(value: T): T {
  return observable(value, undefined, { deep: true, proxy: true })
}

export function ref<T>(value: T): Ref<T>
export function ref<T = any>(): Ref<T | undefined>
export function ref<T>(value?: T): Ref<T | undefined> {
  return new RefImpl(value, true)
}

/** A ref whose value is kept as it is: a DOM node, a list replaced whole. */
export function shallowRef<T>(value: T): ShallowRef<T>
export function shallowRef<T = any>(): ShallowRef<T | undefined>
export function shallowRef<T>(value?: T): ShallowRef<T | undefined> {
  return new RefImpl(value, false)
}

/** A cached value, recomputed on the first read after what it read changes. One made at module level stays for good;
 *  one made in a component's setup goes with the component. */
export function computed<T>(getter: () => T): ComputedRef<T> {
  return new ComputedImpl(mobxComputed(getter, { keepAlive: !activeScope }), activeScope)
}

/* --- scopes ------------------------------------------------------------------------------------------------------- */

export interface EffectScope {
  readonly active: boolean
  run<T>(fn: () => T): T | undefined
  stop(): void
}

let activeScope: Scope | undefined

class Scope implements EffectScope {
  active = true
  private readonly stops: (() => void)[] = []
  constructor(parent: Scope | undefined) {
    parent?.add(() => this.stop())
  }
  add(stop: () => void): void {
    if (this.active) this.stops.push(stop)
    else stop()
  }
  run<T>(fn: () => T): T | undefined {
    if (!this.active) return undefined
    const outer = activeScope
    activeScope = this
    try {
      return fn()
    } finally {
      activeScope = outer
    }
  }
  stop(): void {
    if (!this.active) return
    this.active = false
    for (const stop of this.stops.splice(0)) stop()
  }
}

/** What watchers and effects are made inside `run` stop together; a detached scope is not stopped with the one around it. */
export function effectScope(detached = false): EffectScope {
  return new Scope(detached ? undefined : activeScope)
}

/* --- watchers ----------------------------------------------------------------------------------------------------- */

type Flush = 'pre' | 'post' | 'sync'
type OnCleanup = (fn: () => void) => void
export type WatchCallback<V = any, OV = any> = (value: V, oldValue: OV, onCleanup: OnCleanup) => any
type MaybeUndefined<T, I> = I extends true ? T | undefined : T
type MapSources<T, Immediate> = {
  [K in keyof T]: T[K] extends WatchSource<infer V> ? MaybeUndefined<V, Immediate> : T[K] extends object ? MaybeUndefined<T[K], Immediate> : never
}
type MultiWatchSources = (WatchSource<unknown> | object)[]
export interface WatchEffectOptions {
  flush?: Flush
}
export interface WatchOptions<Immediate = boolean> extends WatchEffectOptions {
  immediate?: Immediate
  once?: boolean
}

/** Runs a reaction's turn in its component's place in the tick, or at the change itself for `flush: 'sync'`. */
function scheduler(flush: Flush | undefined): ((run: () => void) => void) | undefined {
  if (flush === 'sync') return undefined
  const id = owner()
  return (run) => queueJob(flush === 'post' ? 'post' : 'pre', run, id)
}

/** Reads every property below an observable, so a watcher of the whole object hears a change anywhere in it. */
function traverse(value: unknown, seen = new Set<unknown>()): unknown {
  if (!value || typeof value !== 'object' || seen.has(value) || !isObservable(value)) return value
  seen.add(value)
  if (value instanceof Map) value.forEach((item, key) => { traverse(key, seen); traverse(item, seen) })
  else if (value instanceof Set) value.forEach((item) => traverse(item, seen))
  else for (const key of Object.keys(value)) traverse((value as Record<string, unknown>)[key], seen)
  return value
}

function reader(source: unknown): { read: () => unknown; whole: boolean } {
  if (isRef(source)) return { read: () => source.value, whole: false }
  if (typeof source === 'function') return { read: source as () => unknown, whole: false }
  return { read: () => traverse(source), whole: true }
}

function changed(next: unknown, prev: unknown, many: boolean): boolean {
  if (!many) return !Object.is(next, prev)
  const a = next as unknown[]
  const b = prev as unknown[] | undefined
  return !b || a.length !== b.length || a.some((item, at) => !Object.is(item, b[at]))
}

export function watch<T, Immediate extends Readonly<boolean> = false>(source: WatchSource<T>, cb: WatchCallback<T, MaybeUndefined<T, Immediate>>, options?: WatchOptions<Immediate>): WatchHandle
export function watch<T extends Readonly<MultiWatchSources>, Immediate extends Readonly<boolean> = false>(sources: readonly [...T] | T, cb: WatchCallback<MapSources<T, false>, MapSources<T, Immediate>>, options?: WatchOptions<Immediate>): WatchHandle
export function watch<T extends object, Immediate extends Readonly<boolean> = false>(source: T, cb: WatchCallback<T, MaybeUndefined<T, Immediate>>, options?: WatchOptions<Immediate>): WatchHandle
export function watch(source: unknown, cb: WatchCallback, options: WatchOptions = {}): WatchHandle {
  const many = Array.isArray(source) && !isObservable(source)
  const readers = many ? (source as unknown[]).map(reader) : [reader(source)]
  const whole = readers.some((r) => r.whole)
  const read = many ? () => readers.map((r) => r.read()) : readers[0]!.read
  let cleanup: (() => void) | undefined
  const onCleanup: OnCleanup = (fn) => { cleanup = fn }
  let stopped = false
  let current: unknown
  const queue = scheduler(options.flush)
  // The source is tracked; the callback runs after, outside the tracking, so what it writes is heard at once.
  const measure = (): unknown => {
    let value: unknown
    watcher.track(() => { value = read() })
    return value
  }
  const call = (value: unknown, old: unknown): void => {
    const before = cleanup
    cleanup = undefined
    if (before) untracked(before)
    cb(value, old, onCleanup)
    if (options.once) stop()
  }
  const job = (): void => {
    if (stopped) return
    const value = measure()
    // A watcher of a whole object hears any change in it, the object staying the same one.
    if (!whole && !changed(value, current, many)) return
    const old = current
    current = value
    call(value, old)
  }
  const watcher = new Reaction('watch', () => (queue ? queue(job) : job()))
  current = measure()
  if (options.immediate) call(current, many ? [] : undefined)
  const id = (options.flush ?? 'pre') === 'pre' ? owner() : undefined
  const entry = { watcher, job }
  if (id !== undefined) {
    if (!preWatchers.has(id)) preWatchers.set(id, new Set())
    preWatchers.get(id)!.add(entry)
  }
  function stop(): void {
    if (stopped) return
    stopped = true
    watcher.dispose()
    if (id !== undefined) {
      const set = preWatchers.get(id)
      set?.delete(entry)
      if (!set?.size) preWatchers.delete(id)
    }
    cleanup?.()
  }
  activeScope?.add(stop)
  return Object.assign(stop, { stop })
}

export function watchEffect(effect: (onCleanup: OnCleanup) => void, options: WatchEffectOptions = {}): WatchHandle {
  // Runs at once, then again in the tick after anything it read changes; it may write, as an autorun does.
  let cleanup: (() => void) | undefined
  const queue = scheduler(options.flush)
  const run = (): void => {
    if (effectReaction.isDisposed) return
    const before = cleanup
    cleanup = undefined
    if (before) untracked(before)
    effectReaction.track(() => {
      effect((fn) => { cleanup = fn })
    })
  }
  const effectReaction = new Reaction('watchEffect', () => (queue ? queue(run) : run()))
  run()
  const stop = () => {
    effectReaction.dispose()
    cleanup?.()
  }
  activeScope?.add(stop)
  return Object.assign(stop, { stop })
}
