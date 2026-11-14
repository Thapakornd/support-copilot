import { Link } from '@tanstack/react-router'
import type { Ticket } from '../shared/api/tickets'
import { catName } from '../shared/config/categories'
import { age, fmt } from '../shared/lib/format'
import { pillClass, sevClass } from '../features/cases/status'

type Props = {
  tickets: Ticket[]
  /** queue: waiting time + take button; list: last update. */
  mode: 'queue' | 'list'
  onTake?: (t: Ticket) => void
  empty: string
}

export function CaseTable({ tickets, mode, onTake, empty }: Props) {
  const queue = mode === 'queue'
  return (
    <div className="card tw">
      <table>
        <thead>
          <tr>
            <th>Case ID</th><th>Title</th><th>Area</th>
            {queue ? <><th>Severity</th><th>Status</th><th>Waiting</th></> : <><th>Status</th><th>Severity</th></>}
            <th>Assignee</th>
            {!queue && <th>Last update</th>}
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => {
            const sev = <td><span className={`pill ${sevClass(t.severity)}`}>{t.severity}</span></td>
            const status = <td><span className={`pill ${pillClass(t.status)}`}>{t.status}</span></td>
            return (
              <tr key={t.id}>
                <td className="mono">{t.id}</td>
                <td>
                  <Link className="case-link" to="/cases/$caseId" params={{ caseId: t.id }}>{t.title}</Link>
                  {queue && t.aiAnswer && <span className="ai-tag">AI tried</span>}
                </td>
                <td className="meta">{catName(t.category)}</td>
                {queue ? <>{sev}{status}<td className="meta">{age(t.created)}</td></> : <>{status}{sev}</>}
                <td>
                  {t.assignee
                    ? <span className="meta nowrap">{t.assignee}</span>
                    : onTake ? <button className="btn pri sm" onClick={() => onTake(t)}>Take case</button> : <span className="meta">Unassigned</span>}
                </td>
                {!queue && <td className="meta">{fmt(t.updated)}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
      {!tickets.length && <p className="empty meta">{empty}</p>}
    </div>
  )
}
