import * as demo from './demo/tickets'

export const STATUSES = ['Draft', 'Submitted', 'In progress', 'Waiting for customer', 'Resolved'] as const
export const SEVERITIES = ['Low', 'Normal', 'High', 'Critical'] as const
export type Status = (typeof STATUSES)[number]
export type Severity = (typeof SEVERITIES)[number]

export type Comment = { author: string; role: 'customer' | 'agent' | 'system'; at: string; body: string }
export type Source = { id?: string; title: string } // id is missing when the article was removed

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
  sources: Source[] // articles the AI search used
  aiAnswer?: string // what the assistant said before the customer escalated
  assignee?: string
  comments: Comment[] // oldest first; role 'system' = status/assignment events
}

export type NewTicket = Pick<Ticket, 'title' | 'category' | 'severity' | 'description' | 'sources' | 'aiAnswer'>
export type TicketPatch = Partial<Pick<Ticket, 'status' | 'assignee' | 'severity'>>

// ponytail: localStorage demo; each line becomes one api() call. The backend then owns the
// rules in demo/tickets.ts (who may change what, status transitions, system events).
export const listTickets = (): Promise<Ticket[]> => demo.list()
export const getTicket = (id: string): Promise<Ticket | null> => demo.get(id)
export const createTicket = (t: NewTicket): Promise<Ticket> => demo.create(t)
export const updateTicket = (id: string, patch: TicketPatch): Promise<Ticket> => demo.update(id, patch)
export const takeTicket = (id: string): Promise<Ticket> => demo.take(id)
/** Agents pick the next status; a customer reply hands the case back to support. */
export const replyToTicket = (id: string, body: string, status?: Status): Promise<Ticket> => demo.reply(id, body, status)
