import { api, orNull } from './client'

export type Article = {
  id: string
  title: string
  type: 'Knowledge Article' | 'Documentation' | 'Community Forum' | 'Video'
  product: 'Atlas' | 'Server' | 'Drivers' | 'Ops Manager'
  topic: string // category id
  updated: string // ISO
  excerpt: string
}
export type ArticleBody = { steps: string[]; note?: string }
export type ArticleDetail = Article & { content: string; sourceUrl: string; body?: ArticleBody }

/** Newest first. */
export const listArticles = () => api<Article[]>('/articles')

export async function getArticle(id: string): Promise<ArticleDetail | null> {
  if (id === 'search') return null // /articles/search is the search endpoint, never an article
  return orNull(api<ArticleDetail>(`/articles/${encodeURIComponent(id)}`))
}

/** Matching articles only, best first. The API accepts at most 4000 characters. */
export const searchArticles = (q: string, topic?: string) =>
  api<Article[]>(`/articles/search?${new URLSearchParams({ q: q.slice(0, 4000), ...(topic && { topic }) })}`)
