import { useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { saveProfile, type Profile } from '../../shared/api/profile'
import { q } from '../../shared/api/queries'
import type { Role } from '../../shared/api/users'

const ZONES = ['Asia/Bangkok', 'Asia/Singapore', 'Asia/Kolkata', 'Europe/London', 'America/New_York', 'America/Los_Angeles', 'UTC']

/** Local edit copy of the profile; save writes it and refreshes the header name. */
function useProfileEditor() {
  const qc = useQueryClient()
  const { data } = useSuspenseQuery(q.profile)
  const [p, setP] = useState(data)
  const save = useMutation({
    mutationFn: saveProfile,
    onSuccess: (saved) => {
      qc.setQueryData(q.profile.queryKey, saved)
      return qc.invalidateQueries({ queryKey: q.me.queryKey })
    },
  })
  const edit = (patch: Partial<Profile>) => { setP({ ...p, ...patch }); save.reset() }
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(p) }
  return { p, edit, submit, save }
}

function Actions({ saved, failed, pending, children }: { saved: boolean; failed: boolean; pending: boolean; children: ReactNode }) {
  return <div className="actions gap">{failed && <span className="meta" role="alert">Could not save. Check the fields and try again.</span>}{saved && <span className="meta">Saved.</span>}<button className="btn pri" disabled={pending}>{children}</button></div>
}

export function ProfileForm() {
  const { p, edit, submit, save } = useProfileEditor()
  return (
    <form className="card form acct" onSubmit={submit}>
      <div className="grid2">
        <label className="lbl">Full name<input className="fld" required value={p.name} onChange={(e) => edit({ name: e.target.value })} /></label>
        <label className="lbl">Email<input className="fld" type="email" required value={p.email} onChange={(e) => edit({ email: e.target.value })} /></label>
        <label className="lbl">Company<input className="fld" value={p.company} onChange={(e) => edit({ company: e.target.value })} /></label>
        <label className="lbl">Phone (for critical cases)<input className="fld" type="tel" value={p.phone} onChange={(e) => edit({ phone: e.target.value })} placeholder="Optional" /></label>
        <label className="lbl">Time zone
          <select className="fld" value={p.timezone} onChange={(e) => edit({ timezone: e.target.value })}>
            {[...new Set([...ZONES, p.timezone])].map((z) => <option key={z}>{z}</option>)}
          </select>
        </label>
      </div>
      <Actions saved={save.isSuccess} failed={save.isError} pending={save.isPending}>Save changes</Actions>
    </form>
  )
}

export function NotificationsForm({ role }: { role: Role }) {
  const { p, edit, submit, save } = useProfileEditor()
  const rows = [
    ['replies', role === 'agent' ? 'A customer replies on a case assigned to me' : 'Support replies on one of my cases'],
    ['status', role === 'agent' ? 'A case is escalated to the queue' : 'A case changes status'],
    ['digest', 'Weekly summary of open cases'],
  ] as const
  return (
    <form className="card form acct" onSubmit={submit}>
      <p className="meta">Email goes to {p.email}.</p>
      {rows.map(([k, label]) => (
        <label key={k} className="check row-check">
          <input type="checkbox" checked={p.notify[k]} onChange={(e) => edit({ notify: { ...p.notify, [k]: e.target.checked } })} />{label}
        </label>
      ))}
      <Actions saved={save.isSuccess} failed={save.isError} pending={save.isPending}>Save preferences</Actions>
    </form>
  )
}
