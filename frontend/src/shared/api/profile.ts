import { TEAM, demoProfile, saveDemoProfile } from './demo/users'

export type Profile = {
  name: string
  email: string
  company: string
  timezone: string
  phone: string
  notify: { replies: boolean; status: boolean; digest: boolean }
}
export type TeamMember = (typeof TEAM)[number]

// ponytail: demo stand-ins; become GET/PUT /profile and GET /team.
export const getProfile = async (): Promise<Profile> => demoProfile()
export const saveProfile = async (p: Profile): Promise<Profile> => { saveDemoProfile(p); return p }
export const listTeam = async (): Promise<TeamMember[]> => TEAM
