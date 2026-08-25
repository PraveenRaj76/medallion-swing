import { useEffect, useRef } from 'react'

interface Star {
  x: number
  y: number
  r: number
  baseAlpha: number
  phase: number
  speed: number
  drift: number
  gold: boolean
}

interface ShootingStar {
  x: number
  y: number
  vx: number
  vy: number
  life: number
}

export function Starfield() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let w = 0
    let h = 0
    let stars: Star[] = []
    const N = 130

    function resize() {
      w = canvas!.width = window.innerWidth
      h = canvas!.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    stars = Array.from({ length: N }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.3 + 0.3,
      baseAlpha: Math.random() * 0.5 + 0.15,
      phase: Math.random() * Math.PI * 2,
      speed: Math.random() * 0.15 + 0.03,
      drift: (Math.random() - 0.5) * 0.02,
      gold: Math.random() < 0.08,
    }))

    let shootingStar: ShootingStar | null = null
    let nextShootIn = 900 + Math.random() * 900
    let t = 0
    let raf = 0

    function tick() {
      t += 0.012
      ctx!.clearRect(0, 0, w, h)

      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          const a = stars[i]
          const b = stars[j]
          const d = Math.hypot(a.x - b.x, a.y - b.y)
          if (d < 110 && a.baseAlpha > 0.4 && b.baseAlpha > 0.4) {
            ctx!.strokeStyle = `rgba(154,163,188,${0.045 * (1 - d / 110)})`
            ctx!.lineWidth = 1
            ctx!.beginPath()
            ctx!.moveTo(a.x, a.y)
            ctx!.lineTo(b.x, b.y)
            ctx!.stroke()
          }
        }
      }

      for (const s of stars) {
        if (!reduceMotion) {
          s.y += s.drift
          if (s.y < -5) s.y = h + 5
          if (s.y > h + 5) s.y = -5
        }
        const twinkle = reduceMotion ? s.baseAlpha : s.baseAlpha + Math.sin(t * s.speed * 10 + s.phase) * 0.15
        ctx!.fillStyle = s.gold ? `rgba(228,183,92,${Math.max(0, twinkle)})` : `rgba(233,235,243,${Math.max(0, twinkle)})`
        ctx!.beginPath()
        ctx!.arc(s.x, s.y, s.gold ? s.r * 1.6 : s.r, 0, Math.PI * 2)
        ctx!.fill()
        if (s.gold) {
          ctx!.fillStyle = `rgba(228,183,92,${Math.max(0, twinkle) * 0.15})`
          ctx!.beginPath()
          ctx!.arc(s.x, s.y, s.r * 5, 0, Math.PI * 2)
          ctx!.fill()
        }
      }

      if (!reduceMotion) {
        if (!shootingStar) {
          nextShootIn--
          if (nextShootIn <= 0) {
            shootingStar = {
              x: Math.random() * w * 0.6,
              y: Math.random() * h * 0.3,
              vx: 7 + Math.random() * 4,
              vy: 3 + Math.random() * 2,
              life: 1,
            }
            nextShootIn = 1400 + Math.random() * 1600
          }
        } else {
          shootingStar.x += shootingStar.vx
          shootingStar.y += shootingStar.vy
          shootingStar.life -= 0.02
          if (shootingStar.life <= 0 || shootingStar.x > w || shootingStar.y > h) {
            shootingStar = null
          } else {
            const grad = ctx!.createLinearGradient(
              shootingStar.x,
              shootingStar.y,
              shootingStar.x - shootingStar.vx * 10,
              shootingStar.y - shootingStar.vy * 10,
            )
            grad.addColorStop(0, `rgba(233,235,243,${shootingStar.life})`)
            grad.addColorStop(1, 'rgba(233,235,243,0)')
            ctx!.strokeStyle = grad
            ctx!.lineWidth = 1.4
            ctx!.beginPath()
            ctx!.moveTo(shootingStar.x, shootingStar.y)
            ctx!.lineTo(shootingStar.x - shootingStar.vx * 10, shootingStar.y - shootingStar.vy * 10)
            ctx!.stroke()
          }
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(raf)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'fixed', inset: 0, zIndex: 0, opacity: 0.75, pointerEvents: 'none' }}
    />
  )
}
