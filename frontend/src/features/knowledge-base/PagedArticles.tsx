import { useState } from 'react'
import type { Article } from '../../shared/api/articles'
import { Icon } from '../../shared/ui/Icon'
import { ICONS } from '../../shared/ui/icons'
import { ArticleRow } from './ArticleRow'

const PER = 5

/** Article list with prev/next paging. Remount (key) to reset to page 1. */
export function PagedArticles({ articles }: { articles: Article[] }) {
  const [pg, setPg] = useState(0)
  const pages = Math.ceil(articles.length / PER)
  return (
    <section className="results card" aria-label="Related articles">
      {articles.slice(pg * PER, pg * PER + PER).map((a) => <ArticleRow key={a.id} a={a} />)}
      <div className="pager">
        <span className="meta">{pg * PER + 1}–{Math.min(articles.length, pg * PER + PER)} of {articles.length} articles</span>
        <span>
          <button className="icon-btn" aria-label="Previous page" disabled={pg === 0} onClick={() => setPg(pg - 1)}><Icon d={ICONS.chevronLeft} /></button>
          <span className="meta">{pg + 1} of {pages}</span>
          <button className="icon-btn" aria-label="Next page" disabled={pg >= pages - 1} onClick={() => setPg(pg + 1)}><Icon d={ICONS.chevronRight} /></button>
        </span>
      </div>
    </section>
  )
}
