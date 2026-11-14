import { useSuspenseQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { q } from '../../shared/api/queries'
import { SEVERITIES } from '../../shared/api/tickets'
import { isOpen } from '../cases/status'

const RESPONSE_TARGETS = ['2 business days', '1 business day', '8 hours', '1 hour'] // by severity, Low → Critical

export function TeamTable() {
  const { data: team } = useSuspenseQuery(q.team)
  return (
    <div className="card tw">
      <table>
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Can open cases</th></tr></thead>
        <tbody>
          {team.map((m) => (
            <tr key={m.email}><td><b>{m.name}</b></td><td className="meta">{m.email}</td><td>{m.role}</td><td>{m.cases ? 'Yes' : 'No'}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="empty meta">Demo team. Inviting people needs real sign-in, which this prototype does not have yet.</p>
    </div>
  )
}

export function SubscriptionStats() {
  const { data: tickets } = useSuspenseQuery(q.tickets)
  return (
    <div className="stats">
      <div className="card stat"><span className="meta">Plan</span><b>Developer</b><span className="meta">Business-hours support</span></div>
      <div className="card stat"><span className="meta">Open cases</span><b>{tickets.filter(isOpen).length}</b><span className="meta">No case limit on this plan</span></div>
      <div className="card stat wide-stat">
        <span className="meta">First response target</span>
        <dl className="dl">{SEVERITIES.flatMap((s, i) => [<dt key={s}>{s}</dt>, <dd key={s + 'v'}>{RESPONSE_TARGETS[i]}</dd>])}</dl>
      </div>
    </div>
  )
}

export function WorkloadTable() {
  const { data: me } = useSuspenseQuery(q.me)
  const { data: tickets } = useSuspenseQuery(q.tickets)
  const mine = tickets.filter((t) => t.assignee === me.name && isOpen(t))
  return (
    <div className="card tw">
      <table>
        <thead><tr><th>Case ID</th><th>Title</th><th>Status</th><th>Severity</th></tr></thead>
        <tbody>
          {mine.map((t) => (
            <tr key={t.id}><td className="mono">{t.id}</td><td><Link className="case-link" to="/cases/$caseId" params={{ caseId: t.id }}>{t.title}</Link></td><td>{t.status}</td><td>{t.severity}</td></tr>
          ))}
        </tbody>
      </table>
      {!mine.length && <p className="empty meta">No open cases assigned to you. <Link to="/queue">Take one from the queue</Link>.</p>}
    </div>
  )
}
