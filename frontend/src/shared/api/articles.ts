import { ARTICLES, BODIES } from './demo/articles'

export type Article = {
  id: string
  title: string
  type: 'Knowledge Article' | 'Documentation' | 'Community Forum' | 'Video'
  product: 'Atlas' | 'Server' | 'Drivers' | 'Ops Manager'
  topic: string // category id
  updated: string
  excerpt: string
}
export type ArticleBody = { steps: string[]; note?: string }
export type ArticleDetail = Article & { body?: ArticleBody }

// ponytail: async over static data so pages already treat this as a network call; swap bodies for api() later.
export const listArticles = async (): Promise<Article[]> => ARTICLES

export const getArticle = async (id: string): Promise<ArticleDetail | null> => {
  const a = ARTICLES.find((x) => x.id === id)
  return a ? { ...a, body: BODIES[a.id] } : null
}

/** Category narrows the corpus first; the question only ranks within it. */
export async function searchArticles(q: string, topic?: string): Promise<Article[]> {
  const words = q.toLowerCase().split(/\W+/).filter((w) => w.length > 2)
  const pool = topic ? ARTICLES.filter((a) => a.topic === topic) : ARTICLES
  const score = (a: Article) => words.filter((w) => (a.title + ' ' + a.excerpt).toLowerCase().includes(w)).length
  return [...pool].sort((a, b) => score(b) - score(a))
}
