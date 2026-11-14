import { Link, useLocation, useRouter } from '@tanstack/react-router'
import { useState } from 'react'
import { CaseForm } from '../features/cases/CaseForm'
import type { Ticket } from '../shared/api/tickets'
import { Icon } from '../shared/ui/Icon'
import { ICONS } from '../shared/ui/icons'

export function NewCasePage() {
  const draft = useLocation({ select: (l) => l.state.caseDraft })
  const router = useRouter()
  const [done, setDone] = useState<Ticket | null>(null)

  if (done) return (
    <section className="page narrow center stack">
      <span className="done-ic"><Icon d={ICONS.check} size={28} /></span>
      <h1 className="h2">Case {done.id} submitted</h1>
      <p className="meta">A support engineer will pick it up. You can follow it under Cases.</p>
      <Link className="btn pri" to="/cases/$caseId" params={{ caseId: done.id }}>View case</Link>
    </section>
  )

  return (
    <section className="page narrow">
      <Link className="link" to="/help" onClick={(e) => { if (draft) { e.preventDefault(); router.history.back() } }}>← Back</Link>
      <h1 className="h2">Review your support case</h1>
      <p className="meta">{draft ? 'Pre-filled from your AI search. Nothing is sent until you submit.' : 'Tell us what is going on.'}</p>
      <CaseForm draft={draft} onCreated={setDone} />
    </section>
  )
}
