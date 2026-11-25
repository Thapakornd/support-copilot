import { useSuspenseQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { q } from '../../shared/api/queries'
import { switchDemoRole, type Role } from '../../shared/api/users'
import { Icon } from '../../shared/ui/Icon'
import { ICONS } from '../../shared/ui/icons'
import { ProfileMenu } from './ProfileMenu'

const TABS = {
  agent: [['/queue', 'Support queue'], ['/cases', 'All cases'], ['/kb', 'Knowledge base']],
  customer: [['/help', 'Get help'], ['/kb', 'Knowledge base'], ['/cases', 'Cases']],
} as const

export function Header() {
  const { data: me } = useSuspenseQuery(q.me)
  const agent = me.role === 'agent'

  // ponytail: demo role switch stands in for login; delete with real auth.
  // A full reload drops everything cached for the previous user.
  function switchRole(r: Role) {
    switchDemoRole(r)
    location.hash = '#/'
    location.reload()
  }

  return (
    <header className="top">
      <Link className="brand" to="/">
        <span className="logo"><Icon d={ICONS.logo} /></span>
        Support Copilot
      </Link>
      <nav aria-label="Primary" className="tabs">
        {TABS[me.role].map(([to, label]) => (
          <Link key={to} to={to} activeProps={{ className: 'on' }}>{label}</Link>
        ))}
      </nav>
      {!agent && <Link className="btn pri sm" to="/case">Create a case</Link>}
      <div className="role" role="group" aria-label="View as">
        <button aria-pressed={!agent} onClick={() => switchRole('customer')}>Customer</button>
        <button aria-pressed={agent} onClick={() => switchRole('agent')}>Support</button>
      </div>
      <ProfileMenu me={me} onSwitch={switchRole} />
    </header>
  )
}
