import { useEffect, useRef, useState } from 'react'

/**
 * Animates a number counting up from 0 whenever `value` changes.
 *
 * Deliberately uses setInterval, not requestAnimationFrame — rAF simply
 * never fires while a tab is backgrounded/not compositing (verified live:
 * a hidden tab shows zero rAF callbacks even after 100ms), which silently
 * froze this component at its initial value for any user who loaded the
 * page in a background tab or minimized window. setInterval keeps firing
 * (browsers throttle it in background tabs, but don't suspend it outright)
 * so the counter reliably reaches its target either way.
 */
export function CountUp({
  value,
  decimals = 0,
  durationMs = 700,
}: {
  value: number | null | undefined
  decimals?: number
  durationMs?: number
}) {
  const [display, setDisplay] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const target = value ?? 0
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (timerRef.current) clearInterval(timerRef.current)
    if (reduceMotion) {
      setDisplay(target)
      return
    }
    const start = Date.now()
    const stepMs = 30
    timerRef.current = setInterval(() => {
      const t = Math.min(1, (Date.now() - start) / durationMs)
      const eased = 1 - Math.pow(1 - t, 3)
      setDisplay(target * eased)
      if (t >= 1 && timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }, stepMs)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  if (value == null) return <>—</>
  return <>{display.toFixed(decimals)}</>
}
