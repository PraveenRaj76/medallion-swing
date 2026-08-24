import logo from '../assets/medallion-logo.png'

/**
 * variant "hero" shows the full artwork (medal + ribbon) at a large size for
 * the login screen. variant "icon" clips to just the coin face, zoomed and
 * centered, for the small navbar mark — the source image is a square crop
 * with the ribbon taking up the top third, which reads as a tiny black
 * smudge at 26px if shown uncropped.
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
            width: '190%',
            height: '190%',
            objectFit: 'cover',
            objectPosition: '50% 68%',
            transform: 'translate(-24%, -34%)',
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
      height={size}
      style={{ width: size, height: size, objectFit: 'contain', display: 'block', margin: '0 auto' }}
    />
  )
}
