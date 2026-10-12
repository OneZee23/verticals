/* The opened goal is seen whole (Kirill's rule, PR #1): if it fits where it was clicked, the column stays; otherwise it
   scrolls just enough, 16 px from the window's edge, and a goal taller than the window shows its top. Read by the move
   that opens it (`lib/familyMotion.ts`), which lands the column there in the same movement, and by `GoalDetail.tsx` for
   an opening the move doesn't draw. */

export const GAP = 16

/** Where `el` starts inside `scroller`'s content, as laid out: a lift or a glide doesn't count. */
export function contentTop(el: HTMLElement, scroller: HTMLElement): number {
  let y = 0
  for (let e: HTMLElement | null = el; e && e !== scroller; e = e.offsetParent as HTMLElement | null) y += e.offsetTop
  return y
}

/** The element that scrolls `el`'s column. */
export function scrollerOf(el: HTMLElement): HTMLElement | null {
  let scroller = el.parentElement
  while (scroller && !/auto|scroll/.test(getComputedStyle(scroller).overflowY)) scroller = scroller.parentElement
  return scroller
}

/** The open goal's family as one block (flow 4): from its first line, so the levels stepped through stay in view above
 *  the card, to the end of its list, notes included. `detail` is the open goal's notes (`#goal-detail`). */
export function familyBlock(detail: HTMLElement): { card: HTMLElement; list: HTMLElement } | null {
  let list = detail.parentElement
  while (list?.parentElement?.closest('.goal-card__children')) list = list.parentElement.closest<HTMLElement>('.goal-card__children')
  const card = list?.previousElementSibling as HTMLElement | null
  return list && card ? { card, list } : null
}

/** How much of `scroller` shows in the window. */
export function seenHeight(scroller: HTMLElement): number {
  return Math.min(scroller.clientHeight, window.innerHeight - scroller.getBoundingClientRect().top)
}

/** What the goals scroll under at the top of `scroller`: its padding, which lies under the desktop title bar (App.tsx), and
 *  the line pinned at its start, which holds that room and its own 28 px (ColumnLine.tsx, docs/design/column-bars.md). */
function under(scroller: HTMLElement): number {
  const line = scroller.querySelector<HTMLElement>(':scope > [data-role="column-line"]')
  return (parseFloat(getComputedStyle(scroller).paddingTop) || 0) + (line?.offsetHeight ?? 0)
}

/** The scroll at which the block from `top` to `bottom` (in `scroller`'s content) is seen whole, moving as little as
 *  possible from `from`. The block stops below what the goals scroll under at the top. */
export function fitScroll(scroller: HTMLElement, top: number, bottom: number, from: number): number {
  return Math.max(0, Math.min(top - GAP - under(scroller), Math.max(from, bottom + GAP - seenHeight(scroller))))
}
