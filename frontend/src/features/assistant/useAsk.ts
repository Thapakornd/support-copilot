import { useMutation } from '@tanstack/react-query'
import { searchArticles, type Article } from '../../shared/api/articles'
import { askChat } from '../../shared/api/chat'
import { catName } from '../../shared/config/categories'

export type AskResult = { question: string; answer: string; live: boolean; sources: Article[] }

/** Search the category's articles, then ask the assistant. Backend offline → summarise the top matches. */
export function useAsk(category?: string) {
  return useMutation({
    mutationFn: async (question: string): Promise<AskResult> => {
      const sources = await searchArticles(question, category)
      try {
        const { answer } = await askChat(question, category ? catName(category) : null)
        return { question, answer, live: true, sources }
      } catch {
        const answer = sources.slice(0, 3).map((s, i) => `${s.excerpt} [${i + 1}]`).join('\n')
        return { question, answer, live: false, sources }
      }
    },
  })
}
