export const fmt = (iso: string) => new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })

/** "5h" under two days, then "3d". */
export function age(iso: string) {
  const h = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 36e5))
  return h < 48 ? `${h}h` : `${Math.round(h / 24)}d`
}

export const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
