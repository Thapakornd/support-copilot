import { Icon } from './Icon'
import { ICONS } from './icons'

type Props = { id: string; label: string; value: string; onChange: (v: string) => void; placeholder?: string; className?: string }

export function SearchInput({ id, label, value, onChange, placeholder, className = '' }: Props) {
  return (
    <div className={`kb-search ${className}`}>
      <Icon d={ICONS.search} />
      <label htmlFor={id} className="sr">{label}</label>
      <input id={id} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  )
}
