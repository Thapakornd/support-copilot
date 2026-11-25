import { useMutation } from '@tanstack/react-query'
import { askChat, type ChatResponse } from '../../shared/api/chat'

export type AskResult = ChatResponse & { question: string }

export async function submitQuestion(question: string, category?: string): Promise<AskResult> {
  const response = await askChat(question, category ?? null)
  return { question, ...response }
}

export function useAsk(category?: string) {
  return useMutation({
    mutationFn: (question: string) => submitQuestion(question, category),
  })
}
