import { useState, type FormEvent } from 'react'
import { replyToTicket, type Status, type Ticket } from '../../shared/api/tickets'
import { failureText, useTicketMutation } from './useTicketMutation'

const AFTER: Status[] = ['Waiting for customer', 'In progress', 'Resolved']

export function ReplyForm({ ticket, agent }: { ticket: Ticket; agent: boolean }) {
  const [draft, setDraft] = useState('')
  const [after, setAfter] = useState<Status>('Waiting for customer')
  const reply = useTicketMutation((body: string) => replyToTicket(ticket.id, body, agent ? after : undefined))

  function post(e: FormEvent) {
    e.preventDefault()
    if (!draft.trim()) return
    reply.mutate(draft.trim(), { onSuccess: () => setDraft('') })
  }

  return (
    <form className="card pad" onSubmit={post}>
      <label htmlFor="reply" className="sec">{agent ? 'Reply to customer' : 'Add a comment'}</label>
      <textarea id="reply" className="fld" rows={4} maxLength={20000} value={draft} onChange={(e) => setDraft(e.target.value)}
        placeholder={agent ? 'Write your reply…' : 'Add details, answer a question, or tell support what changed…'} />
      {reply.isError && <p className="meta" role="alert">{failureText(reply.error)}</p>}
      <div className="reply-bar">
        {agent && (
          <label className="meta nowrap">After sending, set status to{' '}
            <select className="fld inline" value={after} onChange={(e) => setAfter(e.target.value as Status)}>
              {AFTER.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
        )}
        <button className="btn pri" disabled={!draft.trim() || reply.isPending}>{agent ? 'Send reply' : 'Post comment'}</button>
      </div>
    </form>
  )
}
