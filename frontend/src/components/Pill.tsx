export function Pill({ kind, children }: { kind: 'win' | 'open' | 'loss' | 'info' | 'neutral'; children: React.ReactNode }) {
  return <span className={`pill ${kind}`}>{children}</span>
}

export function qualityPill(quality: string | null | undefined) {
  const q = (quality || '').toUpperCase()
  if (q === 'SOURCED') return <Pill kind="win">SOURCED</Pill>
  if (q === 'CACHED') return <Pill kind="info">CACHED</Pill>
  if (q.startsWith('FALLBACK')) return <Pill kind="open">{q}</Pill>
  if (q === 'MISSING') return <Pill kind="loss">MISSING</Pill>
  return <Pill kind="neutral">{q || '—'}</Pill>
}
