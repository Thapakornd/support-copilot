import { api } from './client'

export const askChat = (question: string, category: string | null) =>
  api<{ answer: string }>('/chat', { method: 'POST', body: JSON.stringify({ question, category }) })
