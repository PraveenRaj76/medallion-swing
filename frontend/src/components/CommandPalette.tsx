import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface Item {
  label: string
  tag: string
  action: () => void
}

const PAGES: { label: string; path: string }[] = [
  { label: 'India Screener', path: '/screener/in' },
  { label: 'US Screener', path: '/screener/us' },
  { label: 'Search Profile', path: '/profile' },
  { label: 'Forward-Test', path: '/forward-test' },
]

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
      setTimeout(() => inputRef.current?.focus(), 10)
    }
  }, [open])

  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLowerCase()
    const pageItems: Item[] = PAGES.filter((p) => !q || p.label.toLowerCase().includes(q)).map((p) => ({
      label: p.label,
      tag: 'page',
      action: () => navigate(p.path),
    }))
    const tickerItems: Item[] =
      q.length >= 1
        ? [
            {
              label: `Search "${query.toUpperCase()}" in India Screener`,
              tag: 'ticker · IN',
              action: () => navigate(`/profile?market=in&ticker=${query.toUpperCase()}`),
            },
          ]
        : []
    return [...pageItems, ...tickerItems]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActive((a) => Math.min(a + 1, items.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActive((a) => Math.max(a - 1, 0))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const item = items[active]
        if (item) {
          item.action()
          onClose()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, items, active, onClose])

  if (!open) return null

  return (
    <div className="cmdk-backdrop" role="dialog" aria-modal="true" aria-label="Jump to" onClick={onClose}>
      <div className="cmdk" onClick={(e) => e.stopPropagation()}>
        <div className="cmdk-input-row">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            placeholder="Go to a page, or jump straight to a ticker…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setActive(0)
            }}
            autoComplete="off"
          />
          <span className="kbd">Esc</span>
        </div>
        <div className="cmdk-list">
          {items.length === 0 ? (
            <div className="cmdk-empty">No matches</div>
          ) : (
            <>
              <div className="cmdk-group">Jump to</div>
              {items.map((item, i) => (
                <div
                  key={item.label}
                  className={`cmdk-item ${i === active ? 'active' : ''}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => {
                    item.action()
                    onClose()
                  }}
                >
                  <span className="l">{item.label}</span>
                  <span className="tag">{item.tag}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
