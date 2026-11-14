import { useSuspenseQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { isOpen, sevRank } from '../features/cases/status'
import { q } from '../shared/api/queries'
import { SEVERITIES, STATUSES, type Status } from '../shared/api/tickets'
import { CATEGORIES } from '../shared/config/categories'
import { SearchInput } from '../shared/ui/SearchInput'
import { StatRow } from '../shared/ui/StatRow'
import { CaseTable } from '../widgets/CaseTable'

type View = 'open' | 'all' | Status
type Sort = 'updated' | 'created' | 'severity'

export function CasesPage() {
  const { data: me } = useSuspenseQuery(q.me)
  const { data: all } = useSuspenseQuery(q.tickets)
  const agent = me.role === 'agent'
  const [view, setView] = useState<View>('open')
  const [text, setText] = useState('')
  const [area, setArea] = useState('')
  const [sev, setSev] = useState('')
  const [sort, setSort] = useState<Sort>('updated')

  const views: [View, string, number][] = [
    ['open', 'Open', all.filter(isOpen).length],
    ['all', 'All cases', all.length],
    ...STATUSES.map((s): [View, string, number] => [s, s, all.filter((t) => t.status === s).length]),
  ]
  const needle = text.trim().toLowerCase()
  const list = all
    .filter((t) => (view === 'open' ? isOpen(t) : view === 'all' || t.status === view))
    .filter((t) => !needle || (t.id + ' ' + t.title + ' ' + (t.assignee ?? '')).toLowerCase().includes(needle))
    .filter((t) => !area || t.category === area)
    .filter((t) => !sev || t.severity === sev)
    .sort((x, y) => sort === 'severity' ? sevRank(y) - sevRank(x) : y[sort].localeCompare(x[sort]))

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="display sm">{agent ? 'All cases' : 'Cases'}</h1>
          <p className="meta">{agent ? 'Every case across customers.' : 'Every support case opened from this account.'} Demo data, stored in this browser.</p>
        </div>
        {!agent && <Link className="btn pri" to="/case">Create a case</Link>}
      </div>

      <StatRow stats={[
        ['Open', all.filter(isOpen).length],
        ['Waiting on customer', all.filter((t) => t.status === 'Waiting for customer').length],
        ['High / critical open', all.filter((t) => isOpen(t) && sevRank(t) >= 2).length],
        ['Resolved', all.filter((t) => !isOpen(t)).length],
      ]} />

      <div className="pills" role="group" aria-label="Filter by status">
        {views.map(([v, label, n]) => (
          <button key={v} className="tabpill" aria-pressed={view === v} onClick={() => setView(v)}>{label} <span className="count">{n}</span></button>
        ))}
      </div>

      <div className="toolbar">
        <SearchInput id="cq" className="grow" label="Search cases" value={text} onChange={setText} placeholder="Search by case ID, title or assignee" />
        <label className="sr" htmlFor="ca">Area</label>
        <select id="ca" className="fld" value={area} onChange={(e) => setArea(e.target.value)}>
          <option value="">All areas</option>
          {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <label className="sr" htmlFor="cs">Severity</label>
        <select id="cs" className="fld" value={sev} onChange={(e) => setSev(e.target.value)}>
          <option value="">All severities</option>
          {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <label className="sr" htmlFor="co">Sort</label>
        <select id="co" className="fld" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="updated">Last updated</option>
          <option value="created">Newest first</option>
          <option value="severity">Highest severity</option>
        </select>
      </div>

      <CaseTable tickets={list} mode="list" empty="No cases match these filters." />
      <p className="meta">{list.length} of {all.length} cases</p>
    </section>
  )
}
