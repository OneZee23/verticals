// Snake playing itself, one of the mascot's games when nobody is there (lib/oval.ts). It runs on points inside the oval,
// heads for the food by the shortest way that leaves it room, and when it is boxed in it fades and starts again as the
// mascot's line. Between points it moves smoothly and takes its turns round.
import { BALL, INTRO, MASCOT, dot, easeOut, fromMiddle, stroke, type IdleGame, type Point } from './oval'
import { knob } from './tuning'

/** Between neighbouring points: three of them, as the game starts, are the mascot's line. */
const GAP = MASCOT
const REACH = 32

const POINTS: Point[] = []
const at = new Map<string, number>()
for (let j = -3; j <= 3; j++) {
  for (let i = -6; i <= 6; i++) {
    const x = i * GAP, y = j * GAP
    if (fromMiddle(x, y) > REACH) continue
    at.set(`${i},${j}`, POINTS.length)
    POINTS.push([x, y])
  }
}
const NEIGHBOURS = POINTS.map(([x, y]) => {
  const i = Math.round(x / GAP), j = Math.round(y / GAP)
  return [[1, 0], [0, 1], [-1, 0], [0, -1]]
    .map(([di, dj]) => at.get(`${i + di!},${j + dj!}`))
    .filter((n): n is number => n !== undefined)
})

/** Steps the snake takes to fade when it is boxed in. */
const FADE = 3

interface Snake {
  /** Points, head first. */
  body: number[]
  food: number
  /** Steps of fading left; 0 while it plays. */
  dying: number
  /** Which game this is, so a new one is never drawn as a move of the last. */
  game: number
}

let games = 0

function placeFood(body: number[]): number {
  const taken = new Set(body)
  const free = POINTS.map((_, p) => p).filter((p) => !taken.has(p))
  return free[Math.floor(Math.random() * free.length)] ?? -1
}

function newSnake(): Snake {
  const body = [at.get('0,-1')!, at.get('0,0')!, at.get('0,1')!]
  return { body, food: placeFood(body), dying: 0, game: ++games }
}

/** Steps from `from` to `to` past `walls`, or Infinity. */
function distance(from: number, to: number, walls: Set<number>): number {
  const seen = new Map([[from, 0]])
  const queue = [from]
  for (let k = 0; k < queue.length; k++) {
    const p = queue[k]!
    if (p === to) return seen.get(p)!
    for (const n of NEIGHBOURS[p]!) {
      if (walls.has(n) || seen.has(n)) continue
      seen.set(n, seen.get(p)! + 1)
      queue.push(n)
    }
  }
  return Infinity
}

/** How many points can be reached from `from` past `walls`. */
function room(from: number, walls: Set<number>): number {
  const seen = new Set([from])
  const queue = [from]
  for (let k = 0; k < queue.length; k++) {
    for (const n of NEIGHBOURS[queue[k]!]!) {
      if (walls.has(n) || seen.has(n)) continue
      seen.add(n)
      queue.push(n)
    }
  }
  return seen.size
}

/** One step of the game. */
function step(snake: Snake): Snake {
  if (snake.dying > 0) return snake.dying === 1 ? newSnake() : { ...snake, dying: snake.dying - 1 }
  const { body, food } = snake
  const head = body[0]!
  const [hx, hy] = POINTS[head]!
  const [nx, ny] = POINTS[body[1] ?? head]!
  let best: { to: number; score: number } | null = null
  for (const to of NEIGHBOURS[head]!) {
    const eats = to === food
    const after = [to, ...(eats ? body : body.slice(0, -1))]
    const walls = new Set(after.slice(1))
    if (walls.has(to)) continue
    const space = room(to, walls)
    const far = eats ? 0 : distance(to, food, walls)
    const [tx, ty] = POINTS[to]!
    const straight = tx - hx === hx - nx && ty - hy === hy - ny
    // Room first, then the food, then going straight on.
    const score = (space >= after.length ? 0 : 1e6 - space * 1e3) + Math.min(far, 999) + (straight ? 0 : 0.5)
    if (!best || score < best.score) best = { to, score }
  }
  if (!best) return { ...snake, dying: FADE }
  const eats = best.to === food
  const next = [best.to, ...(eats ? body : body.slice(0, -1))]
  if (next.length === POINTS.length) return { ...snake, body: next, food: -1, dying: FADE }
  return { ...snake, body: next, food: eats ? placeFood(next) : food }
}

const lerpPoint = (a: Point, b: Point, t: number): Point => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]

/** The body between two steps, `t` of the way, head first. */
function shape(prev: Snake, next: Snake, t: number): Point[] {
  const was = prev.body.map((p) => POINTS[p]!)
  if (prev.game !== next.game || next.body[0] === prev.body[0]) return next.body.map((p) => POINTS[p]!)
  const head = lerpPoint(was[0]!, POINTS[next.body[0]!]!, t)
  if (next.body.length > prev.body.length) return [head, ...was]
  return [head, ...was.slice(0, -1), lerpPoint(was[was.length - 1]!, was[was.length - 2]!, t)]
}

function opacity(prev: Snake, next: Snake, t: number): number {
  if (prev.game !== next.game) return t
  const of = (s: Snake) => (s.dying ? (s.dying - 1) / FADE : 1)
  return of(prev) + (of(next) - of(prev)) * t
}

export function playSnake(start: number): IdleGame {
  let prev = newSnake()
  let next = prev
  // The line stands as the oval widens around it, then it sets off.
  let since = start + INTRO
  let food = next.food
  let foodSince = start
  return {
    draw(g, now) {
      const ms = knob('circle.snakeStepMs')
      if (now - since > ms * 4) since = now
      while (now - since >= ms) {
        prev = next
        next = step(next)
        since += ms
      }
      if (prev.food !== food) {
        food = prev.food
        foodSince = now
      }
      const t = Math.max(0, Math.min(1, (now - since) / ms))
      if (food >= 0 && prev.game === next.game) dot(g, ...POINTS[food]!, BALL * easeOut((now - foodSince) / 200))
      g.globalAlpha = opacity(prev, next, t)
      stroke(g, shape(prev, next, t), GAP / 2)
      g.globalAlpha = 1
    },
  }
}
