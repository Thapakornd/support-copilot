import { api } from './client'
import { setDemoRole } from './identity'

export type Role = 'customer' | 'agent'
export type Me = { name: string; email: string; company: string; role: Role }

export const getMe = () => api<Me>('/me')
/** Agents only; the API answers 403 to customers. */
export const listAgents = () => api<string[]>('/agents')

/** Demo-only: the header's Customer/Support toggle. Remove with real auth. */
export const switchDemoRole = (r: Role) => setDemoRole(r)
