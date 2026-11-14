import type { Profile } from '../profile'
import type { Role } from '../users'
import { read, write } from './storage'

const CUSTOMER: Profile = { name: 'Demo customer', email: 'customer@demo.test', company: 'Demo Org', timezone: 'Asia/Bangkok', phone: '', notify: { replies: true, status: true, digest: false } }
const AGENT: Profile = { ...CUSTOMER, name: 'Alex Chen', email: 'alex.chen@support.demo.test', company: 'Support Copilot · Support engineering' }

export const AGENTS = [AGENT.name, 'Priya Nair', 'Sam Okafor']
export const TEAM = [
  { name: 'Demo customer', email: 'customer@demo.test', role: 'Owner', cases: true },
  { name: 'Mina Park', email: 'mina@demo.test', role: 'Member', cases: true },
  { name: 'Jordan Lee', email: 'jordan@demo.test', role: 'Read only', cases: false },
]

// ponytail: the "logged-in user" is whichever role the header toggle picked; real auth replaces all of this.
export const demoRole = (): Role => (read<string>('role', 'customer') === 'agent' ? 'agent' : 'customer')
export const setDemoRole = (r: Role) => write('role', r)

export const demoProfile = (role = demoRole()): Profile => ({ ...(role === 'agent' ? AGENT : CUSTOMER), ...read(`profile-${role}`, {}) })
export const saveDemoProfile = (p: Profile) => write(`profile-${demoRole()}`, p)
