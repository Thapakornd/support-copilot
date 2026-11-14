import type { Article } from '../../shared/api/articles'
import { catName } from '../../shared/config/categories'

export type FacetKey = 'type' | 'product' | 'topic'
export type Selection = Record<FacetKey, Set<string>>

export const FACETS: { key: FacetKey; label: string; name?: (v: string) => string }[] = [
  { key: 'type', label: 'Type' },
  { key: 'product', label: 'Product' },
  { key: 'topic', label: 'Topic', name: catName },
]

export const emptySelection = (): Selection => ({ type: new Set(), product: new Set(), topic: new Set() })
export const hasSelection = (sel: Selection) => FACETS.some((f) => sel[f.key].size > 0)
export const applySelection = (articles: Article[], sel: Selection) =>
  articles.filter((a) => FACETS.every((f) => sel[f.key].size === 0 || sel[f.key].has(a[f.key])))
