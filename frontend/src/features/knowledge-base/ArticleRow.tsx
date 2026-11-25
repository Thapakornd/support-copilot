import { Link } from '@tanstack/react-router'
import type { Article } from '../../shared/api/articles'
import { fmtDate } from '../../shared/lib/format'
import { Icon } from '../../shared/ui/Icon'
import { ICONS } from '../../shared/ui/icons'

export function ArticleRow({ a }: { a: Article }) {
  return (
    <article className="row">
      <p className="meta">Last update {fmtDate(a.updated)} | <b>{a.type}</b></p>
      <h3><Icon d={ICONS.book} size={16} /> <Link to="/kb/$articleId" params={{ articleId: a.id }}>{a.title}</Link></h3>
      <p>{a.excerpt}</p>
    </article>
  )
}
