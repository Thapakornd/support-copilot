import { api } from './client'

export type Profile = {
  name: string
  email: string
  company: string
  timezone: string
  phone: string
  notify: { replies: boolean; status: boolean; digest: boolean }
}
export type TeamMember = { name: string; email: string; role: string; cases: boolean }

export const getProfile = () => api<Profile>('/profile')
export const saveProfile = (p: Profile) => api<Profile>('/profile', { method: 'PUT', body: JSON.stringify(p) })
export const listTeam = () => api<TeamMember[]>('/team')
