import { useSuspenseQuery } from '@tanstack/react-query'
import { Link, getRouteApi } from '@tanstack/react-router'
import { SubscriptionStats, TeamTable, WorkloadTable } from '../features/account/AccountPanels'
import { NotificationsForm, ProfileForm } from '../features/account/ProfileForms'
import { ACCOUNT_TABS } from '../features/account/tabs'
import { q } from '../shared/api/queries'
import { initials } from '../shared/lib/format'

const route = getRouteApi('/account/$tab')

export function AccountPage() {
  const { tab } = route.useParams()
  const { data: me } = useSuspenseQuery(q.me)
  const tabs = ACCOUNT_TABS[me.role]
  const cur = tabs.some(([id]) => id === tab) ? tab : 'profile'
  const agent = me.role === 'agent'

  return (
    <section className="page wide">
      <div className="acct-head">
        <span className="avatar lg">{initials(me.name)}</span>
        <div>
          <h1 className="h2">{me.name}</h1>
          <p className="meta">{me.email} · {agent ? 'Support engineer' : `Owner at ${me.company}`}</p>
        </div>
      </div>
      <nav className="subtabs" aria-label="Account sections">
        {tabs.map(([id, label]) => (
          <Link key={id} to="/account/$tab" params={{ tab: id }} className={cur === id ? 'on' : ''} aria-current={cur === id ? 'page' : undefined}>{label}</Link>
        ))}
      </nav>

      {cur === 'profile' && <ProfileForm />}
      {cur === 'notifications' && <NotificationsForm role={me.role} />}
      {cur === 'team' && <TeamTable />}
      {cur === 'subscription' && <SubscriptionStats />}
      {cur === 'workload' && <WorkloadTable />}
    </section>
  )
}
