import { useState } from 'react'
import type { ExplainerItem } from '../data/checklistExplainers'

function ExplainerCard({ item, index }: { item: ExplainerItem; index: number }) {
  const [open, setOpen] = useState(false)
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
