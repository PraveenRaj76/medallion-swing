export function MedallionLogo({ size = 130 }: { size?: number }) {
  return (
    <svg width={size} height={size * 1.25} viewBox="0 0 130 162" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="medGold" cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor="#fff3c4" />
          <stop offset="35%" stopColor="#f2c94c" />
          <stop offset="68%" stopColor="#c8932a" />
          <stop offset="100%" stopColor="#8a5f18" />
        </radialGradient>
        <linearGradient id="medRibbon" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#3b2f8f" />
          <stop offset="45%" stopColor="#7c3aed" />
          <stop offset="100%" stopColor="#1e1b4b" />
        </linearGradient>
        <radialGradient id="medShine" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* ribbon */}
      <path d="M50 6 L65 46 L50 46 Z" fill="url(#medRibbon)" opacity="0.92" />
      <path d="M80 6 L65 46 L80 46 Z" fill="url(#medRibbon)" opacity="0.92" />

      {/* outer star ring */}
      <circle cx="65" cy="98" r="58" fill="url(#medGold)" stroke="#f2c94c" strokeWidth="1.5" />
      <circle cx="65" cy="98" r="51" fill="none" stroke="#7a5417" strokeWidth="1" strokeDasharray="1.5 5" opacity="0.6" />

      {/* inner disc */}
      <circle cx="65" cy="98" r="44" fill="url(#medGold)" stroke="#8a5f18" strokeWidth="1.5" />
      <circle cx="65" cy="98" r="44" fill="url(#medShine)" />

      {/* engraved text */}
      <text
        x="65"
        y="90"
        textAnchor="middle"
        fontFamily="'Cinzel', 'Times New Roman', serif"
        fontWeight="700"
        fontSize="13"
        fill="#5c3d10"
        letterSpacing="0.5"
      >
        MEDALLION
      </text>
      <text
        x="65"
        y="107"
        textAnchor="middle"
        fontFamily="'Cinzel', 'Times New Roman', serif"
        fontWeight="700"
        fontSize="15"
        fill="#5c3d10"
        letterSpacing="1.5"
      >
        SWING
      </text>
      <line x1="45" y1="114" x2="85" y2="114" stroke="#5c3d10" strokeWidth="0.75" opacity="0.6" />
      <text x="65" y="123" textAnchor="middle" fontFamily="serif" fontSize="6" fill="#5c3d10" opacity="0.7">
        N S E · I N D
      </text>
    </svg>
  )
}
