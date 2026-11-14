// ponytail: in-browser stand-in for the tickets backend. Business rules live here only until the
// real endpoints exist; the backend must enforce them (and role checks) itself.
import type { Comment, NewTicket, Status, Ticket, TicketPatch } from '../tickets'
import { ARTICLES } from './articles'
import { read, write } from './storage'
import { demoProfile, demoRole } from './users'

const KEY = 'cases-v3' // v3: sources became {id, title}
const nowIso = () => new Date().toISOString().slice(0, 16)
const sys = (at: string, body: string): Comment => ({ author: 'System', role: 'system', at, body })
const src = (title: string) => ({ id: ARTICLES.find((a) => a.title === title)?.id, title })

const c = (id: string, title: string, category: string, status: Ticket['status'], severity: Ticket['severity'], created: string, updated: string, summary: string, sources: string[] = [], assignee?: string): Ticket => ({
  id, title, category, status, severity, created, updated, summary, assignee,
  reporter: 'Demo customer',
  description: summary,
  sources: sources.map(src),
  aiAnswer: sources.length ? `Suggested steps from: ${sources.join(', ')}. The customer reported this did not resolve the issue.` : undefined,
  comments: [
    sys(created, sources.length ? 'Escalated after the AI suggestion did not help' : 'Case opened'),
    ...(assignee ? [
      sys(created, `${assignee} took the case`),
      { author: assignee, role: 'agent' as const, at: updated, body: `Hi, I'm ${assignee.split(' ')[0]} and I'll be assisting you through this case.\n\nI've read the description and the articles you already tried. ${status === 'Waiting for customer' ? 'Could you confirm whether there were any application changes or redeployments around the time this started?' : status === 'Resolved' ? 'Glad that fixed it. I am closing this case; reply here if it comes back.' : 'I am pulling the cluster diagnostics now and will follow up with findings.'}` },
    ] : []),
  ],
})

const SEED: Ticket[] = [
  c('SC-10482', 'Node.js server selection timeouts after VPC peering change', 'connectivity', 'In progress', 'High', '2026-11-09T11:08', '2026-11-09T13:20', 'All connections time out after the peering change. Access list and routes were checked; mongosh still fails.', ['Troubleshoot server selection timeouts', 'Set up a network peering connection'], 'Alex Chen'),
  c('SC-10476', 'Resident memory keeps growing on primary', 'performance', 'Submitted', 'Normal', '2026-11-08T17:02', '2026-11-08T17:02', 'Resident memory up 30% over a week with flat workload. Suspect fragmentation.', ['How to identify and address memory fragmentation']),
  c('SC-10461', 'Replica set elections after maintenance window', 'replication', 'Waiting for customer', 'Normal', '2026-11-06T08:15', '2026-11-07T16:40', 'Two elections during the window; app saw brief write errors.', ['Unexpected elections after a maintenance window'], 'Priya Nair'),
  c('SC-10455', 'Bad auth after rotating database user password', 'security', 'Resolved', 'High', '2026-11-05T22:10', '2026-11-06T09:30', 'Password contained @ and was not URL-encoded in the connection string.', ['Authentication failed: bad auth'], 'Alex Chen'),
  c('SC-10437', 'Index build slow on large collection', 'queries', 'Submitted', 'Low', '2026-11-05T09:18', '2026-11-05T09:18', 'Index build on 400M docs has run for 9 hours.', ['Abort long-running index builds on replica sets']),
  c('SC-10422', 'Point-in-time restore fails with window error', 'backup', 'In progress', 'Critical', '2026-11-03T03:44', '2026-11-04T10:05', 'Restore target timestamp reported as outside the window although it is 2 hours old.', ['Restore a cluster to a point in time'], 'Sam Okafor'),
  c('SC-10401', 'Aggregation exceeded memory limit in nightly report', 'queries', 'Resolved', 'Normal', '2026-10-31T19:20', '2026-11-01T08:00', 'Moved $match before $group and added allowDiskUse.', ['Aggregation pipeline exceeded memory limit'], 'Priya Nair'),
  c('SC-10390', 'TLS handshake failure from Python driver', 'security', 'Resolved', 'Normal', '2026-10-28T10:11', '2026-10-29T14:02', 'Fixed by passing tlsCAFile=certifi.where().', ['TLS handshake failure from the Python driver'], 'Sam Okafor'),
]

const all = () => read<Ticket[]>(KEY, SEED)
const one = (id: string) => {
  const t = all().find((x) => x.id === id)
  if (!t) throw new Error(`Case ${id} not found`)
  return t
}

/** Apply a change, stamp it, log events, persist. */
function save(t: Ticket, patch: Partial<Ticket>, events: string[] = [], extra: Comment[] = []): Ticket {
  const at = nowIso()
  const next = { ...t, ...patch, updated: at, comments: [...t.comments, ...extra, ...events.map((e) => sys(at, e))] }
  write(KEY, [next, ...all().filter((x) => x.id !== t.id)])
  return next
}

export const list = async () => all()
export const get = async (id: string) => all().find((x) => x.id === id) ?? null

export async function create(input: NewTicket): Promise<Ticket> {
  const now = nowIso()
  const t: Ticket = {
    ...input,
    id: `SC-${10500 + Math.floor(Math.random() * 400)}`,
    status: 'Submitted',
    created: now,
    updated: now,
    summary: (input.description ?? '').slice(0, 200),
    reporter: demoProfile().name,
    comments: [sys(now, input.aiAnswer ? 'Escalated after the AI suggestion did not help' : 'Case opened')],
  }
  write(KEY, [t, ...all()])
  return t
}

export async function update(id: string, patch: TicketPatch): Promise<Ticket> {
  const t = one(id)
  const agent = demoRole() === 'agent'
  const events: string[] = []
  if (patch.status && patch.status !== t.status) {
    events.push(agent ? `Status changed to ${patch.status}` : patch.status === 'Resolved' ? 'Customer marked the case resolved' : 'Customer reopened the case')
  }
  if ('assignee' in patch && patch.assignee !== t.assignee) events.push(patch.assignee ? `Assigned to ${patch.assignee}` : 'Unassigned')
  if (patch.severity && patch.severity !== t.severity) events.push(`Severity changed to ${patch.severity}`)
  return save(t, patch, events)
}

export async function take(id: string): Promise<Ticket> {
  const me = demoProfile().name
  return save(one(id), { assignee: me, status: 'In progress' }, [`${me} took the case`])
}

export async function reply(id: string, body: string, next?: Status): Promise<Ticket> {
  const t = one(id)
  const agent = demoRole() === 'agent'
  const me = demoProfile().name
  const msg: Comment = { author: agent ? (t.assignee ?? me) : me, role: agent ? 'agent' : 'customer', at: nowIso(), body }
  const status = agent ? (next ?? t.status) : t.status === 'Waiting for customer' || t.status === 'Resolved' ? 'In progress' : t.status
  const patch: Partial<Ticket> = agent && !t.assignee ? { status, assignee: me } : { status }
  return save(t, patch, status !== t.status ? [`Status changed to ${status}`] : [], [msg])
}
