import { useEffect, useRef, useState } from 'react'
import { useAuth, type ProfileFields } from '../context/AuthContext'

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function UserProfileMenu() {
  const { profile, updateProfile, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<ProfileFields | null>(profile)
  const [savedFlash, setSavedFlash] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setDraft(profile)
  }, [profile])

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!profile || !draft) return null

  function field(key: keyof ProfileFields, label: string, type = 'text') {
    return (
      <div className="profile-menu-field">
        <label htmlFor={`pm-${key}`}>{label}</label>
        <input
          id={`pm-${key}`}
          type={type}
          value={draft![key]}
          onChange={(e) => setDraft({ ...draft!, [key]: e.target.value })}
        />
      </div>
    )
  }

  function handleSave() {
    if (!draft) return
    updateProfile(draft)
    setSavedFlash(true)
    setTimeout(() => setSavedFlash(false), 1800)
  }

  return (
    <div className="profile-menu" ref={rootRef}>
      <button className="profile-menu-trigger" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="profile-avatar">{initials(profile.firstName || profile.username)}</span>
        <span className="profile-menu-name">{profile.firstName || profile.username}</span>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ opacity: 0.6 }}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div className="profile-menu-dropdown">
          <div className="profile-menu-head">
            <span className="profile-avatar profile-avatar--lg">{initials(draft.firstName || draft.username)}</span>
            <div>
              <div className="profile-menu-fullname">
                {draft.firstName} {draft.lastName}
              </div>
              <div className="profile-menu-sub">{draft.email || 'no email set'}</div>
            </div>
          </div>

          {field('firstName', 'First Name')}
          {field('lastName', 'Last Name')}
          {field('username', 'Username')}
          {field('email', 'Email Address', 'email')}

          <button className="profile-menu-save" onClick={handleSave}>
            {savedFlash ? 'Saved ✓' : 'Save Changes'}
          </button>

          <div className="profile-menu-divider" />

          <button className="profile-menu-logout" onClick={signOut}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Log Out
          </button>
        </div>
      )}
    </div>
  )
}
