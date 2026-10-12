// Brushing an answer away (docs/design/agent-fixes.md, fix 8). An answer waiting in the field goes back into the circle with a
// sideways swipe on the trackpad or a drag down, as it does with Esc (SearchBar.tsx's `sendBack`); the conversation keeps it.
//
// How it moves (kk-motion): by hand the shape follows the hand one to one, so it never lags and never jumps to meet it; the
// first few pixels of a press are slop, taken off so the shape starts exactly where it was grabbed. Past its limit it gives
// less the further it is pulled, and upward, where nothing goes, it gives from the start. What happens at the end is the
// system's: letting go far enough, or flicking quickly (above 0.11 px/ms, whatever the distance), sends the answer back and the
// shape lands in the circle on the field's own curve in one movement with its shrinking, with no overshoot; short of that it
// returns to its place, on the same curve (circleField.css gives the transform that timing in every state). A trackpad has no
// release to read: a swipe ends when the wheel has been quiet for a moment, or as soon as it has gone far enough. Reduced
// motion keeps the hand-following and drops the returns.
/** Pixels a press may move and still be a click; the first of them are also the drag's slop. */
const SLOP = 8
/** Pixels down a held drag must go before letting go sends the answer back. */
const DRAG_COMMIT = 36
/** px per ms: a flick this fast sends it back whatever the distance (kk-motion's 0.11). */
const FLICK = 0.11
/** Pixels a sideways swipe must go before the answer goes. */
const SWIPE_COMMIT = 64
/** ms of a quiet wheel that end a swipe which did not go far enough. */
const SWIPE_QUIET = 140
/** How far a drag down follows the hand one to one before it starts to give. */
const FREE = 140
/** The pull at which the giving halves. */
const GIVE = 200

/** Past its limit a thing moves less the further it is pulled (kk-motion: edges give, then hold). */
function rubber(over: number, dim: number): number {
  return (over * dim * 0.55) / (dim + 0.55 * Math.abs(over))
}

/** What is added to a wheel's deltas so a mouse wheel's lines and a page's worth count as pixels. */
function pixels(event: WheelEvent, delta: number): number {
  return event.deltaMode === 1 ? delta * 16 : event.deltaMode === 2 ? delta * innerHeight : delta
}

export interface Brush {
  stop(): void
  /** True once, right after a gesture that moved the shape: its click is not a click on the answer. */
  swallowed(): boolean
}

/** Lets `shape` be brushed away while `active()` says there is an answer to brush; `sendBack()` is what then happens. */
export function brush(shape: HTMLElement, active: () => boolean, sendBack: () => void): Brush {
  let swallow = false
  let swallowTimer: ReturnType<typeof setTimeout> | null = null
  const swallowNext = () => {
    swallow = true
    if (swallowTimer) clearTimeout(swallowTimer)
    swallowTimer = setTimeout(() => { swallow = false }, 80)
  }

  const place = (x: number, y: number) => { shape.style.transform = x || y ? `translate3d(${x}px, ${y}px, 0)` : '' }
  /** The shape goes home, sent back or not, by the stylesheet's own transition for it: the circle forming is one movement
   *  with it, and a returning shape takes the same curve (reduced motion has none, and it is home at once). */
  function release(): void {
    shape.style.willChange = ''
    shape.style.transition = ''
    place(0, 0)
  }
  function hold(): void {
    shape.style.transition = 'none'
    shape.style.willChange = 'transform'
  }

  // --- a drag down ------------------------------------------------------------------------------------------------------
  let press: { id: number; x: number; y: number; samples: { t: number; y: number }[]; dragging: boolean; moved: number } | null = null
  function onPointerDown(event: PointerEvent): void {
    if (!active() || (event.pointerType === 'mouse' && event.button !== 0)) return
    press = { id: event.pointerId, x: event.clientX, y: event.clientY, samples: [{ t: event.timeStamp, y: event.clientY }], dragging: false, moved: 0 }
  }
  function onPointerMove(event: PointerEvent): void {
    if (!press || event.pointerId !== press.id) return
    const dx = event.clientX - press.x
    const dy = event.clientY - press.y
    press.moved = Math.max(press.moved, Math.hypot(dx, dy))
    if (!press.dragging) {
      if (dy <= SLOP || dy <= Math.abs(dx)) return  // a drag down: what goes another way is not ours
      press.dragging = true
      shape.setPointerCapture(event.pointerId)
      hold()
    }
    press.samples.push({ t: event.timeStamp, y: event.clientY })
    if (press.samples.length > 6) press.samples.shift()
    const pulled = dy - SLOP
    place(0, pulled < 0 ? -rubber(-pulled, 120) : pulled <= FREE ? pulled : FREE + rubber(pulled - FREE, GIVE))
    event.preventDefault()
  }
  function onPointerUp(event: PointerEvent): void {
    if (!press || event.pointerId !== press.id) return
    const { dragging, moved, samples, y } = press
    press = null
    if (moved > SLOP) swallowNext()
    if (!dragging) return
    const pulled = event.clientY - y - SLOP
    const first = samples[0]!
    const last = samples[samples.length - 1]!
    const speed = last.t > first.t ? (last.y - first.y) / (last.t - first.t) : 0
    const sentBack = pulled >= DRAG_COMMIT || (speed >= FLICK && pulled >= 8)
    release()
    if (sentBack) sendBack()
  }
  function onPointerCancel(event: PointerEvent): void {
    if (!press || event.pointerId !== press.id) return
    const { dragging } = press
    press = null
    if (dragging) release()
  }

  // --- a sideways swipe -------------------------------------------------------------------------------------------------
  let swept = 0
  let swiping = false
  let tail = false  // the momentum after a swipe that has already sent the answer back
  let quiet: ReturnType<typeof setTimeout> | null = null
  function onWheel(event: WheelEvent): void {
    if (!active() && !tail) return
    const dx = pixels(event, event.deltaX)
    const dy = pixels(event, event.deltaY)
    if (!swiping && !tail && Math.abs(dx) <= Math.abs(dy)) return  // a swipe is sideways; the rest is not ours
    event.preventDefault()  // or the browser takes the sideways swipe for going back
    if (quiet) clearTimeout(quiet)
    quiet = setTimeout(() => {
      quiet = null
      if (swiping) release()
      swiping = tail = false
      swept = 0
    }, SWIPE_QUIET)
    if (tail) return
    if (!swiping) { swiping = true; hold() }
    swept -= dx  // the answer moves as a page would under the fingers
    place(swept, 0)
    if (Math.abs(swept) >= SWIPE_COMMIT) {
      swiping = false
      tail = true
      swept = 0
      release()
      sendBack()
    }
  }

  shape.addEventListener('pointerdown', onPointerDown)
  shape.addEventListener('pointermove', onPointerMove)
  shape.addEventListener('pointerup', onPointerUp)
  shape.addEventListener('pointercancel', onPointerCancel)
  shape.addEventListener('wheel', onWheel, { passive: false })
  return {
    stop() {
      shape.removeEventListener('pointerdown', onPointerDown)
      shape.removeEventListener('pointermove', onPointerMove)
      shape.removeEventListener('pointerup', onPointerUp)
      shape.removeEventListener('pointercancel', onPointerCancel)
      shape.removeEventListener('wheel', onWheel)
      if (quiet) clearTimeout(quiet)
      if (swallowTimer) clearTimeout(swallowTimer)
    },
    swallowed() {
      const was = swallow
      swallow = false
      return was
    },
  }
}
