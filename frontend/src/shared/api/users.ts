import { AGENTS, demoProfile, demoRole, setDemoRole } from './demo/users'

export type Role = 'customer' | 'agent'
export type Me = { name: string; email: string; company: string; role: Role }

// ponytail: demo stand-ins; becomes api<Me>('/me') and api<string[]>('/agents') with real auth.
export const getMe = async (): Promise<Me> => {
  const p = demoProfile()
  return { name: p.name, email: p.email, company: p.company, role: demoRole() }
}
export const listAgents = async (): Promise<string[]> => AGENTS

/** Demo-only: the header's Customer/Support toggle. Remove with real auth. */
export const switchDemoRole = async (r: Role) => setDemoRole(r)
