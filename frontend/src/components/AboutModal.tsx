import { useEffect } from 'react'
import fullLogo from '../assets/medallion-logo.png'

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
        <img src={fullLogo} alt="Medallion Swing" className="about-modal-logo" />

        <div className="about-modal-story">
          <p className="about-modal-greeting">Hi, I'm Praveen. I built Medallion Swing.</p>
          <p>
            I'm a software engineer. I've also been a physics teacher and a science communicator, and I've been
            investing in stocks for a while now.
          </p>
          <p>
            The idea came from Jim Simons and his Medallion Fund. He built one of the best investing records ever,
            just by trusting data over opinions. I loved that, so I built this app on the same thinking: pick good,
            undervalued stocks using a proper quality checklist and real momentum, not guesswork.
          </p>
          <p>
            I started with India. I wanted a proper way to check around 200 good mid cap and small cap stocks, and
            also rank the best sectors, not just the best individual stocks.
          </p>
          <p>
            I invest in the US market too, for diversification. So I built the same kind of checklist for S&amp;P 500
            stocks as well.
          </p>
          <p>
            Every score you see here is real. Nothing is made up, and nothing is hidden. This was the tool I built
            for myself first. Now I'm sharing it with you.
          </p>
        </div>

        <div className="about-modal-signoff">Praveen, founder</div>
      </div>
    </div>
  )
}
