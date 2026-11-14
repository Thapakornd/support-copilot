import { Link } from '@tanstack/react-router'
import { CATEGORIES } from '../../shared/config/categories'
import { Icon } from '../../shared/ui/Icon'

export function CategoryGrid() {
  return (
    <div className="cats">
      {CATEGORIES.map((c) => (
        <Link key={c.id} className="cat" to="/help/$category" params={{ category: c.id }}>
          <span className="cat-ic"><Icon d={c.icon} size={22} /></span>
          <span><b>{c.name}</b><span className="meta">{c.blurb}</span></span>
        </Link>
      ))}
    </div>
  )
}
