import heroLogo from '../assets/medallion-logo-cropped.png'
import iconLogo from '../assets/medallion-icon.png'

/**
 * Two dedicated assets, not one image reused at different sizes:
 *   - medallion-logo-cropped.png ("hero"): ribbon trimmed to its bottom
 *     ~25% stub above the crest, for the login screen.
 *   - medallion-icon.png ("icon"): just the coin disc, no ribbon at all,
 *     pre-shrunk to 160px with Lanczos + a light unsharp mask.
 * The icon used to be the hero image cropped live via object-fit — at
 * nav size (~28-34px) that left a stray bit of the ribbon hook poking
 * above the circle and the fine engraving turned to mush from a single
 * huge live downscale. A separate, tightly-cropped, pre-sharpened asset
 * fixes both — see the project history for the before/after render.
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
          src={iconLogo}
          alt="Medallion Swing"
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </span>
    )
  }

  return (
    <img
      src={heroLogo}
      alt="Medallion Swing"
      width={size}
      style={{ width: size, height: 'auto', objectFit: 'contain', display: 'block', margin: '0 auto' }}
    />
  )
}
