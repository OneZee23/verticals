/* The game the mascot plays in the oval when nobody is there (lib/mascot.ts): snake, pong or arkanoid, each drawn as the
   mascot's line and starting as it, where the line stood (lib/oval.ts). */
import { onBeforeUnmount } from '../reactivity'
import { HEIGHT, WIDTH, type IdleGame } from '../lib/oval'
import { playSnake } from '../lib/snake'
import { playPong } from '../lib/pong'
import { playBreakout } from '../lib/breakout'
import type { MascotGame } from '../lib/mascot'
import { tracked } from '../tracked'
import { useSetup } from '../setup'

const GAMES: Record<MascotGame, (start: number) => IdleGame> = { snake: playSnake, pong: playPong, breakout: playBreakout }

export const CircleGame = tracked(function CircleGame({ game }: { game: MascotGame }) {
  const s = useSetup({ game }, (props) => {
    let el: HTMLCanvasElement | null = null
    let playing: IdleGame | null = null
    let frame = 0

    function draw(now: number): void {
      const g = el?.getContext('2d')
      if (!el || !g || !playing) return
      const scale = devicePixelRatio || 1
      if (el.width !== Math.round(WIDTH * scale)) {
        el.width = Math.round(WIDTH * scale)
        el.height = Math.round(HEIGHT * scale)
      }
      g.setTransform(scale, 0, 0, scale, (WIDTH / 2) * scale, (HEIGHT / 2) * scale)
      g.clearRect(-WIDTH / 2, -HEIGHT / 2, WIDTH, HEIGHT)
      g.save()
      g.beginPath()
      g.roundRect(-WIDTH / 2, -HEIGHT / 2, WIDTH, HEIGHT, HEIGHT / 2)
      g.clip()
      g.fillStyle = g.strokeStyle = getComputedStyle(el).color
      playing.draw(g, now)
      g.restore()
    }
    function loop(now: number): void {
      draw(now)
      frame = requestAnimationFrame(loop)
    }
    // Drawn as the canvas is put in, before the page paints, so the line never goes missing between the two.
    function attach(canvas: HTMLCanvasElement | null): void {
      el = canvas
      if (!canvas || frame) return
      const now = performance.now()
      playing = GAMES[props.game](now)
      draw(now)
      frame = requestAnimationFrame(loop)
    }

    onBeforeUnmount(() => cancelAnimationFrame(frame))
    return { attach }
  })
  return <canvas ref={s.attach} className="circle-field__game" aria-hidden="true" />
})
