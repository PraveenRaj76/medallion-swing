import { useState } from 'react'
import type { ExplainerItem, ExampleRange } from '../data/checklistExplainers'

function fmtRangeVal(v: number, unit: string): string {
  const n = Number.isInteger(v) ? String(v) : v.toFixed(1)
  return `${n}${unit}`
}

/** Visual min/normal/max scale for one checklist item, with a small
 * illustrative example marked on it — this panel is the generic glossary
 * (shown before picking any stock), so the marker is a representative
 * sample value, not a live stock's actual reading. */
function RangeBar({ range, maxMarks }: { range: ExampleRange; maxMarks: number }) {
  const { min, max, unit, bands, example } = range
  const span = max - min || 1
  const pct = (v: number) => Math.max(0, Math.min(100, ((v - min) / span) * 100))
  const tier = (marks: number) => {
    const ratio = maxMarks > 0 ? marks / maxMarks : 0
    if (ratio >= 0.7) return 'strong'
    if (ratio >= 0.35) return 'mid'
    return 'weak'
  }

  let from = min
  const segments = bands.map((b) => {
    const seg = { from, to: b.to, label: b.label, marks: b.marks }
    from = b.to
    return seg
  })

  return (
    <div className="range-bar-wrap">
      <div className="range-bar">
        {segments.map((s) => (
          <div
            key={s.label}
            className={`range-seg tier-${tier(s.marks)}`}
            style={{ width: `${Math.max(0, pct(s.to) - pct(s.from))}%` }}
            title={`${s.label}: ${s.marks}/${maxMarks} marks`}
          />
        ))}
        <div className="range-marker" style={{ left: `${pct(example)}%` }}>
          <span className="range-marker-dot" />
        </div>
      </div>
      <div className="range-scale">
        <span>{fmtRangeVal(min, unit)}</span>
        <span className="range-example">e.g. {fmtRangeVal(example, unit)}</span>
        <span>{fmtRangeVal(max, unit)}</span>
      </div>
      <div className="range-band-labels">
        {segments.map((s) => (
          <span key={s.label} className={`range-band-label tier-${tier(s.marks)}`}>
            {s.label} ({s.marks}/{maxMarks})
          </span>
        ))}
      </div>
    </div>
  )
}

function ExplainerCard({ item, index }: { item: ExplainerItem; index: number }) {
  // Starts open — opening the parent panel ("Understand the X Checklist")
  // should show every item's full detail at once, not require clicking
  // each one individually. The chevron still lets you collapse a single
  // card back down if you want to tidy up.
  const [open, setOpen] = useState(true)
  return (
    <div className={`explainer-card ${open ? 'open' : ''}`}>
      <button className="explainer-card-head" onClick={() => setOpen((o) => !o)}>
        <span className="explainer-num">{String(index + 1).padStart(2, '0')}</span>
        <span className="explainer-title">{item.name}</span>
        {item.maxMarks > 0 && <span className="explainer-max mono">/{item.maxMarks}</span>}
        <svg
          className="explainer-chevron"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="explainer-body">
          <div className="explainer-row">
            <span className="explainer-label">What it is</span>
            <p>{item.what}</p>
          </div>
          <div className="explainer-row">
            <span className="explainer-label">Why it matters</span>
            <p>{item.why}</p>
          </div>
          <div className="explainer-row">
            <span className="explainer-label">How it's scored</span>
            <p className="mono explainer-scoring">{item.scoring}</p>
            {item.range && <RangeBar range={item.range} maxMarks={item.maxMarks} />}
          </div>
        </div>
      )}
    </div>
  )
}

export function ChecklistExplainer({
  title,
  subtitle,
  items,
}: {
  title: string
  subtitle: string
  items: ExplainerItem[]
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="section">
      <button className="explainer-toggle" onClick={() => setExpanded((e) => !e)}>
        <span className="explainer-toggle-icon">{expanded ? '−' : '+'}</span>
        <span>
          <strong>{title}</strong>
          <span className="explainer-toggle-sub">{subtitle}</span>
        </span>
      </button>
      {expanded && (
        <div className="explainer-grid">
          {items.map((item, i) => (
            <ExplainerCard key={item.name} item={item} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}
