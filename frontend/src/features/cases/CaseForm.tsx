import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { SEVERITIES, createTicket, type Severity, type Ticket } from '../../shared/api/tickets'
import { CATEGORIES } from '../../shared/config/categories'
import type { CaseDraft } from './draft'

export function CaseForm({ draft, onCreated }: { draft?: CaseDraft; onCreated: (t: Ticket) => void }) {
  const qc = useQueryClient()
  const [title, setTitle] = useState(draft?.question.slice(0, 2000) ?? '')
  const [category, setCategory] = useState(draft?.category ?? '')
  const [sev, setSev] = useState<Severity>('Normal')
  const [desc, setDesc] = useState(draft?.answer ? `${draft.question}\n\nWhat I tried from the AI suggestion, and what happened:\n` : draft?.question ?? '')
  const [ok, setOk] = useState(false)

  const create = useMutation({
    mutationFn: createTicket,
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ['tickets'] })
      onCreated(t)
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    create.mutate({ title, category, severity: sev, description: desc, sources: draft?.sources ?? [], aiAnswer: draft?.answer, consent: ok })
  }

  return (
    <form className="form card" onSubmit={submit}>
      <label className="lbl">Title<input className="fld" required maxLength={2000} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <label className="lbl">Area
        <select className="fld" required value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Choose an area…</option>
          {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <fieldset className="sev">
        <legend className="lbl">Severity</legend>
        {SEVERITIES.map((s) => (
          <label key={s} className="sevo"><input type="radio" name="sev" checked={sev === s} onChange={() => setSev(s)} /><b>{s}</b></label>
        ))}
      </fieldset>
      <label className="lbl">Description<textarea className="fld" rows={8} required maxLength={20000} value={desc} onChange={(e) => setDesc(e.target.value)} /></label>
      {!!draft?.sources.length && (
        <div><p className="sec">Articles already consulted</p><ul>{draft.sources.map((s, i) => <li key={i}>{s.title}</li>)}</ul></div>
      )}
      <label className="check"><input type="checkbox" required checked={ok} onChange={(e) => setOk(e.target.checked)} />I understand the text I supplied may be shared with the support team.</label>
      {create.isError && <p className="meta" role="alert">Could not submit the case. Try again.</p>}
      <div className="actions"><button className="btn pri" disabled={create.isPending}>Submit case</button></div>
    </form>
  )
}
