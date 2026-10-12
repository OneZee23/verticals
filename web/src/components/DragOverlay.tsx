/* The flying goal while it is dragged and while it settles, in dnd-kit's DragOverlay: a pointer-transparent clone of the
   rendered row at its grab offset, and the live measure of the drop preview. The clone is taken in a `flush: 'sync'`
   watcher, at the change of the drag's id, before the board draws the source row as a ghost. dnd-kit holds the overlay at
   the pointer and keeps it through the landing, which flies it to where the goal settles (lib/dragSettle.ts). */
import { DragOverlay as DndOverlay, type DropAnimationFunction, type Modifier } from '@dnd-kit/core'
import { useCallback, type CSSProperties, type Ref as ReactRef } from 'react'
import { computed, nextTick, shallowRef, watch, type Ref } from '../reactivity'
import { store } from '../store'
import { SETTLE_EASING } from '../lib/drag'
import { dots } from '../lib/spansDrag'
import { spanGoal, spans } from '../lib/spans'
import { findGoal } from '../lib/boardIndex'
import { goalHoverBackground, goalLight, goalSquare } from '../lib/look'
import { NEUTRAL_LIGHT } from '../lib/goalColor'
import { atRest } from '../lib/cardLift'
import { reducedMotion } from '../lib/motion'
import { cx, fallthrough, sx } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './dragOverlay.css'

function cloneRenderedRow(id: string): HTMLElement | null {
  // A goal waiting above the field is the one in the hand.
  const source = document.querySelector<HTMLElement>(`[data-parked][data-goal-id="${CSS.escape(id)}"] > .goal-card__row`)
    ?? document.querySelector<HTMLElement>(`[data-goal-id="${CSS.escape(id)}"] > .goal-card__row`)
  if (!source) return null
  const clone = source.cloneNode(true) as HTMLElement
  const sources = [source, ...source.querySelectorAll<HTMLElement>('*')]
  const clones = [clone, ...clone.querySelectorAll<HTMLElement>('*')]
  sources.forEach((node, index) => {
    const style = getComputedStyle(node)
    for (const property of style) clones[index].style.setProperty(property, style.getPropertyValue(property))
    clones[index].style.pointerEvents = 'none'
    // A source caught mid-ghost would carry `visibility: hidden` onto every copied node; opacity stays, it is the card's.
    clones[index].style.visibility = 'visible'
  })
  // Copied styles freeze used sizes in px; the row's flow boxes follow the overlay's live width so the title rewraps.
  clone.style.width = '100%'
  clone.style.height = 'auto'
  for (const element of clone.querySelectorAll<HTMLElement>(
    '.goal-card__text, .goal-card__title, .goal-card__meta, .goal-card__progress',
  )) {
    element.style.width = 'auto'
    element.style.height = 'auto'
  }
  // The dots keep to the right edge as the row takes its slot's width.
  const tools = clone.querySelector<HTMLElement>('.goal-card__tools')
  if (tools) tools.style.left = 'auto'
  clone.style.opacity = '1'
  clone.classList.remove('goal-card__row--drag-source', 'goal-card__row--drop-candidate')
  /* Drag geometry is the ROW box, so the overlay stays the row; the card's look is a wrapper that bleeds the card's
     padding outward, as the resting card's background extends beyond its row. */
  const card = source.parentElement as HTMLElement
  const cardStyle = getComputedStyle(card)
  const pad = {
    top: cardStyle.paddingTop,
    right: cardStyle.paddingRight,
    bottom: cardStyle.paddingBottom,
    left: cardStyle.paddingLeft,
  }
  const box = document.createElement('div')
  box.style.position = 'absolute'
  box.style.top = `-${pad.top}`
  box.style.right = `-${pad.right}`
  box.style.bottom = `-${pad.bottom}`
  box.style.left = `-${pad.left}`
  box.style.padding = `${pad.top} ${pad.right} ${pad.bottom} ${pad.left}`
  box.style.boxSizing = 'border-box'
  // A coloured goal paints its wash on a layer behind the row and leaves its own box clear; the flying card takes it.
  const layer = getComputedStyle(source, '::before')
  const fromLayer = cardStyle.backgroundColor === 'rgba(0, 0, 0, 0)' && layer.opacity === '1'
  box.style.backgroundColor = fromLayer ? layer.backgroundColor : cardStyle.backgroundColor
  if (fromLayer) box.style.backgroundImage = layer.backgroundImage // a lifted card's wash is laid over its base
  // The goal in the hand is lit as a lifted one is on the board: its wash at the hover strength, over the board.
  else if (cardStyle.backgroundColor === 'rgba(0, 0, 0, 0)') {
    paintLight(box, card, cardStyle.getPropertyValue('--goal-hover-background').trim() || `rgb(${NEUTRAL_LIGHT.join(', ')})`)
  }
  box.style.borderRadius = cardStyle.borderRadius
  box.style.overflow = 'hidden'
  box.style.pointerEvents = 'none'
  box.setAttribute('aria-hidden', 'true')
  box.appendChild(clone)
  keepOwnColour(box, fromLayer)
  return box
}

/* The goal in the hand takes the colour a drop there would give it (`colorAfterDrop`), and its own back elsewhere. */
function keepOwnColour(box: HTMLElement, full: boolean): void {
  box.dataset.own = box.style.backgroundColor
  box.dataset.ownImage = box.style.backgroundImage
  box.dataset.ownLight = box.style.boxShadow
  if (full) box.dataset.full = ''
  box.style.transition = 'background-color 180ms ease, box-shadow 180ms ease'
  const square = box.querySelector<HTMLElement>('[data-role="checkbox-box"]')
  if (!square) return
  square.dataset.own = square.style.backgroundColor
  square.dataset.ownCheck = square.style.color
  square.style.transition = 'background-color 180ms ease, color 180ms ease'
}

/* A wash laid over the board's ground, at the hover strength unless full. As a layer, a see-through palette wash
   stays solid over the rows it passes, and its colour can ease. */
function paintLight(box: HTMLElement, card: HTMLElement, wash: string, full = false): void {
  const style = getComputedStyle(card)
  const tint = parseFloat(style.getPropertyValue('--goal-light-tint')) || 0.7
  const light = full ? wash : `color-mix(in srgb, ${wash} ${Math.round(tint * 100)}%, transparent)`
  box.style.backgroundColor = getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim() || '#fff'
  box.style.backgroundImage = 'none'
  box.style.boxShadow = `inset 0 0 0 100vmax ${light}`
}

/* A goal with subtasks drawn under it flies as the whole piece the board shows: its card and its list, copied as they
   look and where they sit around the row. */
function frozenCopy(source: HTMLElement): HTMLElement {
  const clone = source.cloneNode(true) as HTMLElement
  const sources = [source, ...source.querySelectorAll<HTMLElement>('*')]
  const clones = [clone, ...clone.querySelectorAll<HTMLElement>('*')]
  sources.forEach((node, index) => {
    const style = getComputedStyle(node)
    for (const property of style) clones[index].style.setProperty(property, style.getPropertyValue(property))
    clones[index].style.pointerEvents = 'none'
    clones[index].style.visibility = 'visible'
    // A copy must never answer a lookup for the real goal.
    for (const name of ['id', 'data-goal-id', 'data-row-key', 'data-role']) clones[index].removeAttribute(name)
  })
  return clone
}

function cloneFamily(id: string): HTMLElement | null {
  return atRest(() => copyFamily(id))
}

function copyFamily(id: string): HTMLElement | null {
  const row = document.querySelector<HTMLElement>(`[data-parked][data-goal-id="${CSS.escape(id)}"] > .goal-card__row`)
    ?? document.querySelector<HTMLElement>(`[data-goal-id="${CSS.escape(id)}"] > .goal-card__row`)
  const card = row?.parentElement
  const list = card?.nextElementSibling
  if (!row || !card || !(list instanceof HTMLElement) || !list.classList.contains('goal-card__children')) return null
  const origin = row.getBoundingClientRect()
  const family = document.createElement('div')
  family.style.position = 'absolute'
  family.style.left = '0'
  family.style.top = '0'
  family.style.pointerEvents = 'none'
  family.setAttribute('aria-hidden', 'true')
  for (const part of [card, list]) {
    const box = part.getBoundingClientRect()
    const copy = frozenCopy(part)
    copy.style.position = 'absolute'
    copy.style.margin = '0'
    copy.style.transform = 'none'
    copy.style.left = `${box.left - origin.left}px`
    copy.style.top = `${box.top - origin.top}px`
    copy.style.width = `${box.width}px`
    copy.style.height = `${box.height}px`
    // Lit as a lifted piece is on the board (lib/cardLift.ts), without its growth: the copy holds its size.
    copy.classList.add(part === card ? 'goal-card--lifted' : 'goal-card__children--lifted')
    family.appendChild(copy)
  }
  return family
}

function renderedRowHeightAtWidth(id: string, width: number): number | null {
  const box = cloneRenderedRow(id)
  const row = box?.querySelector<HTMLElement>(':scope > .goal-card__row')
  if (!row) return null
  const host = document.createElement('div')
  host.style.position = 'fixed'
  host.style.left = '-10000px'
  host.style.top = '0'
  host.style.width = `${width}px`
  host.style.visibility = 'hidden'
  host.style.pointerEvents = 'none'
  host.appendChild(row)
  document.body.appendChild(host)
  const height = row.getBoundingClientRect().height
  host.remove()
  return height > 0 ? height : null
}

/** The root's own element ref and the parent's `ref` on one element, as one stable callback. */
/** The clone waiting for the overlay's element, which dnd-kit draws once the drag has started. */
let pendingClone: HTMLElement | null = null

function useRootRef(own: Ref<HTMLElement | null>, outer: ReactRef<HTMLDivElement> | undefined): (node: HTMLDivElement | null) => void {
  return useCallback((node: HTMLDivElement | null) => {
    own.value = node
    if (node && pendingClone) {
      node.replaceChildren(pendingClone)
      pendingClone = null
    }
    if (typeof outer === 'function') outer(node)
    else if (outer) outer.current = node
  }, [own, outer])
}

/** The overlay's corner on the pointer; its own `translate` takes it back by the grab's share of its size. */
const toPointer: Modifier = ({ transform, activatorEvent, activeNodeRect }) => {
  if (!(activatorEvent instanceof PointerEvent) || !activeNodeRect) return transform
  return {
    ...transform,
    x: activatorEvent.clientX + transform.x - activeNodeRect.left,
    y: activatorEvent.clientY + transform.y - activeNodeRect.top,
  }
}

/** The landing: from where it was let go to where it settles, in the settle's time and curve, growing into the box it
 *  lands in. No settle (kept above the field), no flight. */
const settle: DropAnimationFunction = async ({ dragOverlay, transform }) => {
  const settling = store.state.drag.settling
  if (!settling) return
  const d = store.state.drag
  const node = dragOverlay.node
  const from = getComputedStyle(node)
  const base = { left: parseFloat(from.left) || 0, top: parseFloat(from.top) || 0 }
  const fx = d.width ? d.offsetX / d.width : 0
  const fy = d.height ? d.offsetY / d.height : 0
  const width = settling.width ?? d.width
  const height = settling.height ?? d.height
  node.animate([
    { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, width: from.width, height: from.height },
    {
      transform: `translate3d(${settling.left + fx * width - base.left}px, ${settling.top + fy * height - base.top}px, 0)`,
      width: `${width}px`,
      height: `${height}px`,
    },
  ], { duration: settling.duration, easing: SETTLE_EASING, fill: 'forwards' })
  // It stays, landed, until the goal's own row shows again (the settle's grace after the flight, or a press that ends it at
  // once) and has been drawn: never a frame with neither, and the flight is not undone under it.
  let stop: (() => void) | null = null
  await new Promise<void>((resolve) => {
    stop = watch(() => store.state.drag.settling, (now) => {
      if (now !== settling) resolve()
    }, { flush: 'sync' })
  })
  ;(stop as (() => void) | null)?.()
  await new Promise((resolve) => requestAnimationFrame(resolve))
}

interface Props {
  ref?: ReactRef<HTMLDivElement>
  className?: string
}

export const DragOverlay = tracked(function DragOverlay({ ref: outer, ...attrs }: Props & Record<string, unknown>) {
  const s = useSetup({}, () => {
    const overlayHost = shallowRef<HTMLElement | null>(null)
    const dragVisualId = computed(() => store.state.drag.id ?? store.state.drag.settling?.id ?? null)
    // Over the spans the goal in the hand is its colour's light wash, lit from under.
    const light = computed(() => {
      const id = dragVisualId.value
      if (!spans.vertical || !id) return null
      return goalLight((findGoal(store.state.board, id) ?? spanGoal(id))?.color ?? null)
    })

    function paintHand(id: string, color: string | null | undefined): void {
      const box = overlayHost.value?.firstElementChild
      const card = document.querySelector<HTMLElement>(`[data-goal-id="${CSS.escape(id)}"]`)
      if (!(box instanceof HTMLElement) || box.dataset.own === undefined || !card) return
      const square = box.querySelector<HTMLElement>('[data-role="checkbox-box"]')
      if (color === undefined) {
        box.style.backgroundColor = box.dataset.own
        box.style.backgroundImage = box.dataset.ownImage ?? ''
        box.style.boxShadow = box.dataset.ownLight ?? ''
        if (square) {
          square.style.backgroundColor = square.dataset.own ?? ''
          square.style.color = square.dataset.ownCheck ?? ''
        }
        return
      }
      paintLight(box, card, goalHoverBackground(color), box.dataset.full !== undefined)
      if (!square) return
      const { box: fill, check } = goalSquare(color)
      square.style.backgroundColor = fill
      square.style.color = check
    }

    watch(
      dragVisualId,
      (id) => {
        if (!id) return
        const clone = cloneFamily(id) ?? cloneRenderedRow(id)
        if (!clone) return
        if (overlayHost.value) overlayHost.value.replaceChildren(clone)
        else pendingClone = clone
      },
      { flush: 'sync' },
    )

    const handColor = computed(() => {
      const { id, target } = store.state.drag
      return id && !spans.vertical ? store.colorAfterDrop(id, target) : undefined
    })
    watch(handColor, (color) => {
      const id = store.state.drag.id
      if (id) paintHand(id, color)
    })

    const dragPreviewKey = computed(() => {
      const drag = store.state.drag
      if (!drag.id) return ''
      // Keyed on `slot`: re-measuring during a combine would resize the held placeholder.
      const slot = drag.slot
      // The group owner is in the key: two groups in one column can both resolve `insertBeforeId: null`.
      if (slot) {
        return `${drag.id}:reorder:${slot.vertical}:${slot.periodKey ?? ''}:${slot.insertBeforeId ?? ''}:${slot.parentId ?? ''}`
      }
      const target = drag.target
      return target?.kind === 'combine' ? `${drag.id}:combine:${target.targetId}` : `${drag.id}:none`
    })
    let previewMeasureVersion = 0
    watch(
      dragPreviewKey,
      async (key) => {
        const version = ++previewMeasureVersion
        const id = store.state.drag.id
        if (!id) return
        await nextTick()
        if (version !== previewMeasureVersion || key !== dragPreviewKey.value) return
        const drag = store.state.drag
        const target = drag.target
        if (!drag.slot && target?.kind === 'combine') {
          const row = document.querySelector<HTMLElement>(
            `[data-goal-id="${CSS.escape(target.targetId)}"] > .goal-card__row`,
          )
          const rect = row?.getBoundingClientRect()
          if (rect) store.setDragPreviewSize(rect.width, renderedRowHeightAtWidth(id, rect.width) ?? drag.height)
          return
        }
        if (!drag.slot) {
          store.setDragPreviewSize(drag.width, drag.height)
          return
        }
        const indicator = document.querySelector<HTMLElement>('[data-role="drop-indicator"]')
        if (!indicator) return
        if (indicator.dataset.box === 'card') {
          const row = indicator.querySelector<HTMLElement>('[data-role="drop-row-target"]')
          const rect = row?.getBoundingClientRect()
          if (rect) store.setDragPreviewSize(rect.width, rect.height)
          return
        }
        const width = indicator.getBoundingClientRect().width
        store.setDragPreviewSize(width, renderedRowHeightAtWidth(id, width) ?? drag.height)
      },
      { flush: 'post' },
    )

    // The box dnd-kit holds at the pointer: the goal takes the size of the slot under it before it lands, one flying with
    // its subtasks keeps its own; the grab point is a share of the box, so it stays under the hand while the box changes size.
    const overlayStyle = computed((): CSSProperties => {
      const d = store.state.drag
      const fx = d.width ? d.offsetX / d.width : 0
      const fy = d.height ? d.offsetY / d.height : 0
      const sized = d.tailHeight === 0
      return {
        pointerEvents: 'none',
        boxSizing: 'border-box',
        width: `${sized ? d.previewWidth : d.width}px`,
        height: `${sized ? d.previewHeight : d.height}px`,
        translate: `${-fx * 100}% ${-fy * 100}%`,
        transition: reducedMotion() ? 'none' : 'width 200ms var(--vt-ease-large), height 200ms var(--vt-ease-large)',
      }
    })
    const grab = computed(() => {
      const d = store.state.drag
      return { '--grab-x': `${d.width ? (d.offsetX / d.width) * 100 : 0}%`, '--grab-y': `${d.height ? (d.offsetY / d.height) * 100 : 0}%` }
    })
    return { overlayHost, dragVisualId, light, overlayStyle, grab }
  })
  const rootRef = useRootRef(s.overlayHost, outer)
  const light = s.light.value
  return (
    <DndOverlay zIndex={2147483647} modifiers={[toPointer]} dropAnimation={settle} style={s.overlayStyle.value}>
      {s.dragVisualId.value ? (
        <div
          {...fallthrough({
            ref: rootRef,
            className: cx('pattern-vertical-board__drag-overlay', { 'drag-overlay--melted': dots.melted, 'drag-overlay--lit': light }),
            'data-role': 'drag-overlay',
            'data-dnd-overlay': '',
            style: sx(s.grab.value, light ?? {}),
          }, attrs)}
        />
      ) : null}
    </DndOverlay>
  )
})
