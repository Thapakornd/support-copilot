import { useSuspenseQuery } from '@tanstack/react-query'
import { Link, getRouteApi } from '@tanstack/react-router'
import { CaseSidebar } from '../features/cases/CaseSidebar'
import { CommentThread } from '../features/cases/CommentThread'
import { ReplyForm } from '../features/cases/ReplyForm'
import { isOpen, pillClass } from '../features/cases/status'
import { useTicketMutation } from '../features/cases/useTicketMutation'
import { q } from '../shared/api/queries'
import { takeTicket, updateTicket, type Status } from '../shared/api/tickets'
import { fmt } from '../shared/lib/format'
import { NotFound } from '../shared/ui/NotFound'

const route = getRouteApi('/cases/$caseId')

export function CaseDetailPage() {
  const { caseId } = route.useParams()
  const { data: me } = useSuspenseQuery(q.me)
  const { data: t } = useSuspenseQuery(q.ticket(caseId))
  const take = useTicketMutation(takeTicket)
  const setStatus = useTicketMutation((status: Status) => updateTicket(caseId, { status }))
  const agent = me.role === 'agent'

  if (!t) return <NotFound title={`Case ${caseId} not found`} back="/cases" backLabel="Back to cases" />

  return (
    <section className="page wide">
      {agent ? <Link className="link" to="/queue">← Support queue</Link> : <Link className="link" to="/cases">← All cases</Link>}
      <div className="page-head">
        <div>
          <h1 className="h2">{t.title}</h1>
          <p className="case-meta">
            <span className={`pill ${pillClass(t.status)}`}>{t.status.toUpperCase()}</span>
            <span><b>UPDATED:</b> {fmt(t.updated)}</span>
            <span><b>CREATED:</b> {fmt(t.created)}</span>
          </p>
        </div>
        {agent && !t.assignee && isOpen(t) && <button className="btn pri" onClick={() => take.mutate(t.id)}>Take case</button>}
        {!agent && (isOpen(t)
          ? <button className="btn" onClick={() => setStatus.mutate('Resolved')}>Mark as resolved</button>
          : <button className="btn" onClick={() => setStatus.mutate('Submitted')}>Reopen case</button>)}
      </div>

      <div className="case-grid">
        <div className="col">
          <CommentThread ticket={t} />
          {(isOpen(t) || !agent) && <ReplyForm ticket={t} agent={agent} />}
        </div>
        <CaseSidebar ticket={t} agent={agent} />
      </div>
    </section>
  )
}
