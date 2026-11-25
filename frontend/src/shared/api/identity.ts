import type { Role } from './users'

// ponytail: the header toggle picks one seeded demo user per role; real auth replaces this file.
const SUBJECT: Record<Role, string> = { customer: 'customer', agent: 'alex' }

export function demoRole(): Role {
  try { return localStorage.getItem('role')?.includes('agent') ? 'agent' : 'customer' } catch { return 'customer' }
}
export function setDemoRole(r: Role) {
  try { localStorage.setItem('role', r) } catch { /* private mode: stays customer */ }
}
export const identityHeader = () => ({ 'X-Demo-User': SUBJECT[demoRole()] })
