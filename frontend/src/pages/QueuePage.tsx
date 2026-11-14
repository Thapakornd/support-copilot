import { useSuspenseQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { isOpen, sevRank } from '../features/cases/status'
import { useTicketMutation } from '../features/cases/useTicketMutation'
import { q } from '../shared/api/queries'
import { takeTicket } from '../shared/api/tickets'
import { StatRow } from '../shared/ui/StatRow'
import { CaseTable } from '../widgets/CaseTable'

const VIEWS = [['unassigned', 'Unassigned'], ['mine', 'Assigned to me'], ['open', 'All open']] as const
type View = (typeof VIEWS)[number][0]

export function QueuePage() {
  const { data: me } = useSuspenseQuery(q.me)
  const { data: all } = useSuspenseQuery(q.tickets)
  const [view, setView] = useState<View>('unassigned')
  const navigate = useNavigate()
  const take = useTicketMutation(takeTicket)

  const open = all.filter(isOpen)
  const views: Record<View, typeof all> = {
    unassigned: open.filter((t) => !t.assignee),
    mine: open.filter((t) => t.assignee === me.name),
    open,
  }
  const list = [...views[view]].sort((x, y) => sevRank(y) - sevRank(x) || x.created.localeCompare(y.created))

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="display sm">Support queue</h1>
          <p className="meta">Cases customers escalated after the AI suggestion did not help. Highest severity and oldest first.</p>
        </div>
      </div>
      <StatRow stats={[
        ['Unassigned', views.unassigned.length],
        ['Assigned to me', views.mine.length],
        ['Waiting on customer', open.filter((t) => t.status === 'Waiting for customer').length],
        ['Critical open', open.filter((t) => t.severity === 'Critical').length],
      ]} />
      <div className="pills" role="group" aria-label="Queue view">
        {VIEWS.map(([v, label]) => (
          <button key={v} className="tabpill" aria-pressed={view === v} onClick={() => setView(v)}>{label} <span className="count">{views[v].length}</span></button>
        ))}
      </div>
      <CaseTable
        tickets={list}
        mode="queue"
        onTake={(t) => take.mutate(t.id, { onSuccess: () => navigate({ to: '/cases/$caseId', params: { caseId: t.id } }) })}
        empty={`Nothing here. ${view === 'unassigned' ? 'Every escalated case has an owner.' : ''}`}
      />
    </section>
  )
}
