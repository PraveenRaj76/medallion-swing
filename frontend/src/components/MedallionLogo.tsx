import logo from '../assets/medallion-logo-cropped.png'

/**
 * Source asset is medallion-logo-cropped.png — the original artwork with
 * the ribbon trimmed to its bottom ~25% (just the stub sitting above the
 * crest) and the black background chroma-keyed to real alpha transparency
 * (Pillow, decontaminated edges — see the asset's generation notes in the
 * project history). variant "hero" shows the full artwork (ribbon stub +
 * medal) for the login screen. variant "icon" crops to just the coin
 * circle for the small navbar mark.
 */
export function MedallionLogo({
  size = 130,
  variant = 'hero',
}: {
  size?: number
  variant?: 'hero' | 'icon'
}) {
  if (variant === 'icon') {
    return (
      <span
        style={{
          display: 'block',
          width: size,
          height: size,
          borderRadius: '50%',
          overflow: 'hidden',
          flex: 'none',
          boxShadow: '0 0 0 1px rgba(240, 180, 41, 0.4)',
        }}
      >
        <img
          src={logo}
          alt="Medallion Swing"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: '50% 100%',
          }}
        />
      </span>
    )
  }

  return (
    <img
      src={logo}
      alt="Medallion Swing"
      width={size}
      style={{ width: size, height: 'auto', objectFit: 'contain', display: 'block', margin: '0 auto' }}
    />
  )
}
