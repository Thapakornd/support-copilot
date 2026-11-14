import { queryOptions } from '@tanstack/react-query'
import { getArticle, listArticles, searchArticles } from './articles'
import { getProfile, listTeam } from './profile'
import { getTicket, listTickets } from './tickets'
import { getMe, listAgents } from './users'

/** Every cache key lives here, so invalidation and route loaders agree on names. */
export const q = {
  me: queryOptions({ queryKey: ['me'], queryFn: getMe, staleTime: Infinity }),
  agents: queryOptions({ queryKey: ['agents'], queryFn: listAgents, staleTime: Infinity }),
  profile: queryOptions({ queryKey: ['profile'], queryFn: getProfile }),
  team: queryOptions({ queryKey: ['team'], queryFn: listTeam }),
  tickets: queryOptions({ queryKey: ['tickets'], queryFn: listTickets }),
  ticket: (id: string) => queryOptions({ queryKey: ['tickets', id], queryFn: () => getTicket(id) }),
  articles: queryOptions({ queryKey: ['articles'], queryFn: listArticles, staleTime: Infinity }),
  article: (id: string) => queryOptions({ queryKey: ['articles', id], queryFn: () => getArticle(id), staleTime: Infinity }),
  articleSearch: (text: string, topic?: string) =>
    queryOptions({ queryKey: ['articles', 'search', text, topic ?? null], queryFn: () => searchArticles(text, topic), staleTime: Infinity }),
}
