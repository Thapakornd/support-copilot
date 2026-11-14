import { useSuspenseQuery } from '@tanstack/react-query'
import { q } from '../../shared/api/queries'
import { SEVERITIES, STATUSES, updateTicket, type Severity, type Status, type Ticket, type TicketPatch } from '../../shared/api/tickets'
import { catName } from '../../shared/config/categories'
import { useTicketMutation } from './useTicketMutation'

/** Case facts; agents can change assignee, status and severity in place. */
export function CaseSidebar({ ticket: t, agent }: { ticket: Ticket; agent: boolean }) {
  const { data: agents } = useSuspenseQuery(q.agents)
  const update = useTicketMutation((patch: TicketPatch) => updateTicket(t.id, patch))

  return (
    <aside className="col side">
      <h2 className="h3">Case</h2>
      <section className="card pad">
        <dl className="dl">
          <dt>Case</dt><dd className="mono">{t.id}</dd>
          <dt>Assignee</dt>
          <dd>{agent
            ? <select className="fld inline" aria-label="Assignee" value={t.assignee ?? ''} onChange={(e) => update.mutate({ assignee: e.target.value || undefined })}>
                <option value="">Unassigned</option>
                {agents.map((a) => <option key={a}>{a}</option>)}
              </select>
            : t.assignee ?? 'Waiting for an engineer'}</dd>
          <dt>Status</dt>
          <dd>{agent
            ? <select className="fld inline" aria-label="Status" value={t.status} onChange={(e) => update.mutate({ status: e.target.value as Status })}>
                {STATUSES.map((s) => <option key={s}>{s}</option>)}
              </select>
            : t.status}</dd>
          <dt>Severity</dt>
          <dd>{agent
            ? <select className="fld inline" aria-label="Severity" value={t.severity} onChange={(e) => update.mutate({ severity: e.target.value as Severity })}>
                {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
              </select>
            : t.severity}</dd>
          <dt>Area</dt><dd>{catName(t.category)}</dd>
        </dl>
      </section>
      <h2 className="h3">Account</h2>
      <section className="card pad">
        <dl className="dl">
          {/* ponytail: company and plan are demo constants until the ticket API returns the account */}
          <dt>Reporter</dt><dd>{t.reporter}</dd>
          <dt>Company</dt><dd>Demo Org</dd>
          <dt>Subscription</dt><dd>Developer</dd>
        </dl>
      </section>
    </aside>
  )
}
