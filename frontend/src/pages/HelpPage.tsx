import { Link } from '@tanstack/react-router'
import { CategoryGrid } from '../features/assistant/CategoryGrid'
import { Icon } from '../shared/ui/Icon'
import { ICONS } from '../shared/ui/icons'

export function HelpPage() {
  return (
    <section className="hero">
      <h1 className="display">How can we help?</h1>
      <p className="lead">Pick the area your issue is in. The assistant will only search articles from that area.</p>
      <CategoryGrid />
      <Link className="btn ghost sm" to="/help/$category" params={{ category: 'any' }}>None of the above or unsure? <Icon d={ICONS.arrowRight} size={16} /></Link>
    </section>
  )
}
