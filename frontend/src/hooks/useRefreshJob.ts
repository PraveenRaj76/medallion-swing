import { useCallback, useEffect, useRef, useState } from 'react'
import { getRefreshStatus, postRefresh } from '../api/client'
import type { RefreshStatus } from '../types'

const POLL_MS = 3000

/** Drives the "Refresh universe" button against the server-side background
 * job (see backend/engine/refresh_jobs.py). On mount this always asks the
 * server whether a refresh is already running for this market — that's
 * what makes navigating away mid-refresh and coming back show real,
 * continuing progress instead of a reset "not refreshing" state: the job
 * lives on the server regardless of which page (or tab) is open. */
export function useRefreshJob(market: 'IN' | 'US', onDone: () => void) {
  const [status, setStatus] = useState<RefreshStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const poll = useCallback(async () => {
    try {
      const s = await getRefreshStatus(market)
      setStatus(s)
      if (s.status !== 'running') {
        stopPolling()
        if (s.status === 'done') onDoneRef.current()
        if (s.status === 'error') setError(s.error || s.message || 'Refresh failed.')
      }
    } catch {
      // A transient status-check failure shouldn't kill the poll loop — the
      // actual refresh keeps running server-side regardless of whether this
      // particular poll succeeded.
    }
  }, [market, stopPolling])

  useEffect(() => {
    let cancelled = false
    getRefreshStatus(market)
      .then((s) => {
        if (cancelled) return
        setStatus(s)
        if (s.status === 'running' && !pollRef.current) {
          pollRef.current = setInterval(poll, POLL_MS)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
      stopPolling()
    }
    // Re-check only when the market tab changes — `poll` is stable for a
    // given market (see its own dependency array).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market])

  const start = useCallback(
    async (body: Parameters<typeof postRefresh>[0]) => {
      setError(null)
      try {
        const s = await postRefresh(body)
        setStatus(s)
        // s.status is already the job's real current status right after
        // start() returns — 'running' whether this call just started it or
        // joined one already in flight — so this is the same condition the
        // poll loop itself uses, not a separate started/already_running case.
        if (s.status === 'running' && !pollRef.current) {
          pollRef.current = setInterval(poll, POLL_MS)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not start the refresh.')
      }
    },
    [poll],
  )

  return { status, running: status?.status === 'running', error, start }
}

export function formatEta(etaSec: number | null | undefined): string | null {
  if (etaSec == null || !Number.isFinite(etaSec) || etaSec < 0) return null
  if (etaSec < 5) return 'almost done'
  const mins = Math.floor(etaSec / 60)
  const secs = Math.round(etaSec % 60)
  if (mins <= 0) return `~${secs}s remaining`
  return `~${mins}m ${secs}s remaining`
}
