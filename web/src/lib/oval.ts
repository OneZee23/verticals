// The oval the circle widens into while the mascot plays when nobody is there (components/CircleGame.tsx), and how its
// games draw: as the mascot's line, 3 px with round ends, from the oval's centre.

export const WIDTH = 132
export const HEIGHT = 84
/** Half of the oval's straight middle; its ends are half circles around the ends of this. */
const STRAIGHT = (WIDTH - HEIGHT) / 2
export const LINE = 3
/** Half the mascot's line between the centres of its round ends: 24 px long in all. */
export const MASCOT = 12 - LINE / 2
export const BALL = 3

export type Point = [number, number]

export interface IdleGame {
  /** Draws the game as it is at `now`, the canvas's origin at the oval's centre. */
  draw(g: CanvasRenderingContext2D, now: number): void
}

export const easeOut = (t: number) => 1 - (1 - Math.max(0, Math.min(1, t))) ** 3
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t
/** The intro: how far along the oval's widening is, 300 ms as the shape's own (--vt-dur-shape). */
export const INTRO = 300

/** A line with round ends through `points`, its turns rounded up to `turn`. */
export function stroke(g: CanvasRenderingContext2D, points: Point[], turn = 0): void {
  const far = (a: Point, b: Point) => Math.hypot(b[0] - a[0], b[1] - a[1])
  g.lineWidth = LINE
  g.lineCap = g.lineJoin = 'round'
  g.beginPath()
  g.moveTo(...points[0]!)
  for (let k = 1; k < points.length - 1; k++) {
    g.arcTo(...points[k]!, ...points[k + 1]!, Math.min(turn, far(points[k - 1]!, points[k]!), far(points[k]!, points[k + 1]!)))
  }
  g.lineTo(...points[points.length - 1]!)
  g.stroke()
}

export function dot(g: CanvasRenderingContext2D, x: number, y: number, r: number): void {
  if (r <= 0) return
  g.beginPath()
  g.arc(x, y, r, 0, Math.PI * 2)
  g.fill()
}

/** How far a point is from the oval's middle, as its edge is 42 px from it all round. */
export function fromMiddle(x: number, y: number): number {
  return Math.hypot(Math.max(0, Math.abs(x) - STRAIGHT), y)
}

/** A ball kept `inside` px of the middle: past it, it is put back on it and its velocity reflected off the edge. */
export function bounceOffEdge(ball: { x: number; y: number; vx: number; vy: number }, inside: number): boolean {
  const cx = Math.max(-STRAIGHT, Math.min(STRAIGHT, ball.x))
  const dx = ball.x - cx, dy = ball.y
  const d = Math.hypot(dx, dy)
  if (d <= inside || d === 0) return false
  const nx = dx / d, ny = dy / d
  ball.x = cx + nx * inside
  ball.y = ny * inside
  const out = ball.vx * nx + ball.vy * ny
  if (out > 0) {
    ball.vx -= 2 * out * nx
    ball.vy -= 2 * out * ny
  }
  return true
}
