import type { Source } from '../../shared/api/tickets'

/** What the AI search hands to the case form. Travels in router history state, so it survives a reload. */
export type CaseDraft = { question: string; category?: string; answer: string; sources: Source[] }

declare module '@tanstack/react-router' {
  interface HistoryState {
    caseDraft?: CaseDraft
  }
}
