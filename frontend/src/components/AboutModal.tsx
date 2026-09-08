import { useEffect } from 'react'
import { MedallionLogo } from './MedallionLogo'

export function AboutModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="about-modal-backdrop" onClick={onClose}>
      <div className="about-modal" onClick={(e) => e.stopPropagation()}>
        <button className="about-modal-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
        <MedallionLogo size={110} variant="hero" />
        <div className="about-modal-name">MEDALLION SWING</div>
        <div className="about-modal-tagline">Quantamental Swing-Trading Checklist</div>

        <div className="about-modal-body">
          <div className="about-modal-row">
            <div className="about-modal-row-label">What it is</div>
            <p>
              A fundamental + technical checklist engine for NSE (India) and S&amp;P 500 (US) stocks. Every score you
              see — composite, fundamental, technical — is built from real, individually-listed filters: what each
              one checked, the actual value it found, and the real threshold it was measured against. Nothing is
              summarized away.
            </p>
          </div>
          <div className="about-modal-row">
            <div className="about-modal-row-label">Why it was built</div>
            <p>
              Most "buy signals" ask you to trust a number without showing the reasoning behind it. This app takes
              the opposite position: no score without its full breakdown, no data point invented when the real
              source didn't have one, no verdict without the specific gates it passed or failed. Named after
              Renaissance Technologies' Medallion Fund — not a claim to their results, but a nod to the discipline
              this app is built around: data over opinions.
            </p>
          </div>
          <div className="about-modal-row">
            <div className="about-modal-row-label">What it's for</div>
            <p>
              A personal decision-support tool, not a broker or an advisor. Screen a universe, pull up any single
              stock to see exactly why it scores what it scores, and track real forward-tested outcomes — never
              backtested hindsight — to find out whether the checklist actually holds up. The verdict is a starting
              point for your own judgment, not a replacement for it.
            </p>
          </div>
        </div>

        <div className="about-modal-quote">
          "We do data. We don't have opinions." <b>— Jim Simons</b>
        </div>
      </div>
    </div>
  )
}
