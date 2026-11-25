import { api } from './client'

export type ChatSource = {
  number: number
  document_id: string
  revision_id: string
  chunk_set_id: string
  chunk_id: string
  title: string
  heading_path: string[]
  source_url: string
}

export type ChatResponse = {
  answer: string
  status: 'answered' | 'insufficient_evidence'
  sources: ChatSource[]
}

export const askChat = (question: string, category: string | null) =>
  api<ChatResponse>('/chat', { method: 'POST', body: JSON.stringify({ question, category }) })
