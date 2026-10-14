// Pong playing itself, one of the mascot's games when nobody is there (lib/oval.ts). The mascot's line parts into the two
// paddles; the ball bounces off the oval's edge and off the paddles, the further from a paddle's middle the steeper, a
// little faster each time. The paddles follow it no faster than they can, so now and then one misses: the ball fades
// past it and the next is served from the middle.
import { BALL, INTRO, LINE, MASCOT, bounceOffEdge, dot, easeOut, stroke, type IdleGame } from './oval'
import { knob } from './tuning'

const SIDE = 50
const REACH = 15
const EDGE = 33
const PADDLE_SPEED = 55
const SPEEDUP = 1.06
const STEEPEST = Math.PI / 3.5
const FACE = SIDE - LINE / 2 - BALL
const GRIP = MASCOT + LINE / 2 + BALL
const FADE = 400
const SERVE = 600

export function playPong(start: number): IdleGame {
  const paddles = [{ side: -1, y: 0, aim: 0 }, { side: 1, y: 0, aim: 0 }]
  const ball = { x: 0, y: 0, vx: 0, vy: 0 }
  let speed = 0
  let shownAt = 0
  let servedAt = 0
  let lostAt = 0
  let last = start

  /** The ball shows in the middle at `now` and sets off a moment later. */
  function serve(now: number): void {
    const toward = Math.random() < 0.5 ? -1 : 1
    const angle = (Math.random() - 0.5) * (Math.PI / 3)
    speed = knob('circle.ballSpeed')
    Object.assign(ball, { x: 0, y: 0, vx: toward * speed * Math.cos(angle), vy: speed * Math.sin(angle) })
    for (const p of paddles) p.aim = (Math.random() - 0.5) * 16
    shownAt = now
    servedAt = now + SERVE
    lostAt = 0
  }
  serve(start + INTRO)

  function move(now: number, dt: number): void {
    for (const p of paddles) {
      const coming = ball.vx * p.side > 0 && now >= servedAt && !lostAt
      const target = coming ? ball.y + p.aim : ball.y * 0.3
      p.y += Math.max(-PADDLE_SPEED * dt, Math.min(PADDLE_SPEED * dt, target - p.y))
      p.y = Math.max(-REACH, Math.min(REACH, p.y))
    }
    if (now < servedAt) return
    const wasX = ball.x
    ball.x += ball.vx * dt
    ball.y += ball.vy * dt
    if (lostAt) return
    for (const p of paddles) {
      const s = p.side
      if (ball.vx * s <= 0 || s * ball.x < FACE || s * wasX > FACE + 1) continue
      if (Math.abs(ball.y - p.y) > GRIP) continue
      const angle = ((ball.y - p.y) / GRIP) * STEEPEST
      speed = Math.min(speed * SPEEDUP, knob('circle.ballSpeed') * 2)
      ball.x = s * FACE
      ball.vx = -s * speed * Math.cos(angle)
      ball.vy = speed * Math.sin(angle)
      for (const other of paddles) other.aim = (Math.random() - 0.5) * 16
    }
    if (ball.x * Math.sign(ball.vx) > FACE + 1) lostAt = now
    else bounceOffEdge(ball, EDGE)
  }

  return {
    draw(g, now) {
      const dt = Math.min(0.05, Math.max(0, now - last) / 1000)
      last = now
      move(now, dt)
      if (lostAt && now - lostAt > FADE) serve(now)
      // The line parts into the two paddles as the oval widens.
      const apart = easeOut((now - start) / INTRO)
      for (const p of paddles) stroke(g, [[p.side * SIDE * apart, p.y - MASCOT], [p.side * SIDE * apart, p.y + MASCOT]])
      g.globalAlpha = lostAt ? Math.max(0, 1 - (now - lostAt) / FADE) : 1
      dot(g, ball.x, ball.y, BALL * easeOut((now - shownAt) / 200))
      g.globalAlpha = 1
    },
  }
}
