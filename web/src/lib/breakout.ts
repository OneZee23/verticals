// Arkanoid playing itself, one of the mascot's games when nobody is there (lib/oval.ts). The mascot's line lies down to be
// the paddle and the bricks come in above it; the ball bounces off the oval's edge, the bricks and the paddle, the further
// from its middle the steeper. A missed ball fades and the next starts from the paddle; when the bricks are gone, they
// come back.
import { BALL, INTRO, LINE, MASCOT, bounceOffEdge, dot, easeOut, stroke, type IdleGame } from './oval'
import { knob } from './tuning'

const PADDLE_Y = 26
const REACH = 30
const EDGE = 33
const PADDLE_SPEED = 75
const STEEPEST = Math.PI / 3
const TOP = PADDLE_Y - LINE / 2 - BALL
const GRIP = MASCOT + LINE / 2 + BALL
/** Half a brick's length, its round ends in. */
const BRICK = 5
const ROWS = [-25, -18, -11]
const COLS = [-35, -21, -7, 7, 21, 35]
const BREAK = 200
const FADE = 400
const SERVE = 600
const REFILL = 600

type Brick = { x: number; y: number; brokenAt: number; bornAt: number }

export function playBreakout(start: number): IdleGame {
  const bricks: Brick[] = ROWS.flatMap((y, row) => COLS.map((x, col) => ({ x, y, brokenAt: 0, bornAt: start + INTRO + (row * COLS.length + col) * 25 })))
  const paddle = { x: 0, aim: 0 }
  const ball = { x: 0, y: TOP, vx: 0, vy: 0 }
  let shownAt = start + INTRO
  let servedAt = shownAt + SERVE
  let lostAt = 0
  let clearedAt = 0
  let last = start

  function serve(now: number): void {
    Object.assign(ball, { x: paddle.x, y: TOP, vx: 0, vy: 0 })
    shownAt = now
    servedAt = now + SERVE
    lostAt = 0
  }

  function launch(): void {
    const speed = knob('circle.ballSpeed'), angle = (Math.random() - 0.5) * (Math.PI / 3)
    ball.vx = speed * Math.sin(angle)
    ball.vy = -speed * Math.cos(angle)
    paddle.aim = (Math.random() - 0.5) * 16
  }

  function hitBrick(now: number): void {
    for (const b of bricks) {
      if (b.brokenAt || now < b.bornAt) continue
      const dx = ball.x - b.x, dy = ball.y - b.y
      const px = BRICK + BALL - Math.abs(dx), py = LINE / 2 + BALL - Math.abs(dy)
      if (px < 0 || py < 0) continue
      b.brokenAt = now
      if (px < py) ball.vx = Math.sign(dx) * Math.abs(ball.vx)
      else ball.vy = Math.sign(dy) * Math.abs(ball.vy)
      return
    }
  }

  function move(now: number, dt: number): void {
    const waiting = now < servedAt
    const target = waiting ? 0 : ball.vy > 0 && !lostAt ? ball.x + paddle.aim : ball.x * 0.5
    paddle.x += Math.max(-PADDLE_SPEED * dt, Math.min(PADDLE_SPEED * dt, target - paddle.x))
    paddle.x = Math.max(-REACH, Math.min(REACH, paddle.x))
    if (waiting) {
      ball.x = paddle.x
      return
    }
    if (!ball.vx && !ball.vy) launch()
    ball.x += ball.vx * dt
    ball.y += ball.vy * dt
    if (lostAt) return
    hitBrick(now)
    if (ball.vy > 0 && ball.y >= TOP && ball.y <= TOP + LINE + 2 && Math.abs(ball.x - paddle.x) <= GRIP) {
      const speed = Math.hypot(ball.vx, ball.vy), angle = ((ball.x - paddle.x) / GRIP) * STEEPEST
      ball.y = TOP
      ball.vx = speed * Math.sin(angle)
      ball.vy = -speed * Math.cos(angle)
      paddle.aim = (Math.random() - 0.5) * 16
    } else if (ball.y > TOP + LINE + 2) lostAt = now
    else bounceOffEdge(ball, EDGE)
  }

  return {
    draw(g, now) {
      const dt = Math.min(0.05, Math.max(0, now - last) / 1000)
      last = now
      move(now, dt)
      if (lostAt && now - lostAt > FADE) serve(now)
      if (!clearedAt && bricks.every((b) => b.brokenAt)) clearedAt = now
      if (clearedAt && now - clearedAt > REFILL) {
        bricks.forEach((b, k) => Object.assign(b, { brokenAt: 0, bornAt: now + k * 25 }))
        clearedAt = 0
      }
      for (const b of bricks) {
        const alpha = b.brokenAt ? 1 - (now - b.brokenAt) / BREAK : easeOut((now - b.bornAt) / 200)
        if (alpha <= 0) continue
        g.globalAlpha = alpha
        stroke(g, [[b.x - BRICK + LINE / 2, b.y], [b.x + BRICK - LINE / 2, b.y]])
      }
      // The line lies down and sinks to be the paddle as the oval widens.
      const down = easeOut((now - start) / INTRO), turn = (down * Math.PI) / 2
      const dx = MASCOT * Math.sin(turn), dy = MASCOT * Math.cos(turn), y = PADDLE_Y * down
      g.globalAlpha = 1
      stroke(g, [[paddle.x - dx, y - dy], [paddle.x + dx, y + dy]])
      g.globalAlpha = lostAt ? Math.max(0, 1 - (now - lostAt) / FADE) : 1
      dot(g, ball.x, ball.y, BALL * easeOut((now - shownAt) / 200))
      g.globalAlpha = 1
    },
  }
}
