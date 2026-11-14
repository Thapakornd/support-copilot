import type { Role } from '../../shared/api/users'

/** One list for the account page tabs and the header profile menu. */
export const ACCOUNT_TABS = {
  customer: [['profile', 'Profile'], ['notifications', 'Notifications'], ['team', 'Team & access'], ['subscription', 'Subscription']],
  agent: [['profile', 'Profile'], ['notifications', 'Notifications'], ['workload', 'My workload']],
} as const satisfies Record<Role, readonly (readonly [string, string])[]>

export type AccountTab = (typeof ACCOUNT_TABS)[Role][number][0]
