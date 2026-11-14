import { SEVERITIES, type Severity, type Status, type Ticket } from '../../shared/api/tickets'

export const pillClass = (s: Status) => ({ Draft: 'gray', Submitted: 'blue', 'In progress': 'blue', 'Waiting for customer': 'amber', Resolved: '' })[s]
export const sevClass = (s: Severity) => ({ Low: 'gray', Normal: 'gray', High: 'amber', Critical: 'red' })[s]
export const isOpen = (t: Ticket) => t.status !== 'Resolved'
export const sevRank = (t: Ticket) => SEVERITIES.indexOf(t.severity)
