import { Link } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import type { Me, Role } from '../../shared/api/users'
import { ACCOUNT_TABS } from '../../features/account/tabs'
import { initials } from '../../shared/lib/format'

export function ProfileMenu({ me, onSwitch }: { me: Me; onSwitch: (r: Role) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const shut = () => setOpen(false)
    const outside = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) shut() }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') shut() }
    addEventListener('pointerdown', outside)
    addEventListener('keydown', esc)
    return () => { removeEventListener('pointerdown', outside); removeEventListener('keydown', esc) }
  }, [open])

  const agent = me.role === 'agent'
  return (
    <div className="pmenu" ref={ref}>
      <button className="avatar btn-reset" aria-haspopup="menu" aria-expanded={open} aria-label={`Account menu for ${me.name}`} onClick={() => setOpen(!open)}>
        {initials(me.name)}
      </button>
      {open && (
        <div className="pmenu-pop card" role="menu">
          <div className="pmenu-head">
            <b>{me.name}</b>
            <span className="meta">{me.email}</span>
            <span className="pill gray">{agent ? 'Support engineer' : 'Customer'}</span>
          </div>
          {ACCOUNT_TABS[me.role].map(([id, label]) => (
            <Link key={id} role="menuitem" to="/account/$tab" params={{ tab: id }} onClick={() => setOpen(false)}>{label}</Link>
          ))}
          <button role="menuitem" onClick={() => { setOpen(false); onSwitch(agent ? 'customer' : 'agent') }}>Switch to {agent ? 'customer' : 'support'} view</button>
        </div>
      )}
    </div>
  )
}
