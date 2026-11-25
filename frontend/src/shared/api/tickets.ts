import { api, orNull } from './client'

export const STATUSES = ['Draft', 'Submitted', 'In progress', 'Waiting for customer', 'Resolved'] as const
export const SEVERITIES = ['Low', 'Normal', 'High', 'Critical'] as const
export type Status = (typeof STATUSES)[number]
export type Severity = (typeof SEVERITIES)[number]

export type Comment = { author: string; role: 'customer' | 'agent' | 'system'; at: string; body: string }
export type Source = { id?: string; title: string; url?: string }

export type Ticket = {
  id: string
  title: string
  category: string
  status: Status
  severity: Severity
  created: string // ISO
  updated: string // ISO
  summary: string
  description?: string
  reporter: string
  company: string
  plan: string // plan code, e.g. "developer"
  sources: Source[] // articles the AI search used
  aiAnswer?: string // what the assistant said before the customer escalated
  assignee?: string
  comments: Comment[] // oldest first; role 'system' = status/assignment events
}

export type NewTicket = Pick<Ticket, 'title' | 'category' | 'severity' | 'description' | 'sources' | 'aiAnswer'> & { consent: boolean }
export type TicketPatch = Partial<Pick<Ticket, 'status' | 'assignee' | 'severity'>>

// The backend owns the rules: who may change what, status transitions, system events.
const path = (id: string) => `/tickets/${encodeURIComponent(id)}`
const send = (url: string, method: string, body?: unknown) =>
  api<Ticket>(url, { method, body: body === undefined ? undefined : JSON.stringify(body) })

export const listTickets = () => api<Ticket[]>('/tickets')
export const getTicket = (id: string) => orNull(api<Ticket>(path(id)))
export const createTicket = (t: NewTicket) => send('/tickets', 'POST', t)
/** A missing field is unchanged, so "unassigned" has to travel as null (JSON drops undefined). */
export const updateTicket = (id: string, patch: TicketPatch) =>
  send(path(id), 'PATCH', 'assignee' in patch ? { ...patch, assignee: patch.assignee ?? null } : patch)
export const takeTicket = (id: string) => send(path(id) + '/take', 'POST')
/** Agents pick the next status; a customer reply hands the case back to support. */
export const replyToTicket = (id: string, body: string, status?: Status) => send(path(id) + '/replies', 'POST', { body, status })
